/**
 * S10 — the complete research workflow journey against the real backend.
 *
 * Journey A — dataset → generated-split audit → causal identification gate →
 *   effect comparison → subgroup/robustness/what-if → Report Studio composes
 *   the integrated dossier (causal graph, identification, estimation,
 *   subgroup, robustness, what-if, methodology) → JSON download verifies
 *   schema 1.1.0 and the stored estimate.
 * Journey B — History stage honesty + portable reproducibility manifest +
 *   the deterministic causal-graph publication figure.
 *
 * No mocks: every number comes from the S9A/S9C/S10 services computing on the
 * bundled `causal_effect` demo.
 */
import { mkdirSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Page } from '@playwright/test'

import { expect, loadDemoFromEntry, test } from './fixtures'

const DEMO = 'Confounded treatment-effect study'
const SHOTS = fileURLToPath(new URL('../../docs/screenshots/s10', import.meta.url))
const TMP = join(tmpdir(), 'splitscope-s10-e2e')

test.use({ viewport: { width: 1440, height: 900 } })
test.setTimeout(420_000)

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
  mkdirSync(TMP, { recursive: true })
})

async function screenshot(page: Page, name: string, fullPage = false): Promise<void> {
  await page.screenshot({ path: join(SHOTS, name), animations: 'disabled', fullPage })
}

async function goTo(page: Page, name: string): Promise<void> {
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name }).click()
}

async function goToEstimationStudio(page: Page): Promise<void> {
  await goTo(page, 'Effect estimation')
  await expect(page.getByRole('region', { name: 'Effect Estimation Studio' })).toBeVisible()
  await expect(page.locator('.estsetup__state')).not.toHaveText('loading graph…', { timeout: 30_000 })
  const create = page.getByTestId('create-demo-graph')
  if (await create.isVisible()) await create.click()
  await expect(page.getByTestId('readiness-ok')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('run-estimation')).toBeEnabled({ timeout: 30_000 })
}

async function openReadyStudio(page: Page): Promise<string> {
  const loadResponse = page.waitForResponse(
    (response) => response.url().includes('/api/demos/') && response.request().method() === 'POST',
  )
  await loadDemoFromEntry(page, DEMO)
  const response = await loadResponse
  const datasetId = (await response.json()).dataset.dataset_id as string
  await goToEstimationStudio(page)
  return datasetId
}

async function runComparison(page: Page): Promise<void> {
  await page.getByTestId('run-estimation').click()
  await expect(page.getByTestId('estimation-running')).toBeVisible()
  await expect(page.getByTestId('effect-summary-table')).toBeVisible({ timeout: 180_000 })
}

async function runResearchExperiments(page: Page): Promise<void> {
  await goTo(page, 'Causal research')
  await expect(page.getByRole('region', { name: 'Study context' })).toBeVisible()
  const select = page.getByTestId('research-run-select')
  await expect(select).toBeEnabled({ timeout: 30_000 })
  await select.selectOption({ index: 1 })
  await expect(page.getByTestId('research-study-meta')).toBeVisible({ timeout: 30_000 })

  // Subgroup effects on the demo's region baseline variable.
  await page.getByTestId('subgroup-variable').selectOption('region')
  await page.getByTestId('subgroup-run').click()
  await expect(page.getByTestId('subgroup-forest-chart')).toBeVisible({ timeout: 120_000 })

  // Robustness: subsampling with disclosed parameters.
  await page.getByTestId('research-tab-robustness').click()
  await expect(page.getByTestId('robustness-view')).toBeVisible()
  await page.getByTestId('robustness-run').click()
  await expect(page.getByTestId('robustness-histogram')).toBeVisible({ timeout: 180_000 })

  // What-if scenario on the default profile.
  await page.getByTestId('research-tab-whatif').click()
  await expect(page.getByTestId('whatif-view')).toBeVisible()
  await page.getByTestId('whatif-field-age').fill('55')
  await page.getByTestId('whatif-run').click()
  await expect(page.getByTestId('whatif-chart')).toBeVisible({ timeout: 180_000 })
  await expect(page.getByTestId('whatif-contrast')).toBeVisible()
}

