/**
 * S6-A — user-reported defect regressions.
 *
 * These tests exist because the four S5 defects were only found by hand:
 *
 *  1. Explore → Scatter grew the document without bound (a ResizeObserver fed
 *     the container's height back into the SVG it sized, and the inline SVG's
 *     line box added a few pixels every frame).
 *  2. Header hover put pale text on the pale global control hover background.
 *  3. The navigation numbered Study/Explore before Results even though "Run
 *     audit" on Data goes straight to Results.
 *  4. Parallel coordinates explained nothing to a first-time reader.
 *
 * Every assertion below is behavioural: measured document heights, computed
 * colours, accessible names and exact selection counts.
 */
import { expect, loadDemoFromEntry, test } from './fixtures'
import type { Page } from '@playwright/test'

test.use({ viewport: { width: 1440, height: 900 } })

const DEMO = 'Drifting sensor stream split at random'

async function openDemoAnd(page: Page, tab: string) {
  await loadDemoFromEntry(page, DEMO)
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Explore' }).click()
  await expect(page.locator('[data-testid="parallel-coordinates"] svg')).toBeVisible()
  if (tab !== 'Parallel coordinates') {
    await page.getByRole('button', { name: tab, exact: true }).click()
  }
}

const height = (page: Page) =>
  page.evaluate(() => document.documentElement.scrollHeight)

test('scatter: document height settles and never grows while scrolling, resizing or reconfiguring', async ({
  page,
}) => {
  await openDemoAnd(page, 'Scatter')
  const figure = page.locator('[data-figure="scatter"]')
  await expect(figure.locator('svg')).toBeVisible()

  // Layout must settle to a single height: legitimate one-time changes are
  // allowed, continuous growth is the defect.
  const settled: number[] = []
  for (let i = 0; i < 8; i += 1) {
    settled.push(await height(page))
    await page.waitForTimeout(200)
  }
  expect(Math.max(...settled) - Math.min(...settled), `heights ${settled.join(',')}`).toBeLessThanOrEqual(4)
  const baseline = settled[settled.length - 1]

  // Repeated scrolling in both directions must not extend the page.
  for (let i = 0; i < 4; i += 1) {
    await page.mouse.wheel(0, 4000)
    await page.waitForTimeout(150)
    await page.mouse.wheel(0, -4000)
    await page.waitForTimeout(150)
  }
  expect(Math.abs((await height(page)) - baseline)).toBeLessThanOrEqual(4)

  // The SVG stays inside its container: no taller-than-parent plot.
  const geometry = await page.evaluate(() => {
    const plot = document.querySelector('[data-figure="scatter"] .xfig__plot')
    const svg = plot?.querySelector('svg')
    if (!plot || !svg) return null
    const p = plot.getBoundingClientRect()
    const s = svg.getBoundingClientRect()
    return { plotHeight: p.height, plotWidth: p.width, svgHeight: s.height, svgWidth: s.width }
  })
  expect(geometry).not.toBeNull()
  expect(geometry!.svgHeight).toBeLessThanOrEqual(geometry!.plotHeight + 1)

  // Viewport changes resize the plot without runaway growth.
  await page.setViewportSize({ width: 1100, height: 820 })
  await page.waitForTimeout(600)
  const afterResize = await height(page)
  await page.waitForTimeout(800)
  expect(Math.abs((await height(page)) - afterResize)).toBeLessThanOrEqual(4)

  // Changing both axes re-renders the chart, not the document.
  const selects = figure.locator('.xfig__control select')
  const options = await selects.nth(1).locator('option').evaluateAll((nodes) =>
    nodes.map((node) => (node as HTMLOptionElement).value),
  )
  const nextX = options[options.length - 1]
  const nextY = options.find((value) => value !== nextX) ?? options[0]
  if (nextX) await selects.nth(0).selectOption(nextX)
  if (nextY) await selects.nth(1).selectOption(nextY)
  await page.waitForTimeout(900)
  const afterAxes = await height(page)
  await page.waitForTimeout(600)
  expect(Math.abs((await height(page)) - afterAxes)).toBeLessThanOrEqual(4)

  // Opening and closing the evidence inspector (focus mode) stays finite and
  // returns to the same height.
  await page.getByRole('button', { name: 'Focus the plot' }).click()
  await page.waitForTimeout(500)
  await page.getByRole('button', { name: 'Show row evidence' }).click()
  await page.waitForTimeout(700)
  const restored = await height(page)
  await page.waitForTimeout(600)
  expect(Math.abs((await height(page)) - restored)).toBeLessThanOrEqual(4)

  // The plot is still visible and usable after all of that.
  await expect(figure.locator('svg')).toBeVisible()
  expect((await figure.locator('path[stroke]').count())).toBeGreaterThan(0)
})

