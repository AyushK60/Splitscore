/**
 * S8C — identification journeys against the real backend (no mocks).
 *
 * Journey A: valid confounder adjustment — build a confounded graph, identify,
 * inspect the verified minimal set, verify on-graph highlights and the
 * d-separation probe.
 *
 * Journey B: collider conditioning and unobserved confounding — the empty set
 * is correct under an M-structure; conditioning on the collider is refused
 * with a structured violation; a hypothetical unobserved confounder is never
 * offered as a covariate and the honesty caveat is shown.
 *
 * Journey C: scientific invalidation — an identification run goes stale when
 * the graph's structure changes; rerunning yields the updated, verified answer.
 *
 * Screenshots land in docs/screenshots/s8c/ for the visual verification pass.
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Page } from '@playwright/test'

import { expect, loadDemoFromEntry, test } from './fixtures'

const DEMO = 'Repeated-entity subscription panel'
const SHOTS = fileURLToPath(new URL('../../docs/screenshots/s8c', import.meta.url))

test.use({ viewport: { width: 1440, height: 900 } })
test.setTimeout(180_000)

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
})

async function screenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: join(SHOTS, name), animations: 'disabled' })
}

async function goTo(page: Page, name: string): Promise<void> {
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name }).click()
}

async function addColumn(page: Page, column: string): Promise<void> {
  await page.getByRole('button', { name: `Add ${column}` }).click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
}

/** Clicks a node and connects it to a target through the keyboard method. */
async function connect(page: Page, source: string, target: string): Promise<void> {
  await page.locator(`.cnode[data-node-id="${source}"]`).click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
  await page
    .getByRole('combobox', { name: 'Connect this variable to a target' })
    .selectOption(target)
}

async function saveGraph(page: Page): Promise<void> {
  await page.getByRole('button', { name: /Save changes/ }).click()
  await expect(page.getByText(/Saved revision/)).toBeVisible({ timeout: 15_000 })
}

async function enterIdentification(page: Page): Promise<void> {
  await page.getByTestId('mode-identification').click()
  await expect(page.getByTestId('identification-panel')).toBeVisible()
}

async function runIdentification(page: Page): Promise<void> {
  await page.getByTestId('run-identification').click()
  await expect(page.getByTestId('identification-status')).toBeVisible({ timeout: 15_000 })
}

/**
 * Builds the M-structure used by journeys B and C:
 *   support_tickets → monthly_spend (treatment)
 *   support_tickets → month_index ← tenure_months → churned (outcome)
 *   monthly_spend → churned
 * The only backdoor path is blocked by the collider month_index, so the empty
 * set satisfies the criterion.
 */
async function buildColliderGraph(page: Page): Promise<void> {
  await loadDemoFromEntry(page, DEMO)
  await goTo(page, 'Causal Lab')
  await page.getByRole('button', { name: 'New graph' }).click()
  await addColumn(page, 'support_tickets')
  await addColumn(page, 'month_index')
  await addColumn(page, 'tenure_months')
  await addColumn(page, 'monthly_spend')
  await addColumn(page, 'churned')

  await connect(page, 'support_tickets', 'monthly_spend')
  await connect(page, 'support_tickets', 'month_index')
  await connect(page, 'tenure_months', 'month_index')
  await connect(page, 'tenure_months', 'churned')
  await connect(page, 'monthly_spend', 'churned')
  await expect(page.locator('.react-flow__edge')).toHaveCount(5)

  await page.locator('.cnode[data-node-id="monthly_spend"]').click()
  await page.getByRole('button', { name: 'Set as treatment' }).click()
  await page.locator('.cnode[data-node-id="churned"]').click()
  await page.getByRole('button', { name: 'Set as outcome' }).click()
}

