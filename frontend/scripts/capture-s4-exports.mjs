/**
 * S4-D figure export verification.
 *
 * Downloads the real SVG, PNG and JSON exports of two charts and inspects
 * their content: the SVG must contain the actual plotted geometry and the
 * caption block (not an empty container), the PNG must be a non-trivial
 * raster, and the JSON must carry the full provenance (fingerprint, filters,
 * sampling, counts, figure id).
 */
import { chromium } from 'playwright'
import { mkdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

const BASE = process.env.SPLITSCOPE_BASE ?? 'http://127.0.0.1:8300'
const TMP = join(tmpdir(), 'splitscope-s4-exports')
const failures = []
const check = (name, ok, detail = '') => {
  console.log(`${ok ? ' *' : 'FAIL'} ${name}${detail ? `: ${detail}` : ''}`)
  if (!ok) failures.push(name)
}
rmSync(TMP, { recursive: true, force: true })
mkdirSync(TMP, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('pageerror', (e) => errors.push(e.message))

async function exportAndSave(figureSelector, kind) {
  const figure = page.locator(figureSelector)
  const exportGroup = figure.locator('.xexport')
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }),
    exportGroup.getByRole('button', { name: kind, exact: true }).click(),
  ])
  const path = join(TMP, download.suggestedFilename())
  await download.saveAs(path)
  return path
}

await page.goto(`${BASE}/#/overview`, { waitUntil: 'networkidle' })
await page.getByText('Browse other demos').click()
await page
  .locator('.demo-list__row')
  .filter({ hasText: 'Repeated-entity subscription panel' })
  .first()
  .getByRole('button', { name: 'Load', exact: true })
  .click()
await page.waitForURL(/#\/dataset/)
await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Explore' }).click()
await page.waitForSelector('.xpc__axisname', { timeout: 10000 })
await page.waitForTimeout(800)

// Brush so the export must carry the active selection.
const firstAxis = page.locator('.xpc__axis rect[fill="transparent"]').first()
const box = await firstAxis.boundingBox()
await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.1)
await page.mouse.down()
await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.4, { steps: 6 })
await page.mouse.up()
await page.waitForTimeout(800)

// --- parallel coordinates exports --------------------------------------------
const pcSvgPath = await exportAndSave('[data-testid="parallel-coordinates"]', 'SVG')
const pcSvg = readFileSync(pcSvgPath, 'utf-8')
check('PC SVG contains axis geometry', pcSvg.includes('<line') && pcSvg.includes('month_index'), `${pcSvg.length} bytes`)
check('PC SVG contains polylines of real data', pcSvg.includes('<path') && /M\d/.test(pcSvg))
check('PC SVG embeds the caption block', pcSvg.includes('Active selection') && pcSvg.includes('sha256:'))
check('PC SVG states the render sample', pcSvg.includes('every') || pcSvg.includes('All rows'))

const pcPngPath = await exportAndSave('[data-testid="parallel-coordinates"]', 'PNG')
const pcPngSize = statSync(pcPngPath).size
check('PC PNG is a real raster', pcPngSize > 20000, `${pcPngSize} bytes`)

const pcJsonPath = await exportAndSave('[data-testid="parallel-coordinates"]', 'JSON')
const pcManifest = JSON.parse(readFileSync(pcJsonPath, 'utf-8'))
check(
  'PC manifest carries dataset identity',
  typeof pcManifest.dataset?.sha256 === 'string' && pcManifest.dataset.sha256.length === 64,
  pcManifest.dataset?.name,
)
check(
  'PC manifest carries the active predicates and counts',
  Array.isArray(pcManifest.active_selection?.predicates) &&
    pcManifest.active_selection.predicates.length > 0 &&
    typeof pcManifest.active_selection.total_selected === 'number',
  JSON.stringify(pcManifest.active_selection?.predicates),
)
check('PC manifest states no raw rows embedded', pcManifest.privacy?.raw_rows_embedded === false)
check('PC manifest has a figure id and caption', Boolean(pcManifest.figure_id) && Array.isArray(pcManifest.caption))

// --- correlation exports -------------------------------------------------------
await page.getByRole('button', { name: 'Correlations' }).click()
await page.waitForSelector('[data-figure="correlation"] svg', { timeout: 10000 })
await page.waitForTimeout(400)
const corrSvgPath = await exportAndSave('[data-figure="correlation"]', 'SVG')
const corrSvg = readFileSync(corrSvgPath, 'utf-8')
check('correlation SVG contains the matrix cells', corrSvg.includes('<rect') && corrSvg.includes('pearson'))
const corrJsonPath = await exportAndSave('[data-figure="correlation"]', 'JSON')
const corrManifest = JSON.parse(readFileSync(corrJsonPath, 'utf-8'))
check('correlation manifest carries the method', corrManifest.settings.includes('pearson'), corrManifest.settings)

// --- scatter matrix: JSON-only path --------------------------------------------
await page.getByRole('button', { name: 'Scatter matrix' }).click()
await page.waitForSelector('.xmatrix__panel svg', { timeout: 10000 })
const vectorButtons = await page
  .locator('[data-figure="scatter-matrix"] .xexport')
  .getByRole('button', { name: 'SVG' })
  .count()
check('matrix correctly offers JSON only', vectorButtons === 0)
const matrixJsonPath = await exportAndSave('[data-figure="scatter-matrix"]', 'JSON')
const matrixManifest = JSON.parse(readFileSync(matrixJsonPath, 'utf-8'))
check('matrix manifest names its variables', (matrixManifest.title ?? '').includes('month_index'), matrixManifest.title)

// Exported SVG renders outside the app: rasterise via the browser itself.
const rendered = await page.evaluate(async (svgText) => {
  const image = new Image()
  const blob = new Blob([svgText], { type: 'image/svg+xml' })
  image.src = URL.createObjectURL(blob)
  await new Promise((resolve, reject) => {
    image.onload = resolve
    image.onerror = reject
  })
  return image.naturalWidth > 100 && image.naturalHeight > 100
}, readFileSync(pcSvgPath, 'utf-8'))
check('exported SVG decodes as an image (self-contained)', rendered === true)

check('no page errors', errors.length === 0, errors.slice(0, 3).join(' | '))

await browser.close()
if (failures.length) {
  console.error(`\n${failures.length} check(s) failed`)
  process.exit(1)
}
console.log('\nall S4-D export checks passed')
