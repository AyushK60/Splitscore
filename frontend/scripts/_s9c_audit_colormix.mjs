// Probe why .estrow__interval computes stroke:none on the live research page.
import { chromium } from '@playwright/test'

const BASE = process.env.SPLITSCOPE_BASE_URL ?? 'http://127.0.0.1:8300'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.goto(`${BASE}/#/overview`)
await page.locator('.we__demo').filter({ hasText: 'Confounded treatment-effect study' }).getByRole('button', { name: 'Open', exact: true }).click()
await page.waitForURL(/#\/dataset/)
await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Effect estimation' }).click()
await page.waitForFunction(() => !document.querySelector('.estsetup__state')?.textContent?.includes('loading'), null, { timeout: 30000 })
const create = page.getByTestId('create-demo-graph')
await create.or(page.getByTestId('readiness-ok')).first().waitFor({ timeout: 60000 })
if (await create.isVisible()) await create.click()
await page.getByTestId('readiness-ok').waitFor({ timeout: 60000 })
await page.getByTestId('run-estimation').click()
await page.getByTestId('effect-summary-table').waitFor({ timeout: 180000 })
await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Causal research' }).click()
const select = page.getByTestId('research-run-select')
await select.waitFor({ timeout: 30000 })
await select.selectOption({ index: 1 })
await page.getByTestId('subgroup-variable').selectOption('region')
await page.getByTestId('subgroup-run').click()
await page.getByTestId('subgroup-forest-chart').waitFor({ timeout: 120000 })

const probe = await page.evaluate(() => {
  const rootStyle = getComputedStyle(document.documentElement)
  const line = document.querySelector('.estrow__interval')
  const lineStyle = line ? getComputedStyle(line) : null
  // Does a plain color-mix work at all in this engine?
  const testEl = document.createElement('div')
  testEl.style.stroke = 'color-mix(in srgb, #0a6d7d 55%, transparent)'
  document.body.appendChild(testEl)
  const plainColorMix = getComputedStyle(testEl).stroke
  testEl.style.stroke = 'color-mix(in srgb, var(--est-teal) 55%, transparent)'
  const varColorMix = getComputedStyle(testEl).stroke
  testEl.style.stroke = 'color-mix(in srgb, var(--est-teal) 55%, white)'
  const varColorMixWhite = getComputedStyle(testEl).stroke
  testEl.remove()
  return {
    estTeal: rootStyle.getPropertyValue('--est-teal'),
    lineStroke: lineStyle?.stroke,
    lineClass: line?.getAttribute('class'),
    plainColorMix,
    varColorMix,
    varColorMixWhite,
    chromiumVersion: navigator.userAgent,
  }
})
console.log(JSON.stringify(probe, null, 2))
await browser.close()
