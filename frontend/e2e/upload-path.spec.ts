/**
 * Upload-path E2E: a real CSV upload through the guided setup, both entry paths.
 *
 * Nothing is mocked and no request is intercepted: the files below are uploaded
 * to the real backend, the roles are confirmed through the UI, the audit runs on
 * the server, and the downloaded assignment CSV is read back from disk. The two
 * fixtures are generated in the test so the expectations (row counts, mapped
 * labels, shared entities) can be recomputed here rather than trusted from a
 * stored file.
 */
import { readFileSync } from 'node:fs'

import type { Page } from '@playwright/test'

import { expect, test } from './fixtures'

// --------------------------------------------------------------------------- //
// Fixtures (generated, tiny, synthetic — never anyone's real data)
// --------------------------------------------------------------------------- //

/**
 * 60 rows over 30 customers (2 rows each) with the file's own `split` column.
 * Customers C-1..C-5 have one row on each side, so the entity-overlap check has
 * something real to find; the rest of the customers sit on one side only.
 */
function existingSplitCsv(): string {
  const rows = ['customer_id,signal,score,churn,split']
  let index = 0
  for (let entity = 1; entity <= 30; entity += 1) {
    const labels =
      entity <= 5 ? ['train', 'test'] : entity <= 17 ? ['train', 'train'] : ['test', 'test']
    for (const label of labels) {
      index += 1
      rows.push(
        [`C-${entity}`, index % 7, (index * 3) % 11, index % 2 ? 'yes' : 'no', label].join(','),
      )
    }
  }
  return rows.join('\n')
}

/** 60 rows of wine-like measurements: a target, no split, no entity, no time. */
function noSplitCsv(): string {
  const rows = ['fixed_acidity,volatile_acidity,citric_acid,residual_sugar,sulphates,alcohol,quality']
  for (let index = 0; index < 60; index += 1) {
    rows.push(
      [
        (3 + (index % 5) * 0.4).toFixed(1),
        (0.2 + (index % 4) * 0.1).toFixed(2),
        (0.1 + (index % 3) * 0.15).toFixed(2),
        (1.2 + (index % 6) * 0.3).toFixed(1),
        (0.4 + (index % 5) * 0.08).toFixed(2),
        (9 + (index % 7) * 0.5).toFixed(1),
        String(4 + (index % 5)),
      ].join(','),
    )
  }
  return rows.join('\n')
}

// --------------------------------------------------------------------------- //
// Helpers (upload and download only — no audit logic)
// --------------------------------------------------------------------------- //

async function uploadCsv(page: Page, name: string, csv: string): Promise<void> {
  await page.goto('/#/overview')
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('button', { name: /Data/ })
    .click()
  await expect(page.getByText('No dataset is loaded')).toBeVisible()
  await page
    .locator('input[type="file"]')
    .setInputFiles({ name, mimeType: 'text/csv', buffer: Buffer.from(csv) })
  await expect(page.getByRole('heading', { level: 1, name: new RegExp(name) })).toBeVisible()
}

async function captureDownload(page: Page, action: () => Promise<void>): Promise<{ text: string; filename: string }> {
  const downloadPromise = page.waitForEvent('download')
  await action()
  const download = await downloadPromise
  const filePath = await download.path()
  expect(filePath, 'the browser must have saved the download').not.toBeNull()
  return { text: readFileSync(filePath as string, 'utf8'), filename: download.suggestedFilename() }
}

// --------------------------------------------------------------------------- //
// Tests
// --------------------------------------------------------------------------- //

