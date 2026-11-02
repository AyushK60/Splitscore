/**
 * Stage 4a happy-path E2E: the real user journey against the real backend.
 *
 * Target: the production build served by `python -m app.main` (see
 * playwright.config.ts). Nothing is mocked — audit, comparison and export all run
 * on the server, and every assertion is made on what the UI renders or on files
 * the browser actually downloaded.
 *
 * Fixture: `datasets/repeated_entity.csv` (committed, synthetic). Row ids are the
 * documented ones — `row-000001` upward in file order — so downloaded assignments
 * can be joined back to the fixture *independently* of anything the server reports.
 */
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import type { Page } from '@playwright/test'

import { expect, test } from './fixtures'

const FIXTURE_PATH = fileURLToPath(new URL('../../datasets/repeated_entity.csv', import.meta.url))
const DEMO_PANEL = 'Repeated-entity subscription panel'
const DEMO_NAME = 'repeated_entity.csv'

// --------------------------------------------------------------------------- //
// Small helpers (CSV parsing and download capture only — no audit logic)
// --------------------------------------------------------------------------- //

function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (quoted) {
      if (char === '"') {
        if (text[index + 1] === '"') {
          cell += '"'
          index += 1
        } else {
          quoted = false
        }
      } else {
        cell += char
      }
    } else if (char === '"') {
      quoted = true
    } else if (char === ',') {
      row.push(cell)
      cell = ''
    } else if (char === '\n') {
      row.push(cell)
      rows.push(row)
      row = []
      cell = ''
    } else if (char !== '\r') {
      cell += char
    }
  }
  if (cell !== '' || row.length > 0) {
    row.push(cell)
    rows.push(row)
  }
  return rows
}

/** Parse the split-assignment export: optional leading `# note` row, then header + rows. */
function parseAssignmentCsv(text: string): { header: string[]; records: Record<string, string>[] } {
  const rows = parseCsv(text).filter((row) => row.some((cell) => cell.trim() !== ''))
  const start = rows.length > 0 && rows[0].length === 1 && rows[0][0].trimStart().startsWith('#') ? 1 : 0
  const header = rows[start]
  const records = rows.slice(start + 1).map((row) => Object.fromEntries(header.map((key, i) => [key, row[i]])))
  return { header, records }
}

async function captureDownload(page: Page, action: () => Promise<void>): Promise<{ text: string; filename: string }> {
  // Register the listener before triggering the click.
  const downloadPromise = page.waitForEvent('download')
  await action()
  const download = await downloadPromise
  const filePath = await download.path()
  expect(filePath, 'the browser must have saved the download').not.toBeNull()
  return { text: readFileSync(filePath as string, 'utf8'), filename: download.suggestedFilename() }
}

/** Independent entity-overlap computation: fixture entities joined to downloaded assignments. */
function sharedEntities(
  assignments: Map<string, string>,
  entityByRowId: Map<string, string>,
): { train: Set<string>; test: Set<string>; shared: Set<string> } {
  const train = new Set<string>()
  const test = new Set<string>()
  for (const [rowId, label] of assignments) {
    const entity = entityByRowId.get(rowId)
    if (entity === undefined || entity.trim() === '') continue // documented missing rule: empty cell
    if (label === 'train') train.add(entity.trim())
    else if (label === 'test') test.add(entity.trim())
  }
  return { train, test, shared: new Set([...train].filter((value) => test.has(value))) }
}

// --------------------------------------------------------------------------- //

