import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const OUT = '../docs/screenshots/s3/_preview'
mkdirSync(OUT, { recursive: true })

async function settle(page) {
  await page.evaluate(async () => {
    document.documentElement.style.scrollBehavior = 'auto'
    const step = Math.round(window.innerHeight * 0.6)
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y)
      await new Promise((r) => setTimeout(r, 80))
    }
    window.scrollTo(0, 0)
  })
  await page.waitForTimeout(900)
}

const browser = await chromium.launch()
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 0.72,
  colorScheme: 'dark',
})
await page.goto('http://127.0.0.1:8300/', { waitUntil: 'networkidle' })
await page.waitForTimeout(1200)

const pause = page.getByRole('button', { name: /Pause the observatory/i })
if (await pause.count()) await pause.click()

const phases = [
  ['forming', 'Registers'],
  ['scanning', 'Boundary'],
  ['discovery', 'Discovery'],
  ['evidence', 'Evidence'],
]

for (const [id, label] of phases) {
  await page.locator('.lp-console__phase', { hasText: label }).first().click()
  await page.waitForTimeout(1500)
  await page.screenshot({ path: `${OUT}/phase-${id}.jpg`, type: 'jpeg', quality: 82 })
  console.log('captured', id)
}

await page.locator('.lp-console__phase', { hasText: 'Registers' }).first().click()
await page.waitForTimeout(900)
await settle(page)
await page.screenshot({ path: `${OUT}/desktop.jpg`, fullPage: true, type: 'jpeg', quality: 72 })
console.log('captured desktop')

const wide = await browser.newPage({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 0.6,
  colorScheme: 'dark',
})
await wide.goto('http://127.0.0.1:8300/', { waitUntil: 'networkidle' })
await wide.waitForTimeout(1800)
await wide.screenshot({ path: `${OUT}/wide.jpg`, type: 'jpeg', quality: 78 })
const wideOverflow = await wide.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
console.log('wide overflow', wideOverflow)
await wide.close()

for (const [name, width, height] of [
  ['tablet', 768, 1024],
  ['mobile', 390, 844],
]) {
  const p = await browser.newPage({
    viewport: { width, height },
    deviceScaleFactor: 1,
    colorScheme: 'dark',
  })
  await p.goto('http://127.0.0.1:8300/', { waitUntil: 'networkidle' })
  await p.waitForTimeout(1400)
  await settle(p)
  await p.screenshot({ path: `${OUT}/${name}.jpg`, fullPage: true, type: 'jpeg', quality: 68 })
  const overflow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  console.log(name, 'overflow', overflow)
  await p.close()
}

await browser.close()
