// S9C visual audit probe: drive the real subgroup journey and inspect the
// forest-plot interval lines in the live DOM (bounding boxes + computed CSS).
import { chromium } from '@playwright/test'

const BASE = process.env.SPLITSCOPE_BASE_URL ?? 'http://127.0.0.1:8300'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
page.on('pageerror', (e) => console.log('PAGEERROR:', String(e)))

await page.goto(`${BASE}/#/overview`)
await page.locator('.we__demo').filter({ hasText: 'Confounded treatment-effect study' }).getByRole('button', { name: 'Open', exact: true }).click()
await page.waitForURL(/#\/dataset/)
await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Effect estimation' }).click()
await page.waitForFunction(() => !document.querySelector('.estsetup__state')?.textContent?.includes('loading'), null, { timeout: 30000 })
const create = page.getByTestId('create-demo-graph')
await create.or(page.getByTestId('readiness-ok')).first().waitFor({ timeout: 60000 })
if (await create.isVisible()) await create.click()
try {
  await page.getByTestId('readiness-ok').waitFor({ timeout: 60000 })
} catch {
  console.log('SETUP STATE:', await page.locator('.estsetup__state').allTextContents())
  console.log('BODY SNIP:', (await page.content()).slice(0, 500))
  throw new Error('readiness-ok never appeared')
}
await page.getByTestId('run-estimation').click()
await page.getByTestId('effect-summary-table').waitFor({ timeout: 180000 })
await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Causal research' }).click()
const select = page.getByTestId('research-run-select')
await select.waitFor({ timeout: 30000 })
await select.selectOption({ index: 1 })
await page.getByTestId('subgroup-variable').selectOption('region')
await page.getByTestId('subgroup-run').click()
await page.getByTestId('subgroup-forest-chart').waitFor({ timeout: 120000 })

const info = await page.evaluate(() => {
  const svg = document.querySelector('[data-testid="subgroup-forest-chart"]')
  const lines = [...svg.querySelectorAll('.estrow__interval')]
  const caps = [...svg.querySelectorAll('.estrow__cap')]
  const dots = [...svg.querySelectorAll('.rsdot--group')]
  const describe = (el) => {
    const r = el.getBoundingClientRect()
    const cs = getComputedStyle(el)
    return {
      x: +r.x.toFixed(1), y: +r.y.toFixed(1), w: +r.width.toFixed(2), h: +r.height.toFixed(2),
      stroke: cs.stroke, strokeWidth: cs.strokeWidth, display: cs.display, visibility: cs.visibility,
      opacity: cs.opacity,
    }
  }
  return {
    svgSize: { w: svg.getBoundingClientRect().width, h: svg.getBoundingClientRect().height },
    intervals: lines.map(describe),
    caps: caps.map(describe),
    dots: dots.map(describe),
  }
})
console.log(JSON.stringify(info, null, 2))
await page.screenshot({ path: '../docs/screenshots/s9c/_preview/forest-zoom.png', clip: { x: 0, y: 380, width: 1440, height: 520 } })
await browser.close()