test('upload with its own split column: map the labels, confirm, audit, evidence, compare', async ({
  page,
}) => {
  await uploadCsv(page, 'customers_split.csv', existingSplitCsv())

  // -- 1. The entry question comes first; the run gate names what is missing -- //
  await expect(
    page.getByRole('heading', {
      name: /^Step 1 — Does your file already say which rows are training and testing\?/,
    }),
  ).toBeVisible()
  await expect(
    page.getByRole('button', { name: /Run audit/ }),
    'no run before the entry question is answered',
  ).toBeDisabled()
  await expect(page.getByText(/does the file already say which rows are training and testing/)).toBeVisible()

  await page.getByRole('button', { name: 'Yes — check my existing split.' }).click()

  // -- 2. The file's split column, its observed values and the label mapping -- //
  await expect(page.getByRole('combobox', { name: 'Split column' })).toHaveValue('split')
  await expect(page.getByLabel('Train value')).toHaveValue('train')
  await expect(page.getByLabel('Test value')).toHaveValue('test')
  await expect(page.getByText('Values observed in split')).toBeVisible()
  await expect(page.getByText(/29 train \+ 31 test rows/)).toBeVisible()

  // -- 3. Name-based suggestions must be confirmed before anything runs ------ //
  await expect(page.getByRole('button', { name: /Run audit/ })).toBeDisabled()

  // An incomplete mapping can never be run, even after the roles are confirmed.
  // (A successful column validation is not workflow readiness.)
  await page.getByLabel('Test value').selectOption('__none__')
  await page.getByRole('button', { name: 'Confirm these column roles' }).click()
  await expect(page.getByText(/Map the values of split to train and test/)).toBeVisible()
  await expect(
    page.getByRole('button', { name: /Run audit/ }),
    'an unmapped split must not enable the audit',
  ).toBeDisabled()

  // Recovering is just mapping the second label — no reload, no reset.
  await page.getByLabel('Test value').selectOption('test')
  await expect(page.getByRole('button', { name: /Run audit/ })).toBeEnabled()
  await page.getByRole('button', { name: /Run audit/ }).click()

  // -- 4. The audit finds the planted entity overlap ------------------------- //
  await expect(page).toHaveURL(/#\/audit$/)
  const finding = page.locator('article.finding').filter({ hasText: 'SS-ENT-001' })
  await expect(finding).toBeVisible()
  const toggle = finding.locator('button.finding__toggle')
  if ((await toggle.getAttribute('aria-expanded')) !== 'true') {
    await toggle.click()
  }
  await expect(toggle).toHaveAttribute('aria-expanded', 'true')

  // -- 5. Every explanation level renders, exactly one at a time ------------ //
  await finding.getByRole('button', { name: 'Technical details' }).click()
  await expect(finding.locator('.explain[data-level="technical"]')).toBeVisible()
  await expect(finding.locator('.explain[data-level="quick"]')).toHaveCount(0)
  await finding.getByRole('button', { name: 'More context' }).click()
  await expect(finding.locator('.explain[data-level="context"]')).toBeVisible()
  await finding.getByRole('button', { name: 'Quick explanation' }).click()
  await expect(finding.locator('.explain[data-level="quick"]')).toBeVisible()

  // -- 6. The evidence view cites real uploaded rows ------------------------- //
  await finding.getByRole('button', { name: /Open in evidence view/ }).click()
  await expect(page).toHaveURL(/#\/evidence$/)
  await page.getByRole('button', { name: 'Fetch and highlight cited rows' }).click()
  const cited = await page.locator('table th').filter({ hasText: /^row-\d{6}$/ }).allTextContents()
  expect(cited.length, 'the uploaded audit must cite real rows').toBeGreaterThan(0)

  // -- 7. The comparison keeps the file's split as a candidate --------------- //
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Compare/ }).click()
  await expect(page.getByRole('button', { name: 'Run the comparison' })).toBeEnabled()
  await page.getByRole('button', { name: 'Run the comparison' }).click()
  const resultsTable = page
    .locator('table')
    .filter({ has: page.getByRole('columnheader', { name: 'Achieved' }) })
  await expect(resultsTable.getByRole('row').filter({ hasText: 'Existing split' })).toBeVisible()

  // -- 8. Export: the report exists; an existing split has no assignment ----- //
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Export/ }).click()
  await expect(page.getByRole('button', { name: 'Download JSON report' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Download split assignment CSV' })).toHaveCount(0)
})

test('upload without a split column: create a split, audit it, download its assignment', async ({
  page,
}) => {
  await uploadCsv(page, 'wine_like.csv', noSplitCsv())

  // -- 1. Entry question → create a split ------------------------------------ //
  await expect(page.getByRole('heading', { name: /^Step 1 — Does your file already say/ })).toBeVisible()
  await page.getByRole('button', { name: 'No — help me create a split.' }).click()

  // -- 2. Strategy eligibility is spelled out, not silently dropped ---------- //
  await expect(page.getByRole('heading', { name: /^Step 2 — Choose how to split the rows/ })).toBeVisible()
  await expect(page.getByRole('radio', { name: /Random holdout/ })).toBeEnabled()
  await expect(page.getByRole('radio', { name: /Stratified holdout/ })).toBeEnabled()
  await expect(page.getByRole('radio', { name: /Group holdout/ })).toBeDisabled()
  await expect(page.getByText('Unavailable — this strategy needs the entity column')).toBeVisible()
  await expect(page.getByRole('radio', { name: /Chronological holdout/ })).toBeDisabled()
  await expect(page.getByText('Unavailable — this strategy needs the timestamp column')).toBeVisible()

  // -- 3. A stratified holdout with a recorded seed --------------------------- //
  await page.getByRole('radio', { name: /Stratified holdout/ }).click()
  await page.getByLabel('Test share of rows').selectOption('30')
  await page.getByRole('spinbutton', { name: 'Seed' }).fill('4242')

  // -- 4. Confirm the guessed roles, then run --------------------------------- //
  await page.getByRole('button', { name: 'Confirm these column roles' }).click()
  await expect(page.getByRole('button', { name: /Run audit/ })).toBeEnabled()
  await page.getByRole('button', { name: /Run audit/ }).click()

  // -- 5. The result records the strategy, the seed and the split it used ----- //
  await expect(page).toHaveURL(/#\/audit$/)
  const summaryKv = page.locator('.kv').filter({ hasText: 'Split audited' })
  await expect(summaryKv).toContainText('Stratified holdout')
  await expect(summaryKv.locator('dd.mono', { hasText: /^4242$/ })).toBeVisible()
  await expect(summaryKv, 'a generated split comes from no data column').toContainText(
    '—',
  )

  // -- 6. The comparison cannot offer the file's own split, and says why ------ //
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Compare/ }).click()
  await expect(page.getByText(/Not available: no split column is selected/)).toBeVisible()
  await page.getByRole('button', { name: 'Run the comparison' }).click()
  const resultsTable = page
    .locator('table')
    .filter({ has: page.getByRole('columnheader', { name: 'Achieved' }) })
  await expect(resultsTable.getByRole('row').filter({ hasText: 'Random holdout' })).toBeVisible()
  await expect(resultsTable.getByRole('row').filter({ hasText: 'Existing split' })).toHaveCount(0)

  // -- 7. The audited split is downloadable, keyed by internal row id -------- //
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Export/ }).click()
  const assignment = await captureDownload(page, () =>
    page.getByRole('button', { name: 'Download split assignment CSV' }).click(),
  )
  const lines = assignment.text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line !== '')
  // The export leads with one quoted `# note` line (spreadsheet-formula
  // sanitization); skip it the same way the report parser does.
  const noteLines = lines[0].includes('# Text cells') ? 1 : 0
  const header = lines[noteLines]
  expect(header).toContain('row_id')
  expect(header).toContain('split')
  expect(header).toContain('seed')
  const records = lines.slice(noteLines + 1)
  expect(records, 'every uploaded row is assigned').toHaveLength(60)
  expect(records.every((line) => line.includes('stratified'))).toBe(true)
  expect(records.every((line) => line.includes('4242'))).toBe(true)
})