test('S8C-A: confounder identification, verified set, highlights and probe', async ({ page }) => {
  page.on('dialog', (dialog) => void dialog.accept())
  await loadDemoFromEntry(page, DEMO)
  await goTo(page, 'Causal Lab')
  await page.getByRole('button', { name: 'New graph' }).click()

  await addColumn(page, 'support_tickets')
  await addColumn(page, 'monthly_spend')
  await addColumn(page, 'churned')

  await connect(page, 'support_tickets', 'monthly_spend')
  await connect(page, 'support_tickets', 'churned')
  await connect(page, 'monthly_spend', 'churned')
  await expect(page.locator('.react-flow__edge')).toHaveCount(3)

  await page.locator('.cnode[data-node-id="monthly_spend"]').click()
  await page.getByRole('button', { name: 'Set as treatment' }).click()
  await page.locator('.cnode[data-node-id="churned"]').click()
  await page.getByRole('button', { name: 'Set as outcome' }).click()

  await saveGraph(page)

  // --- identification on the saved graph ----------------------------------- //
  await enterIdentification(page)
  await runIdentification(page)
  await expect(page.getByText(/Backdoor adjustment available/)).toBeVisible()
  await expect(page.getByTestId('suggested-set')).toBeVisible()
  await expect(page.getByTestId('suggested-set').getByRole('button', { name: 'support_tickets' })).toBeVisible()
  // The empty set is not admissible here (a backdoor path exists), so exactly
  // one minimal set is reported.
  await expect(page.getByTestId('suggested-set')).toHaveCount(1)
  await screenshot(page, 's8c_identification_available.png')

  // --- inspect the set: chips highlight the variable on the real canvas ----- //
  await page.getByRole('button', { name: 'Inspect this set' }).click()
  await expect(page.locator('.cnode--adjustment')).toHaveCount(1)
  await expect(page.locator('.cnode--adjustment')).toHaveAttribute('data-node-id', 'support_tickets')
  await expect(page.locator('.clab-legend')).toBeVisible()

  // --- evaluate the set explicitly: admissible, graphically ----------------- //
  await page.getByTestId('evaluate-set').click()
  await expect(page.getByTestId('adjustment-verdict')).toBeVisible()
  await expect(page.getByText(/Set admissible/)).toBeVisible()

  // --- d-separation probe ---------------------------------------------------- //
  // An isolated variable is d-separated from everything given nothing. The
  // probe runs against the saved graph, so save the new node first.
  await page.getByTestId('mode-authoring').click()
  await addColumn(page, 'tenure_months')
  await saveGraph(page)
  await page.getByTestId('mode-identification').click()
  await page
    .getByRole('combobox', { name: 'd-separation variable X' })
    .selectOption({ label: 'tenure_months' })
  await page
    .getByRole('combobox', { name: 'd-separation variable Y' })
    .selectOption({ label: 'monthly_spend' })
  await page.getByTestId('run-d-separation').click()
  await expect(page.getByTestId('d-separation-verdict')).toBeVisible()
  await expect(page.getByText(/d-separated given nothing/)).toBeVisible()
})

test('S8C-B: collider conditioning is refused and unobserved confounding is honest', async ({
  page,
}) => {
  page.on('dialog', (dialog) => void dialog.accept())
  await buildColliderGraph(page)
  await saveGraph(page)

  await enterIdentification(page)
  await runIdentification(page)
  await expect(page.getByText(/Backdoor adjustment available/)).toBeVisible()
  // The empty set is the one verified minimal set: the collider blocks the
  // only backdoor path.
  await expect(page.getByText('Empty set — adjust for nothing.')).toBeVisible()
  await screenshot(page, 's8c_collider_empty_set.png')

  // Conditioning on the collider opens the path: the backend refuses the set.
  await page
    .getByTestId('adjustment-candidates')
    .getByRole('checkbox', { name: 'Adjust for month_index' })
    .check()
  await page.getByTestId('evaluate-set').click()
  await expect(page.getByTestId('adjustment-verdict')).toBeVisible()
  await expect(page.getByText(/Set not admissible/)).toBeVisible()
  await expect(page.getByText(/A backdoor path remains open/)).toBeVisible()
  await screenshot(page, 's8c_collider_conditioning_refused.png')

  // --- an unobserved confounder closes the criterion ------------------------- //
  await page.getByTestId('mode-authoring').click()
  await page.getByRole('button', { name: 'Add hypothetical variable' }).click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
  await connect(page, 'u_1', 'monthly_spend')
  await connect(page, 'u_1', 'churned')
  await expect(page.locator('.react-flow__edge')).toHaveCount(7)
  await saveGraph(page)

  await enterIdentification(page)
  await runIdentification(page)
  await expect(page.getByText(/No eligible observed backdoor set found/)).toBeVisible()
  await expect(page.getByText(/does not prove the effect is unidentifiable by every method/).first()).toBeVisible()
  // The unobserved variable is never offered as an adjustment covariate.
  await expect(
    page.getByTestId('adjustment-candidates').getByRole('checkbox', { name: /Hypothetical U1/ }),
  ).toHaveCount(0)
  // The rule-based explanation names it.
  await expect(page.getByText(/Unobserved variables cannot be adjusted for/)).toBeVisible()
  await screenshot(page, 's8c_unobserved_confounder_warning.png')
})