/** WCAG relative luminance and contrast for two `rgb()`/`rgba()` colours. */
async function contrastOf(page: Page, selector: string) {
  return page.evaluate((sel) => {
    const element = document.querySelector(sel)
    if (!element) return null
    const style = getComputedStyle(element)
    const parse = (value: string) => {
      const match = value.match(/rgba?\(([^)]+)\)/)
      if (!match) return null
      const parts = match[1].split(',').map((part) => Number(part.trim()))
      return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 }
    }
    const luminance = ({ r, g, b }: { r: number; g: number; b: number }) => {
      const channel = (raw: number) => {
        const c = raw / 255
        return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
      }
      return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    }
    const foreground = parse(style.color)
    // Walk up for the first painted background, compositing alpha over the
    // next painted ancestor (the masthead is rgba over the page).
    let node: Element | null = element
    const layers: Array<{ r: number; g: number; b: number; a: number }> = []
    while (node) {
      const bg = parse(getComputedStyle(node).backgroundColor)
      if (bg && bg.a > 0) {
        layers.push(bg)
        if (bg.a >= 1) break
      }
      node = node.parentElement
    }
    let background = { r: 255, g: 255, b: 255 }
    for (let i = layers.length - 1; i >= 0; i -= 1) {
      const layer = layers[i]
      background = {
        r: layer.r * layer.a + background.r * (1 - layer.a),
        g: layer.g * layer.a + background.g * (1 - layer.a),
        b: layer.b * layer.a + background.b * (1 - layer.a),
      }
    }
    if (!foreground) return null
    const l1 = luminance(foreground)
    const l2 = luminance(background)
    return {
      color: style.color,
      background: style.backgroundColor,
      ratio: (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05),
    }
  }, selector)
}

test('header: every primary navigation state keeps readable contrast', async ({ page }) => {
  await loadDemoFromEntry(page, DEMO)
  const nav = page.getByRole('navigation', { name: 'Primary' })
  const labels = ['Start', 'Data', 'Audit results', 'Study', 'Explore', 'Compare']

  for (const label of labels) {
    const button = nav.getByRole('button', { name: label, exact: true })
    await button.hover()
    const contrast = await contrastOf(page, '.app-nav button:hover')
    expect(contrast, `hover contrast for ${label}`).not.toBeNull()
    expect(contrast!.ratio, `hover contrast for ${label}: ${JSON.stringify(contrast)}`).toBeGreaterThanOrEqual(4.5)
  }

  // Active + hover: the current stage must not invert.
  await nav.getByRole('button', { name: 'Audit results', exact: true }).click()
  const current = nav.locator('button[aria-current="page"]')
  await current.hover()
  const active = await contrastOf(page, '.app-nav button[aria-current="page"]')
  expect(active!.ratio).toBeGreaterThanOrEqual(4.5)

  // The brand is a button too: hovering it must not paint a pale fill behind
  // the pale wordmark.
  await page.locator('.app-header__brand--home').hover()
  const brand = await contrastOf(page, '.app-header__brand--home .app-header__title')
  expect(brand!.ratio).toBeGreaterThanOrEqual(4.5)
  const brandBackground = await page.evaluate(
    () => getComputedStyle(document.querySelector('.app-header__brand--home')!).backgroundColor,
  )
  expect(brandBackground).toMatch(/rgba\(0, 0, 0, 0\)|transparent/)

  // Keyboard focus is visible on the dark masthead.
  await page.keyboard.press('Tab')
  const focusRing = await page.evaluate(() => {
    const el = document.querySelector('.app-nav button') as HTMLElement
    el.focus()
    const style = getComputedStyle(el)
    return {
      focusVisible: el.matches(':focus-visible'),
      outlineWidth: style.outlineWidth,
      outlineColor: style.outlineColor,
    }
  })
  expect(focusRing.focusVisible).toBe(true)
  expect(Number.parseFloat(focusRing.outlineWidth)).toBeGreaterThanOrEqual(2)
  expect(focusRing.outlineColor).toBe('rgb(180, 208, 189)')
})

