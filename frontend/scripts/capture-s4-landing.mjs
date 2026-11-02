/**
 * S4 Part 1 — landing colour refinement captures.
 *
 * Full-page landing screenshots at the two acceptance viewports (1440x900 and
 * 390x844), before and after the palette adjustment. The scroll pass runs first
 * so IntersectionObserver-revealed sections are visible in full-page captures.
 *
 * Usage: node scripts/capture-s4-landing.mjs before|after
 * Env: SPLITSCOPE_BASE (default http://127.0.0.1:8300)
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const label = process.argv[2] ?? 'before'
const BASE = process.env.SPLITSCOPE_BASE ?? 'http://127.0.0.1:8300'
const OUT = `../docs/screenshots/s4/landing-${label}`
mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()

async function capture(width, height, name) {
  const page = await browser.newPage({ viewport: { width, height }, colorScheme: 'dark' })
  const errors = []
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text())
  })
  page.on('pageerror', (e) => errors.push(e.message))
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  const pause = page.getByRole('button', { name: /Pause the observatory/i })
  if (await pause.count()) await pause.click()
  // Scroll pass so reveal-on-scroll sections render.
  await page.evaluate(async () => {
    document.documentElement.style.scrollBehavior = 'auto'
    const step = Math.round(window.innerHeight * 0.7)
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y)
      await new Promise((r) => setTimeout(r, 90))
    }
    window.scrollTo(0, 0)
  })
  await page.waitForTimeout(700)
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  )
  console.log(`${errors.length ? 'WARN console errors: ' + errors.join(' | ') : ' *'} ${name} captured (h-overflow ${overflow}px)`)
  await page.close()
}

await capture(1440, 900, 'landing-1440')
await capture(390, 844, 'landing-390')
await browser.close()
console.log(`done: ${OUT}`)
