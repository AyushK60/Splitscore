/**
 * Figure and run exports.
 *
 * The CSV must carry exactly the plotted values, the SVG must be the live
 * chart plus its caption, and the JSON must describe the same figure. Blobs are
 * captured rather than written to disk, so the assertions read the bytes.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildFigureSvg,
  exportFigureCsv,
  exportFigureJson,
  figureFilename,
  type FigureExportMeta,
} from '../src/estimation/estimationExport'
import { estimationExport } from '../src/estimation/downloadRun'
import { runPayload } from './estimationFixtures'

function meta(): FigureExportMeta {
  return {
    figureId: 'effect-summary',
    title: 'Average treatment effect by estimator',
    settings: 'Comparison of three estimators · 120 analysed rows',
    note: 'Intervals are 95% percentile bootstrap intervals; agreement is not causal proof.',
    provenance: ['Run run-s9b-fixture', 'Dataset ds-s9b-fixture · sha256:aaaaaaaaaaaaaaaa…'],
    csv: 'estimator,estimate,ci_lower,ci_upper\nregression_adjustment,2,1.7,2.3\nipw,1.6,1.29,1.91\n',
    metadata: {
      estimators: ['regression_adjustment', 'ipw'],
      method: 'bootstrap_percentile',
    },
  }
}

function captureDownload() {
  const blobs: Array<{ blob: Blob; filename: string }> = []
  // jsdom does not implement object URLs at all; provide the two statics so the
  // export path can be exercised as written in the browser.
  for (const name of ['createObjectURL', 'revokeObjectURL'] as const) {
    if (typeof URL[name] !== 'function') {
      Object.defineProperty(URL, name, { value: () => '', configurable: true, writable: true })
    }
  }
  vi.spyOn(URL, 'createObjectURL').mockImplementation((blob: Blob | MediaSource) => {
    blobs.push({ blob: blob as Blob, filename: '' })
    return 'blob:s9b-test'
  })
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, 'click')
    .mockImplementation(function (this: HTMLAnchorElement) {
      if (blobs.length > 0) blobs[blobs.length - 1].filename = this.download
    })
  return { blobs, click }
}

afterEach(() => {
  vi.restoreAllMocks()
})

/** jsdom's Blob has no `text()`; FileReader reads the same bytes. */
function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
}

describe('figure exports', () => {
  it('builds a standalone SVG that contains the live chart and its caption', () => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    svg.setAttribute('width', '600')
    svg.setAttribute('height', '300')
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
    circle.setAttribute('cx', '120')
    circle.setAttribute('cy', '80')
    circle.setAttribute('r', '5')
    circle.style.fill = 'rgb(180, 120, 60)'
    svg.appendChild(circle)

    const built = buildFigureSvg(svg, meta())
    expect(built.width).toBe(600)
    expect(built.height).toBeGreaterThan(300)
    const markup = built.svg.outerHTML
    expect(markup).toContain('<circle')
    expect(markup).toContain('Average treatment effect by estimator')
    expect(markup).toContain('Run run-s9b-fixture')
    expect(markup).toContain('agreement is not causal proof')
    // The live element is untouched.
    expect(svg.querySelectorAll('circle')).toHaveLength(1)
  })

  it('writes exactly the plotted CSV values to a named file', async () => {
    const { blobs } = captureDownload()
    exportFigureCsv(meta())
    expect(blobs).toHaveLength(1)
    expect(blobs[0].filename).toMatch(/^splitscope_effect-summary_.*\.csv$/)
    await expect(readBlob(blobs[0].blob)).resolves.toBe(meta().csv)
  })

  it('writes structured figure metadata rather than a rendered screenshot', async () => {
    const { blobs } = captureDownload()
    exportFigureJson(meta())
    const text = await readBlob(blobs[0].blob)
    const parsed = JSON.parse(text) as Record<string, unknown>
    expect(parsed['figure_id']).toBe('effect-summary')
    expect(parsed).toMatchObject({ method: 'bootstrap_percentile' })
    expect(parsed['figure_schema_version']).toBe('1.0.0')
    expect(String(parsed['note'])).toContain('agreement is not causal proof')
  })

  it('names files with the figure id and a timestamp', () => {
    expect(figureFilename(meta(), 'svg')).toMatch(/^splitscope_effect-summary_\d{4}-\d{2}-\d{2}T.*\.svg$/)
  })
})

describe('run export', () => {
  it('downloads the backend payload verbatim inside an export envelope', async () => {
    const { blobs } = captureDownload()
    const payload = runPayload()
    estimationExport(payload)

    expect(blobs[0].filename).toBe('splitscope_estimation_run-s9b-fixture.json')
    const parsed = JSON.parse(await readBlob(blobs[0].blob)) as {
      export_kind: string
      run: typeof payload
    }
    expect(parsed.export_kind).toBe('splitscope_causal_estimation_run')
    expect(parsed.run.run_id).toBe('run-s9b-fixture')
    expect(parsed.run.results[1].estimate).toBe(1.6)
    expect(parsed.run.reproducibility.graph_spec_fingerprint_sha256).toBe(payload.reproducibility.graph_spec_fingerprint_sha256)
  })
})
