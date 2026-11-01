/**
 * AppProvider behaviour: catalogue loading on mount, error state and recovery,
 * StrictMode safety, dataset switching, and stale-response races.
 *
 * The API boundary (`src/api/client`) is mocked; the provider under test is the
 * real one, driven through its public context contract (`useApp`).
 */
import { StrictMode, type ReactNode } from 'react'
import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, api } from '../src/api/client'
import type * as ApiClient from '../src/api/client'
import type { PreviewResponse, RoleValidationResult } from '../src/api/types'
import { AppProvider, useApp } from '../src/state/AppState'
import {
  auditResponseFixture,
  checksFixture,
  comparisonResponseFixture,
  datasetSummaryFixture,
  demosFixture,
  healthFixture,
  loadedFixture,
  previewFixture,
  validationFixture,
} from './fixtures'

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof ApiClient>()
  return {
    ...actual,
    api: {
      health: vi.fn(),
      checks: vi.fn(),
      demos: vi.fn(),
      loadDemo: vi.fn(),
      uploadDataset: vi.fn(),
      dataset: vi.fn(),
      preview: vi.fn(),
      validateRoles: vi.fn(),
      columnValues: vi.fn(),
      audit: vi.fn(),
      compare: vi.fn(),
    },
    downloadExport: vi.fn(),
  }
})

type Ctx = ReturnType<typeof useApp>

const store: { ctx: Ctx | null } = { ctx: null }

function Probe() {
  const ctx = useApp()
  store.ctx = ctx
  return (
    <div>
      <span data-testid="checks">{ctx.checks ? ctx.checks.checks.length : 'none'}</span>
      <span data-testid="demos">{ctx.demos ? ctx.demos.demos.length : 'none'}</span>
      <span data-testid="health">{ctx.health?.app_version ?? 'none'}</span>
      <span data-testid="health-store">
        {ctx.health ? `${ctx.health.store.datasets} datasets, ${ctx.health.store.runs} runs` : 'none'}
      </span>
      <span data-testid="status">
        {ctx.status.kind}:{ctx.status.message}
      </span>
      <span data-testid="dataset">{ctx.dataset?.dataset.dataset_id ?? 'none'}</span>
      <span data-testid="roles">{ctx.roles.features.join('|')}</span>
      <span data-testid="audit">{ctx.audit?.run_id ?? 'none'}</span>
      <span data-testid="comparison">{ctx.comparison?.run_id ?? 'none'}</span>
      <span data-testid="preview">{ctx.preview ? `${ctx.preview.row_ids.length} rows` : 'none'}</span>
    </div>
  )
}

function renderApp(ui: ReactNode = <Probe />) {
  return render(<AppProvider>{ui}</AppProvider>)
}

function context(): Ctx {
  if (!store.ctx) throw new Error('provider never rendered')
  return store.ctx
}

/**
 * Wait until the mount-time catalogue request has landed. `findByTestId` is not
 * enough: the test ids exist from the first render, so it can resolve before
 * the mocked promises settle and make the next assertion race the state update.
 */
async function waitForCatalogue(): Promise<void> {
  await waitFor(() => {
    expect(screen.getByTestId('checks')).toHaveTextContent('2')
    expect(screen.getByTestId('demos')).toHaveTextContent('1')
    expect(screen.getByTestId('health')).toHaveTextContent('1.0.0-test')
    expect(screen.getByTestId('status')).toHaveTextContent('idle:')
  })
}

beforeEach(() => {
  store.ctx = null
})

