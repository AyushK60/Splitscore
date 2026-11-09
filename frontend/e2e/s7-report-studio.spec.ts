/**
 * dossier - Report / Export Studio and visual-polish journey.
 *
 * This is the contract test for the decision layer: the studio must compose the
 * runs that actually exist, the downloaded JSON and print HTML must match the
 * preview, section toggles must change the artifact rather than only the screen,
 * and the scatter/matrix marks must remain legible and honest under selection.
 *
 * Screenshots are captured at the viewport sizes named in the dossier brief so the
 * visual review is reproducible instead of relying on a stale image folder.
 */
import { mkdirSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import type { Page } from '@playwright/test'

import { expect, loadDemoFromEntry, test } from './fixtures'

const DEMO = 'Repeated-entity subscription panel'
const DATASET_NAME = 'repeated_entity.csv'
const SHOTS = fileURLToPath(new URL('../test-results/shots/s7', import.meta.url))
const TMP = join(tmpdir(), 'splitscope-s7-e2e')

test.use({ viewport: { width: 1920, height: 1080 } })
test.setTimeout(180_000)

test.beforeAll(() => {
  mkdirSync(SHOTS, { recursive: true })
  mkdirSync(TMP, { recursive: true })
})

async function screenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: join(SHOTS, name), animations: 'disabled' })
}

async function scrollTo(page: Page, top: number): Promise<void> {
  // The workspace enables CSS smooth scrolling for reading links, so a plain
  // `scrollTop` assignment would still be mid-animation when captured.
  await page.evaluate((nextTop) => {
    window.scrollTo({ top: nextTop, left: 0, behavior: 'instant' })
  }, top)
  await page.waitForTimeout(120)
}

async function goTo(page: Page, name: string): Promise<void> {
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name }).click()
}

