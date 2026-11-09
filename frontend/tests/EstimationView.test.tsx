/**
 * Effect Estimation Studio integration, against the estimation API contract.
 *
 * The API boundary is mocked with the hand-written payloads in
 * `estimationFixtures.ts`; the studio, its request construction, sequencing and
 * views are real. The live-backend behaviour is covered by
 * `e2e/s9b-estimation.spec.ts`.
 *
 * Pinned here: readiness validation (and its debounce), explicit run, partial
 * and failed results, staleness after a configuration change, dataset expiry,
 * out-of-order readiness answers, run history reload and the demonstration
 * banner. Exports are tested in `estimationExport.test.ts`.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useEffect } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AppProvider, useApp } from '../src/state/AppState'
import { EstimationView } from '../src/estimation/EstimationView'
import { ApiError } from '../src/api/client'
import type * as ApiClient from '../src/api/client'
import type {
  CausalGraphSummary,
  EstimationRequestPayload,
  EstimationRunSummary,
  EstimationValidateResponse,
} from '../src/api/types'
import { datasetSummaryFixture, loadedFixture } from './fixtures'
import {
  DATASET_FINGERPRINT,
  DATASET_ID,
  GRAPH_FINGERPRINT,
  GRAPH_ID,
  graphPayload,
  identificationPayload,
  runPayload,
  validatePayload,
} from './estimationFixtures'

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
    causalApi: {
      list: vi.fn(),
      create: vi.fn(),
      get: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      validate: vi.fn(),
      identify: vi.fn(),
      evaluateAdjustment: vi.fn(),
      fetchExport: vi.fn(),
      import: vi.fn(),
    },
    estimationApi: {
      validate: vi.fn(),
      run: vi.fn(),
      compare: vi.fn(),
      runs: vi.fn(),
      runDetail: vi.fn(),
    },
    downloadExport: vi.fn(),
  }
})

import { api, causalApi, estimationApi } from '../src/api/client'

const COLUMNS = ['unit_id', 'age', 'baseline_score', 'region', 'treatment', 'outcome', 'split']

const demoLoaded = () =>
  loadedFixture({
    dataset: datasetSummaryFixture({
      dataset_id: DATASET_ID,
      name: 'causal_effect.csv',
      fingerprint_sha256: DATASET_FINGERPRINT,
      columns: COLUMNS,
      row_count: 1200,
      column_count: COLUMNS.length,
      demo_id: 'causal_effect',
    }),
    demo: {
      demo_id: 'causal_effect',
      title: 'Confounded treatment effect',
      subtitle: 'Measured confounding with a known constant effect.',
      filename: 'causal_effect.csv',
      synthetic: true,
      is_control: false,
      seed: 9,
      row_count: 1200,
      column_count: COLUMNS.length,
      columns: COLUMNS,
      sha256: DATASET_FINGERPRINT,
      teaching_point: 'Adjustment removes measured confounding; the raw difference does not.',
      generation_method: 'Documented simulator, seed 9.',
      expected_findings: [],
      recommended_audit: {},
      recommended_split: null,
      planted_cases: [],
      notes: [],
      file_present: true,
      summary_metrics: { true_ate: 1.5, naive_difference: 3.1724 },
    },
  })

function graphSummary(): CausalGraphSummary {
  const graph = graphPayload()
  return {
    graph_id: GRAPH_ID,
    name: graph.name,
    description: graph.description,
    revision: graph.revision,
    node_count: graph.nodes.length,
    edge_count: graph.edges.length,
    analysis: graph.analysis,
    spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    created_at_utc: graph.created_at_utc,
    updated_at_utc: graph.updated_at_utc,
    validation_ok: true,
    error_count: 0,
    warning_count: 0,
  }
}

function storedRun(): EstimationRunSummary {
  return {
    run_id: 'run-stored-1',
    kind: 'compare',
    dataset_id: DATASET_ID,
    label: 'Three-estimator comparison',
    created_seconds_ago: 120,
  }
}

function Harness() {
  const ctx = useApp()
  useEffect(() => {
    if (!ctx.dataset) void ctx.loadDemo('causal_effect')
  }, [])
  return ctx.dataset ? (
    <EstimationView onNavigate={() => {}} />
  ) : (
    <p>loading…</p>
  )
}

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void }

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function renderStudio({ graphs }: { graphs?: CausalGraphSummary[] } = {}) {
  vi.mocked(api.health).mockResolvedValue({} as Awaited<ReturnType<typeof api.health>>)
  vi.mocked(api.checks).mockResolvedValue({} as Awaited<ReturnType<typeof api.checks>>)
  vi.mocked(api.demos).mockResolvedValue({} as Awaited<ReturnType<typeof api.demos>>)
  vi.mocked(api.loadDemo).mockResolvedValue(demoLoaded())
  vi.mocked(api.columnValues).mockResolvedValue({
    dataset_id: DATASET_ID,
    column: 'treatment',
    total_rows: 1200,
    distinct_count: 2,
    missing_count: 0,
    values: [
      { value: '0', count: 900 },
      { value: '1', count: 300 },
    ],
    truncated: false,
    note: 'Two observed values.',
  } as Awaited<ReturnType<typeof api.columnValues>>)
  vi.mocked(causalApi.list).mockResolvedValue({
    dataset_id: DATASET_ID,
    graphs: graphs ?? [graphSummary()],
    schema_version: '1.0.0',
    storage_note: 'Bounded in-memory store.',
  })
  vi.mocked(causalApi.get).mockResolvedValue(graphPayload())
  vi.mocked(causalApi.identify).mockResolvedValue(identificationPayload())
  vi.mocked(causalApi.evaluateAdjustment).mockResolvedValue({
    valid: true,
    violations: [],
    interpretation: 'Every backdoor path is blocked.',
  } as Awaited<ReturnType<typeof causalApi.evaluateAdjustment>>)
  vi.mocked(estimationApi.runs).mockResolvedValue({ dataset_id: DATASET_ID, runs: [storedRun()] })
  vi.mocked(estimationApi.validate).mockResolvedValue(validatePayload())
  vi.mocked(estimationApi.compare).mockResolvedValue(runPayload())
  vi.mocked(estimationApi.run).mockResolvedValue(runPayload())
  vi.mocked(estimationApi.runDetail).mockResolvedValue(runPayload())

  render(
    <AppProvider>
      <Harness />
    </AppProvider>,
  )
  await screen.findByRole('region', { name: 'Effect Estimation Studio' })
  if (graphs && graphs.length === 0) {
    await waitFor(() => expect(screen.getByTestId('readiness-blocked')).toBeInTheDocument(), {
      timeout: 3000,
    })
    return
  }
  // The probe runs after a 420 ms debounce and the adjustment set arrives from
  // identification, so wait for the run to become *enabled* rather than for the
  // first "Ready" render - that proves the readiness answer matches the current
  // signature.
  await waitFor(() => expect(runButton().disabled).toBe(false), { timeout: 5000 })
}

function runButton(): HTMLButtonElement {
  return screen.getByTestId('run-estimation') as HTMLButtonElement
}

describe('EstimationView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('probes readiness with the exact estimation request and only then enables the run', async () => {
    await renderStudio()

    const calls = vi.mocked(estimationApi.validate).mock.calls
    const request = calls[calls.length - 1][2] as EstimationRequestPayload
    expect(request).toMatchObject({
      estimand: 'ate',
      treatment_node: 'treatment',
      outcome_node: 'outcome',
      adjustment_nodes: ['age', 'baseline_score', 'region'],
      treatment_mapping: { treated: '1', control: '0' },
      cohort: { split_assignment_id: null, partition: null },
      missing_data_policy: 'complete_case',
      cross_fit: { splits: 5, group_column: null },
      uncertainty: { method: 'bootstrap', level: 0.95, reps: 500, seed: null },
      propensity_truncation: null,
      expected_spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    })
    expect(runButton().disabled).toBe(false)
    expect(screen.getByTestId('readiness-ok').textContent).toContain('120 rows would be analysed')
    expect(screen.getByTestId('demo-banner').textContent).toContain('1.500 outcome units')
  })

  it('runs a comparison only when the user asks, then renders backend numbers', async () => {
    await renderStudio()
    expect(estimationApi.compare).not.toHaveBeenCalled()

    fireEvent.click(runButton())
    await waitFor(() => expect(estimationApi.compare).toHaveBeenCalledTimes(1))
    await screen.findByTestId('effect-summary-table')

    const table = screen.getByTestId('effect-summary-table')
    expect(within(table).getByText('2.000')).toBeInTheDocument()
    expect(screen.getByTestId('result-meta').textContent).toContain('run-s9b-fixture')
    expect(screen.getByTestId('summary-dot-ipw').getAttribute('data-value')).toBe('1.6')
    // Five analytical views, one figure each.
    expect(screen.getAllByTestId(/^tab-/)).toHaveLength(5)
  })

  it('marks a completed result stale after a configuration change, naming the reason', async () => {
    await renderStudio()
    fireEvent.click(runButton())
    await screen.findByTestId('effect-summary-table')

    fireEvent.change(screen.getByLabelText('Bootstrap replicates'), { target: { value: '700' } })
    const banner = await screen.findByTestId('stale-banner')
    expect(banner.textContent).toContain('These results no longer describe the current study')
    expect(banner.textContent).toContain('The number of bootstrap replicates changed.')
    // The earlier numbers are still the real earlier numbers.
    expect(screen.getByTestId('effect-summary-table')).toBeInTheDocument()
  })

  it('reports an expired dataset and offers a reload route instead of a spinner', async () => {
    await renderStudio()
    vi.mocked(estimationApi.compare).mockRejectedValue(
      new ApiError(410, 'dataset_expired', 'This dataset is no longer available.'),
    )
    fireEvent.click(runButton())
    const alert = await screen.findByTestId('run-error')
    expect(alert.textContent).toContain('The dataset is no longer available')
    expect(within(alert).getByRole('button', { name: 'Reload the dataset' })).toBeInTheDocument()
    expect(screen.queryByTestId('estimation-running')).toBeNull()
    expect(runButton().disabled).toBe(false)
  })

  it('keeps a partial failure honest: one estimator estimated, one failed', async () => {
    await renderStudio()
    vi.mocked(estimationApi.compare).mockResolvedValue(
      runPayload({
        results: [
          runPayload().results[0],
          {
            estimator: 'ipw',
            status: 'failed',
            failure: {
              reason: 'The propensity model could not be fitted.',
              details: { library_error: 'ValueError' },
            },
          },
          runPayload().results[2],
        ],
      }),
    )
    fireEvent.click(runButton())
    await screen.findByTestId('effect-summary-table')
    expect(screen.getByTestId('summary-failure-ipw').textContent).toContain('Failed')
    expect(screen.queryByTestId('summary-dot-ipw')).toBeNull()
    expect(screen.getByTestId('summary-dot-aipw')).toBeInTheDocument()
  })

  it('discards an older readiness answer that arrives after a newer one', async () => {
    await renderStudio()
    const pending: Array<Deferred<EstimationValidateResponse>> = []
    vi.mocked(estimationApi.validate).mockImplementation(() => {
      const next = deferred<EstimationValidateResponse>()
      pending.push(next)
      return next.promise
    })

    fireEvent.change(screen.getByLabelText('Bootstrap replicates'), { target: { value: '300' } })
    await waitFor(() => expect(pending).toHaveLength(1), { timeout: 3000 })

    fireEvent.change(screen.getByLabelText('Interval level'), { target: { value: '0.99' } })
    await waitFor(() => expect(pending).toHaveLength(2), { timeout: 3000 })

    const newer = validatePayload({
      cohort_preview: { ...validatePayload().cohort_preview, rows_final: 999 },
    })
    const older = validatePayload({
      cohort_preview: { ...validatePayload().cohort_preview, rows_final: 111 },
    })
    pending[1].resolve(newer)
    await waitFor(() =>
      expect(screen.getByTestId('readiness-chip').textContent).toContain('999'),
    )

    pending[0].resolve(older)
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.getByTestId('readiness-chip').textContent).toContain('999')
    expect(screen.getByTestId('readiness-chip').textContent).not.toContain('111')
  })

  it('reloads a stored run from the bounded session history', async () => {
    await renderStudio()
    fireEvent.click(screen.getByTestId('history-summary'))
    const load = await screen.findByRole('button', { name: 'Load' })
    fireEvent.click(load)

    await waitFor(() => expect(estimationApi.runDetail).toHaveBeenCalledWith(DATASET_ID, 'run-stored-1'))
    const meta = await screen.findByTestId('result-meta')
    expect(meta.textContent).toContain('loaded from history')
    expect(screen.getByTestId('history-summary').textContent).toContain('Run history (1)')
    expect(screen.getByText(/bounded in-memory session store/)).toBeInTheDocument()
  })

  it('explains that no graph exists and offers the demonstration DAG', async () => {
    await renderStudio({ graphs: [] })
    expect(screen.getByTestId('create-demo-graph').textContent).toContain(
      'Create the demonstration DAG',
    )
    expect(runButton().disabled).toBe(true)
    expect(screen.getByTestId('readiness-blocked').textContent).toContain(
      'No saved causal graph',
    )
  })
})