describe('catalogue loading', () => {
  it('requests health, checks and demos on mount and exposes them to consumers', async () => {
    vi.mocked(api.health).mockResolvedValue(healthFixture())
    vi.mocked(api.checks).mockResolvedValue(checksFixture())
    vi.mocked(api.demos).mockResolvedValue(demosFixture())

    renderApp()

    await waitForCatalogue()
    expect(screen.getByTestId('status')).toHaveTextContent('idle:')

    expect(api.health).toHaveBeenCalledTimes(1)
    expect(api.checks).toHaveBeenCalledTimes(1)
    expect(api.demos).toHaveBeenCalledTimes(1)
  })

  it('shows an error state when the catalogue request fails, and recovers on reload', async () => {
    vi.mocked(api.health).mockRejectedValue(new ApiError(0, 'unreachable', 'backend unreachable'))
    vi.mocked(api.checks).mockResolvedValue(checksFixture())
    vi.mocked(api.demos).mockResolvedValue(demosFixture())

    renderApp()

    // The status element exists from the first render, so wait for the failed
    // request to land rather than for the element itself.
    await waitFor(() => {
      expect(screen.getByTestId('status')).toHaveTextContent('error:backend unreachable')
    })
    expect(screen.getByTestId('checks')).toHaveTextContent('none')

    // Recovery: the backend comes back and the user reloads the catalogue.
    vi.mocked(api.health).mockResolvedValue(healthFixture())
    await act(async () => {
      await context().reloadCatalogue()
    })

    expect(screen.getByTestId('checks')).toHaveTextContent('2')
    expect(screen.getByTestId('status')).toHaveTextContent('idle:')
  })

  it('keeps consistent state when StrictMode mounts effects twice', async () => {
    vi.mocked(api.health).mockResolvedValue(healthFixture())
    vi.mocked(api.checks).mockResolvedValue(checksFixture())
    vi.mocked(api.demos).mockResolvedValue(demosFixture())

    renderApp(
      <StrictMode>
        <Probe />
      </StrictMode>,
    )

    await waitForCatalogue()
    // Effects may run twice; the visible state must still be one catalogue,
    // not a duplicated or permanently busy one.
    expect(vi.mocked(api.checks).mock.calls.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByTestId('demos')).toHaveTextContent('1')
    expect(screen.getByTestId('status')).toHaveTextContent('idle:')
  })

  it('repeated reloads leave the catalogue in the same, non-error state', async () => {
    vi.mocked(api.health).mockResolvedValue(healthFixture())
    vi.mocked(api.checks).mockResolvedValue(checksFixture())
    vi.mocked(api.demos).mockResolvedValue(demosFixture())

    renderApp()
    await waitForCatalogue()

    await act(async () => {
      await context().reloadCatalogue()
      await context().reloadCatalogue()
    })

    expect(screen.getByTestId('checks')).toHaveTextContent('2')
    expect(screen.getByTestId('status')).toHaveTextContent('idle:')
  })

  it('refreshHealth re-fetches health so store counters update, and keeps the last snapshot on failure', async () => {
    vi.mocked(api.health).mockResolvedValue(healthFixture())
    vi.mocked(api.checks).mockResolvedValue(checksFixture())
    vi.mocked(api.demos).mockResolvedValue(demosFixture())

    renderApp()
    await waitForCatalogue()
    expect(screen.getByTestId('health-store')).toHaveTextContent('1 datasets, 2 runs')

    // A later visit (e.g. the export page) sees updated store counters.
    const updated = healthFixture()
    updated.store = { ...updated.store, datasets: 3, runs: 5 }
    vi.mocked(api.health).mockResolvedValue(updated)
    await act(async () => {
      await context().refreshHealth()
    })
    expect(screen.getByTestId('health-store')).toHaveTextContent('3 datasets, 5 runs')
    expect(screen.getByTestId('status')).toHaveTextContent('idle:')

    // A failed refresh keeps the previous snapshot and does not raise an error status.
    vi.mocked(api.health).mockRejectedValue(new ApiError(0, 'unreachable', 'backend unreachable'))
    await act(async () => {
      await context().refreshHealth()
    })
    expect(screen.getByTestId('health-store')).toHaveTextContent('3 datasets, 5 runs')
    expect(screen.getByTestId('status')).toHaveTextContent('idle:')
  })
})