test('dossier: audit, compare, fit, inspect marks and export one evidence dossier', async ({ page }) => {
  await loadDemoFromEntry(page, DEMO)

  // --- compact chrome: brand and primary nav share one sticky row ---------- //
  const primary = page.locator('.app-topbar__primary')
  const brand = page.locator('.app-header__brand')
  const navButton = page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('button', { name: /Audit results/ })
  const primaryBox = await primary.boundingBox()
  const brandBox = await brand.boundingBox()
  const navBox = await navButton.boundingBox()
  expect(primaryBox).not.toBeNull()
  expect(brandBox).not.toBeNull()
  expect(navBox).not.toBeNull()
  expect(primaryBox!.height).toBeLessThanOrEqual(62)
  expect(Math.abs(brandBox!.y + brandBox!.height / 2 - (navBox!.y + navBox!.height / 2))).toBeLessThan(10)

  // The context band is deliberately not sticky: orientation scrolls away.
  await page.evaluate(() => window.scrollTo({ top: 500, behavior: 'instant' }))
  await page.waitForTimeout(80)
  const topbarTop = (await page.locator('.app-topbar').boundingBox())!.y
  const contextTop = (await page.locator('.app-context').boundingBox())!.y
  expect(topbarTop).toBeLessThanOrEqual(1)
  expect(contextTop).toBeLessThan(-100)
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))

  // --- audit --------------------------------------------------------------- //
  await page.getByRole('button', { name: /Run audit/ }).click()
  await expect(page).toHaveURL(/#\/audit$/)
  await expect(page.getByText('SS-ENT-001').first()).toBeVisible()
  await scrollTo(page, 0)
  await screenshot(page, 's7-chrome-1920.png')

  // --- comparison ---------------------------------------------------------- //
  await goTo(page, 'Compare')
  await page.getByRole('button', { name: 'Run the comparison' }).click()
  const resultsTable = page.locator('table').filter({ has: page.getByRole('columnheader', { name: 'Achieved' }) })
  await expect(resultsTable).toBeVisible()

  // --- one statistical model run ------------------------------------------ //
  await goTo(page, 'Model Lab')
  await expect(page.locator('.mlab__grid')).toBeVisible()
  await page.getByLabel('Task').selectOption('ols')
  await page.getByLabel('Outcome').selectOption('tenure_months')
  await page.getByRole('button', { name: 'Fit model' }).click()
  await expect(page.locator('.mlab__meta')).toContainText(/run-[a-f0-9]+/)
  await expect(page.locator('.mlab__stats')).toContainText('R²')
  const modelRunId = ((await page.locator('.mlab__meta').textContent()) ?? '').match(/run-[a-f0-9]+/)?.[0] ?? ''
  expect(modelRunId).toMatch(/^run-/)
  await screenshot(page, 's7-model-lab-1920.png')

  // --- scatter: discrete stack, visible marks, disclosed jitter ------------ //
  await goTo(page, 'Explore')
  await page.getByRole('button', { name: 'Scatter', exact: true }).click()
  const scatter = page.locator('[data-figure="scatter"]')
  await expect(scatter.locator('svg[role="img"]')).toBeVisible()
  const axisSelects = scatter.locator('.xfig__controls .xfig__control select')
  await axisSelects.nth(0).selectOption('month_index')
  await axisSelects.nth(1).selectOption('tenure_months')
  await expect(scatter.locator('.xfig__sub')).toContainText('discrete month_index')
  await expect(scatter.locator('.xfig__sub')).toContainText('marks offset ≤4px')
  const markOpacity = await scatter.evaluate((element) => {
    const marks = Array.from(element.querySelectorAll('svg path'))
      .map((path) => Number(path.getAttribute('opacity')))
      .filter((value) => Number.isFinite(value) && value > 0)
    return Math.max(...marks)
  })
  expect(markOpacity).toBeGreaterThanOrEqual(0.8)
  await scrollTo(page, 0)
  await screenshot(page, 's7-scatter-1920.png')

  // --- matrix: grouped colour, per-panel r, readable panels ---------------- //
  await page.getByRole('button', { name: 'Scatter matrix', exact: true }).click()
  const matrix = page.locator('[data-figure="scatter-matrix"]')
  await expect(matrix.locator('.xmatrix__panel')).toHaveCount(6)
  await expect(matrix.locator('.xmatrix__panel').first()).toHaveAttribute('aria-label', /r [+−]?\d\.\d{2}/)
  await expect(matrix.locator('.xfig__note')).toContainText('not a finding or a causal claim')
  const groupStrokes = await matrix.locator('.xmatrix__panel').first().evaluate((panel) => {
    const strokes = Array.from(panel.querySelectorAll('svg path'))
      .map((path) => path.getAttribute('stroke'))
      .filter((stroke): stroke is string => Boolean(stroke) && stroke !== 'var(--rs-surface)')
    return [...new Set(strokes)]
  })
  expect(groupStrokes.length).toBeGreaterThan(1)
  await scrollTo(page, 0)
  await screenshot(page, 's7-matrix-1920.png')

  // --- studio: real sources, sections and auto-generated preview ---------- //
  await goTo(page, 'Export')
  await expect(page.locator('.report-paper')).toBeVisible()
  await expect(page.locator('.report-cover h1')).toHaveText(DATASET_NAME)
  await expect(page.locator('.report-cover')).toContainText('Evidence dossier')
  await expect(page.locator('#report-summary')).toBeVisible()
  await expect(page.locator('#report-models .report-model')).toHaveCount(1)
  await expect(page.locator('#report-models')).toContainText(modelRunId)
  await expect(page.locator('#report-comparison')).toContainText('Group holdout')
  await expect(page.locator('#report-audit')).toContainText('SS-ENT-001')
  await expect(page.locator('.report-toc a')).toHaveCount(17) // dossier: the default dossier now requests all 17 sections
  await expect(page.locator('.report-studio__identity')).toContainText(DATASET_NAME)
  await expect(page.locator('.report-config__actions')).toBeVisible()
  await scrollTo(page, 0)
  await screenshot(page, 's7-report-1920.png')

  // A TOC jump moves the page, not just the scroll container inside the paper.
  const yBefore = await page.evaluate(() => window.scrollY)
  await page.locator('.report-toc a').filter({ hasText: 'Findings and evidence' }).click()
  // The workspace honours prefers-reduced-motion with CSS smooth scrolling,
  // so let the in-page jump settle instead of sampling mid-animation.
  await expect
    .poll(() => page.evaluate(() => window.scrollY), { timeout: 5000 })
    .toBeGreaterThan(yBefore + 200)
  await page.waitForFunction(() => {
    const section = document.getElementById('report-findings')
    if (!section) return false
    const top = section.getBoundingClientRect().top
    return Math.abs(top - 76) < 4
  })
  const findingsTop = (await page.locator('#report-findings').boundingBox())!.y
  expect(findingsTop).toBeGreaterThanOrEqual(60)
  expect(findingsTop).toBeLessThan(120)

  // --- section include/exclude changes the preview ------------------------ //
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  const comparisonToggle = page
    .locator('.report-section-toggle')
    .filter({ hasText: 'Split comparison' })
    .locator('input')
  await comparisonToggle.uncheck()
  await page.getByRole('button', { name: 'Update preview' }).click()
  await expect(page.locator('#report-comparison')).toHaveCount(0)
  await expect(page.locator('.report-toc a')).toHaveCount(16)
  await comparisonToggle.check()
  await page.getByRole('button', { name: 'Update preview' }).click()
  await expect(page.locator('#report-comparison')).toHaveCount(1)

  // --- downloads: the same payload and a script-free print artifact ------- //
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
    included_sections: string[]
    dataset: { name: string; sha256: string }
    summary: { findings_total: number; evaluated_rule_count: number; not_evaluated_count: number }
    sections: Record<string, { available: boolean; data: unknown }>
    integrity: { raw_data_embedded: boolean; row_predictions_embedded: boolean }
  }
  expect(dossier.report_kind).toBe('dossier')
  expect(dossier.schema_version).toBe('1.1.0') // dossier: additive section schema
  expect(dossier.dataset.name).toBe(DATASET_NAME)
  expect(dossier.dataset.sha256).toHaveLength(64)
  expect(dossier.included_sections).toHaveLength(17) // dossier: default requests all sections
  expect(dossier.summary.findings_total).toBeGreaterThan(0)
  expect(dossier.summary.evaluated_rule_count).toBeGreaterThan(0)
  expect(dossier.summary.not_evaluated_count).toBeGreaterThan(0)
  expect(dossier.integrity.raw_data_embedded).toBe(false)
  expect(dossier.integrity.row_predictions_embedded).toBe(false)
  const models = dossier.sections.models.data as { runs: Array<{ run_id: string; kind: string }> }
  expect(models.runs.map((run) => run.run_id)).toContain(modelRunId)
  expect(models.runs.find((run) => run.run_id === modelRunId)?.kind).toBe('statistical_model')

  const [htmlDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download self-contained HTML', exact: true }).click(),
  ])
  expect(htmlDownload.suggestedFilename()).toMatch(/^splitscope-dossier-.*\.html$/)
  const htmlPath = join(TMP, htmlDownload.suggestedFilename())
  await htmlDownload.saveAs(htmlPath)
  const html = readFileSync(htmlPath, 'utf-8')
  expect(html.trimStart().toLowerCase().startsWith('<!doctype html')).toBe(true)
  expect(html.trimEnd().endsWith('</html>')).toBe(true)
  expect(html.toLowerCase()).not.toContain('<script')
  expect(html).toContain('@media print')
  expect(html).toContain(DATASET_NAME)
  expect(html).toContain(modelRunId)
  expect(html).toContain('SS-ENT-001')
  expect(html).toContain('Dataset and provenance')

  // Open the generated file itself, not a re-render of the app.
  const generated = await page.context().newPage()
  await generated.setViewportSize({ width: 1440, height: 1000 })
  await generated.goto(pathToFileURL(htmlPath).href)
  await expect(generated.locator('body')).toContainText(DATASET_NAME)
  await expect(generated.locator('body')).toContainText('SS-ENT-001')
  await expect(generated.locator('h1').first()).toContainText(DATASET_NAME)
  await generated.screenshot({ path: join(SHOTS, 's7-generated-dossier-1440.png'), animations: 'disabled' })
  await generated.close()

  // --- print stylesheet: chrome and controls disappear, paper remains ----- //
  await page.emulateMedia({ media: 'print' })
  await expect(page.locator('.app-topbar')).toBeHidden()
  await expect(page.locator('.report-config')).toBeHidden()
  await expect(page.locator('.report-paper')).toBeVisible()
  await scrollTo(page, 0)
  await screenshot(page, 's7-print-1440.png')
  await page.emulateMedia({ media: 'screen' })

  // --- responsive review --------------------------------------------------- //
  await page.setViewportSize({ width: 1366, height: 900 })
  await scrollTo(page, 0)
  await screenshot(page, 's7-report-1366.png')

  await page.setViewportSize({ width: 834, height: 1112 })
  const tabletGrid = await page.evaluate(() => {
    const grid = document.querySelector('.report-studio__grid')
    return grid ? grid.getBoundingClientRect().top + window.scrollY : 0
  })
  await scrollTo(page, Math.max(0, tabletGrid - 68))
  await screenshot(page, 's7-report-tablet-834.png')
  const tabletPaper = await page.evaluate(() => {
    const paper = document.querySelector('.report-paper')
    return paper ? paper.getBoundingClientRect().top + window.scrollY : 0
  })
  await scrollTo(page, Math.max(0, tabletPaper - 68))
  await screenshot(page, 's7-report-paper-tablet-834.png')
  const tabletOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(tabletOverflow).toBeLessThanOrEqual(1)

  await page.setViewportSize({ width: 390, height: 844 })
  const mobileGrid = await page.evaluate(() => {
    const grid = document.querySelector('.report-studio__grid')
    return grid ? grid.getBoundingClientRect().top + window.scrollY : 0
  })
  await scrollTo(page, Math.max(0, mobileGrid - 58))
  await screenshot(page, 's7-report-mobile-390.png')
  const mobilePaper = await page.evaluate(() => {
    const paper = document.querySelector('.report-paper')
    return paper ? paper.getBoundingClientRect().top + window.scrollY : 0
  })
  await scrollTo(page, Math.max(0, mobilePaper - 58))
  await screenshot(page, 's7-report-paper-mobile-390.png')
  const mobileOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  expect(mobileOverflow).toBeLessThanOrEqual(1)

  // Both archive downloads from the pre-dossier export view are still present.
  await expect(page.getByRole('button', { name: 'Download JSON report' })).toHaveCount(1)
  await expect(page.getByRole('button', { name: 'Download self-contained HTML report' })).toHaveCount(1)
})
