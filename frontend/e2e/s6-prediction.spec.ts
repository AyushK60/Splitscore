/**
 * S6-C — predictive Model Lab journeys against the real backend.
 *
 * One classification journey and one regression journey, both on the bundled
 * clean-control dataset with its confirmed split. The exported run is checked
 * against the screen: the confusion counts must sum to the reported test
 * evaluation, candidates must carry validation scores only, and the test
 * partition must be evaluated exactly once.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

import { expect, loadDemoFromEntry, test } from './fixtures'
import type { Page } from '@playwright/test'

test.use({ viewport: { width: 1440, height: 950 } })

const DEMO = 'Clean control dataset'
const EXPORT_DIR = tmpdir()

async function openPredictive(page: Page) {
  await loadDemoFromEntry(page, DEMO)
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('button', { name: 'Model Lab' })
    .click()
  await page.getByRole('tab', { name: 'Predictive ML' }).click()
  await expect(page.getByRole('heading', { name: /Compare candidates/ })).toBeVisible()
}

async function exportRun(page: Page) {
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export run JSON' }).click(),
  ])
  const path = join(EXPORT_DIR, download.suggestedFilename())
  await download.saveAs(path)
  return JSON.parse(readFileSync(path, 'utf-8')) as {
    run_id: string
    kind: string
    task: string
    specification: { test_evaluations: number; selection_rule: string }
    split: { partitions: { fit: number; validation: number; test: number } }
    candidates: Array<Record<string, unknown>>
    selected: { family: string; validation: { metric: string; score: number } }
    evaluation: {
      n: number
      metrics: {
        confusion_matrix: number[][]
        accuracy: number
        roc_auc: number | null
        mae?: number
        rmse?: number
      }
      diagnostics: { roc_curve: { auc: number } | null; sample?: { drawn_rows: number } }
      predictions: { rows: Array<Record<string, unknown>>; test_rows: number; truncated: boolean }
    }
    subgroups: {
      test_rows: number
      grouped_rows: number
      rows: Array<{ n: number; metric: number | null }>
    } | null
  }
}

test('classification journey reports sealed-test metrics and exports the same run', async ({ page }) => {
  await openPredictive(page)

  await page.getByLabel('Prediction task').selectOption('classification')
  await page.getByLabel('Prediction outcome').selectOption('label')
  await page.getByLabel('Positive class').selectOption('1')
  await page.getByLabel('Subgroup column').selectOption('segment')
  await page.getByRole('button', { name: 'Evaluate predictions' }).click()

  const stats = page.locator('.plab__teststats')
  await expect(stats).toContainText('Test accuracy')
  await expect(stats).toContainText('Balanced accuracy')
  await expect(stats).toContainText('ROC-AUC')
  await expect(page.locator('.plab__matrix')).toBeVisible()
  await expect(page.locator('.plab__roc')).toBeVisible()
  await expect(page.getByText('Candidate comparison')).toBeVisible()

  const payload = await exportRun(page)
  expect(payload.kind).toBe('prediction_model')
  expect(payload.task).toBe('classification')
  expect(payload.specification.test_evaluations).toBe(1)
  expect(payload.specification.selection_rule).toContain('validation')
  expect(payload.evaluation.n).toBe(payload.split.partitions.test)
  expect(payload.evaluation.n).toBeGreaterThan(0)

  const counts = payload.evaluation.metrics.confusion_matrix.flat()
  expect(counts.reduce((total, value) => total + value, 0)).toBe(payload.evaluation.n)
  expect(payload.evaluation.metrics.accuracy).toBeGreaterThanOrEqual(0)
  expect(payload.evaluation.metrics.accuracy).toBeLessThanOrEqual(1)
  expect(payload.evaluation.predictions.test_rows).toBe(payload.evaluation.n)
  expect(payload.evaluation.predictions.rows.length).toBe(payload.evaluation.n)
  expect(payload.evaluation.predictions.truncated).toBe(false)
  expect(payload.evaluation.diagnostics.roc_curve?.auc).toBeGreaterThanOrEqual(0)

  for (const candidate of payload.candidates) {
    expect(candidate).not.toHaveProperty('test')
  }

  expect(payload.subgroups).not.toBeNull()
  expect(payload.subgroups?.test_rows).toBe(payload.evaluation.n)
  expect(payload.subgroups?.grouped_rows).toBe(payload.evaluation.n)
  const grouped = (payload.subgroups?.rows ?? []).reduce((total, row) => total + row.n, 0)
  expect(grouped).toBe(payload.evaluation.n)
})

test('regression journey reports MAE, RMSE and R-squared with residual diagnostics', async ({
  page,
}) => {
  await openPredictive(page)

  await page.getByLabel('Prediction task').selectOption('regression')
  await page.getByLabel('Prediction outcome').selectOption('x1')
  await page.getByRole('button', { name: 'Evaluate predictions' }).click()

  const stats = page.locator('.plab__teststats')
  await expect(stats).toContainText('Test MAE')
  await expect(stats).toContainText('Test RMSE')
  await expect(stats).toContainText('Test R²')
  await expect(page.locator('.plab__residuals')).toBeVisible()
  await expect(page.locator('.plab__residuals circle')).toHaveCount(60)

  const payload = await exportRun(page)
  expect(payload.task).toBe('regression')
  expect(payload.kind).toBe('prediction_model')
  expect(payload.evaluation.n).toBe(payload.split.partitions.test)
  expect(payload.evaluation.metrics.mae).toBeGreaterThanOrEqual(0)
  expect(payload.evaluation.metrics.rmse).toBeGreaterThanOrEqual(payload.evaluation.metrics.mae ?? 0)
  expect(payload.evaluation.diagnostics.sample?.drawn_rows).toBe(payload.evaluation.n)
  expect(payload.evaluation.predictions.rows.length).toBe(payload.evaluation.n)
  expect(payload.selected.family).toBeTruthy()
})
