import { useCallback, useRef, useState } from 'react'

import {
  buildStandaloneSvg,
  downloadBlob,
  exportFilename,
  figureManifest,
  pngBlob,
  svgBlob,
  type FigureMeta,
} from '../../explore/figureExport'
import { useExplore } from '../../explore/ExploreState'
import { useApp } from '../../state/AppState'

/**
 * Export menu for one figure: SVG, PNG and a JSON provenance manifest.
 *
 * `getSvg` must return the LIVE chart element - exports always reflect the
 * currently rendered state (visible axes, active brushes, current selection),
 * never a cached snapshot.
 */

interface Props {
  figureId: string
  title: string
  settings: string
  counts: string
  sampling?: string
  notes?: string[]
  /** Returns the chart's live SVG; multi-panel figures may return null. */
  getSvg: () => SVGSVGElement | null
  /** False for figures without a single exportable SVG (JSON manifest only). */
  vectorExports?: boolean
}

export function FigureExport({
  figureId,
  title,
  settings,
  counts,
  sampling,
  notes,
  getSvg,
  vectorExports = true,
}: Props) {
  const { schema, selection } = useExplore()
  const { health } = useApp()
  const [error, setError] = useState<string | null>(null)
  const busy = useRef(false)

  const context = useCallback(
    () => ({
      schema: schema as NonNullable<typeof schema>,
      selection,
      appVersion: health?.app_version ?? '1.0.0',
      generatedAtUtc: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
    }),
    [schema, selection, health],
  )

  const meta = useCallback(
    (): FigureMeta => ({ figureId, title, settings, counts, sampling, notes }),
    [figureId, title, settings, counts, sampling, notes],
  )

  const run = useCallback(
    async (kind: 'svg' | 'png' | 'json') => {
      if (busy.current || !schema) return
      busy.current = true
      setError(null)
      try {
        const datasetName = schema.dataset.name
        if (kind === 'json') {
          const manifest = figureManifest(meta(), context())
          downloadBlob(
            new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' }),
            exportFilename(figureId, datasetName, 'json'),
          )
          return
        }
        const source = getSvg()
        if (!source) {
          setError('Nothing is drawn yet - wait for the chart to render, then export.')
          return
        }
        const standalone = buildStandaloneSvg(source, meta(), context())
        if (kind === 'svg') {
          downloadBlob(svgBlob(standalone.svg), exportFilename(figureId, datasetName, 'svg'))
        } else {
          const blob = await pngBlob(standalone.svg, standalone.width, standalone.height)
          downloadBlob(blob, exportFilename(figureId, datasetName, 'png'))
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'The export failed.')
      } finally {
        busy.current = false
      }
    },
    [schema, meta, context, getSvg, figureId],
  )

  return (
    <div className="xexport" role="group" aria-label={`Export ${title}`}>
      <span className="xexport__label">Export</span>
      {vectorExports && (
        <>
          <button type="button" className="xbtn xbtn--tiny" onClick={() => void run('svg')}>
            SVG
          </button>
          <button type="button" className="xbtn xbtn--tiny" onClick={() => void run('png')}>
            PNG
          </button>
        </>
      )}
      <button type="button" className="xbtn xbtn--tiny" onClick={() => void run('json')}>
        JSON
      </button>
      {!vectorExports && (
        <span className="xexport__hint">open a pair in the focus scatter for SVG/PNG</span>
      )}
      {error && (
        <span className="xexport__error" role="alert">
          {error}
        </span>
      )}
    </div>
  )
}
