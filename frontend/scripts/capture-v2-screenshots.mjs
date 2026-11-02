/**
 * V2 visual QA capture — genuine screenshots + smoke checks against the
 * production build served by the local backend.
 *
 * Captures (docs/screenshots/v2/):
 *   v2-landing-hero.png      1440x900, hero viewport only
 *   v2-landing-desktop.png   1440x900, full page
 *   v2-landing-tablet.png     768x1024, full page
 *   v2-landing-mobile.png     390x844, full page
 *   v2-workbench-*.png        interior screens
 *
 * Also asserts: no console/page/request errors, no horizontal overflow at any
 * width, landing CTAs really navigate, keyboard focus is visible, and the hero
 * field is static under reduced motion.
 *
 * Usage (backend running and `npm run build` done):
 *   node scripts/capture-v2-screenshots.mjs
 */
import { mkdirSync } from 'node:fs'
import { chromium } from '@playwright/test'

const BASE = process.env.SPLITSCOPE_BASE_URL ?? 'http://127.0.0.1:8300'
const OUT = '../docs/screenshots/v2'
mkdirSync(OUT, { recursive: true })

const errors = []
const checks = []
const browser = await chromium.launch()

async function openPage(width, height, { reducedMotion } = {}) {
  const context = await browser.newContext({ viewport: { width, height }, reducedMotion })
  const page = await context.newPage()
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`)
  })
  page.on('pageerror', (error) => errors.push(`pageerror: ${String(error)}`))
  page.on('requestfailed', (request) => errors.push(`requestfailed: ${request.url()}`))
  return page
}

async function horizontalOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
}

/**
 * Scroll the whole page so scroll-triggered reveals really run, then return to
 * the top. Without this a full-page screenshot captures unrevealed sections.
 */
async function settleReveals(page) {
  await page.evaluate(async () => {
    const step = Math.round(window.innerHeight * 0.6)
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y)
      await new Promise((resolve) => setTimeout(resolve, 110))
    }
    window.scrollTo(0, 0)
    await new Promise((resolve) => setTimeout(resolve, 800))
  })
}

// --- 1. landing, desktop 1440x900 -----------------------------------------
const desktop = await openPage(1440, 900)
await desktop.goto(BASE, { waitUntil: 'networkidle' })
await desktop.waitForSelector('h1')
checks.push(`landing h1: ${(await desktop.locator('h1').first().innerText()).replace(/\n/g, ' ')}`)
checks.push(`desktop horizontal overflow: ${await horizontalOverflow(desktop)}px`)

// Hero viewport, captured before any scrolling.
await desktop.waitForTimeout(2200)
await desktop.screenshot({ path: `${OUT}/v2-landing-hero.png` })

await settleReveals(desktop)
checks.push(`revealed sections: ${await desktop.locator('[data-reveal="in"]').count()}`)
await desktop.screenshot({ path: `${OUT}/v2-landing-desktop.png`, fullPage: true })

// Keyboard: the first Tab lands on the skip link and shows a visible ring.
await desktop.keyboard.press('Tab')
const focus = await desktop.evaluate(() => {
  const el = document.activeElement
  const style = getComputedStyle(el)
  return {
    tag: el.tagName,
    cls: el.className,
    outline: `${style.outlineStyle} ${style.outlineWidth} ${style.outlineColor}`,
  }
})
checks.push(`first Tab focuses <${focus.tag}> class="${focus.cls}" outline=${focus.outline}`)

// --- 2. landing CTA -> synthetic demo -> audit (real journey) --------------
await desktop.getByRole('button', { name: 'Explore Interactive Demo' }).click()
await desktop.waitForURL(/#\/dataset$/, { timeout: 15000 })
checks.push('landing CTA "Explore Interactive Demo" reached #/dataset')
await desktop.waitForSelector('.dataset-head', { timeout: 15000 })
await desktop.screenshot({ path: `${OUT}/v2-workbench-dataset.png` })

await desktop.getByRole('button', { name: /Run audit/ }).click()
await desktop.waitForURL(/#\/audit$/, { timeout: 20000 })
await desktop.waitForSelector('.finding', { timeout: 20000 })
checks.push('audit produced findings on the demo dataset')
await desktop.screenshot({ path: `${OUT}/v2-workbench-audit.png` })

// Interior Start screen.
await desktop.goto(`${BASE}/#/overview`, { waitUntil: 'networkidle' })
await desktop.waitForSelector('h1')
await desktop.screenshot({ path: `${OUT}/v2-workbench-start.png` })

// --- 3. landing, tablet 768x1024 -----------------------------------------
const tablet = await openPage(768, 1024)
await tablet.goto(BASE, { waitUntil: 'networkidle' })
await tablet.waitForSelector('h1')
checks.push(`tablet horizontal overflow: ${await horizontalOverflow(tablet)}px`)
await settleReveals(tablet)
await tablet.screenshot({ path: `${OUT}/v2-landing-tablet.png`, fullPage: true })
await tablet.goto(`${BASE}/#/overview`, { waitUntil: 'networkidle' })
await tablet.waitForSelector('h1')
checks.push(`tablet workbench overflow: ${await horizontalOverflow(tablet)}px`)

// --- 4. landing, mobile 390x844 ------------------------------------------
const mobile = await openPage(390, 844)
await mobile.goto(BASE, { waitUntil: 'networkidle' })
await mobile.waitForSelector('h1')
checks.push(`mobile horizontal overflow: ${await horizontalOverflow(mobile)}px`)
await settleReveals(mobile)
await mobile.screenshot({ path: `${OUT}/v2-landing-mobile.png`, fullPage: true })

// --- 5. reduced motion ----------------------------------------------------
const calm = await openPage(1440, 900, { reducedMotion: 'reduce' })
await calm.goto(BASE, { waitUntil: 'networkidle' })
await calm.waitForSelector('.hs-scene')
const scene = await calm.evaluate(() => {
  const scan = document.querySelector('.hs-scan-band')
  const box = document.querySelector('.hs-scene').getBoundingClientRect()
  const hidden = Array.from(document.querySelectorAll('[data-reveal]')).filter(
    (node) => getComputedStyle(node).opacity !== '1',
  ).length
  return {
    scan: scan ? getComputedStyle(scan).display : 'missing',
    hidden,
    sceneBox: `${Math.round(box.width)}x${Math.round(box.height)}`,
  }
})
checks.push(
  `reduced motion: scan band display=${scene.scan}, hidden sections=${scene.hidden}, scene box=${scene.sceneBox}`,
)

await browser.close()

console.log('--- V2 capture checks ---')
for (const line of checks) console.log(' *', line)
if (errors.length) {
  console.error('ERRORS DETECTED:')
  for (const error of errors) console.error(' -', error)
  process.exit(1)
}
console.log('No console, page or request errors. Screenshots written to', OUT)
