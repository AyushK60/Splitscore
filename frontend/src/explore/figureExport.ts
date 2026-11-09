import type { BrushPredicate, ExploreSchema } from '../api/types'
import type { SelectionState } from './ExploreState'

/**
 * Scientific figure export (F22 preliminary).
 *
 * Three formats, one provenance story:
 *  - **SVG** - a serialization of the LIVE chart: the same geometry the user
 *    sees, with computed styles baked in (CSS custom properties resolved to
 *    literal values, so the file renders correctly outside the app), a
 *    print-safe paper background and a caption block carrying title, counts,
 *    active filters and dataset identity.
 *  - **PNG** - the same SVG rasterised at 2× for report embedding.
 *  - **JSON manifest** - the figure's full provenance: dataset fingerprint,
 *    active predicates, sampling description, counts, chart settings and the
 *    caption. No raw rows are embedded; the manifest references the dataset,
 *    it does not carry it.
 */

export interface FigureMeta {
  figureId: string
  title: string
  /** Method/settings line, e.g. "Pearson · 5 variables". */
  settings: string
  /** Counts line, e.g. "240 of 240 rows drawn · 80 selected". */
  counts: string
  /** Sampling description when a render sample is involved. */
  sampling?: string
  notes?: string[]
}

export interface FigureContext {
  schema: ExploreSchema
  selection: SelectionState
  appVersion: string
  generatedAtUtc: string
}

export function captionLines(meta: FigureMeta, context: FigureContext): string[] {
  const lines: string[] = [meta.title, [meta.settings, meta.counts].filter(Boolean).join(' - ')]
  if (meta.sampling) lines.push(meta.sampling)
  if (context.selection.predicates.length > 0) {
    lines.push(
      `Active selection: ${describePredicates(context.selection.predicates)} (${context.selection.totalSelected.toLocaleString('en-US')} of ${context.schema.row_count.toLocaleString('en-US')} rows)`,
    )
  } else {
    lines.push('Active selection: none (full dataset population)')
  }
  lines.push(
    `${context.schema.dataset.name} · sha256:${context.schema.dataset.fingerprint_sha256.slice(0, 16)}… · ${context.schema.row_count.toLocaleString('en-US')} rows · SplitScope ${context.appVersion} · ${meta.figureId} · ${context.generatedAtUtc}`,
  )
  for (const note of meta.notes ?? []) lines.push(note)
  return lines
}

export function describePredicates(predicates: BrushPredicate[]): string {
  // The documented combination rule, in words: ranges on the same column
  // union; different columns intersect.
  const describe = (p: BrushPredicate): string =>
    p.kind === 'range'
      ? `${p.column} ∈ [${formatValue(p.min)}, ${formatValue(p.max)}]`
      : `${p.column} ∈ {${p.values.slice(0, 5).join(', ')}${p.values.length > 5 ? ', …' : ''}}`
  const byColumn = new Map<string, string[]>()
  for (const predicate of predicates) {
    const list = byColumn.get(predicate.column) ?? []
    list.push(describe(predicate))
    byColumn.set(predicate.column, list)
  }
  return [...byColumn.values()].map((group) => group.join(' OR ')).join(' AND ')
}

function formatValue(value: number): string {
  return Number.isInteger(value) ? value.toLocaleString('en-US') : value.toPrecision(4)
}

export function figureManifest(meta: FigureMeta, context: FigureContext): Record<string, unknown> {
  return {
    figure_schema_version: '1.0.0',
    figure_id: meta.figureId,
    generated_at_utc: context.generatedAtUtc,
    application: { name: 'SplitScope', version: context.appVersion },
    title: meta.title,
    settings: meta.settings,
    counts: meta.counts,
    sampling: meta.sampling ?? null,
    notes: meta.notes ?? [],
    caption: captionLines(meta, context),
    dataset: {
      dataset_id: context.schema.dataset.dataset_id,
      name: context.schema.dataset.name,
      source: context.schema.dataset.source,
      is_synthetic: context.schema.dataset.is_synthetic,
      sha256: context.schema.dataset.fingerprint_sha256,
      row_count: context.schema.row_count,
      column_count: context.schema.dataset.column_count,
    },
    active_selection: {
      predicates: context.selection.predicates,
      total_selected: context.selection.totalSelected,
      population: context.schema.row_count,
      ids_truncated: context.selection.idsTruncated,
    },
    privacy: {
      raw_rows_embedded: false,
      note: 'The manifest references the in-memory dataset; it carries no cell values.',
    },
  }
}

