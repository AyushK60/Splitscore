import { defineConfig, devices } from '@playwright/test'

/**
 * E2E configuration.
 *
 * Target under test: **the production build served by the FastAPI backend**
 * (`python -m app.main` serves `frontend/dist` at `/` when it exists). That is the
 * documented single-command startup path, so the E2E suite exercises the same
 * artifact a user gets from it. `npm run test:e2e` rebuilds first, so the bundle
 * under test is never stale.
 *
 * Ports are dedicated to tests and configurable:
 *   SPLITSCOPE_E2E_PORT  backend port for the E2E server (default 8123)
 *
 * The server is a *fresh* process started by Playwright's `webServer` and stopped
 * when the run finishes; `reuseExistingServer: false` means an already-running
 * server is never silently reused.
 *
 * Windows-safe: plain commands, no shell-specific syntax.
 */
const E2E_PORT = Number(process.env.SPLITSCOPE_E2E_PORT ?? 8123)
const BASE_URL = `http://127.0.0.1:${E2E_PORT}`

export default defineConfig({
  testDir: './e2e',
  // One shared backend process and one shared in-memory store: keep runs sequential
  // so state isolation between tests is deterministic and reproducible.
  fullyParallel: false,
  workers: 1,
  // No automatic retries: flakiness must surface in the local verification run.
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  outputDir: 'test-results',
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 15_000,
    navigationTimeout: 20_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'python -m app.main',
    cwd: '../backend',
    url: `${BASE_URL}/api/health`,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: 'pipe',
    stderr: 'pipe',
    env: {
      SPLITSCOPE_HOST: '127.0.0.1',
      SPLITSCOPE_PORT: String(E2E_PORT),
      SPLITSCOPE_LOG_LEVEL: 'WARNING',
    },
  },
})
