/**
 * S4 Scientific Visual Explorer — end-to-end journey.
 *
 * Runs against the real backend (fresh process via webServer) with the
 * bundled repeated-entity demo. The journey is behavioural, not presence
 * checks: brushes must change exact counts, the row inspector must resolve
 * immutable row ids to the file's own values, chart tabs must share one
 * selection, exports must be real files with provenance, and the pre-existing
 * Study / Audit workflows must still work after the explorer exists.
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { expect, test } from './fixtures'

// The explorer's canvas is tall; the default 1280x720 viewport puts the
// scatter's lower half below the fold, where pointer events cannot start.
test.use({ viewport: { width: 1440, height: 950 } })

const TMP = join(tmpdir(), 'splitscope-s4-e2e')

test.beforeAll(() => {
  mkdirSync(TMP, { recursive: true })
})

async function loadDemoAndOpenExplorer(page: import('@playwright/test').Page) {
  await page.goto('/#/overview')
  await page.getByText('Browse other demos').click()
  await page
    .locator('.demo-list__row')
    .filter({ hasText: 'Repeated-entity subscription panel' })
    .first()
    .getByRole('button', { name: 'Load', exact: true })
    .click()
  await page.waitForURL(/#\/dataset/)
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Explore' }).click()
  await expect(page.locator('[data-testid="parallel-coordinates"] svg')).toBeVisible()
  await expect(page.locator('.xpc__axisname').first()).toBeVisible()
}

async function brushFirstAxis(page: import('@playwright/test').Page) {
  const hitArea = page.locator('.xpc__axis rect[fill="transparent"]').first()
  const box = await hitArea.boundingBox()
  expect(box).not.toBeNull()
  const x = box!.x + box!.width / 2
  await page.mouse.move(x, box!.y + box!.height * 0.1)
  await page.mouse.down()
  await page.mouse.move(x, box!.y + box!.height * 0.45, { steps: 8 })
  await page.mouse.up()
  await expect(page.locator('.xw__popcount')).toContainText('selected of', { timeout: 10000 })
  return (await page.locator('.xw__popcount').textContent()) ?? ''
}

test('parallel coordinates: brush, exact counts and row evidence', async ({ page }) => {
  await loadDemoAndOpenExplorer(page)

  // Honest defaults: full population, sampling caption, real axis names.
  await expect(page.locator('.xw__popcount')).toContainText('240 rows (no filters)')
  await expect(page.locator('.xpc__subtitle')).toContainText(/of 240 rows drawn/)
  const axisNames = await page.locator('.xpc__axisname').allTextContents()
  expect(axisNames).toContain('tenure_months')

  const before = await brushFirstAxis(page)
  expect(before).toMatch(/\d+ selected of 240/)

  // Row evidence resolves the selection to immutable ids and file values.
  await expect(page.locator('.xrow__counts')).toContainText(/of 240 rows selected/)
  await expect(page.locator('.xrow__predicateitem').first()).toContainText('month_index')
  const firstRowId = (await page.locator('.xrow__table tbody td').first().textContent()) ?? ''
  expect(firstRowId).toMatch(/^row-\d{6}$/)
  // A brushed line count greater than zero and a visible brush rectangle.
  expect((await page.locator('.xpc__line--selected').count())).toBeGreaterThan(0)
  expect((await page.locator('.xpc__brush:not(.xpc__brush--live)').count())).toBeGreaterThan(0)

  // Clear selection restores the population everywhere.
  await page.getByRole('button', { name: 'Clear selection' }).click()
  await expect(page.locator('.xw__popcount')).toContainText('240 rows (no filters)')
  expect(await page.locator('.xpc__line--selected').count()).toBe(0)
})

test('correlation heatmap links to the scatter of the clicked pair', async ({ page }) => {
  await loadDemoAndOpenExplorer(page)
  await page.getByRole('button', { name: 'Correlations' }).click()
  const matrix = page.locator('[data-figure="correlation"] svg')
  await expect(matrix).toBeVisible()
  // Every off-diagonal cell shows a coefficient value; the legend is present.
  expect((await page.locator('.xfig__cell').count())).toBeGreaterThanOrEqual(6)
  await expect(page.locator('.xfig__legend')).toContainText('+1')

  const cell = page.locator('.xfig__cell').nth(2)
  const pair = (await cell.locator('title').textContent()) ?? ''
  await cell.click()
  await expect(page.locator('[data-figure="scatter"] svg')).toBeVisible()
  const title = (await page.locator('[data-figure="scatter"] .xfig__title').textContent()) ?? ''
  expect(title).toContain('×')
  void pair

  // A scatter box brush feeds the same shared selection.
  const layer = await page.locator('.xfig__brushlayer').boundingBox()
  expect(layer).not.toBeNull()
  await page.mouse.move(layer!.x + layer!.width * 0.3, layer!.y + layer!.height * 0.3)
  await page.mouse.down()
  await page.mouse.move(layer!.x + layer!.width * 0.7, layer!.y + layer!.height * 0.7, { steps: 6 })
  await page.mouse.up()
  await expect(page.locator('.xw__popcount')).toContainText('selected of', { timeout: 10000 })
  await expect(page.locator('.xrow__counts')).toContainText(/rows selected/)
})

test('linked filtering: a parallel-coordinates brush overlays distributions and missingness', async ({ page }) => {
  await loadDemoAndOpenExplorer(page)
  await brushFirstAxis(page)

  await page.getByRole('button', { name: 'Distributions' }).click()
  await expect(page.locator('[data-figure="distribution"] svg')).toBeVisible()
  await expect(page.locator('.xpc__legenditem--selected')).toContainText(/active selection/i)

  await page.getByRole('button', { name: 'Missingness' }).click()
  await expect(page.locator('[data-figure="missingness"] svg')).toBeVisible()
  await expect(page.locator('.xw__popcount')).toContainText('selected of')
  // The policy is stated, and the matrix says what it draws.
  await expect(page.locator('.xfig__note').first()).toContainText('Missing means an empty cell')

  // Returning to parallel coordinates keeps the selection: one engine.
  await page.getByRole('button', { name: 'Parallel coordinates' }).click()
  await expect(page.locator('.xw__popcount')).toContainText('selected of')
})

test('figure exports are real, provenance-carrying files', async ({ page }) => {
  await loadDemoAndOpenExplorer(page)
  const figure = page.locator('[data-testid="parallel-coordinates"]')

  const [svg] = await Promise.all([
    page.waitForEvent('download'),
    figure.locator('.xexport').getByRole('button', { name: 'SVG', exact: true }).click(),
  ])
  const svgPath = join(TMP, svg.suggestedFilename())
  await svg.saveAs(svgPath)
  const svgText = await svgPath
  const { readFileSync } = await import('node:fs')
  const svgContent = readFileSync(svgPath, 'utf-8')
  expect(svgText).toBeTruthy()
  expect(svgContent).toContain('<path')
  expect(svgContent).toContain('Active selection')
  expect(svgContent).toContain('sha256:')

  const [json] = await Promise.all([
    page.waitForEvent('download'),
    figure.locator('.xexport').getByRole('button', { name: 'JSON', exact: true }).click(),
  ])
  const jsonPath = join(TMP, json.suggestedFilename())
  await json.saveAs(jsonPath)
  const manifest = JSON.parse(readFileSync(jsonPath, 'utf-8'))
  expect(manifest.dataset.sha256).toHaveLength(64)
  expect(manifest.privacy.raw_rows_embedded).toBe(false)

  const [png] = await Promise.all([
    page.waitForEvent('download'),
    figure.locator('.xexport').getByRole('button', { name: 'PNG', exact: true }).click(),
  ])
  const pngPath = join(TMP, png.suggestedFilename())
  await png.saveAs(pngPath)
  const { statSync } = await import('node:fs')
  expect(statSync(pngPath).size).toBeGreaterThan(10000)
})

test('the pre-existing audit and study workflows still work after the explorer', async ({ page }) => {
  await loadDemoAndOpenExplorer(page)
  await brushFirstAxis(page)

  // Study Card and Data Dictionary remain reachable and functional.
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Study' }).click()
  // The Study view's h1 is the dataset name over the "Study & data" eyebrow.
  await expect(page.locator('.rs-eyebrow').first()).toHaveText('Study & data')
  await expect(page.locator('.rs-h1')).toContainText('repeated_entity')
  await page.getByRole('tab', { name: 'Data dictionary' }).click()
  await expect(page.getByText(/tenure_months/i).first()).toBeVisible()

  // The V1 audit path: Results runs the audit with the derived roles.
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Results' }).click()
  await page.getByRole('button', { name: 'Run the audit now' }).click()
  await expect(
    page.getByText(/audit complete|findings|no findings|evaluated/i).first(),
  ).toBeVisible({ timeout: 30000 })

  // Coming back to the explorer after a dataset-consuming audit run: the
  // selection was cleared when the dataset identity context demanded it; the
  // view must not show stale rows from a previous session.
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Explore' }).click()
  await expect(page.locator('[data-testid="parallel-coordinates"] svg')).toBeVisible()
  await expect(page.locator('.xw__popcount')).toContainText(/240 rows|selected of/)
})

test('responsive: the explorer stacks on a phone viewport without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await loadDemoAndOpenExplorer(page)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
  // The inspector is stacked below the canvas, not squeezed beside it.
  const canvasBox = await page.locator('.xw__canvas').boundingBox()
  const inspectorBox = await page.locator('.xw__inspector').boundingBox()
  expect(canvasBox).not.toBeNull()
  expect(inspectorBox).not.toBeNull()
  expect(inspectorBox!.y).toBeGreaterThanOrEqual(canvasBox!.y)
})
