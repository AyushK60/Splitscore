/**
 * Shared E2E fixtures.
 *
 * Attaches failure diagnostics to every test:
 *  - browser page errors (`pageerror`) are collected and must be empty;
 *  - failed requests and HTTP >= 400 responses from the application origin are
 *    collected and must be empty unless the test explicitly allows them. The
 *    error-recovery test registers its intentional 422 through `allowFailure(...)`,
 *    so intentional failures stay visible in the report instead of being silently
 *    filtered.
 *
 * Traces and screenshots are captured on failure by `playwright.config.ts`.
 */
import { test as base, expect, type Page } from '@playwright/test'

type FailureDiagnostics = {
  /** Register an intentional failure so it is reported but not treated as a bug. */
  allowFailure: (matcher: RegExp) => void
}

const test = base.extend<FailureDiagnostics>({
  allowFailure: [
    async ({ page }, use, testInfo) => {
      const pageErrors: string[] = []
      const appFailures: string[] = []
      const allowed: RegExp[] = []
      const origin = testInfo.project.use.baseURL ?? ''

      page.on('pageerror', (error) => {
        pageErrors.push(String(error))
      })
      page.on('requestfailed', (request) => {
        if (request.url().startsWith(origin)) {
          appFailures.push(
            `requestfailed ${request.method()} ${request.url()} :: ${request.failure()?.errorText ?? 'unknown'}`,
          )
        }
      })
      page.on('response', (response) => {
        if (response.url().startsWith(origin) && response.status() >= 400) {
          appFailures.push(`HTTP ${response.status()} ${response.request().method()} ${response.url()}`)
        }
      })

      await use((matcher: RegExp) => allowed.push(matcher))

      const unexpected = appFailures.filter((line) => !allowed.some((pattern) => pattern.test(line)))
      const intentional = appFailures.filter((line) => allowed.some((pattern) => pattern.test(line)))
      if (intentional.length) {
        testInfo.annotations.push({ type: 'intentional-failure', description: intentional.join('\n') })
      }
      expect(pageErrors, 'browser page errors (uncaught exceptions in application code)').toEqual([])
      expect(unexpected, 'unexpected failed or HTTP >= 400 application requests').toEqual([])
    },
    { auto: true },
  ],
})

export { expect, test }

/**
 * Loads a bundled demo from the S5 workspace entry panel and waits for the
 * Data stage. The old collapsed "Browse other demos" disclosure no longer
 * exists; the entry lists every demo with a real Open action.
 *
 * Since S11 the Data workspace is a lazy route chunk, so arriving at
 * `#/dataset` shows a labelled loading card first; every caller assumes the
 * workspace content itself, so this waits for the dataset heading to render.
 */
export async function loadDemoFromEntry(page: Page, title: string): Promise<void> {
  await page.goto('/#/overview')
  await page
    .locator('.we__demo')
    .filter({ hasText: title })
    .getByRole('button', { name: 'Open', exact: true })
    .click()
  await page.waitForURL(/#\/dataset/)
  await page.locator('.dataset-head h1').waitFor({ state: 'visible' })
}
