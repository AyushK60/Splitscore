/**
 * S9C — Causal Research journeys against the real backend.
 *
 * No mocks: every number comes from the S9A/S9C services computing on the
 * bundled `causal_effect` demo.
 *
 * Journey A — subgroup effects: run a comparison in the estimation studio,
 *   build on the stored run in Causal research, estimate subgroup effects on
 *   `region`, and inspect the forest plot, table and contrast.
 * Journey B — robustness and what-if: subsampling distribution with the
 *   original reference, then a model-based scenario with disclosed defaults.
 * Journey C — staleness honesty: a structural graph edit marks the stored run
 *   stale and the research stage refuses to build on it.
 * Journey D — responsive QA at 1440 / 1024 / 768 / 390 with screenshots in
 *   docs/screenshots/s9c/.
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Page } from '@playwright/test'

import { expect, loadDemoFromEntry, test } from './fixtures'

const DEMO = 'Confounded treatment-effect study'
const SHOTS = fileURLToPath(new URL('../../docs/screenshots/s9c', import.meta.url))

test.use({ viewport: { width: 1440, height: 900 } })
test.setTimeout(300_000)

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
})

async function screenshot(page: Page, name: string, fullPage = false): Promise<void> {
  await page.screenshot({ path: join(SHOTS, name), animations: 'disabled', fullPage })
}

async function goTo(page: Page, name: string): Promise<void> {
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name }).click()
}

async function openReadyStudio(page: Page, reps = '100'): Promise<void> {
  await loadDemoFromEntry(page, DEMO)
  await goTo(page, 'Effect estimation')
  await expect(page.getByRole('region', { name: 'Effect Estimation Studio' })).toBeVisible()
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
}

/**
 * Runs one comparison, then opens Causal research with that stored run selected.
 */
