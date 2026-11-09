/**
 * study journey: Study Card → dictionary conflict → profile → provenance round trip.
 *
 * Runs against the real backend with the committed synthetic demo. Every check is
 * made on rendered output or on the API the UI itself calls; nothing is mocked.
 * The manifest is exported through the API, written to disk and imported back
 * through the file input - the same path a user takes.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { expect, loadDemoFromEntry, test } from './fixtures'

const DEMO_PANEL = 'Repeated-entity subscription panel'
const TMP = join(tmpdir(), 'splitscope-s3-e2e')

test('study card, role conflicts and a manifest round trip', async ({ page }) => {
  mkdirSync(TMP, { recursive: true })

  await loadDemoFromEntry(page, DEMO_PANEL)

  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Study/ }).click()
  await expect(page.getByRole('heading', { name: /repeated_entity\.csv/ })).toBeVisible()

  const datasetId = await page.locator('.rs').getAttribute('data-dataset-id')
  expect(datasetId).toMatch(/^ds-/)

  // --- Study card ---------------------------------------------------------
  await page.getByLabel(/Study title/i).fill('study browser study')
  await page.getByLabel(/Research question/i).fill('Does the split leak customer identity?')
  await page.getByLabel(/Study design/i).selectOption('observational')
  await page.getByLabel(/Unit of analysis/i).fill('customer')
  await page.getByLabel(/Target task/i).selectOption('descriptive')
  await page.getByRole('button', { name: /Save study card/i }).click()
  await expect(page.getByText(/Saved as revision 1/)).toBeVisible()
  await expect(page.getByText('5/5', { exact: false }).first()).toBeVisible()

  // --- Dictionary: a real conflict is refused -----------------------------
  await page.getByRole('tab', { name: 'Data dictionary' }).click()
  await expect(page.locator('.rs-table tbody tr')).toHaveCount(8)

  const numericRow = page
    .locator('.rs-table tbody tr')
    .filter({ hasText: 'tenure_months' })
    .first()
  await numericRow.locator('.rs-rowlink').click()
  await page.getByLabel(/Future-only variable/i).check()
  await page.getByLabel(/^Predictor$/i).check()
  await page.getByRole('button', { name: /Save roles and declarations/i }).click()
  await expect(page.locator('.rs-inspector .rs-issue--error').first()).toContainText(
    /only known after the outcome/i,
  )

  await page.getByLabel(/Future-only variable/i).uncheck()
  await page.getByRole('button', { name: /Save roles and declarations/i }).click()
  await expect(page.locator('.rs-panel .rs-ok').first()).toContainText(/Saved/)

  // --- Profile: computed, not decorative ----------------------------------
  await page.getByRole('tab', { name: 'Data profile' }).click()
  await expect(page.getByText('240', { exact: true }).first()).toBeVisible()
  await expect(page.getByText(/missing/i).first()).toBeVisible()

  // --- Provenance: real fingerprint and a manifest round trip -------------
  await page.getByRole('tab', { name: 'Provenance' }).click()
  const sha = (await page.locator('.rs-dl dd.rs-mono').first().textContent())?.trim() ?? ''
  expect(sha).toMatch(/^[0-9a-f]{64}$/)

  const manifestResponse = await page.request.get(`/api/datasets/${datasetId}/manifest`)
  expect(manifestResponse.ok()).toBeTruthy()
  const manifest = await manifestResponse.json()
  const manifestPath = join(TMP, 'manifest.json')
  writeFileSync(manifestPath, JSON.stringify(manifest))
  expect(manifest.dataset.sha256).toBe(sha)

  await page.setInputFiles('.rs-file', manifestPath)
  await expect(page.locator('.rs-check-result__status')).toHaveText(/Match/i)
  await page.getByRole('button', { name: /Apply study metadata/i }).click()
  await expect(page.getByRole('heading', { name: 'What this study is asking' })).toBeVisible()
  await expect(page.getByLabel(/Study title/i)).toHaveValue('study browser study')

  // --- The original audit still works with the saved roles ----------------
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: /Results|Audit/ }).click()
  const runAudit = page.getByRole('button', { name: /Run audit/ })
  if (await runAudit.isVisible().catch(() => false)) {
    await expect(runAudit).toBeEnabled()
    await runAudit.click()
    await expect(page.getByRole('heading', { name: /Findings|Audit results/i }).first()).toBeVisible()
  }
})
