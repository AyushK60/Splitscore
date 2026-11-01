/**
 * One-off capture: landing + audit results at the three explanation levels,
 * desktop and mobile, against the local backend. Also fails loudly on any
 * console/page error so the capture doubles as a smoke check.
 *
 * Usage (backend running on 8123):  node scripts/capture-screenshots.mjs
 */
import { mkdirSync } from 'node:fs'
import { chromium } from '@playwright/test'

const BASE = process.env.SPLITSCOPE_BASE_URL ?? 'http://127.0.0.1:8123'
const OUT = 'screenshots'
mkdirSync(OUT, { recursive: true })

const errors = []
const browser = await chromium.launch()

async function newPage(width, height) {
  const page = await browser.newPage({ viewport: { width, height } })
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`)
  })
  page.on('pageerror', (error) => errors.push(`pageerror: ${String(error)}`))
  page.on('requestfailed', (request) => errors.push(`requestfailed: ${request.url()}`))
  return page
}

// --- desktop: landing ------------------------------------------------------ //
const desktop = await newPage(1280, 900)
await desktop.goto(BASE)
await desktop.waitForSelector('h1')
await desktop.screenshot({ path: `${OUT}/landing-desktop.png`, fullPage: true })

// --- desktop: demo -> audit -> three explanation levels --------------------- //
await desktop.getByRole('button', { name: 'Try a demo' }).click()
await desktop.waitForURL(/#\/dataset$/)
await desktop.getByRole('button', { name: /Run audit/ }).click()
await desktop.waitForURL(/#\/audit$/)

const findingToggle = desktop.getByRole('button', { name: /^Entity overlap/ })
await findingToggle.click()
await desktop.waitForSelector('[data-level="quick"]')
await desktop.evaluate(() => window.scrollTo(0, 0))
await desktop.locator('.finding').first().scrollIntoViewIfNeeded()
await desktop.screenshot({ path: `${OUT}/results-quick.png` })

await desktop.getByRole('button', { name: 'More context' }).click()
await desktop.waitForSelector('[data-level="context"]')
await desktop.screenshot({ path: `${OUT}/results-context.png` })

await desktop.getByRole('button', { name: 'Technical details' }).click()
await desktop.waitForSelector('[data-level="technical"]')
await desktop.screenshot({ path: `${OUT}/results-technical.png` })

// --- mobile: landing -------------------------------------------------------- //
const mobile = await newPage(390, 844)
await mobile.goto(BASE)
await mobile.waitForSelector('h1')
await mobile.screenshot({ path: `${OUT}/landing-mobile.png`, fullPage: true })

await browser.close()

if (errors.length) {
  console.error('ERRORS DETECTED:')
  for (const error of errors) console.error(' -', error)
  process.exit(1)
}
console.log(`Saved 4 screenshots to ${OUT}/ and no console, page or request errors were seen.`)
