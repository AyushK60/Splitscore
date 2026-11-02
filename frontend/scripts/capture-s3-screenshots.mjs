/**
 * S3 visual + behavioural capture.
 *
 * Drives the real production build served by the local backend and writes the
 * screenshots referenced by docs/S3_VERIFICATION.md. It asserts behaviour, not
 * just pixels: phase transitions, pause/replay, reduced motion, overflow and
 * console cleanliness. Exits non-zero when a check fails.
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = process.env.SPLITSCOPE_BASE ?? 'http://127.0.0.1:8300'
const OUT = '../docs/screenshots/s3'
mkdirSync(OUT, { recursive: true })

const failures = []
const check = (name, ok, detail = '') => {
  console.log(`${ok ? ' *' : 'FAIL'} ${name}${detail ? `: ${detail}` : ''}`)
  if (!ok) failures.push(name)
}

const browser = await chromium.launch()

async function open(width, height, scheme = 'dark') {
  const page = await browser.newPage({ viewport: { width, height }, colorScheme: scheme })
  const errors = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  return { page, errors }
}

async function settle(page) {
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
}

// --- hero phases at the reference viewport ---------------------------------
{
  const { page, errors } = await open(1440, 900)
  await page.waitForTimeout(1400)
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
    await page.waitForTimeout(1400)
    await page.screenshot({ path: `${OUT}/s3-hero-${id}.png` })
    const phase = await page.locator('.hs-scene').getAttribute('data-phase')
    check(`hero phase ${id}`, phase === id, phase ?? 'missing')
  }

  // Pause / replay are real controls, not decoration.
  await page.locator('.lp-console__phase', { hasText: 'Discovery' }).first().click()
  await page.getByRole('button', { name: /Replay the observatory/i }).click()
  await page.waitForTimeout(300)
  check(
    'replay returns to the first phase',
    (await page.locator('.hs-scene').getAttribute('data-phase')) === 'forming',
  )
  await page.waitForTimeout(4000)
  check(
    'the sequence advances on its own',
    (await page.locator('.hs-scene').getAttribute('data-phase')) !== 'forming',
  )

  await page.locator('.lp-console__phase', { hasText: 'Evidence' }).first().click()
  await page.waitForTimeout(1200)
  await page.screenshot({ path: `${OUT}/s3-landing-hero.png` })
  await settle(page)
  await page.screenshot({ path: `${OUT}/s3-landing-desktop.png`, fullPage: true })

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check('landing overflow at 1440', overflow === 0, `${overflow}px`)
  check('no console or page errors on landing', errors.length === 0, errors[0] ?? '')
  await page.close()
}

// --- wider desktop ----------------------------------------------------------
{
  const { page } = await open(1920, 1080)
  await page.waitForTimeout(1800)
  await page.screenshot({ path: `${OUT}/s3-landing-1920.png` })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check('landing overflow at 1920', overflow === 0, `${overflow}px`)
  await page.close()
}

// --- responsive -------------------------------------------------------------
for (const [name, width, height] of [
  ['tablet', 768, 1024],
  ['mobile', 390, 844],
]) {
  const { page, errors } = await open(width, height)
  await page.waitForTimeout(1400)
  // Full-page shots need the scroll pass first: the landing reveals sections
  // through IntersectionObserver, so an unscrolled capture would show blanks.
  await settle(page)
  await page.screenshot({ path: `${OUT}/s3-landing-${name}.png`, fullPage: true })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check(`landing overflow at ${width}`, overflow === 0, `${overflow}px`)
  check(`no errors at ${width}`, errors.length === 0, errors[0] ?? '')
  await page.close()
}

// --- reduced motion: a still, complete frame --------------------------------
{
  const { page } = await open(1440, 900)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  const scan = await page.locator('.hs-scan-band').evaluate((node) => getComputedStyle(node).display)
  const phase = await page.locator('.hs-scene').getAttribute('data-phase')
  const pair = await page.locator('.obs-card--pair').count()
  check('reduced motion hides the scanner', scan === 'none', scan)
  check('reduced motion shows the evidence frame', phase === 'evidence', phase ?? 'missing')
  check('reduced motion keeps the implicated pair', pair === 2, `${pair} plates`)
  await page.screenshot({ path: `${OUT}/s3-hero-reduced-motion.png` })
  await page.close()
}

// --- study workspace --------------------------------------------------------
{
  const { page, errors } = await open(1440, 900)
  await page.getByRole('button', { name: /Explore Interactive Demo/i }).click()
  await page.waitForURL(/#\/dataset/, { timeout: 20000 })
  await page.goto(`${BASE}/#/study`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.rs-table, .rs-card', { timeout: 15000 })
  await page.waitForTimeout(700)

  await page.screenshot({ path: `${OUT}/s3-study-card.png`, fullPage: true })
  await page.getByRole('tab', { name: 'Data dictionary' }).click()
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${OUT}/s3-study-dictionary.png`, fullPage: true })
  await page.getByRole('tab', { name: 'Data profile' }).click()
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${OUT}/s3-study-profile.png`, fullPage: true })
  await page.getByRole('tab', { name: 'Provenance' }).click()
  await page.waitForTimeout(800)
  await page.screenshot({ path: `${OUT}/s3-study-provenance.png`, fullPage: true })

  const sha = await page.locator('.rs-dl dd.rs-mono').first().textContent()
  check('manifest shows a sha256', /^[0-9a-f]{64}$/.test((sha ?? '').trim()), (sha ?? '').slice(0, 12))
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check('study workspace overflow', overflow === 0, `${overflow}px`)
  check('no console errors in the study workspace', errors.length === 0, errors[0] ?? '')
  await page.close()
}

await browser.close()
console.log(`\n${failures.length === 0 ? 'All S3 capture checks passed.' : `${failures.length} check(s) failed.`}`)
if (failures.length) process.exitCode = 1