async function openResearchWithRun(page: Page): Promise<string> {
  // Capture the dataset id from the single demo load inside openReadyStudio;
  // loading twice would leave the overview in its session-active state, where
  // the demo picker is replaced by the session summary.
  const loadResponse = page.waitForResponse(
    (response) =>
      response.url().includes('/api/demos/') && response.request().method() === 'POST',
  )
  await openReadyStudio(page)
  const response = await loadResponse
  lastDatasetId = (await response.json()).dataset.dataset_id as string
  await runComparison(page)
  await goTo(page, 'Causal research')
  await expect(page).toHaveURL(/#\/research$/)
  await expect(page.getByRole('region', { name: 'Study context' })).toBeVisible()
  const select = page.getByTestId('research-run-select')
  await expect(select).toBeEnabled({ timeout: 30_000 })
  await select.selectOption({ index: 1 })
  await expect(page.getByTestId('research-study-meta')).toBeVisible({ timeout: 30_000 })
  return await datasetId(page)
}

test('S9C journey A — subgroup effects on the confounded demonstration study', async ({ page }) => {
  await openResearchWithRun(page)

  // Treatment and outcome are never offered as subgroup variables.
  const options = await page.getByTestId('subgroup-variable').locator('option').allTextContents()
  expect(options.join(' ')).not.toContain('treatment')
  expect(options.join(' ')).not.toContain('outcome')

  await page.getByTestId('subgroup-variable').selectOption('region')
  await page.getByTestId('subgroup-run').click()
  await expect(page.getByTestId('subgroup-forest-chart')).toBeVisible({ timeout: 120_000 })
  await expect(page.getByTestId('subgroup-table')).toBeVisible()
  // The demo has three regions; all three appear in the table.
  await expect(page.getByTestId('subgroup-table-east')).toBeVisible()
  await expect(page.getByTestId('subgroup-table-north')).toBeVisible()
  await expect(page.getByTestId('subgroup-table-south')).toBeVisible()
  // The forest plot names the overall reference and the exploratory intent.
  await expect(page.getByTestId('subgroup-forest')).toContainText('overall')
  await expect(page.getByTestId('subgroup-forest')).toContainText('exploratory')
  await screenshot(page, 'subgroup-forest-1440.png', true)
})

test('S9C journey B — robustness distribution and a what-if scenario', async ({ page }) => {
  await openResearchWithRun(page)

  await page.getByTestId('research-tab-robustness').click()
  await expect(page.getByTestId('robustness-view')).toBeVisible()
  await page.getByTestId('robustness-run').click()
  await expect(page.getByTestId('robustness-histogram')).toBeVisible({ timeout: 180_000 })
  // A vertical SVG line has a zero-width bounding box (invisible to Playwright),
  // so the original reference is asserted through its value text instead.
  await expect(page.getByTestId('robustness-original')).toContainText('1.')
  await expect(page.getByTestId('robustness-summary')).toBeVisible()
  await screenshot(page, 'robustness-1440.png', true)

  await page.getByTestId('research-tab-whatif').click()
  await expect(page.getByTestId('whatif-view')).toBeVisible()
  await page.getByTestId('whatif-field-age').fill('55')
  await page.getByTestId('whatif-run').click()
  await expect(page.getByTestId('whatif-chart')).toBeVisible({ timeout: 120_000 })
  await expect(page.getByTestId('whatif-contrast')).toBeVisible()
  await expect(page.getByTestId('whatif-profile')).toContainText('cohort median (default)')
  await screenshot(page, 'whatif-1440.png', true)
})

test('S9C journey C — a structural graph edit makes the stored run unusable here', async ({ page }) => {
  const dsId = await openResearchWithRun(page)
  await expect(page.getByTestId('research-study-meta')).toBeVisible()

  // Remove the region → outcome edge through the API, exactly what the Causal
  // Lab's save does: the graph's scientific fingerprint changes.
  const listing = await page.request.get(`/api/datasets/${dsId}/causal-graphs`)
  const graphs = (await listing.json()).graphs as Array<{ graph_id: string }>
  const detail = await page.request.get(
    `/api/datasets/${dsId}/causal-graphs/${graphs[0].graph_id}`,
  )
  const graph = await detail.json()
  const spec = {
    schema_version: graph.schema_version,
    dataset_id: graph.dataset_id,
    name: graph.name,
    description: graph.description,
    nodes: graph.nodes.map((node: Record<string, unknown>) => ({
      node_id: node.node_id,
      label: node.label,
      column: node.column,
      observed: node.observed,
      kind: node.kind,
      description: node.description,
      layout: node.layout,
    })),
    edges: graph.edges
      .filter((edge: { source: string; target: string }) => !(edge.source === 'region' && edge.target === 'outcome'))
      .map((edge: Record<string, unknown>) => ({
        source: edge.source,
        target: edge.target,
        rationale: edge.rationale,
        reference: edge.reference,
      })),
    analysis: graph.analysis,
    assumptions: graph.assumptions,
  }
  const save = await page.request.put(
    `/api/datasets/${dsId}/causal-graphs/${graphs[0].graph_id}`,
    { data: { graph: spec } },
  )
  expect(save.ok()).toBeTruthy()

  // Re-selecting the stored run must surface the named stale refusal here —
  // the research stage never builds on a run whose study has changed.
  await page.getByTestId('research-run-select').selectOption({ index: 0 })
  await page.getByTestId('research-run-select').selectOption({ index: 1 })
  await expect(page.getByTestId('research-study-error')).toContainText('stale', {
    timeout: 30_000,
  })
})

let lastDatasetId = ''

async function datasetId(_page: Page): Promise<string> {
  return lastDatasetId
}

test('S9C journey D — responsive QA at four widths', async ({ page }) => {
  await openResearchWithRun(page)
  await page.getByTestId('subgroup-variable').selectOption('region')
  await page.getByTestId('subgroup-run').click()
  await expect(page.getByTestId('subgroup-forest-chart')).toBeVisible({ timeout: 120_000 })

  for (const [width, height, name] of [
    [1440, 900, 'research-1440.png'],
    [1024, 768, 'research-1024.png'],
    [768, 900, 'research-768.png'],
    [390, 844, 'research-390.png'],
  ] as const) {
    await page.setViewportSize({ width, height })
    await page.waitForTimeout(400)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    )
    expect(overflow, `no page-level horizontal overflow at ${width}px`).toBe(false)
    for (const tab of ['research-tab-subgroups', 'research-tab-robustness', 'research-tab-whatif']) {
      await expect(page.getByTestId(tab)).toBeVisible()
    }
    await screenshot(page, name)
  }
})
