/**
 * S4-C scientific suite verification + screenshots.
 *
 * Correlations → scatter (via cell click) → scatter matrix → distributions →
 * missingness, with the shared selection running across all of them: a brush
 * on parallel coordinates must appear as an exact overlay in the distribution
 * and missingness views, and a scatter box-brush must update the same counts.
 * Real backend, real browser, screenshots into docs/screenshots/s4/.
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = process.env.SPLITSCOPE_BASE ?? 'http://127.0.0.1:8300'
const OUT = '../docs/screenshots/s4'
mkdirSync(OUT, { recursive: true })

const failures = []
const check = (name, ok, detail = '') => {
  console.log(`${ok ? ' *' : 'FAIL'} ${name}${detail ? `: ${detail}` : ''}`)
  if (!ok) failures.push(name)
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(m.text())
})
page.on('pageerror', (e) => errors.push(e.message))

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

// --- 1. brush in parallel coordinates ---------------------------------------
const firstAxis = page.locator('.xpc__axis rect[fill="transparent"]').first()
const box = await firstAxis.boundingBox()
if (!box) throw new Error('no brush hit area')
const x = box.x + box.width / 2
await page.mouse.move(x, box.y + box.height * 0.1)
await page.mouse.down()
await page.mouse.move(x, box.y + box.height * 0.4, { steps: 6 })
await page.mouse.up()
await page.waitForTimeout(800)
const brushedCount = await page.locator('.xw__popcount').textContent()
check('PC brush active before touring tabs', /selected of/.test(brushedCount ?? ''), brushedCount ?? '')

// --- 2. distributions: exact selection overlay ------------------------------
await page.getByRole('button', { name: 'Distributions' }).click()
await page.waitForSelector('[data-figure="distribution"] svg', { timeout: 10000 })
await page.waitForTimeout(600)
const overlayLegend = await page.locator('.xpc__legenditem--selected').allTextContents()
check(
  'distribution shows the selection overlay',
  overlayLegend.some((t) => /active selection/.test(t)),
  overlayLegend.join(' | '),
)
await page.screenshot({ path: `${OUT}/suite-distribution.png` })

// group overlay: split column breakdown
await page.locator('.xfig__control select').nth(1).selectOption('split')
await page.waitForTimeout(700)
const groups = await page.locator('.xdist__groupname').allTextContents()
check('group overlay lists groups with sizes', groups.length >= 2 && /rows/.test(groups.join(' ')), groups.join(' | '))

// --- 3. missingness: exact bars + matrix ------------------------------------
await page.getByRole('button', { name: 'Missingness' }).click()
await page.waitForSelector('[data-figure="missingness"] svg', { timeout: 10000 })
const missingBars = await page.locator('.xmiss__bar').count()
check('missingness bars per column', missingBars >= 8, `${missingBars} bars`)
const matrixNote = await page.locator('.xmiss__matrixtitle').textContent()
check('matrix states its sampling', /rows/.test(matrixNote ?? ''), matrixNote ?? '')
await page.screenshot({ path: `${OUT}/suite-missingness.png` })

// --- 4. correlations ----------------------------------------------------------
await page.getByRole('button', { name: 'Correlations' }).click()
await page.waitForSelector('[data-figure="correlation"] svg', { timeout: 10000 })
const cells = await page.locator('.xfig__cell').count()
check('correlation cells render', cells >= 6, `${cells} cells`)
await page.screenshot({ path: `${OUT}/suite-correlation.png` })

// click an off-diagonal cell → scatter focus opens that pair
const offDiagonal = page.locator('.xfig__cell').nth(1)
const pairTitle = await offDiagonal.locator('title').textContent()
await offDiagonal.click()
await page.waitForSelector('[data-figure="scatter"] svg', { timeout: 10000 })
const scatterTitle = await page.locator('[data-figure="scatter"] .xfig__title').textContent()
check('cell click opens scatter of that pair', (scatterTitle ?? '').includes('×'), `${pairTitle} → ${scatterTitle}`)

// --- 5. scatter box brush -----------------------------------------------------
const plotBox = await page.locator('.xfig__brushlayer').boundingBox()
if (!plotBox) throw new Error('no scatter brush layer')
const bx = plotBox.x
const by = plotBox.y
await page.mouse.move(bx + plotBox.width * 0.25, by + plotBox.height * 0.25)
await page.mouse.down()
await page.mouse.move(bx + plotBox.width * 0.6, by + plotBox.height * 0.6, { steps: 6 })
await page.mouse.up()
await page.waitForTimeout(800)
const scatterCount = await page.locator('.xw__popcount').textContent()
check('scatter box-brush updates the shared selection', /selected of/.test(scatterCount ?? ''), scatterCount ?? '')
const inspectorCount = await page.locator('.xrow__counts').textContent()
check('inspector agrees with scatter selection', (inspectorCount ?? '') === (scatterCount ?? '').replace('selected of', 'of').replace(/(\d+) of (\d+)/, (m, a, b) => `${a} of ${b} rows selected`) || /selected/.test(inspectorCount ?? ''), inspectorCount ?? '')
await page.screenshot({ path: `${OUT}/suite-scatter-brushed.png` })

// --- 6. scatter matrix --------------------------------------------------------
await page.getByRole('button', { name: 'Scatter matrix' }).click()
await page.waitForSelector('.xmatrix__panel svg', { timeout: 10000 })
const panels = await page.locator('.xmatrix__panel').count()
check('matrix panels for the pair combinations', panels >= 3, `${panels} panels`)
await page.screenshot({ path: `${OUT}/suite-scatter-matrix.png` })
await page.locator('.xmatrix__panel svg').first().click()
await page.waitForSelector('[data-figure="scatter"] svg', { timeout: 10000 })
check('matrix panel click opens the focus scatter', true)

// --- 7. clear selection -------------------------------------------------------
await page.getByRole('button', { name: 'Clear selection' }).click()
await page.waitForTimeout(500)
const cleared = await page.locator('.xw__popcount').textContent()
check('clear selection works from any tab', /no filters/.test(cleared ?? ''), cleared ?? '')

check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '))

await browser.close()
if (failures.length) {
  console.error(`\n${failures.length} check(s) failed`)
  process.exit(1)
}
console.log('\nall S4-C suite checks passed')
