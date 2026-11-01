import { defineConfig } from 'vitest/config'

/**
 * Vitest configuration.
 *
 * Deliberately separate from `vite.config.ts`: vitest 2.x bundles its own copy
 * of Vite's types, so putting the `test` block next to the app's `defineConfig`
 * (from vite 6) makes the projects' types incompatible. Component tests live in
 * `tests/` and are deliberately separate from the Playwright suite in `e2e/`;
 * generated output (dist, Playwright artefacts) and the quarantined stale build
 * artefacts are excluded.
 */
// No `plugins: [react()]` here on purpose: the app's plugin is typed against
// vite 6, while vitest 2.x bundles vite 5's types, and the two UserConfig
// types are not assignable. Vitest transforms the TSX through esbuild with the
// automatic JSX runtime, which these tests need and nothing else does.
export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/.stale-artifacts/**',
      '**/test-results/**',
      '**/playwright-report/**',
      '**/e2e/**',
    ],
    restoreMocks: true,
    css: false,
    reporters: ['default'],
  },
})