test('workflow: the audit is the third stage and Data runs it directly', async ({ page }) => {
  await loadDemoFromEntry(page, DEMO)
  const nav = page.getByRole('navigation', { name: 'Primary' })
  const order = await nav.locator('button').evaluateAll((buttons) =>
    buttons.map((button) => ({
      step: button.querySelector('.app-nav__step')?.textContent ?? '',
      label: (button.textContent ?? '').replace(/^\d+/, ''),
    })),
  )
  expect(order).toEqual([
    { step: '1', label: 'Start' },
    { step: '2', label: 'Data' },
    { step: '3', label: 'Audit results' },
    { step: '4', label: 'Study' },
    { step: '5', label: 'Explore' },
    { step: '6', label: 'Model Lab' },
    { step: '7', label: 'Causal Lab' },
    { step: '8', label: 'Effect estimation' },
    // S9C added the Causal research stage between estimation and comparison.
    { step: '9', label: 'Causal research' },
    { step: '10', label: 'Compare' },
  ])

  // The breadcrumb names the current stage and offers real next steps.
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Data')
  await expect(page.locator('.app-crumb__next')).toContainText('Run the audit')

  // Run the audit from Data: the third stage becomes current, not the fifth.
  const confirm = page.getByRole('button', { name: 'Confirm these column roles' })
  if (await confirm.isVisible().catch(() => false)) await confirm.click()
  await page.locator('.run-bar button.btn--primary').click()
  await expect(page).toHaveURL(/#\/audit/)
  const active = nav.locator('button[aria-current="page"]')
  await expect(active).toContainText('Audit results')
  await expect(active.locator('.app-nav__step')).toHaveText('3')
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Audit results')

  // Browser back/forward still walk the real history.
  await page.goBack()
  await expect(page).toHaveURL(/#\/dataset/)
  await page.goForward()
  await expect(page).toHaveURL(/#\/audit/)

  // Study and Explore are optional and remain reachable after the audit.
  await nav.getByRole('button', { name: 'Study', exact: true }).click()
  await expect(page).toHaveURL(/#\/study/)
  await expect(page.locator('.app-crumb__next')).toContainText('optional')
})

test('parallel coordinates: reading guide, brush affordance and exact selection count', async ({
  page,
}) => {
  await loadDemoFromEntry(page, DEMO)
  await page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Explore' }).click()
  const figure = page.locator('[data-testid="parallel-coordinates"]')
  await expect(figure).toBeVisible()

  // Compact guidance is visible without opening the full guide.
  await expect(figure.locator('.xpc__readhint')).toContainText('Each line is one observation')
  await expect(figure.locator('.xpc__count')).toContainText('no rows selected')
  await expect(figure.locator('.xpc__emptyhint')).toContainText('Drag vertically')

  // The guide is progressive disclosure and keyboard-operable.
  const help = page.locator('#xpc-help-toggle')
  await help.focus()
  await page.keyboard.press('Enter')
  await expect(help).toHaveAttribute('aria-expanded', 'true')
  const panel = page.locator('#xpc-help')
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('One line = one observation')
  await expect(panel).toContainText('does not by itself prove correlation, causation or data leakage')
  await expect(panel).toContainText('Row evidence')
  await expect(panel.locator('svg[role="img"]')).toBeVisible()
  await expect(help).toHaveAccessibleName('Hide reading guide')
  await help.click()
  await expect(page.locator('#xpc-help')).toHaveCount(0)

  // Brushing a rail selects real rows and the count is stated in the plot.
  const hitArea = figure.locator('.xpc__axis rect[fill="transparent"]').first()
  const box = await hitArea.boundingBox()
  expect(box).not.toBeNull()
  const x = box!.x + box!.width / 2
  await page.mouse.move(x, box!.y + box!.height * 0.15)
  await page.mouse.down()
  await page.mouse.move(x, box!.y + box!.height * 0.55, { steps: 8 })
  await page.mouse.up()

  await expect(figure.locator('.xpc__count')).toContainText(/\d+ selected/)
  const selectedText = (await figure.locator('.xpc__count').textContent()) ?? ''
  const count = Number(selectedText.match(/(\d[\d,]*)\s+selected/)?.[1].replace(/,/g, '') ?? 0)
  expect(count).toBeGreaterThan(0)
  await expect(figure.locator('.xpc__legenditem--selected')).toContainText(`${count} total`)
  await expect(page.locator('.xrow__counts')).toContainText(`${count.toLocaleString('en-US')} of 360 rows selected`)
  await expect(page.locator('.xrow__predicateitem').first()).toContainText('∈')
  expect(await figure.locator('.xpc__line--selected').count()).toBeGreaterThan(0)
  await expect(figure.locator('.xpc__emptyhint')).toHaveCount(0)
})
