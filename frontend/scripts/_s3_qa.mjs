import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'

const BASE = 'http://127.0.0.1:8300'
const OUT = '../docs/screenshots/s3'
mkdirSync(`${OUT}/_preview`, { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 0.8 })
const problems = []
page.on('console', (message) => {
  if (message.type() === 'error') problems.push(`console: ${message.text()}`)
})
page.on('pageerror', (error) => problems.push(`pageerror: ${error.message}`))

await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
await page.getByRole('button', { name: /Explore Interactive Demo/i }).click()
await page.waitForURL(/#\/dataset/, { timeout: 20000 })
await page.waitForTimeout(800)
console.log('demo loaded')

await page.goto(`${BASE}/#/study`, { waitUntil: 'networkidle' })
await page.waitForSelector('.rs', { timeout: 15000 })
await page.waitForTimeout(600)
const datasetId = await page.getAttribute('.rs', 'data-dataset-id')
console.log('dataset:', datasetId)

await page.getByLabel(/Study title/i).fill('Boundary audit of the repeated-entity demo')
await page
  .getByLabel(/Research question/i)
  .fill('Does the existing split share customer identity across train and test?')
await page.getByLabel(/Study design/i).selectOption('observational')
await page.getByLabel(/Unit of analysis/i).fill('customer')
await page.getByLabel(/Target task/i).selectOption('descriptive')
await page.getByRole('button', { name: /Save study card/i }).click()
await page.waitForTimeout(900)
console.log('study save:', await page.locator('.rs-ok').first().textContent())
await page.screenshot({ path: `${OUT}/_preview/study-card.jpg`, type: 'jpeg', quality: 80, fullPage: true })

await page.getByRole('tab', { name: 'Data dictionary' }).click()
await page.waitForTimeout(700)

const firstRow = page.locator('.rs-table tbody tr').first()
await firstRow.locator('.rs-rowlink').click()
await page.getByLabel(/Future-only variable/i).check()
await page.getByLabel(/^Predictor$/i).check()
await page.getByRole('button', { name: /Save roles and declarations/i }).click()
await page.waitForTimeout(900)
console.log(
  'conflict shown:',
  await page.locator('.rs-inspector .rs-issue--error').first().textContent().catch(() => null),
)

await page.getByLabel(/Future-only variable/i).uncheck()
await page.getByRole('button', { name: /Save roles and declarations/i }).click()
await page.waitForTimeout(900)
console.log(
  'roles saved:',
  await page.locator('.rs-panel .rs-ok').first().textContent().catch(() => null),
)
await page.screenshot({ path: `${OUT}/_preview/study-dictionary.jpg`, type: 'jpeg', quality: 80, fullPage: true })

await page.getByRole('tab', { name: 'Data profile' }).click()
await page.waitForTimeout(700)
await page.screenshot({ path: `${OUT}/_preview/study-profile.jpg`, type: 'jpeg', quality: 80, fullPage: true })

await page.getByRole('tab', { name: 'Provenance' }).click()
await page.waitForTimeout(900)
console.log('fingerprint:', (await page.locator('.rs-dl dd.rs-mono').first().textContent())?.slice(0, 16))
await page.screenshot({ path: `${OUT}/_preview/study-provenance.jpg`, type: 'jpeg', quality: 80, fullPage: true })

// Round trip: take the manifest the UI just displayed, import it back, apply it.
const manifest = await page.evaluate(async (id) => {
  const response = await fetch(`/api/datasets/${id}/manifest`)
  return response.ok ? await response.json() : null
}, datasetId)
writeFileSync(`${OUT}/_preview/manifest.json`, JSON.stringify(manifest))
await page.setInputFiles('.rs-file', `${OUT}/_preview/manifest.json`)
await page.waitForTimeout(1200)
console.log('validation:', await page.locator('.rs-check-result__status').textContent())
await page.getByRole('button', { name: /Apply study metadata/i }).click()
await page.waitForTimeout(1000)
console.log('applied:', await page.locator('.rs-check-result .rs-btn').textContent().catch(() => null))

const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
console.log('study overflow:', overflow)
console.log('problems:', problems.length ? problems : 'none')

await browser.close()
