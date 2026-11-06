/**
 * Causal Research stage shell: study-context selection from stored runs,
 * refusal of stale runs, tab navigation and empty states. The API boundary is
 * mocked; the live behaviour is covered by the Playwright journeys.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useEffect } from 'react'
import { AppProvider, useApp } from '../src/state/AppState'
import { ResearchView } from '../src/research/ResearchView'
import type * as ApiClient from '../src/api/client'
import type { CausalGraphSummary } from '../src/api/types'
import { DATASET_ID, DATASET_FINGERPRINT, GRAPH_FINGERPRINT, GRAPH_ID, graphPayload, runPayload } from './estimationFixtures'
import { datasetSummaryFixture, loadedFixture } from './fixtures'
import { subgroupPayload } from './researchFixtures'

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
      subgroups: vi.fn(),
      robustness: vi.fn(),
      whatIf: vi.fn(),
    },
    downloadExport: vi.fn(),
  }
})

import { api, causalApi, estimationApi } from '../src/api/client'

function demoLoaded() {
  return loadedFixture({
    dataset: datasetSummaryFixture({
      dataset_id: DATASET_ID,
      name: 'causal_effect.csv',
      fingerprint_sha256: DATASET_FINGERPRINT,
      columns: ['age', 'baseline_score', 'region', 'treatment', 'outcome'],
      row_count: 1200,
      column_count: 5,
      demo_id: 'causal_effect',
    }),
  })
}

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

function Harness() {
  const ctx = useApp()
  useEffect(() => {
    if (!ctx.dataset) void ctx.loadDemo('causal_effect')
  }, [])
  return ctx.dataset ? <ResearchView onNavigate={() => {}} /> : <p>loading…</p>
}

async function renderStage() {
  vi.mocked(api.health).mockResolvedValue({} as Awaited<ReturnType<typeof api.health>>)
  vi.mocked(api.checks).mockResolvedValue({} as Awaited<ReturnType<typeof api.checks>>)
  vi.mocked(api.demos).mockResolvedValue({} as Awaited<ReturnType<typeof api.demos>>)
  vi.mocked(api.loadDemo).mockResolvedValue(demoLoaded())
  vi.mocked(causalApi.list).mockResolvedValue({
    dataset_id: DATASET_ID,
    graphs: [graphSummary()],
    schema_version: '1.0.0',
    storage_note: 'Bounded in-memory store.',
  })
  vi.mocked(causalApi.get).mockResolvedValue(graphPayload())
  vi.mocked(estimationApi.runs).mockResolvedValue({
    dataset_id: DATASET_ID,
    runs: [
      {
        run_id: 'run-stored-1',
        kind: 'estimation',
        dataset_id: DATASET_ID,
        label: 'comparison: treatment → outcome',
        created_seconds_ago: 90,
      },
    ],
  })
  vi.mocked(estimationApi.runDetail).mockResolvedValue(runPayload())

  render(
    <AppProvider>
      <Harness />
    </AppProvider>,
  )
  await screen.findByRole('region', { name: 'Study context' }, { timeout: 8000 })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ResearchView', () => {
  it('explains the dead end when no estimation runs exist yet', async () => {
    vi.mocked(estimationApi.runs).mockResolvedValue({ dataset_id: DATASET_ID, runs: [] })
    vi.mocked(api.loadDemo).mockResolvedValue(demoLoaded())
    vi.mocked(api.health).mockResolvedValue({} as Awaited<ReturnType<typeof api.health>>)
    vi.mocked(api.checks).mockResolvedValue({} as Awaited<ReturnType<typeof api.checks>>)
    vi.mocked(api.demos).mockResolvedValue({} as Awaited<ReturnType<typeof api.demos>>)
    render(
      <AppProvider>
        <Harness />
      </AppProvider>,
    )
    await screen.findByTestId('research-no-runs', {}, { timeout: 8000 })
    expect(screen.getByTestId('research-no-runs').textContent).toContain(
      'Effect Estimation Studio',
    )
    expect(estimationApi.runDetail).not.toHaveBeenCalled()
  }, 15000)

  it('loads a stored run and shows the study metadata it builds on', async () => {
    await renderStage()
    await waitFor(
      () =>
        expect(
          (screen.getByTestId('research-run-select') as HTMLSelectElement).disabled,
        ).toBe(false),
      { timeout: 8000 },
    )
    fireEvent.change(screen.getByTestId('research-run-select'), {
      target: { value: 'run-stored-1' },
    })
    await waitFor(
      () => expect(screen.getByTestId('research-study-meta')).toBeTruthy(),
      { timeout: 8000 },
    )
    const meta = screen.getByTestId('research-study-meta')
    expect(meta.textContent).toContain('treatment')
    expect(meta.textContent).toContain('outcome')
    expect(estimationApi.runDetail).toHaveBeenCalledWith(DATASET_ID, 'run-stored-1')
    expect(causalApi.get).toHaveBeenCalledWith(DATASET_ID, GRAPH_ID)
  }, 15000)

  it('refuses a stale stored run instead of building on it', async () => {
    await renderStage()
    vi.mocked(estimationApi.runDetail).mockResolvedValue({ ...runPayload(), stale: true })
    await waitFor(
      () =>
        expect(
          (screen.getByTestId('research-run-select') as HTMLSelectElement).disabled,
        ).toBe(false),
      { timeout: 8000 },
    )
    fireEvent.change(screen.getByTestId('research-run-select'), {
      target: { value: 'run-stored-1' },
    })
    await screen.findByTestId('research-study-error')
    expect(screen.getByTestId('research-study-error').textContent).toContain('stale')
    expect(causalApi.get).not.toHaveBeenCalled()
  }, 15000)

  it('switches between the three focused research views', async () => {
    await renderStage()
    await waitFor(
      () =>
        expect(
          (screen.getByTestId('research-run-select') as HTMLSelectElement).disabled,
        ).toBe(false),
      { timeout: 8000 },
    )
    fireEvent.change(screen.getByTestId('research-run-select'), {
      target: { value: 'run-stored-1' },
    })
    await waitFor(
      () => expect(screen.getByTestId('research-study-meta')).toBeTruthy(),
      { timeout: 8000 },
    )
    expect(screen.getByTestId('research-tab-subgroups')).toBeTruthy()
    fireEvent.click(screen.getByTestId('research-tab-robustness'))
    expect(screen.getByTestId('robustness-view')).toBeTruthy()
    fireEvent.click(screen.getByTestId('research-tab-whatif'))
    expect(screen.getByTestId('whatif-view')).toBeTruthy()
    fireEvent.click(screen.getByTestId('research-tab-subgroups'))
    expect(screen.getByTestId('subgroup-view')).toBeTruthy()
  }, 15000)

  it('offers the pretreatment graph nodes as subgroup variables, excluding treatment and outcome', async () => {
    vi.mocked(estimationApi.runDetail).mockResolvedValue(runPayload())
    vi.mocked(estimationApi.subgroups).mockResolvedValue(subgroupPayload())
    await renderStage()
    await waitFor(
      () =>
        expect(
          (screen.getByTestId('research-run-select') as HTMLSelectElement).disabled,
        ).toBe(false),
      { timeout: 8000 },
    )
    fireEvent.change(screen.getByTestId('research-run-select'), {
      target: { value: 'run-stored-1' },
    })
    const select = await screen.findByTestId('subgroup-variable', {}, { timeout: 8000 })
    const options = Array.from(select.querySelectorAll('option')).map((option) => option.value)
    expect(options).toContain('age')
    expect(options).toContain('baseline_score')
    expect(options).toContain('region')
    expect(options).not.toContain('treatment')
    expect(options).not.toContain('outcome')
  }, 15000)
})
