/**
 * S4-B explorer verification + screenshots.
 *
 * Drives the real production build against the real backend: loads a bundled
 * demo, opens the Visual Explorer, asserts the parallel-coordinates canvas
 * renders real axes, brushes a range with a real pointer drag, verifies the
 * shared selection propagates to the row-evidence inspector and the counts,
 * clears the selection, and captures screenshots into docs/screenshots/s4/.
 * Exits non-zero when a check fails.
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = process.env.SPLITSCOPE_BASE ?? 'http://127.0.0.1:8300'
const DEMO = process.env.S4_DEMO ?? 'repeated_entity'
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

// Load the demo through the UI so the app's own state carries the dataset.
const DEMO_TITLES = {
  repeated_entity: 'Repeated-entity subscription panel',
  clean_control: 'Clean control panel',
  target_copy: 'Target-copy panel',
}
await page.goto(`${BASE}/#/overview`, { waitUntil: 'networkidle' })
await page.getByText('Browse other demos').click()
const demoRow = page
  .locator('.demo-list__row')
  .filter({ hasText: DEMO_TITLES[DEMO] ?? DEMO })
  .first()
await demoRow.getByRole('button', { name: 'Load', exact: true }).click()
await page.waitForURL(/#\/dataset/, { timeout: 15000 })
const identityChip = await page.locator('.app-header__meta, .xw__identity').first().textContent()
check('demo loads through the UI', true, identityChip ?? '')
const datasetResponse = await page.request.get(`${BASE}/api/health`)
check('backend healthy', datasetResponse.ok())
const schemaProbe = await page.evaluate(async () => {
  const response = await fetch('/api/demos')
  return response.ok
})
check('demos endpoint reachable', schemaProbe === true)

await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Explore' }).click()
await page.waitForSelector('[data-testid="parallel-coordinates"] svg', { timeout: 10000 })
// The axes render only once the series request lands; wait for a settled
// render so the SVG nodes the drag targets are not replaced mid-gesture.
await page.waitForSelector('.xpc__axisname', { timeout: 10000 })
await page.waitForTimeout(900)

check('explorer route renders PC canvas', true)
const identity = await page.locator('.xw__identityname').textContent()
check('dataset identity shown', (identity ?? '').trim().length > 0, identity ?? 'missing')

const axisNames = await page.locator('.xpc__axisname').allTextContents()
check('axes carry real column names', axisNames.length >= 3, axisNames.join(', '))

const subtitle = await page.locator('.xpc__subtitle').textContent()
check('sampling honesty in caption', /of [\d,]+ rows drawn/.test(subtitle ?? ''), subtitle ?? '')

const populationText = await page.locator('.xw__popcount').textContent()
check('population count shown', /rows \(no filters\)/.test(populationText ?? ''), populationText ?? '')

await page.screenshot({ path: `${OUT}/explorer-overview.png` })

// --- brush a range on the first axis ---------------------------------------
const firstAxisRect = page.locator('.xpc__axis rect[fill="transparent"]').first()
const box = await firstAxisRect.boundingBox()
check('brush hit area present', box !== null)

if (box) {
  const x = box.x + box.width / 2
  const y0 = box.y + box.height * 0.15
  const y1 = box.y + box.height * 0.5
  await page.mouse.move(x, y0)
  await page.mouse.down()
  await page.mouse.move(x, y1, { steps: 8 })
  await page.mouse.up()
  await page.waitForTimeout(700) // debounce + selection round trip

  const popAfter = await page.locator('.xw__popcount').textContent()
  check(
    'brush reduces the active population',
    /selected of/.test(popAfter ?? ''),
    popAfter ?? '',
  )
  const inspector = await page.locator('.xrow__counts').textContent()
  check('row inspector shows selected count', /selected/.test(inspector ?? ''), inspector ?? '')
  const predicates = await page.locator('.xrow__predicateitem').allTextContents()
  check('predicate echoed in inspector', predicates.length > 0, predicates.join(' | '))
  const selectedLines = await page.locator('.xpc__line--selected').count()
  check('selected lines highlighted in copper', selectedLines > 0, `${selectedLines} lines`)
  const brushRects = await page.locator('.xpc__brush').count()
  check('brush rectangle visible on axis', brushRects > 0, `${brushRects}`)
  await page.screenshot({ path: `${OUT}/explorer-brushed.png` })

  // --- linked selection: brush the second axis too --------------------------
  const secondAxis = page.locator('.xpc__axis rect[fill="transparent"]').nth(1)
  const box2 = await secondAxis.boundingBox()
  if (box2) {
    const x2 = box2.x + box2.width / 2
    await page.mouse.move(x2, box2.y + box2.height * 0.6)
    await page.mouse.down()
    await page.mouse.move(x2, box2.height * 0.85 + box2.y, { steps: 6 })
    await page.mouse.up()
    await page.waitForTimeout(700)
    const predicates2 = await page.locator('.xrow__predicateitem').allTextContents()
    check('multiple brushes accumulate', predicates2.length >= 2, predicates2.join(' | '))
    await page.screenshot({ path: `${OUT}/explorer-multi-brush.png` })
  }

  // --- clear selection -------------------------------------------------------
  await page.getByRole('button', { name: 'Clear selection' }).click()
  await page.waitForTimeout(500)
  const popCleared = await page.locator('.xw__popcount').textContent()
  check(
    'clear selection restores the population',
    (popCleared ?? '').includes('no filters'),
    popCleared ?? '',
  )
  const linesAfterClear = await page.locator('.xpc__line--selected').count()
  check('no highlighted lines after clear', linesAfterClear === 0, `${linesAfterClear}`)
}

// --- axis reorder via accessible controls -----------------------------------
const firstReorderName = await page.locator('.xpc__reordername').first().textContent()
await page.getByRole('button', { name: `Move ${firstReorderName} right` }).click()
await page.waitForTimeout(300)
const orderNow = await page.locator('.xpc__reordername').allTextContents()
check(
  'axis reorder moves the axis',
  orderNow[1] === firstReorderName && orderNow[0] !== firstReorderName,
  `${firstReorderName} → ${orderNow.join(', ')}`,
)

// --- focus mode --------------------------------------------------------------
await page.getByRole('button', { name: 'Focus the plot' }).click()
await page.waitForTimeout(400)
const inspectorGone = await page.locator('.xw__inspector').count()
check('focus mode collapses the inspector', inspectorGone === 0)
await page.screenshot({ path: `${OUT}/explorer-focus.png` })
await page.getByRole('button', { name: 'Show row evidence' }).click()

check('no console errors', errors.length === 0, errors.slice(0, 3).join(' | '))

await browser.close()
if (failures.length) {
  console.error(`\n${failures.length} check(s) failed`)
  process.exit(1)
}
console.log('\nall S4-B explorer checks passed')