describe('dataset switching', () => {
  it('clears results that belonged to the previous dataset', async () => {
    vi.mocked(api.health).mockResolvedValue(healthFixture())
    vi.mocked(api.checks).mockResolvedValue(checksFixture())
    vi.mocked(api.demos).mockResolvedValue(demosFixture())

    const datasetA = loadedFixture({ dataset: datasetSummaryFixture({ dataset_id: 'ds-a' }) })
    const datasetB = loadedFixture({ dataset: datasetSummaryFixture({ dataset_id: 'ds-b' }) })
    vi.mocked(api.loadDemo).mockResolvedValueOnce(datasetA).mockResolvedValueOnce(datasetB)
    vi.mocked(api.audit).mockResolvedValue(auditResponseFixture())
    vi.mocked(api.compare).mockResolvedValue(comparisonResponseFixture())
    vi.mocked(api.preview).mockResolvedValue(previewFixture())

    renderApp()
    await waitForCatalogue()

    await act(async () => {
      await context().loadDemo('demo-a')
    })
    expect(screen.getByTestId('dataset')).toHaveTextContent('ds-a')

    await act(async () => {
      await context().runAudit()
    })
    await act(async () => {
      await context().runComparison()
    })
    await act(async () => {
      await context().loadPreview(0, 2)
    })

    expect(screen.getByTestId('audit')).toHaveTextContent('run-fixture-1')
    expect(screen.getByTestId('comparison')).toHaveTextContent('compare-fixture-1')
    expect(screen.getByTestId('preview')).toHaveTextContent('2 rows')

    await act(async () => {
      await context().loadDemo('demo-b')
    })

    expect(screen.getByTestId('dataset')).toHaveTextContent('ds-b')
    // Nothing from dataset A may still look like it belongs to dataset B.
    expect(screen.getByTestId('audit')).toHaveTextContent('none')
    expect(screen.getByTestId('comparison')).toHaveTextContent('none')
    expect(screen.getByTestId('preview')).toHaveTextContent('none')
    expect(screen.getByTestId('roles')).toHaveTextContent('tenure_months|monthly_spend')
  })

  it('ignores a preview that resolves after the dataset has changed', async () => {
    vi.mocked(api.health).mockResolvedValue(healthFixture())
    vi.mocked(api.checks).mockResolvedValue(checksFixture())
    vi.mocked(api.demos).mockResolvedValue(demosFixture())

    vi.mocked(api.loadDemo)
      .mockResolvedValueOnce(loadedFixture({ dataset: datasetSummaryFixture({ dataset_id: 'ds-a' }) }))
      .mockResolvedValueOnce(loadedFixture({ dataset: datasetSummaryFixture({ dataset_id: 'ds-b' }) }))

    let resolvePreview: ((value: PreviewResponse) => void) | undefined
    vi.mocked(api.preview).mockImplementation(
      () =>
        new Promise<PreviewResponse>((resolve) => {
          resolvePreview = resolve
        }),
    )

    renderApp()
    await waitForCatalogue()

    await act(async () => {
      await context().loadDemo('demo-a')
    })

    // Controlled promise: the preview for dataset A stays in flight.
    let pending: Promise<void> | undefined
    act(() => {
      pending = context().loadPreview(0, 2)
    })
    await act(async () => {
      await context().loadDemo('demo-b')
    })
    await act(async () => {
      resolvePreview?.(previewFixture({ dataset_id: 'ds-a' }))
      await pending
    })

    expect(screen.getByTestId('dataset')).toHaveTextContent('ds-b')
    expect(screen.getByTestId('preview')).toHaveTextContent('none')
  })

  it('ignores an audit that resolves after the dataset has changed', async () => {
    vi.mocked(api.health).mockResolvedValue(healthFixture())
    vi.mocked(api.checks).mockResolvedValue(checksFixture())
    vi.mocked(api.demos).mockResolvedValue(demosFixture())

    vi.mocked(api.loadDemo)
      .mockResolvedValueOnce(loadedFixture({ dataset: datasetSummaryFixture({ dataset_id: 'ds-a' }) }))
      .mockResolvedValueOnce(loadedFixture({ dataset: datasetSummaryFixture({ dataset_id: 'ds-b' }) }))

    let resolveAudit: ((value: unknown) => void) | undefined
    vi.mocked(api.audit).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveAudit = resolve
        }),
    )

    renderApp()
    await waitForCatalogue()

    await act(async () => {
      await context().loadDemo('demo-a')
    })

    let pending: Promise<boolean> | undefined
    act(() => {
      pending = context().runAudit()
    })
    await act(async () => {
      await context().loadDemo('demo-b')
    })
    await act(async () => {
      resolveAudit?.(auditResponseFixture())
      await pending
    })

    expect(screen.getByTestId('dataset')).toHaveTextContent('ds-b')
    expect(screen.getByTestId('audit')).toHaveTextContent('none')
  })

  it('discards a validation response whose roles were edited while it was in flight', async () => {
    vi.mocked(api.health).mockResolvedValue(healthFixture())
    vi.mocked(api.checks).mockResolvedValue(checksFixture())
    vi.mocked(api.demos).mockResolvedValue(demosFixture())
    vi.mocked(api.loadDemo).mockResolvedValue(loadedFixture())

    // The first validation is held open; every later one stays pending so the
    // debounced re-check cannot mask the assertion below.
    let resolveFirst: ((value: RoleValidationResult) => void) | undefined
    vi.mocked(api.validateRoles)
      .mockImplementationOnce(
        () =>
          new Promise<RoleValidationResult>((resolve) => {
            resolveFirst = resolve
          }),
      )
      .mockImplementation(() => new Promise<RoleValidationResult>(() => {}))

    renderApp()
    await waitForCatalogue()
    await act(async () => {
      await context().loadDemo('fixture_demo')
    })

    let pending: Promise<void> | undefined
    act(() => {
      pending = context().validateRoles()
    })

    // The user changes a role before the first answer lands. That answer
    // describes the previous roles and must never be shown as current.
    act(() => {
      context().patchRoles({ target: 'monthly_spend' })
    })

    await act(async () => {
      resolveFirst?.(validationFixture())
      await pending
    })

    expect(store.ctx?.validation).toBeNull()
    expect(store.ctx?.validationPending).toBe(true)
    expect(store.ctx?.roles.target).toBe('monthly_spend')
  })
})
