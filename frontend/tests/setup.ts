/**
 * Shared Vitest setup.
 *
 * Adds the jest-dom matchers to Vitest. Testing Library's automatic cleanup runs
 * through the global `afterEach` that `globals: true` provides, so no component
 * tree leaks into the next test.
 */
import '@testing-library/jest-dom/vitest'
