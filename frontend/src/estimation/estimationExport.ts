/**
 * Figure export for the Effect Estimation Studio.
 *
 * One provenance story for every figure:
 *  - **SVG** serialises the live chart, baking computed styles into inline
 *    attributes so the file renders outside the app, and appends a caption block
 *    with the figure title, estimator/method line, study fingerprint and the
 *    scientific note that belongs to that figure.
 *  - **PNG** rasterises the same SVG at 2× for reports and slides.
 *  - **CSV** carries exactly the plotted numbers (no invented rows, no rounding
 *    beyond the value the backend returned).
 *  - **JSON** carries the figure's metadata: which run, which estimator, which
 *    cohort, the exact values plotted and the assumptions the figure relies on.
 *
 * The chart geometry is never rebuilt from a second source: the SVG is the one
 * on screen.
 */

export interface FigureExportMeta {
  figureId: string
  title: string
  /** Method/settings line, e.g. "Cross-fitted AIPW · 1200 analysed rows". */
  settings: string
  /** One paragraph of scientific framing printed under the figure. */
  note: string
  /** Provenance lines: study identity, run id, seeds, fingerprints. */
  provenance: string[]
  /** Exactly the values the figure plots, header row included. */
  csv: string
  /** Structured figure metadata for the JSON export. */
  metadata: Record<string, unknown>
}

const BAKED = [
  'fill',
  'fill-opacity',
  'stroke',
  'stroke-width',
  'stroke-dasharray',
  'stroke-opacity',
  'opacity',
  'font-family',
  'font-size',
  'font-weight',
  'letter-spacing',
]

function captionLines(meta: FigureExportMeta): string[] {
  return [meta.title, meta.settings, ...meta.provenance, meta.note]
}

function stamp(): string {
  return new Date().toISOString()
}

function safeName(text: string): string {
  return text.replace(/[^A-Za-z0-9_-]+/g, '_')
}

export function figureFilename(meta: FigureExportMeta, extension: string): string {
  const time = stamp().replace(/[:.]/g, '-').slice(0, 19)
  return `splitscope_${safeName(meta.figureId)}_${time}.${extension}`
}

/**
 * Clone the live SVG into a standalone document with resolved presentation and
 * a caption block. Dimensions are read from the rendered element with attribute
 * fallbacks, so the export works even when the element is not laid out.
 */
