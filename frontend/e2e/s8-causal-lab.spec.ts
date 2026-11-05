/**
 * S8B — Causal Lab journey against the real backend.
 *
 * The full authoring loop runs against the live S8A endpoints (no mocks):
 * dataset selection → Causal Lab → create graph → add variables → draw
 * directed edges → set analysis scope → document an assumption → validate →
 * save → reload (positions restored) → export. A second journey proves the
 * backend refuses an invalid structure and the draft survives the rejection.
 *
 * Screenshots at 1440/768/390 are captured to docs/screenshots/s8/.
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { Page } from '@playwright/test'

import { expect, loadDemoFromEntry, test } from './fixtures'

const DEMO = 'Repeated-entity subscription panel'
const SHOTS = fileURLToPath(new URL('../../docs/screenshots/s8', import.meta.url))

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

/** Adds a dataset column as an observed node from the left rail palette. */
async function addColumn(page: Page, column: string): Promise<void> {
  await page.getByRole('button', { name: `Add ${column}` }).click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
}

test('S8B: create, validate, save, reload and export a causal graph', async ({ page }) => {
  // Loading a teaching example dirties the draft, so "New graph" asks before
  // discarding it — accept.
  page.on('dialog', (dialog) => void dialog.accept())
  await loadDemoFromEntry(page, DEMO)

  // --- enter the Causal Lab via the real navigation ------------------------ //
  await goTo(page, 'Causal Lab')
  await expect(page).toHaveURL(/#\/causal$/)
  await expect(page.getByRole('region', { name: 'Causal Lab' })).toBeVisible()
  await expect(page.getByTestId('causal-empty-state')).toBeVisible()
  await screenshot(page, 's8_empty_lab.png')

  // --- teaching example is labelled synthetic ------------------------------ //
  await page.getByRole('button', { name: 'Fork example' }).click()
  await expect(page.locator('.cnode')).toHaveCount(3)
  // The example's synthetic teaching label is stated on the example itself
  // (description + assumption source); the graph name confirms it in the
  // graph inspector.
  await page.getByRole('button', { name: 'Graph settings' }).click()
  await expect(page.getByRole('textbox', { name: 'Graph name' })).toHaveValue(/Teaching example — fork/)
  await expect(page.getByRole('textbox', { name: 'Graph description' })).toHaveValue(/Synthetic teaching example/)

  // --- start a real graph and add observed variables ----------------------- //
  await page.getByRole('button', { name: 'New graph' }).click()
  await addColumn(page, 'monthly_spend')
  await page.getByRole('button', { name: 'Add tenure_months' }).click()
  await page.getByRole('button', { name: 'Add churned' }).click()
  await expect(page.locator('.cnode')).toHaveCount(3)

  // --- draw directed edges through the keyboard-accessible method ---------- //
  // Each node is clicked explicitly so the inspector is the intended node's.
  // monthly_spend → tenure_months; monthly_spend is the treatment.
  await page.locator('.cnode[data-node-id="monthly_spend"]').click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
  await page
    .getByRole('combobox', { name: 'Connect this variable to a target' })
    .selectOption('tenure_months')
  await page.getByRole('button', { name: 'Set as treatment' }).click()
  await expect(page.getByRole('button', { name: 'Set as treatment' })).toBeDisabled()

  // tenure_months → churned; churned is the outcome.
  await page.locator('.cnode[data-node-id="tenure_months"]').click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
  await page
    .getByRole('combobox', { name: 'Connect this variable to a target' })
    .selectOption('churned')

  await page.locator('.cnode[data-node-id="churned"]').click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
  await page.getByRole('button', { name: 'Set as outcome' }).click()
  await expect(page.getByRole('button', { name: 'Set as outcome' })).toBeDisabled()

  // The canvas now shows two assumed edges.
  await expect(page.locator('.react-flow__edge')).toHaveCount(2)

  // --- name the graph, record an assumption --------------------------------- //
  await page.getByRole('button', { name: 'Graph settings' }).click()
  await page.getByRole('textbox', { name: 'Graph name' }).fill('Spend shapes tenure, tenure shapes churn')
  await page.getByRole('button', { name: 'Add assumption #1' }).click()
  await page
    .getByTestId('assumption-record')
    .getByRole('combobox', { name: 'Assumption category' })
    .selectOption('temporal_ordering')
  await page
    .getByTestId('assumption-record')
    .getByRole('textbox', { name: 'Assumption rationale' })
    .fill('In the panel, monthly spend is observed before tenure accrues, and tenure precedes churn.')
  await page
    .getByTestId('assumption-record')
    .getByRole('combobox', { name: 'Assumption status' })
    .selectOption('declared')

  // --- save the dirty draft ------------------------------------------------- //
  await expect(page.getByRole('button', { name: /Save changes/ })).toBeEnabled()
  await screenshot(page, 's8_populated_dag.png')
  await page.getByRole('button', { name: /Save changes/ }).click()
  await expect(page.getByText(/Saved revision/)).toBeVisible({ timeout: 15_000 })
  await expect(page.getByRole('button', { name: 'Saved — no unsaved changes' })).toBeDisabled()

  // --- validate: the backend is the only validator --------------------------- //
  await page.getByRole('button', { name: 'Validate' }).click()
  await expect(page.getByTestId('validation-inspector')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Structurally valid DAG' })).toBeVisible()
  await screenshot(page, 's8_validation_pass.png')

  // --- inspector shows structure-derived facts from the backend ------------- //
  await page.locator('.cnode[data-node-id="churned"]').click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
  await expect(page.getByText(/Derived from the drawn edges only/)).toBeVisible()
  await screenshot(page, 's8_node_inspector.png')

  // --- drag a node, save, then re-enter the route ---------------------------- //
  // The dataset is session state by design, so a browser reload intentionally
  // returns to the dataset entry. Restoring a saved graph is exercised by
  // unmounting and remounting the Causal Lab: the graph loads from the
  // backend with its stored layout coordinates.
  await page.keyboard.press('Escape')
  // Graph-space coordinates (the RF transform), not viewport boxes, which
  // zoom and pan would change. Only the transform is compared: React Flow may
  // toggle `visibility` on off-screen nodes between mounts.
  const transformOf = async () =>
    ((await page
      .locator('.react-flow__node[data-id="churned"]')
      .getAttribute('style')) ?? '').match(/transform:[^;]+/)?.[0] ?? ''
  const transformBefore = await transformOf()
  const dragged = page.locator('.cnode[data-node-id="churned"]')
  const beforeBox = (await dragged.boundingBox())!
  await page.mouse.move(beforeBox.x + beforeBox.width / 2, beforeBox.y + 10)
  await page.mouse.down()
  await page.mouse.move(beforeBox.x + beforeBox.width / 2 + 240, beforeBox.y - 120, { steps: 8 })
  await page.mouse.up()
  const transformDragged = await transformOf()
  expect(transformDragged).not.toEqual(transformBefore)
  await expect(page.getByRole('button', { name: /Save changes/ })).toBeEnabled()
  await page.getByRole('button', { name: /Save changes/ }).click()
  await expect(page.getByText(/Saved revision/)).toBeVisible({ timeout: 15_000 })

  await goTo(page, 'Model Lab')
  await goTo(page, 'Causal Lab')
  await expect(page.locator('.cnode')).toHaveCount(3)
  await expect(page.locator('.react-flow__edge')).toHaveCount(2)
  await expect(page.getByText(/revision/)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Saved — no unsaved changes' })).toBeDisabled()
  // The dragged graph-space position came back from the backend's layout.
  expect(await transformOf()).toEqual(transformDragged)

  // --- export the versioned JSON -------------------------------------------- //
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toMatch(/^splitscope-causal-graph-cgraph-/)
})

test('S8B: the backend refuses an invalid structure and the draft survives', async ({
  page,
  allowFailure,
}) => {
  // The cycle save is an intentional 422: visible in the report, not a bug.
  allowFailure(/\/causal-graphs/)

  await loadDemoFromEntry(page, DEMO)
  await goTo(page, 'Causal Lab')

  await page.getByRole('button', { name: 'New graph' }).click()
  await addColumn(page, 'customer_id')
  await page.getByRole('button', { name: 'Add tenure_months' }).click()
  await page.getByRole('button', { name: 'Add churned' }).click()

  // customer_id → tenure_months → churned → customer_id: a directed cycle.
  await page.locator('.cnode[data-node-id="customer_id"]').click()
  await page
    .getByRole('combobox', { name: 'Connect this variable to a target' })
    .selectOption('tenure_months')
  await page.locator('.cnode[data-node-id="tenure_months"]').click()
  await page
    .getByRole('combobox', { name: 'Connect this variable to a target' })
    .selectOption('churned')
  await page.locator('.cnode[data-node-id="churned"]').click()
  await page
    .getByRole('combobox', { name: 'Connect this variable to a target' })
    .selectOption('customer_id')
  await expect(page.locator('.react-flow__edge')).toHaveCount(3)

  const rejected = page.waitForResponse(
    (response) =>
      response.url().includes('/causal-graphs') &&
      response.request().method() === 'POST' &&
      response.status() === 422,
  )
  await page.getByRole('button', { name: /Save changes/ }).click()
  const response = await rejected
  expect(response.status()).toBe(422)

  // The backend verdict is shown, naming the cycle.
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByText(/directed cycle/i).first()).toBeVisible()
  await screenshot(page, 's8_validation_rejected.png')

  // The draft is untouched: three nodes, three edges, save re-enabled.
  await expect(page.locator('.cnode')).toHaveCount(3)
  await expect(page.locator('.react-flow__edge')).toHaveCount(3)
  await expect(page.getByRole('button', { name: /Save changes/ })).toBeEnabled()

  // Fix the cycle by deleting the node that closes it — the inspector's
  // confirmation warns that connected edges go with it.
  await page.keyboard.press('Escape')
  await page.locator('.cnode[data-node-id="customer_id"]').click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
  await page.getByRole('button', { name: 'Delete variable' }).click()
  await page.getByRole('button', { name: 'Confirm delete' }).click()
  await expect(page.locator('.cnode')).toHaveCount(2)
  // Both edges that touched the deleted node cascade away.
  await expect(page.locator('.react-flow__edge')).toHaveCount(1)
  await page.getByRole('button', { name: /Save changes/ }).click()
  await expect(page.getByText(/Saved revision/)).toBeVisible({ timeout: 15_000 })
})

test('S8B: tablet and mobile layouts stay usable', async ({ page }) => {
  await loadDemoFromEntry(page, DEMO)
  await goTo(page, 'Causal Lab')
  await page.getByRole('button', { name: 'Fork example' }).click()
  await expect(page.locator('.cnode')).toHaveCount(3)

  await page.setViewportSize({ width: 768, height: 1024 })
  await page.waitForTimeout(300)
  await screenshot(page, 's8_tablet_768.png')
  // The inspector overlays instead of squeezing the canvas.
  await page.locator('.cnode').first().click()
  await expect(page.getByTestId('node-inspector')).toBeVisible()
  await screenshot(page, 's8_tablet_inspector.png')
  await page.keyboard.press('Escape')

  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(300)
  // No horizontal overflow at phone width.
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(overflow).toBeLessThanOrEqual(1)
  await screenshot(page, 's8_mobile_390.png')
  // The panel toggle keeps the controls reachable: hide, then show again.
  await page.getByRole('button', { name: 'Hide the workspace panel' }).click()
  await expect(page.getByRole('button', { name: 'Add hypothetical variable' })).toBeHidden()
  await page.getByRole('button', { name: 'Show the workspace panel' }).click()
  await expect(page.getByRole('button', { name: 'Add hypothetical variable' })).toBeVisible()
})
