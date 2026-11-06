/**
 * S10-A Research history view: typed run projection, filters, staleness
 * honesty and manifest export. The API boundary is mocked with payloads
 * mirroring the backend contract (tests/test_s10_history.py is the live
 * counterpart); the view, filters, staleness banner and parameter expansion
 * are real.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HistoryView } from '../src/views/HistoryView'
import { researchApi } from '../src/api/client'
import type * as ApiClient from '../src/api/client'
import type { HistoryEntry, HistoryResponse } from '../src/api/types'

vi.mock('../src/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof ApiClient>()
  return {
    ...actual,
    researchApi: {
      ...actual.researchApi,
      runHistory: vi.fn(),
      runManifest: vi.fn(),
    },
  }
})

const DATASET_ID = 'ds-hist-fixture'

function entryFixture(overrides: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    run_id: 'run-estimation-01',
    kind: 'estimation',
    analysis_kind: 'estimation_comparison',
    label: 'comparison: treatment → outcome',
    created_at_utc: '2026-11-07T00:00:00+00:00',
    age_seconds: 42.0,
    dataset: {
      dataset_id: DATASET_ID,
      dataset_name: 'history fixture.csv',
      dataset_fingerprint_sha256: 'a'.repeat(64),
    },
    study: { study_id: null, note: 'Studies are not currently linked to stored runs.' },
    parameters: {
      estimand: 'ate',
      treatment_node: 'treatment',
      outcome_node: 'outcome',
      adjustment_nodes: ['age', 'region'],
      estimators: ['regression_adjustment', 'ipw', 'aipw'],
      cohort_rows: 1200,
    },
    status: 'available',
    stale: false,
    staleness_reasons: [],
    graph: { graph_id: 'cgraph-1', graph_spec_fingerprint_sha256: 'b'.repeat(64), graph_revision: 1 },
    reproducibility: { resolved_seed: 11 },
    ...overrides,
  }
}

function historyFixture(overrides: Partial<HistoryResponse> = {}): HistoryResponse {
  return {
    history_schema_version: '1.0.0',
    generated_at_utc: '2026-11-07T00:01:00+00:00',
    dataset: {
      dataset_id: DATASET_ID,
      name: 'history fixture.csv',
      fingerprint_sha256: 'a'.repeat(64),
      row_count: 1200,
      column_count: 7,
    },
    runs: [
      entryFixture(),
      entryFixture({
        run_id: 'run-audit-01',
        kind: 'audit',
        analysis_kind: 'leakage_audit',
        label: 'Random split',
        created_at_utc: '2026-11-06T23:00:00+00:00',
        age_seconds: 4000,
        graph: null,
        reproducibility: {
          resolved_seed: null,
          note: 'This run kind predates structured reproducibility capture.',
        },
        parameters: { target: 'outcome', split: 'Random split', findings_total: 0 },
        stale: true,
        staleness_reasons: [
          'The dataset in memory no longer matches the fingerprint this run was computed on.',
        ],
      }),
      entryFixture({
        run_id: 'run-subgroups-01',
        kind: 'estimation',
        analysis_kind: 'subgroups',
        label: 'subgroups: region',
        age_seconds: 30,
        parameters: {
          estimand: 'ate',
          treatment_node: 'treatment',
          outcome_node: 'outcome',
          subgroup: { column: 'region', kind: 'categorical' },
        },
        graph: { graph_id: 'cgraph-1', graph_spec_fingerprint_sha256: 'b'.repeat(64), graph_revision: 1 },
      }),
    ],
    counts_by_analysis_kind: {
      estimation_comparison: 1,
      leakage_audit: 1,
      subgroups: 1,
    },
    stale_count: 1,
    storage_note: 'Runs live in this server’s bounded in-memory store (LRU, with a TTL).',
    store: { runs_used: 3, limits: { max_runs: 16, ttl_seconds: 3600 } },
    ...overrides,
  }
}

describe('HistoryView (S10-A)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function renderView() {
    render(
      <HistoryView
        dataset={{
          dataset: {
            dataset_id: DATASET_ID,
            name: 'history fixture.csv',
            source: 'demo',
            is_synthetic: true,
            fingerprint_sha256: 'a'.repeat(64),
            row_count: 1200,
            column_count: 7,
            created_at_utc: '2026-01-01T00:00:00+00:00',
            columns: [],
          },
        } as never}
        onNavigate={() => {}}
      />,
    )
  }

  it('lists every run with its identity, kind and staleness banner', async () => {
    vi.mocked(researchApi.runHistory).mockResolvedValue(historyFixture())
    renderView()
    await waitFor(() => expect(screen.getByTestId('history-view')).toBeInTheDocument())
    expect(screen.getByText('comparison: treatment → outcome')).toBeVisible()
    expect(screen.getByText('Random split')).toBeVisible()
    // The stale audit carries the spelled-out reason, not a bare badge.
    const staleAlert = screen.getByRole('alert')
    expect(staleAlert).toHaveTextContent('Stale.')
    expect(staleAlert).toHaveTextContent('no longer matches')
    // Estimated runs are not marked stale.
    const comparison = screen.getByTestId('history-run-run-estimation-01')
    expect(within(comparison).queryByRole('alert')).toBeNull()
  })

  it('filters by analysis kind and shows honest empty states', async () => {
    vi.mocked(researchApi.runHistory).mockResolvedValue(historyFixture())
    renderView()
    await waitFor(() => expect(screen.getByTestId('history-view')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Subgroup effects (1)' }))
    expect(screen.getByText('subgroups: region')).toBeVisible()
    expect(screen.queryByText('Random split')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Stale (1)' }))
    expect(screen.getByText('Random split')).toBeVisible()
    expect(screen.queryByText('subgroups: region')).toBeNull()
  })

  it('expands parameters and exports a metadata-only manifest', async () => {
    vi.mocked(researchApi.runHistory).mockResolvedValue(historyFixture())
    vi.mocked(researchApi.runManifest).mockResolvedValue({
      manifest_schema_version: '1.0.0',
      manifest_kind: 'reproducibility_manifest',
      generated_at_utc: '2026-11-07T00:02:00+00:00',
      run: {
        run_id: 'run-estimation-01',
        kind: 'estimation',
        analysis_kind: 'estimation_comparison',
        label: 'comparison: treatment → outcome',
        created_at_utc: '2026-11-07T00:00:00+00:00',
        stale: false,
        staleness_reasons: [],
      },
      dataset: {},
      study: { study_id: null, note: '' },
      graph: {},
      analysis_definition: {},
      cohort: {},
      reproducibility: {},
      results_included: 'metadata_only',
      reproduction_requirements: 'Reproduction requires the original dataset.',
      integrity: { canonical_json_sha256: 'c'.repeat(64), canonicalisation: 'sha256' },
    })
    renderView()
    await waitFor(() => expect(screen.getByTestId('history-view')).toBeInTheDocument())

    const row = screen.getByTestId('history-run-run-estimation-01')
    fireEvent.click(within(row).getByRole('button', { name: 'Details' }))
    expect(within(row).getByText('Adjustment set')).toBeVisible()
    expect(within(row).getByText('Cohort rows')).toBeVisible()

    // URL.createObjectURL is unavailable in jsdom; observe the download blob.
    const createdUrls: string[] = []
    const originalCreate = URL.createObjectURL
    const originalRevoke = URL.revokeObjectURL
    URL.createObjectURL = (blob: Blob) => {
      expect(blob.type).toBe('application/json')
      createdUrls.push('created')
      return 'blob:fixture'
    }
    URL.revokeObjectURL = () => {}
    fireEvent.click(within(row).getByRole('button', { name: 'Download manifest' }))
    await waitFor(() => expect(createdUrls).toHaveLength(1))
    URL.createObjectURL = originalCreate
    URL.revokeObjectURL = originalRevoke
    expect(researchApi.runManifest).toHaveBeenCalledWith(DATASET_ID, 'run-estimation-01')
  })

  it('shows the honest empty state for a session with no runs', async () => {
    vi.mocked(researchApi.runHistory).mockResolvedValue(historyFixture({ runs: [], stale_count: 0, counts_by_analysis_kind: {} }))
    renderView()
    await waitFor(() => expect(screen.getByTestId('history-view')).toBeInTheDocument())
    expect(screen.getByText('No runs in this filter')).toBeVisible()
    expect(screen.getByText(/Run an analysis first/)).toBeVisible()
  })
})
