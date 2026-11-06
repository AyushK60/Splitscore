/**
 * S9B — Effect Estimation Studio journeys against the real backend.
 *
 * No mocks and no seeded results: every number asserted here is computed by the
 * S9A engine from the bundled `causal_effect` demo, whose data-generating
 * average effect (1.5) is documented metadata rather than an input to the
 * estimator.
 *
 * Journey A — complete estimation: demo → demonstration DAG → readiness →
 *   three-estimator comparison → balance → overlap → weights → methodology →
 *   SVG/JSON export.
 * Journey B — scientific honesty: influence-function intervals leave
 *   regression adjustment without an interval, and an empty adjustment set is
 *   refused by the backend instead of estimated.
 * Journey C — staleness and navigation: changing the interval level marks the
 *   displayed result stale; returning to a stored run restores its numbers and
 *   its stale state.
 * Journey D — responsive QA at 1440 / 1024 / 768 / 390 with no page-level
 *   horizontal overflow.
 *
 * Screenshots are written to docs/screenshots/s9b/.
 */
import { mkdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Page } from '@playwright/test'

import { expect, loadDemoFromEntry, test } from './fixtures'

const DEMO = 'Confounded treatment-effect study'
const SHOTS = fileURLToPath(new URL('../../docs/screenshots/s9b', import.meta.url))

test.use({ viewport: { width: 1440, height: 900 } })
test.setTimeout(240_000)

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
})

async function screenshot(page: Page, name: string, fullPage = false): Promise<void> {
  await page.screenshot({ path: join(SHOTS, name), animations: 'disabled', fullPage })
}

async function goTo(page: Page, name: string): Promise<void> {
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name }).click()
}

/**
 * Opens the studio on the confounded demo, creates the demonstration DAG when
 * none exists for this dataset, and waits until the backend's readiness probe
 * enables the explicit run. 100 bootstrap replicates is the contract minimum and
 * keeps the browser suite fast without changing the estimator code path.
 */