const BAKED_PROPERTIES = [
  'fill',
  'stroke',
  'stroke-width',
  'stroke-dasharray',
  'stroke-opacity',
  'fill-opacity',
  'opacity',
  'font-family',
  'font-size',
  'font-weight',
  'text-anchor',
]

/**
 * Clone the live SVG into a standalone, self-contained export document.
 *
 * Computed styles are read from the rendered nodes and written as inline
 * styles on the clone: this resolves `var(--rs-*)` tokens to literal colours,
 * because a serialized SVG leaves the app's stylesheets behind.
 */
export function buildStandaloneSvg(
  source: SVGSVGElement,
  meta: FigureMeta,
  context: FigureContext,
): { svg: SVGSVGElement; width: number; height: number } {
  const clone = source.cloneNode(true) as SVGSVGElement
  const width = source.clientWidth || Number(source.getAttribute('width')) || 800
  const chartHeight = source.clientHeight || Number(source.getAttribute('height')) || 460
  const captionHeight = 26 * Math.max(3, captionLines(meta, context).length) + 18
  const height = chartHeight + captionHeight

  const sourceNodes = [source, ...Array.from(source.querySelectorAll('*'))] as SVGElement[]
  const cloneNodes = [clone, ...Array.from(clone.querySelectorAll('*'))] as SVGElement[]
  const sourceStyles = getComputedStyle(source)
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  clone.setAttribute('viewBox', `0 0 ${width} ${height}`)
  for (const node of cloneNodes) node.removeAttribute('class')

  const background = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  background.setAttribute('x', '0')
  background.setAttribute('y', '0')
  background.setAttribute('width', String(width))
  background.setAttribute('height', String(height))
  background.setAttribute('fill', sourceStyles.getPropertyValue('--rs-surface') || '#ffffff')
  clone.insertBefore(background, clone.firstChild)

  sourceNodes.forEach((node, index) => {
    const target = cloneNodes[index]
    if (!target) return
    const styles = getComputedStyle(node)
    for (const prop of BAKED_PROPERTIES) {
      const value = styles.getPropertyValue(prop)
      if (value) target.style.setProperty(prop, value)
    }
  })

  // Caption block under the chart.
  const lines = captionLines(meta, context)
  const ink = sourceStyles.getPropertyValue('--rs-ink') || '#1f1b18'
  const soft = sourceStyles.getPropertyValue('--rs-soft') || '#4d443d'
  lines.forEach((line, index) => {
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    text.setAttribute('x', '12')
    text.setAttribute('y', String(chartHeight + 22 + index * 26))
    text.setAttribute('fill', index === 0 ? ink : soft)
    text.setAttribute('font-family', 'monospace')
    text.setAttribute('font-size', index === 0 ? '15' : '11')
    text.setAttribute('font-weight', index === 0 ? '600' : '400')
    text.textContent = line.length > 160 ? `${line.slice(0, 157)}…` : line
    clone.appendChild(text)
  })

  return { svg: clone, width, height }
}

function serialize(svg: SVGSVGElement): string {
  return new XMLSerializer().serializeToString(svg)
}

export function svgBlob(svg: SVGSVGElement): Blob {
  return new Blob([serialize(svg)], { type: 'image/svg+xml;charset=utf-8' })
}

export async function pngBlob(svg: SVGSVGElement, width: number, height: number): Promise<Blob> {
  const scale = 2
  const url = URL.createObjectURL(svgBlob(svg))
  try {
    const image = new Image()
    image.decoding = 'sync'
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('The figure could not be rasterised.'))
      image.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = width * scale
    canvas.height = height * scale
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas 2D is unavailable in this browser.')
    ctx.scale(scale, scale)
    ctx.drawImage(image, 0, 0, width, height)
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('PNG encoding failed.'))), 'image/png'),
    )
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function exportFilename(figureId: string, datasetName: string, extension: string): string {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
  const safeDataset = datasetName.replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_-]+/g, '_')
  return `splitscope_${figureId}_${safeDataset}_${stamp}.${extension}`
}
