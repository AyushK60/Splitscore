/**
 * ESLint flat configuration.
 *
 * Scoped by area:
 *   - `src/` is browser application code (browser globals, React Hooks rules).
 *   - `tests/` is Vitest component-test code (node + vitest globals are not
 *     used — tests import from vitest explicitly — but jsdom code still runs in
 *     a DOM, so browser globals are allowed there too).
 *   - `e2e/`, `playwright.config.ts` and `vite.config.ts` are Node tooling.
 *   - `eslint.config.js` itself is Node tooling.
 *   - Generated output (dist, playwright-report, test-results) and the
 *     quarantined stale artifacts are never linted.
 */
import js from '@eslint/js'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'playwright-report/**', 'test-results/**', '.stale-artifacts/**', 'e2e/.artifacts/**'] },

  {
    files: ['**/*.ts', '**/*.tsx'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      // The API boundary is deliberately loose (`details: Record<string, unknown>`).
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],
      'no-console': ['error', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'smart'],
      'prefer-const': 'error',
      'no-var': 'error',
    },
  },

  {
    // Browser application code: React Hooks rules.
    files: ['src/**/*.ts', 'src/**/*.tsx'],
    plugins: { 'react-hooks': reactHooks },
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
    },
  },

  {
    // Vitest component tests: DOM is real (jsdom), mocks and assertions are
    // imported from vitest, so no extra globals; node process access is allowed
    // for test tooling.
    files: ['tests/**/*.ts', 'tests/**/*.tsx'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      // Fixtures intentionally build partial API payloads.
      '@typescript-eslint/no-explicit-any': 'off',
      'no-console': 'off',
    },
  },

  {
    // Node tooling: Playwright specs and build/test configuration.
    files: ['e2e/**/*.ts', 'playwright.config.ts', 'vite.config.ts', 'eslint.config.js'],
    languageOptions: {
      globals: globals.node,
    },
    rules: {
      'no-console': 'off',
    },
  },
)
