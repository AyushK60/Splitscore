/**
 * S4 performance probe (Part 17).
 *
 * Uploads two generated datasets (3k and 10k rows — the server's documented
 * row cap), then measures real timings in a real browser:
 *   - explorer schema + first parallel-coordinates render;
 *   - brush commit → exact selection count round trip;
 *   - correlation matrix computation;
 *   - tab switches;
 *   - SVG export of the render sample.
 * Prints a table; asserts only sanity bounds (no hangs, renders bounded).
 */
import { chromium } from 'playwright'
import { writeFileSync, mkdtempSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

const BASE = process.env.SPLITSCOPE_BASE ?? 'http://127.0.0.1:8300'

function makeRows(n) {
  // Deterministic pseudo-random walk so every run measures the same data.
  let seed = 42
  const rand = () => {
    seed = (seed * 1103515245 + 12345) % 2147483648
    return seed / 2147483648
  }
  const header = 'id,x1,x2,x3,x4,x5,segment,split\n'
  const lines = []
  for (let i = 0; i < n; i++) {
    lines.push(
      `R-${i},${(rand() * 100).toFixed(3)},${(rand() * 50).toFixed(3)},${(rand() * 10).toFixed(3)},${(rand() * 1000).toFixed(2)},${(rand() * 5).toFixed(3)},${['alpha', 'beta', 'gamma'][i % 3]},${i % 4 === 0 ? 'test' : 'train'}`,
    )
  }
  return header + lines.join('\n')
}

async function upload(page, name, csv) {
  const response = await page.request.post(`${BASE}/api/datasets`, {
    multipart: { file: { name, buffer: Buffer.from(csv, 'utf-8'), mimeType: 'text/csv' } },
  })
  const body = await response.json()
  return body.dataset.dataset_id
}

const browser = await chromium.launch()
const results = []

async function probe(label, rowCount) {
  const dir = mkdtempSync(join(tmpdir(), 's4-perf-'))
  const csvPath = join(dir, `perf_${rowCount}.csv`)
  writeFileSync(csvPath, makeRows(rowCount))
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))

  const t0 = Date.now()
  const response = await page.request.post(`${BASE}/api/datasets`, {
    multipart: { file: { name: `perf_${rowCount}.csv`, buffer: Buffer.from(makeRows(rowCount), 'utf-8'), mimeType: 'text/csv' } },
  })
  const body = await response.json()
  const datasetId = body.dataset.dataset_id
  const uploadMs = Date.now() - t0

  await page.goto(`${BASE}/#/overview`)
  // Give the app the dataset through its own UI state: navigate home, load via API is not enough.
  // Instead: upload through the real Dataset flow is heavy; the explorer reads AppState, so load
  // via the demo-style route is unavailable for uploads. Use the UI: Start → upload input.
  await page.setInputFiles('input[type="file"]', csvPath)
  await page.waitForURL(/#\/dataset/, { timeout: 30000 })
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Explore' }).click()
  const t1 = Date.now()
  await page.waitForSelector('.xpc__axisname', { timeout: 30000 })
  const firstRenderMs = Date.now() - t1
  await page.waitForTimeout(700)
  const subtitle = await page.locator('.xpc__subtitle').textContent()

  const t2 = Date.now()
  const axis = page.locator('.xpc__axis rect[fill="transparent"]').first()
  const box = await axis.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height * 0.5, { steps: 10 })
  await page.mouse.up()
  await page.waitForFunction(
    () => document.querySelector('.xw__popcount')?.textContent?.includes('selected of'),
    { timeout: 30000 },
  )
  const brushMs = Date.now() - t2

  const t3 = Date.now()
  await page.getByRole('button', { name: 'Correlations' }).click()
  await page.waitForSelector('[data-figure="correlation"] svg', { timeout: 30000 })
  await page.waitForTimeout(500)
  const corrMs = Date.now() - t3

  const t4 = Date.now()
  await page.getByRole('button', { name: 'Missingness' }).click()
  await page.waitForSelector('[data-figure="missingness"] svg', { timeout: 30000 })
  const missMs = Date.now() - t4

  await page.getByRole('button', { name: 'Parallel coordinates' }).click()
  await page.waitForSelector('[data-testid="parallel-coordinates"] svg')
  const t5 = Date.now()
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 30000 }),
    page.locator('[data-testid="parallel-coordinates"] .xexport').getByRole('button', { name: 'SVG', exact: true }).click(),
  ])
  await download.saveAs(join(dir, 'figure.svg'))
  const exportMs = Date.now() - t5

  results.push({
    label: `${label} (${rowCount.toLocaleString('en-US')} rows)`,
    uploadMs,
    firstRenderMs,
    brushMs,
    corrMs,
    missMs,
    exportMs,
    subtitle: subtitle?.trim() ?? '',
    errors: errors.length,
  })
  await page.close()
}

await probe('medium', 3000)
await probe('large (server row cap)', 10000)

await browser.close()
console.log('\nS4 performance (Chromium, 1440x950, dev machine timings)')
for (const r of results) {
  console.log(`\n${r.label}`)
  console.log(`  upload+admit          ${r.uploadMs} ms`)
  console.log(`  first PC render       ${r.firstRenderMs} ms`)
  console.log(`  brush -> exact count  ${r.brushMs} ms`)
  console.log(`  correlation matrix    ${r.corrMs} ms`)
  console.log(`  missingness view      ${r.missMs} ms`)
  console.log(`  SVG export            ${r.exportMs} ms`)
  console.log(`  caption: ${r.subtitle}`)
  if (r.errors) console.log(`  PAGE ERRORS: ${r.errors}`)
}
const bad = results.find((r) => r.errors > 0 || r.firstRenderMs > 15000 || r.brushMs > 5000)
if (bad) {
  console.error('\nperformance probe failed sanity bounds')
  process.exit(1)
}
console.log('\nperformance probe within sanity bounds')