async function openReadyStudio(page: Page, reps = '100'): Promise<void> {
  await loadDemoFromEntry(page, DEMO)
  await goTo(page, 'Effect estimation')
  await expect(page).toHaveURL(/#\/estimation$/)
  await expect(page.getByRole('region', { name: 'Effect Estimation Studio' })).toBeVisible()

  // Wait for the saved-graph listing to settle before offering to create one,
  // otherwise a fast click can race the initial empty listing.
  await expect(page.locator('.estsetup__state')).not.toHaveText('loading graph…', {
    timeout: 30_000,
  })
  const create = page.getByTestId('create-demo-graph')
  if (await create.isVisible()) await create.click()

  await expect(page.getByTestId('readiness-ok')).toBeVisible({ timeout: 30_000 })
  if (reps !== '500') {
    await page.getByLabel('Bootstrap replicates').fill(reps)
  }
  await expect(page.getByTestId('run-estimation')).toBeEnabled({ timeout: 30_000 })
}

async function runComparison(page: Page): Promise<void> {
  await page.getByTestId('run-estimation').click()
  await expect(page.getByTestId('estimation-running')).toBeVisible()
  await expect(page.getByTestId('effect-summary-table')).toBeVisible({ timeout: 180_000 })
  await expect(page.getByTestId('readiness-chip')).toContainText('Ready')
}

test('S9B journey A — full estimation, diagnostics and figure export', async ({ page }) => {
  await openReadyStudio(page)
  await expect(page.getByTestId('demo-banner')).toContainText('1.500 outcome units')
  await expect(page.getByTestId('readiness-ok')).toContainText('1,200 rows would be analysed')
  await screenshot(page, 'setup.png')

  await runComparison(page)

  // --- flagship figure: three estimators, real values and intervals -------- //
  await expect(page.getByTestId('summary-dot-regression_adjustment')).toBeVisible()
  await expect(page.getByTestId('summary-dot-ipw')).toBeVisible()
  await expect(page.getByTestId('summary-dot-aipw')).toBeVisible()
  const table = page.getByTestId('effect-summary-table')
  await expect(table).toContainText('1,200')
  await expect(table).toContainText('95% percentile bootstrap')
  // Every estimate is finite and in the plausible range of this simulation.
  for (const estimator of ['regression_adjustment', 'ipw', 'aipw']) {
    const value = Number(
      await page.getByTestId(`summary-dot-${estimator}`).getAttribute('data-value'),
    )
    expect(Number.isFinite(value)).toBe(true)
    expect(value).toBeGreaterThan(0)
    expect(value).toBeLessThan(6)
  }
  await page.getByTestId('effect-summary-table').scrollIntoViewIfNeeded()
  await screenshot(page, 'effect-summary.png')

  // --- covariate balance: a real Love plot --------------------------------- //
  await page.getByTestId('tab-balance').click()
  await expect(page.getByTestId('love-plot')).toBeVisible()
  const loveRows = page.getByTestId('love-row')
  expect(await loveRows.count()).toBeGreaterThan(2)
  expect(await page.getByTestId('love-unweighted').count()).toBeGreaterThan(2)
  await expect(page.getByText('0.1 heuristic guide')).toBeVisible()
  await page.getByTestId('love-plot').scrollIntoViewIfNeeded()
  await screenshot(page, 'balance.png')

  // --- overlap: fixed 20-bin histograms from the backend ------------------- //
  await page.getByTestId('tab-overlap').click()
  await expect(page.getByTestId('overlap-view')).toBeVisible()
  expect(await page.getByTestId('overlap-bin').count()).toBe(20)
  await expect(page.getByTestId('overlap-table')).toBeVisible()
  await page.getByTestId('overlap-view').scrollIntoViewIfNeeded()
  await screenshot(page, 'overlap.png')

  // --- weights and effective sample size ---------------------------------- //
  await page.getByTestId('tab-weights').click()
  await expect(page.getByTestId('weights-table')).toBeVisible()
  await expect(page.getByTestId('ess-arm-treated')).toContainText('of rows retained')
  await page.getByTestId('weights-view').scrollIntoViewIfNeeded()
  await screenshot(page, 'weights-figure.png')
  await page.getByTestId('weights-table').scrollIntoViewIfNeeded()
  await screenshot(page, 'weights.png')

  // --- methodology: provenance and deterministic interpretation ----------- //
  await page.getByTestId('tab-methods').click()
  await expect(page.getByTestId('interpretation')).toContainText('Under the assumptions encoded in the selected DAG')
  await expect(page.getByTestId('interpretation')).toContainText('not a proof that the effect is causal')
  await expect(page.getByTestId('methodology-view')).toContainText('Dataset fingerprint (sha256)')
  await expect(page.getByTestId('methodology-view')).toContainText('Graph scientific fingerprint')
  await page.getByTestId('interpretation').scrollIntoViewIfNeeded()
  await screenshot(page, 'methodology.png')

  // --- export the live SVG with its caption ------------------------------- //
  await page.getByTestId('tab-summary').click()
  const figure = page.getByTestId('effect-summary')
  await figure.scrollIntoViewIfNeeded()
  const svgDownload = page.waitForEvent('download')
  await figure.getByRole('group', { name: 'Figure export' }).getByRole('button', { name: 'SVG' }).click()
  const svg = await svgDownload
  expect(svg.suggestedFilename()).toMatch(/^splitscope_s9b_effect_summary_.*\.svg$/)
  const svgPath = await svg.path()
  const svgText = readFileSync(svgPath, 'utf8')
  expect(svgText).toContain('<svg')
  expect(svgText).toContain('Average treatment effect by estimator')
  expect(svgText).toContain('Run ')

  // --- export the run payload verbatim ------------------------------------ //
  const jsonDownload = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Run JSON' }).click()
  const json = await jsonDownload
  expect(json.suggestedFilename()).toMatch(/^splitscope_estimation_run-.*\.json$/)
  const envelope = JSON.parse(readFileSync(await json.path(), 'utf8')) as {
    export_kind: string
    run: { results: Array<{ status: string; estimate?: number }> }
  }
  expect(envelope.export_kind).toBe('splitscope_causal_estimation_run')
  expect(envelope.run.results).toHaveLength(3)
  expect(envelope.run.results.every((result) => result.status === 'estimated')).toBe(true)
})

test('S9B journey B — unavailable intervals and refused configurations', async ({
  page,
  allowFailure,
}) => {
  await openReadyStudio(page)

  // Influence-function intervals exist for IPW/AIPW only; regression adjustment
  // must report the interval as unavailable rather than inventing bounds.
  await page.getByLabel('Uncertainty method').selectOption('influence_function')
  await expect(page.getByTestId('run-estimation')).toBeEnabled({ timeout: 30_000 })
  await page.getByTestId('run-estimation').click()
  await expect(page.getByTestId('effect-summary-table')).toBeVisible({ timeout: 180_000 })

  await expect(page.getByTestId('summary-row-regression_adjustment')).toContainText('unavailable')
  await expect(
    page.locator('[data-testid="summary-row-regression_adjustment"] .estrow__interval'),
  ).toHaveCount(0)
  await expect(page.getByTestId('summary-dot-regression_adjustment')).toHaveAttribute(
    'data-value',
    /^-?\d/,
  )

  // An empty adjustment set is not admissible for this DAG: the readiness probe
  // blocks the run and nothing is estimated.
  allowFailure(/HTTP 422 POST .*\/estimation\/validate$/)
  await page.getByRole('button', { name: 'Clear set' }).click()
  await expect(page.getByTestId('readiness-blocked')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('run-estimation')).toBeDisabled()
  await expect(page.getByTestId('readiness-blocked')).toContainText(
    /backdoor|adjustment|admissib/i,
  )
  await page.getByTestId('readiness-blocked').evaluate((element) => {
    // The setup panel is its own sticky scroll region on desktop, so scroll the
    // nearest scrollable ancestors rather than only the window.
    element.scrollIntoView({ block: 'center', behavior: 'instant' })
  })
  await screenshot(page, 'refused-configuration.png')
})

test('S9B journey C — staleness, navigation and stored results', async ({ page }) => {
  await openReadyStudio(page)
  await runComparison(page)
  await expect(page.getByTestId('result-meta')).toContainText('Run ')
  await expect(page.getByTestId('stale-banner')).toHaveCount(0)

  // A meaning-changing configuration edit marks the displayed result stale.
  await page.getByLabel('Interval level').selectOption('0.99')
  await expect(page.getByTestId('stale-banner')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('stale-banner')).toContainText('The interval level changed.')
  await expect(page.getByTestId('stale-banner')).toContainText('not current')
  await page.getByTestId('stale-banner').evaluate((element) => {
    window.scrollTo({
      top: element.getBoundingClientRect().top + window.scrollY - 96,
      behavior: 'instant',
    })
  })
  await screenshot(page, 'stale-result.png')

  // Leave the studio and come back: the result is not on screen, but the stored
  // run can be reloaded from the bounded session history.
  await goTo(page, 'Explore')
  await goTo(page, 'Effect estimation')
  await page.getByTestId('history-summary').click()
  const runCount = page.locator('.esthistory__row')
  await expect(runCount.first()).toBeVisible()
  await page.locator('.esthistory__row').first().getByRole('button', { name: 'Load' }).click()
  await expect(page.getByTestId('result-meta')).toContainText('loaded from history', {
    timeout: 30_000,
  })
  await expect(page.getByTestId('effect-summary-table')).toBeVisible()
  await expect(page.getByTestId('stale-banner')).toBeVisible()
})

test('S9B journey D — responsive QA at four widths', async ({ page }) => {
  await openReadyStudio(page)
  await runComparison(page)

  for (const [label, width, height] of [
    ['desktop-1440', 1440, 900],
    ['laptop-1024', 1024, 768],
    ['tablet-768', 768, 900],
    ['mobile-390', 390, 844],
  ] as const) {
    await page.setViewportSize({ width, height })
    await page.getByTestId('tab-summary').click()
    await expect(page.getByTestId('effect-summary-table')).toBeVisible()

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    )
    expect(overflow, `${label}: page-level horizontal overflow`).toBeLessThanOrEqual(1)
    await screenshot(page, `${label}.png`)

    // The five views stay reachable at every width.
    await page.getByTestId('tab-balance').click()
    await expect(page.getByTestId('love-plot')).toBeVisible()
    await page.getByTestId('tab-overlap').click()
    await expect(page.getByTestId('overlap-view')).toBeVisible()
  }
})