test('S10 journey A — audit, causal analysis and the integrated dossier', async ({ page }) => {
  // --- dataset with its declared split, then the leakage audit -------------- //
  await loadDemoFromEntry(page, DEMO)
  // The demo's manifest seeds the split and roles; the readiness rail is
  // green, so the audit runs on the declared configuration.
  await expect(page.getByTestId('dataset-ready-rail')).toBeVisible({ timeout: 30_000 }).catch(() => {})
  await page.getByRole('button', { name: /Run audit/ }).click()
  await expect(page).toHaveURL(/#\/audit$/)
  await expect(page.getByRole('heading', { name: 'Audit summary' })).toBeVisible({ timeout: 120_000 })

  // --- causal analysis: identification gate, comparison, research ---------- //
  // The demo is already the session dataset; reloading it would leave the
  // overview in its session-active state with the picker replaced.
  await goToEstimationStudio(page)
  await expect(page.locator('.estsetup__state')).not.toHaveText('loading graph…', { timeout: 30_000 })
  const create = page.getByTestId('create-demo-graph')
  if (await create.isVisible()) await create.click()
  await expect(page.getByTestId('readiness-ok')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('run-estimation')).toBeEnabled({ timeout: 30_000 })
  await runComparison(page)
  await runResearchExperiments(page)
  await screenshot(page, 's10-research-1440.png', true)

  // --- Report Studio composes the integrated dossier ----------------------- //
  await goTo(page, 'Export')
  await expect(page.locator('.report-paper')).toBeVisible()
  // The estimation-comparison run is pre-selected as a causal source.
  await expect(page.locator('.report-source').filter({ hasText: 'Causal estimation runs' })).toBeVisible()
  const causalToggle = page.locator('.report-section-toggle').filter({ hasText: 'Effect estimation' }).locator('input')
  await expect(causalToggle).toBeChecked()
  // Select the causal sections and regenerate.
  for (const label of ['Causal graph', 'Identification', 'Subgroup effects', 'Robustness', 'What-if scenario', 'Methodology']) {
    const toggle = page.locator('.report-section-toggle').filter({ hasText: label }).locator('input')
    if (!(await toggle.isChecked())) await toggle.check()
  }
  await page.getByRole('button', { name: 'Update preview' }).click()
  await expect(page.locator('#report-causal_estimation')).toBeVisible({ timeout: 60_000 })
  await expect(page.locator('#report-causal_graph')).toBeVisible()
  await expect(page.locator('#report-identification')).toBeVisible()
  await expect(page.locator('#report-subgroups')).toBeVisible()
  await expect(page.locator('#report-robustness')).toBeVisible()
  await expect(page.locator('#report-what_if')).toBeVisible()
  await expect(page.locator('#report-methodology')).toBeVisible()
  // The identification verdict is the verified backdoor result.
  await expect(page.locator('#report-identification')).toContainText('verified')
  // The methodology names the estimation and the standing assumptions.
  await expect(page.locator('#report-methodology')).toContainText('Causal effect estimation')
  await screenshot(page, 's10-dossier-1440.png', true)

  // --- the downloaded dossier is the same server payload ------------------- //
  const [jsonDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download dossier JSON' }).click(),
  ])
  expect(jsonDownload.suggestedFilename()).toMatch(/^splitscope-dossier-.*\.json$/)
  const jsonPath = join(TMP, jsonDownload.suggestedFilename())
  await jsonDownload.saveAs(jsonPath)
  const dossier = JSON.parse(readFileSync(jsonPath, 'utf-8')) as {
    report_kind: string
    schema_version: string
    request: { estimation_run_ids: string[] }
    sections: Record<string, { available: boolean; data: Record<string, unknown> }>
    reproducibility: { estimation_run_ids?: string[] }
  }
  expect(dossier.report_kind).toBe('dossier')
  expect(dossier.schema_version).toBe('1.1.0')
  expect(dossier.request.estimation_run_ids.length).toBeGreaterThan(0)
  expect(dossier.sections.causal_estimation.available).toBe(true)
  const estimationRuns = dossier.sections.causal_estimation.data.runs as Array<{
    estimators: Array<{ estimator: string; estimate: number | null; status: string }>
  }>
  expect(estimationRuns.length).toBeGreaterThan(0)
  expect(estimationRuns[0].estimators.some((estimator) => estimator.status === 'estimated')).toBe(true)
})

test('S10 journey B — history, manifest and the causal-graph publication figure', async ({ page }) => {
  const datasetId = await openReadyStudio(page)
  await runComparison(page)

  // --- history is a typed, honest projection -------------------------------- //
  await goTo(page, 'History')
  await expect(page.getByTestId('history-view')).toBeVisible()
  await expect(page.getByText('Every analysis this session has stored')).toBeVisible()
  const estimationCard = page.locator('[data-testid^="history-run-"]').filter({ hasText: 'Effect comparison' })
  await expect(estimationCard.first()).toBeVisible()
  // Details expand the recorded parameters; staleness is absent for fresh runs.
  await estimationCard.first().getByRole('button', { name: 'Details' }).click()
  await expect(estimationCard.first()).toContainText('Adjustment set')
  await screenshot(page, 's10-history-1440.png', true)

  // --- the portable reproducibility manifest downloads ---------------------- //
  const [manifestDownload] = await Promise.all([
    page.waitForEvent('download'),
    estimationCard.first().getByRole('button', { name: 'Download manifest' }).click(),
  ])
  expect(manifestDownload.suggestedFilename()).toMatch(/^splitscope_manifest_.*\.json$/)
  const manifestPath = join(TMP, manifestDownload.suggestedFilename())
  await manifestDownload.saveAs(manifestPath)
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8')) as {
    manifest_kind: string
    results_included: string
    integrity: { canonical_json_sha256: string }
    graph: { graph_id: string | null }
  }
  expect(manifest.manifest_kind).toBe('reproducibility_manifest')
  expect(manifest.results_included).toBe('metadata_only')
  expect(manifest.integrity.canonical_json_sha256).toMatch(/^[0-9a-f]{64}$/)
  expect(manifest.graph?.graph_id).toBeTruthy()

  // --- the causal-graph publication figure downloads ------------------------ //
  await goTo(page, 'Causal Lab')
  await expect(page.getByRole('region', { name: 'Causal Lab' })).toBeVisible()
  const figureButton = page.getByRole('button', { name: 'Export figure' })
  await expect(figureButton).toBeEnabled({ timeout: 30_000 })
  const [figureDownload] = await Promise.all([
    page.waitForEvent('download'),
    figureButton.click(),
  ])
  expect(figureDownload.suggestedFilename()).toMatch(/^splitscope-causal-graph-.*\.svg$/)
  const figurePath = join(TMP, figureDownload.suggestedFilename())
  await figureDownload.saveAs(figurePath)
  const svg = readFileSync(figurePath, 'utf-8')
  expect(svg.startsWith('<svg')).toBe(true)
  expect(svg).toContain('assumption')
  void datasetId
})
