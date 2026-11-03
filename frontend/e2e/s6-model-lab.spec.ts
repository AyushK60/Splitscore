/**
 * S6-B — Model Lab end-to-end journey.
 *
 * Runs against the real backend and the bundled clean-control dataset. The
 * assertions are about actual fitted output: a coefficient table from the
 * server, an exported run that matches the screen, a real refusal from the
 * backend for an impossible specification, and no stale result after the
 * dataset is replaced.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

import { expect, loadDemoFromEntry, test } from './fixtures'
import type { Page } from '@playwright/test'

test.use({ viewport: { width: 1440, height: 950 } })

const DEMO = 'Clean control dataset'
const EXPORT_DIR = tmpdir()

async function openModelLab(page: Page) {
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Model Lab' }).click()
  await expect(page.locator('.mlab__grid')).toBeVisible()
}

test('fits an OLS model, shows real coefficients and exports the same run', async ({ page }) => {
  await loadDemoFromEntry(page, DEMO)
  await openModelLab(page)

  // A statistical fit without an audit says so instead of implying validation.
  await expect(page.getByText('No audit in this session')).toBeVisible()

  await page.getByLabel('Task').selectOption('ols')
  await page.getByLabel('Outcome').selectOption('x1')
  await expect(page.getByLabel('Outcome')).toHaveValue('x1')
  await page.getByRole('button', { name: 'Fit model' }).click()

  const formula = page.locator('.mlab__formula')
  await expect(formula).toContainText('x1 ~')
  await expect(page.locator('.mlab__stats')).toContainText('R²')
  await expect(page.locator('.mlab__stats')).toContainText('Adjusted R²')

  const table = page.locator('.mlab__table').first()
  await expect(table).toContainText('const')
  await expect(table).not.toContainText('Odds ratio')
  const rows = table.locator('tbody tr')
  expect(await rows.count()).toBeGreaterThan(1)
  const firstEstimate = (await rows.first().locator('td').first().textContent())?.trim() ?? ''
  expect(firstEstimate).not.toBe('')
  expect(firstEstimate).not.toBe('—')

  // Diagnostics are drawn from the fitted sample and say how much they show.
  await expect(page.locator('.mlab__diagnostics')).toContainText('Residual versus fitted')
  await expect(page.locator('.mlab__diagnostics')).toContainText(/(Every|All) \d+ analysed rows/)
  expect(await page.locator('.mlab__diagnostics circle').count()).toBeGreaterThan(1)

  const metaText = (await page.locator('.mlab__meta').textContent()) ?? ''
  const runId = metaText.match(/run-[a-f0-9]+/)?.[0] ?? ''
  expect(runId).toMatch(/^run-/)

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export run JSON' }).click(),
  ])
  const path = join(EXPORT_DIR, download.suggestedFilename())
  await download.saveAs(path)
  const payload = JSON.parse(readFileSync(path, 'utf-8')) as {
    run_id: string
    kind: string
    coefficients: Array<{ term: string; estimate: number }>
    dataset: { sha256: string }
    population: { analyzed: number }
  }
  expect(payload.run_id).toBe(runId)
  expect(payload.kind).toBe('statistical_model')
  expect(payload.dataset.sha256).toHaveLength(64)
  expect(payload.coefficients.map((entry) => entry.term)).toContain('const')
  expect(payload.population.analyzed).toBeGreaterThan(0)
  const exportedConst = payload.coefficients.find((entry) => entry.term === 'const')?.estimate ?? 0
  expect(Number(firstEstimate)).toBeCloseTo(exportedConst, 3)
})

test('refuses an impossible logistic specification and explains why', async ({ page, allowFailure }) => {
  await loadDemoFromEntry(page, DEMO)
  await openModelLab(page)

  // `segment` has three observed levels, so binary logistic regression is not defined.
  // The 422 is the intended refusal, not a broken request.
  allowFailure(/HTTP 422 POST .*\/models\/statistics/)
  await page.getByLabel('Task').selectOption('logistic')
  await page.getByLabel('Outcome').selectOption('segment')
  await page.getByRole('button', { name: 'Fit model' }).click()

  const alert = page.locator('.callout--danger[role="alert"]').first()
  await expect(alert).toBeVisible()
  await expect(alert).toContainText('exactly two observed levels')
  await expect(page.locator('.mlab__table')).toHaveCount(0)
  await expect(page.locator('.mlab__formula')).toHaveCount(0)

  // A binary outcome with an explicit positive class fits and reports odds ratios.
  await page.getByLabel('Outcome').selectOption('label')
  await page.getByLabel('Positive class (coded 1)').selectOption('1')
  await page.getByRole('button', { name: 'Fit model' }).click()
  await expect(page.locator('.mlab__formula')).toContainText('label ~')
  await expect(page.locator('.mlab__table').first()).toContainText('Odds ratio')
  await expect(page.locator('.mlab__table').first()).not.toContainText('R²')
  await expect(page.locator('.mlab__meta')).toContainText('Binary logistic regression')
})

test('replacing the dataset clears the previous fit', async ({ page }) => {
  await loadDemoFromEntry(page, DEMO)
  await openModelLab(page)
  await page.getByRole('button', { name: 'Fit model' }).click()
  await expect(page.locator('.mlab__table')).toHaveCount(1)
  const oldRun = ((await page.locator('.mlab__meta').textContent()) ?? '').match(/run-[a-f0-9]+/)?.[0]
  expect(oldRun).toBeTruthy()

  // Replace the dataset: Clear in Data removes the current file, then Start
  // offers the demo entry panel again (a session with a dataset shows the
  // contextual overview instead).
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Data' }).click()
  await page.getByRole('button', { name: 'Clear', exact: true }).click()
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Start' }).click()
  await page
    .locator('.we__demo')
    .filter({ hasText: 'Repeated-entity subscription panel' })
    .getByRole('button', { name: 'Open', exact: true })
    .click()
  await expect(page).toHaveURL(/#\/dataset/)
  await openModelLab(page)

  await expect(page.locator('.mlab__placeholder')).toContainText('Nothing fitted yet')
  await expect(page.locator('.mlab__table')).toHaveCount(0)
  await expect(page.getByText(oldRun!)).toHaveCount(0)
})