test('S8C-C: identification results go stale on scientific edits and rerun cleanly', async ({
  page,
}) => {
  page.on('dialog', (dialog) => void dialog.accept())
  await buildColliderGraph(page)
  await saveGraph(page)

  await enterIdentification(page)
  await runIdentification(page)
  await expect(page.getByText(/Backdoor adjustment available/)).toBeVisible()
  await expect(page.getByTestId('identification-stale')).toHaveCount(0)

  // A layout drag is not a scientific edit: no staleness. (Move a node, then
  // come straight back — the draft is dirty, so the run button is gated, but
  // the displayed result is not marked stale.)
  await page.getByTestId('mode-authoring').click()
  const node = page.locator('.cnode[data-node-id="month_index"]')
  const box = (await node.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + 10)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 200, box.y - 90, { steps: 6 })
  await page.mouse.up()
  await page.getByTestId('mode-identification').click()
  await expect(page.getByTestId('identification-save-gate')).toBeVisible()
  await expect(page.getByTestId('identification-stale')).toHaveCount(0)

  // A scientific edit — a new directed edge into the outcome — invalidates.
  await page.getByTestId('mode-authoring').click()
  await connect(page, 'month_index', 'churned')
  await expect(page.locator('.react-flow__edge')).toHaveCount(6)
  await page.getByTestId('mode-identification').click()
  await expect(page.getByTestId('identification-stale')).toBeVisible()
  await screenshot(page, 's8c_stale_results.png')

  // Save through the gate, rerun: the empty set is no longer admissible and
  // the backend reports verified minimal blocking sets instead.
  await page.getByTestId('identification-save-gate').getByRole('button', { name: 'Save graph' }).click()
  await expect(page.getByText(/Saved revision/)).toBeVisible({ timeout: 15_000 })
  await runIdentification(page)
  await expect(page.getByText(/Backdoor adjustment available/)).toBeVisible()
  await expect(page.getByTestId('identification-stale')).toHaveCount(0)
  // The empty set no longer suffices; a real set is reported.
  await expect(page.getByText('Empty set — adjust for nothing.')).toHaveCount(0)
  await expect(page.getByTestId('suggested-set').first()).toBeVisible()
  await screenshot(page, 's8c_identification_rerun.png')
})

test('S8C: tablet and mobile layouts keep identification usable', async ({ page }) => {
  page.on('dialog', (dialog) => void dialog.accept())
  await loadDemoFromEntry(page, DEMO)
  await goTo(page, 'Causal Lab')
  await page.getByRole('button', { name: 'New graph' }).click()
  await addColumn(page, 'support_tickets')
  await addColumn(page, 'monthly_spend')
  await addColumn(page, 'churned')
  await connect(page, 'support_tickets', 'monthly_spend')
  await connect(page, 'support_tickets', 'churned')
  await connect(page, 'monthly_spend', 'churned')
  await page.locator('.cnode[data-node-id="monthly_spend"]').click()
  await page.getByRole('button', { name: 'Set as treatment' }).click()
  await page.locator('.cnode[data-node-id="churned"]').click()
  await page.getByRole('button', { name: 'Set as outcome' }).click()
  await saveGraph(page)
  await enterIdentification(page)
  await runIdentification(page)

  await page.setViewportSize({ width: 768, height: 1024 })
  await page.waitForTimeout(300)
  await expect(page.getByTestId('identification-panel')).toBeVisible()
  await screenshot(page, 's8c_tablet_768.png')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(300)
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
  // The mode switch and the panel's primary action stay reachable.
  await expect(page.getByTestId('mode-authoring')).toBeVisible()
  await expect(page.getByTestId('run-identification')).toBeAttached()
  await screenshot(page, 's8c_mobile_390.png')
})