test('happy path: load demo, audit, evidence, group comparison, report downloads', async ({
  page,
}) => {
  const fixtureRows = parseCsv(readFileSync(FIXTURE_PATH, 'utf8'))
  const fixtureHeader = fixtureRows[0]
  const fixtureData = fixtureRows.slice(1)
  const entityColumnIndex = fixtureHeader.indexOf('customer_id')
  const splitColumnIndex = fixtureHeader.indexOf('split')
  expect(entityColumnIndex).toBeGreaterThanOrEqual(0)
  expect(splitColumnIndex).toBeGreaterThanOrEqual(0)

  const expectedRowIds = fixtureData.map((_, index) => `row-${String(index + 1).padStart(6, '0')}`)
  const entityByRowId = new Map(expectedRowIds.map((rowId, index) => [rowId, fixtureData[index][entityColumnIndex]]))
  const fixtureSplitByRowId = new Map(expectedRowIds.map((rowId, index) => [rowId, fixtureData[index][splitColumnIndex]]))

  // A stale or missing production build must fail with a clear message, not a timeout.
  const builtIndex = fileURLToPath(new URL('../dist/index.html', import.meta.url))
  expect(
    existsSync(builtIndex),
    'frontend/dist/index.html is missing — npm run test:e2e builds it before starting the backend',
  ).toBe(true)

  // -- 1. Open the app ----------------------------------------------------- //
  await page.goto('/#/overview')
  await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible()
  // The S5 workspace entry: a functional panel, not a second landing page.
  await expect(page.getByRole('heading', { name: /Load a dataset to begin/, level: 1 })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Choose a CSV file' })).toBeVisible()

  // -- 2. Load the repeated-entity demo from the entry panel --------------- //
  await page
    .locator('.we__demo')
    .filter({ hasText: DEMO_PANEL })
    .getByRole('button', { name: 'Open', exact: true })
    .click()

  // -- 3. Dataset readiness and selected roles ----------------------------- //
  await expect(page).toHaveURL(/#\/dataset$/)
  await expect(page.getByText(DEMO_NAME)).toBeVisible()
  const dimensions = page.locator('.dataset-head p.muted')
  await expect(dimensions).toContainText(String(fixtureData.length))
  await expect(page.getByRole('combobox', { name: 'Split column' })).toHaveValue('split')
  // `<input list>` maps to the ARIA combobox role, same as the split/target selects.
  await expect(page.getByRole('combobox', { name: 'Train value' })).toHaveValue('train')
  await expect(page.getByRole('combobox', { name: 'Test value' })).toHaveValue('test')
  await expect(page.getByRole('combobox', { name: 'Target column' })).toHaveValue('churned')
  await expect(page.getByRole('combobox', { name: 'Entity column' })).toHaveValue('customer_id')
  await expect(page.getByRole('group', { name: /Which columns should the checks compare\? \(4 selected\)/ })).toBeVisible()
  await expect(page.getByText('Column assignments do not conflict')).toBeVisible()

  // -- 4. Run the audit ---------------------------------------------------- //
  await page.getByRole('button', { name: /Run audit/ }).click()
  await expect(page).toHaveURL(/#\/audit$/)
  const findingCard = page.getByRole('button', { name: /^Entity overlap between train and test splits/ })
  await expect(findingCard).toBeVisible()
  await expect(page.getByText('SS-ENT-001').first()).toBeVisible()

  // Expand the finding card if it is not already open (condition-based, no sleeps).
  const sharedSentence = page.getByText(/entity value\(s\) are shared between the splits/)
  if ((await findingCard.getAttribute('aria-expanded')) !== 'true') {
    await findingCard.click()
  }
  await expect(findingCard).toHaveAttribute('aria-expanded', 'true')
  await expect(sharedSentence.first()).toBeVisible()

  // The manifest plants entity overlap in the existing split: it must be > 0.
  const auditSummary = await sharedSentence.first().textContent()
  const existingSharedFromAudit = Number(/(\d+) entity value\(s\) are shared/.exec(auditSummary ?? '')?.[1])
  expect(
    Number.isFinite(existingSharedFromAudit) && existingSharedFromAudit > 0,
    'existing split shares entities between train and test',
  ).toBe(true)

  // -- 5. Open the entity-overlap evidence --------------------------------- //
  await page.getByRole('button', { name: /Open in evidence view/ }).click()
  await expect(page).toHaveURL(/#\/evidence$/)
  await expect(
    page.getByRole('heading', { name: 'Entity overlap between train and test splits' }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: /^Evidence examples \(\d+ of / })).toBeVisible()
  await expect(page.getByText(`${existingSharedFromAudit} entity value(s) are shared`).first()).toBeVisible()

  // Fetch the cited rows from the dataset (a real request) and check they are real fixture rows.
  await page.getByRole('button', { name: 'Fetch and highlight cited rows' }).click()
  const evidenceRowIds = await page
    .locator('table th')
    .filter({ hasText: /^row-\d{6}$/ })
    .allTextContents()
  expect(evidenceRowIds.length, 'evidence must cite real dataset rows').toBeGreaterThan(0)
  for (const rowId of evidenceRowIds) {
    expect(expectedRowIds, 'evidence rows must exist in the fixture').toContain(rowId)
  }

  // -- 6. Group-holdout comparison ----------------------------------------- //
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Compare/ }).click()
  await expect(page.getByRole('button', { name: 'Run the comparison' })).toBeEnabled()
  // Keep the comparison focused on existing vs group holdout.
  await page
    .getByRole('row')
    .filter({ hasText: 'Random holdout' })
    .getByRole('button', { name: 'Remove' })
    .click()
  await page.getByRole('button', { name: 'Run the comparison' }).click()

  const resultsTable = page.locator('table').filter({ has: page.getByRole('columnheader', { name: 'Achieved' }) })
  await expect(resultsTable).toBeVisible()
  const groupRow = resultsTable.getByRole('row').filter({ hasText: 'Group holdout' })
  const existingRow = resultsTable.getByRole('row').filter({ hasText: 'Existing split' })
  await expect(groupRow).toBeVisible()
  await expect(existingRow).toBeVisible()
  await expect(groupRow).toContainText('0 groups')
  await expect(groupRow).not.toContainText('SS-ENT-001')
  await expect(existingRow).toContainText('SS-ENT-001')

  const existingSharedFromComparison = Number(/(\d+) groups/.exec(await existingRow.textContent())?.[1])
  expect(existingSharedFromComparison, 'existing split overlap in the comparison').toBeGreaterThan(0)
  expect(existingSharedFromComparison, 'audit and comparison must agree on the same split').toBe(
    existingSharedFromAudit,
  )

  // -- 7. Downloads: JSON report, HTML report, split assignments ------------ //
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Export/ }).click()
  await expect(page.getByRole('button', { name: 'Download JSON report' })).toBeEnabled()

  const jsonReport = await captureDownload(page, () => page.getByRole('button', { name: 'Download JSON report' }).click())
  expect(jsonReport.filename).toMatch(/^splitscope-audit-/)
  const report = JSON.parse(jsonReport.text)
  expect(report.report_kind).toBe('audit')
  expect(typeof report.run_id).toBe('string')
  expect(report.run_id.length).toBeGreaterThan(0)
  expect(report.input.name).toBe(DEMO_NAME)
  expect(report.input.synthetic).toBe(true)
  expect(report.input.row_count).toBe(fixtureData.length)
  expect(report.roles.entity).toBe('customer_id')
  expect(report.roles.split).toBe('split')
  expect(report.settings.audit_config).toBeTruthy()
  expect(report.evaluation.findings_total).toBe(report.findings.length)
  const reportFinding = report.findings.find((finding: { rule_id: string }) => finding.rule_id === 'SS-ENT-001')
  expect(reportFinding, 'manifest fixture: SS-ENT-001 must be in the JSON report').toBeTruthy()
  expect(reportFinding.severity).toBe('high')
  expect(reportFinding.examples.length).toBeGreaterThan(0)

  const htmlReport = await captureDownload(page, () =>
    page.getByRole('button', { name: 'Download self-contained HTML report' }).click(),
  )
  expect(htmlReport.filename).toMatch(/^splitscope-audit-/)
  const html = htmlReport.text
  expect(html.toLowerCase().startsWith('<!doctype html')).toBe(true)
  expect(html.trimEnd().endsWith('</html>')).toBe(true)
  expect(html).toContain(DEMO_NAME)
  expect(html).toContain('SS-ENT-001')
  expect(html).toContain(`${existingSharedFromAudit} entity value(s) are shared`)
  expect(html.toLowerCase(), 'the printable report must not execute scripts').not.toContain('<script')

  const groupCsv = await captureDownload(page, () =>
    page
      .getByRole('row')
      .filter({ hasText: 'Group holdout' })
      .getByRole('button', { name: 'Download CSV' })
      .click(),
  )
  const existingCsv = await captureDownload(page, () =>
    page
      .getByRole('row')
      .filter({ hasText: 'Existing split' })
      .getByRole('button', { name: 'Download CSV' })
      .click(),
  )

  // -- 8. CSV structure, row correspondence, valid labels ------------------ //
  const expectedHeader = [
    'row_id',
    'split',
    'strategy',
    'strategy_kind',
    'achieved_test_fraction',
    'seed',
  ]
  const group = parseAssignmentCsv(groupCsv.text)
  const existing = parseAssignmentCsv(existingCsv.text)
  expect(group.header).toEqual(expectedHeader)
  expect(existing.header).toEqual(expectedHeader)

  for (const [label, records] of [
    ['group', group.records],
    ['existing', existing.records],
  ] as const) {
    expect(records, `${label} assignment row count`).toHaveLength(fixtureData.length)
    const rowIds = records.map((record) => record.row_id)
    expect(new Set(rowIds).size, `${label} row ids must be unique`).toBe(fixtureData.length)
    expect([...rowIds].sort(), `${label} rows must correspond to the fixture rows`).toEqual([...expectedRowIds].sort())
    const labels = new Set(records.map((record) => record.split))
    expect([...labels].every((value) => value === 'train' || value === 'test'), `${label} labels are train/test`).toBe(true)
    expect(labels.has('train') && labels.has('test'), `${label} must have both splits`).toBe(true)
  }
  expect(group.records.every((record) => record.strategy_kind === 'group')).toBe(true)
  expect(existing.records.every((record) => record.strategy_kind === 'existing')).toBe(true)

  // Existing assignment must mirror the fixture's own split column exactly.
  for (const record of existing.records) {
    expect(record.split, `existing assignment for ${record.row_id}`).toBe(fixtureSplitByRowId.get(record.row_id))
  }

  // -- 9. Independent entity separation (fixture data + downloaded CSVs) ---- //
  const groupAssignments = new Map(group.records.map((record) => [record.row_id, record.split]))
  const existingAssignments = new Map(existing.records.map((record) => [record.row_id, record.split]))

  const groupSeparation = sharedEntities(groupAssignments, entityByRowId)
  expect(groupSeparation.train.size, 'group holdout must place entities in train').toBeGreaterThan(0)
  expect(groupSeparation.test.size, 'group holdout must place entities in test').toBeGreaterThan(0)
  expect(
    groupSeparation.shared.size,
    'group holdout must share no non-missing entity between train and test',
  ).toBe(0)

  const existingSeparation = sharedEntities(existingAssignments, entityByRowId)
  expect(existingSeparation.shared.size, 'existing split must share entities').toBeGreaterThan(0)
  expect(
    existingSeparation.shared.size,
    'independent recomputation must match what the UI reported',
  ).toBe(existingSharedFromAudit)
})