export function buildFigureSvg(
  source: SVGSVGElement,
  meta: FigureExportMeta,
): { svg: SVGSVGElement; width: number; height: number } {
  const clone = source.cloneNode(true) as SVGSVGElement
  const width = Math.round(source.clientWidth || Number(source.getAttribute('width')) || 900)
  const chartHeight = Math.round(
    source.clientHeight || Number(source.getAttribute('height')) || 420,
  )
  const lines = captionLines(meta)
  const wrap = (text: string, max: number): string[] => {
    const words = text.split(/\s+/)
    const out: string[] = []
    let line = ''
    for (const word of words) {
      if ((line + ' ' + word).trim().length > max && line !== '') {
        out.push(line)
        line = word
      } else {
        line = (line + ' ' + word).trim()
      }
    }
    if (line) out.push(line)
    return out
  }
  const captionRows: Array<{ text: string; heading: boolean }> = []
  lines.forEach((line, index) => {
    const wrapped = wrap(line, 150)
    wrapped.forEach((part, partIndex) => {
      captionRows.push({ text: part, heading: index === 0 && partIndex === 0 })
    })
  })
  const captionHeight = 22 * captionRows.length + 26
  const height = chartHeight + captionHeight

  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  clone.setAttribute('viewBox', `0 0 ${width} ${height}`)
  for (const node of Array.from(clone.querySelectorAll('*'))) node.removeAttribute('class')

  const sourceNodes = [source, ...Array.from(source.querySelectorAll('*'))] as SVGElement[]
  const cloneNodes = [clone, ...Array.from(clone.querySelectorAll('*'))] as SVGElement[]
  const styles = getComputedStyle(source)

  const background = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
  background.setAttribute('width', String(width))
  background.setAttribute('height', String(height))
  background.setAttribute('fill', styles.getPropertyValue('--paper') || '#ffffff')
  clone.insertBefore(background, clone.firstChild)

  sourceNodes.forEach((node, index) => {
    const target = cloneNodes[index]
    if (!target) return
    const computed = getComputedStyle(node)
    for (const property of BAKED) {
      const value = computed.getPropertyValue(property)
      if (value) target.style.setProperty(property, value)
    }
  })

  // A rule under the chart, then the caption.
  const rule = document.createElementNS('http://www.w3.org/2000/svg', 'line')
  rule.setAttribute('x1', '12')
  rule.setAttribute('x2', String(width - 12))
  rule.setAttribute('y1', String(chartHeight - 4))
  rule.setAttribute('y2', String(chartHeight - 4))
  rule.setAttribute('stroke', '#cfc6b5')
  rule.setAttribute('stroke-width', '1')
  clone.appendChild(rule)

  captionRows.forEach((row, index) => {
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text')
    text.setAttribute('x', '12')
    text.setAttribute('y', String(chartHeight + 20 + index * 22))
    text.setAttribute('fill', row.heading ? '#18231d' : '#5c6b62')
    text.setAttribute('font-family', 'Segoe UI, Helvetica, Arial, sans-serif')
    text.setAttribute('font-size', row.heading ? '14' : '10.5')
    text.setAttribute('font-weight', row.heading ? '600' : '400')
    text.textContent = row.text
    clone.appendChild(text)
  })

  return { svg: clone, width, height }
}

function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function exportFigureSvg(source: SVGSVGElement | null, meta: FigureExportMeta): boolean {
  if (!source) return false
  const { svg } = buildFigureSvg(source, meta)
  download(
    new Blob([new XMLSerializer().serializeToString(svg)], {
      type: 'image/svg+xml;charset=utf-8',
    }),
    figureFilename(meta, 'svg'),
  )
  return true
}

export async function exportFigurePng(
  source: SVGSVGElement | null,
  meta: FigureExportMeta,
): Promise<boolean> {
  if (!source) return false
  const { svg, width, height } = buildFigureSvg(source, meta)
  const url = URL.createObjectURL(
    new Blob([new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml;charset=utf-8' }),
  )
  try {
    const image = new Image()
    image.decoding = 'sync'
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('The figure could not be rasterised.'))
      image.src = url
    })
    const scale = 2
    const canvas = document.createElement('canvas')
    canvas.width = width * scale
    canvas.height = height * scale
    const context = canvas.getContext('2d')
    if (!context) throw new Error('Canvas 2D is unavailable in this browser.')
    context.fillStyle = '#ffffff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.scale(scale, scale)
    context.drawImage(image, 0, 0, width, height)
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((value) => resolve(value), 'image/png'),
    )
    if (!blob) throw new Error('PNG encoding failed.')
    download(blob, figureFilename(meta, 'png'))
    return true
  } finally {
    URL.revokeObjectURL(url)
  }
}

export function exportFigureCsv(meta: FigureExportMeta): void {
  download(
    new Blob([meta.csv.endsWith('\n') ? meta.csv : `${meta.csv}\n`], {
      type: 'text/csv;charset=utf-8',
    }),
    figureFilename(meta, 'csv'),
  )
}

export function exportFigureJson(meta: FigureExportMeta): void {
  const payload = {
    figure_schema_version: '1.0.0',
    figure_id: meta.figureId,
    generated_at_utc: stamp(),
    title: meta.title,
    settings: meta.settings,
    note: meta.note,
    provenance: meta.provenance,
    ...meta.metadata,
  }
  download(
    new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' }),
    figureFilename(meta, 'json'),
  )
}
