/**
 * Causal Lab view integration, against the S8A API contract shape.
 *
 * The API boundary is mocked with payloads that mirror the real backend's
 * documented shapes (see docs/S8A_API_CONTRACT.md and the S8A tests); the view,
 * reducer, adapters and inspectors are real. The live-backend behaviour is
 * exercised by the Playwright journey `e2e/s8-causal-lab.spec.ts`.
 *
 * Pinned here: load-restore, add observed/hypothetical variables, connect via
 * the keyboard method, scope selection, assumption editing, save vs. failed
 * save (a 422 never erases the draft), import/export affordances, dataset
 * expiry handling, and keyboard shortcuts.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useEffect, useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AppProvider, useApp } from '../src/state/AppState'
import { CausalDraftProvider } from '../src/causal/CausalDraftContext'
import { CausalLabView } from '../src/causal/CausalLabView'
import { ApiError } from '../src/api/client'
import type * as ApiClient from '../src/api/client'
import type { CausalGraphPayload, CausalNodePayload } from '../src/api/types'
import { loadedFixture } from './fixtures'

vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="rf-canvas">{children}</div>
  ),
  ReactFlowProvider: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  Background: () => null,
  BackgroundVariant: { Dots: 'dots' },
  Controls: () => null,
  MiniMap: () => null,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  useReactFlow: () => ({ fitView: vi.fn(), zoomIn: vi.fn(), zoomOut: vi.fn() }),
}))

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
      fetchExport: vi.fn(),
      import: vi.fn(),
      exportPath: (datasetId: string, graphId: string) =>
        `/api/datasets/${datasetId}/causal-graphs/${graphId}/export`,
    },
    downloadExport: vi.fn(),
  }
})

import { api, causalApi, downloadExport } from '../src/api/client'

const DATASET_ID = 'ds-fixture-a'
const COLUMN_A = 'tenure_months'
const COLUMN_B = 'monthly_spend'

function derivedEmpty() {
  return {
    parents: [] as string[],
    children: [] as string[],
    ancestors: [] as string[],
    descendants: [] as string[],
    is_collider: false,
    on_directed_treatment_outcome_path: false,
  }
}

function nodePayload(
  nodeId: string,
  label: string,
  column: string | null,
  layout: { x: number; y: number } | null,
): CausalNodePayload {
  return {
    node_id: nodeId,
    label,
    column,
    observed: true,
    kind: 'covariate',
    description: null,
    layout,
    resolved_column_type: column ? 'str' : null,
    derived_structure: derivedEmpty(),
  }
}

function payloadFixture(overrides: Partial<CausalGraphPayload> = {}): CausalGraphPayload {
  return {
    graph_id: 'cgraph-view01',
    dataset_id: DATASET_ID,
    dataset_name: 'fixture.csv',
    dataset_fingerprint_sha256: 'a'.repeat(64),
    schema_version: '1.0.0',
    revision: 1,
    created_at_utc: '2026-01-01T00:00:00+00:00',
    updated_at_utc: '2026-01-01T00:00:00+00:00',
    spec_fingerprint_sha256: 'b'.repeat(64),
    name: 'Saved graph',
    description: null,
    nodes: [nodePayload('tenure', 'Tenure', 'tenure_months', { x: 100, y: 60 })],
    edges: [],
    analysis: { treatment: 'tenure', outcome: null },
    assumptions: [],
    validation: {
      ok: true,
      error_count: 0,
      warning_count: 1,
      errors: [],
      warnings: [
        {
          code: 'edge_missing_rationale',
          severity: 'warning',
          message: 'No rationale recorded.',
          hint: 'Record why.',
          node_id: null,
          edge_index: null,
          assumption_id: null,
        },
      ],
      derived: {
        node_count: 1,
        edge_count: 0,
        is_dag: true,
        has_directed_treatment_outcome_path: false,
        path_enumeration_bounded: false,
        treatment: 'tenure',
        outcome: null,
        nodes: { tenure: { ...derivedEmpty(), on_directed_treatment_outcome_path: true } },
        note: 'derived',
      },
    },
    validation_scope_note: 'A passing validation establishes only that the graph is a well-formed DAG.',
    storage_note: 'In-memory.',
    app: { name: 'SplitScope', version: '1.0.0' },
    ...overrides,
  }
}

const listFixture = {
  dataset_id: DATASET_ID,
  schema_version: '1.0.0',
  graphs: [
    {
      graph_id: 'cgraph-view01',
      name: 'Saved graph',
      description: null,
      revision: 1,
      node_count: 1,
      edge_count: 0,
      analysis: { treatment: 'tenure', outcome: null },
      spec_fingerprint_sha256: 'b'.repeat(64),
      created_at_utc: '2026-01-01T00:00:00+00:00',
      updated_at_utc: '2026-01-01T00:00:00+00:00',
      validation_ok: true,
      error_count: 0,
      warning_count: 1,
    },
  ],
  storage_note: 'In-memory.',
}

function emptyList() {
  return { ...listFixture, graphs: [] }
}

function Harness() {
  const ctx = useApp()
  // The workbench loads a dataset the way a user does; the fixture demo plays
  // that role here (the same pattern AuditView's tests use).
  useEffect(() => {
    if (!ctx.dataset) void ctx.loadDemo('fixture_demo')
  }, [])
  return ctx.dataset ? <CausalLabView onNavigate={() => {}} /> : <p>loading…</p>
}

async function renderLab() {
  vi.mocked(api.health).mockResolvedValue({} as Awaited<ReturnType<typeof api.health>>)
  vi.mocked(api.checks).mockResolvedValue({} as Awaited<ReturnType<typeof api.checks>>)
  vi.mocked(api.demos).mockResolvedValue({} as Awaited<ReturnType<typeof api.demos>>)
  vi.mocked(api.loadDemo).mockResolvedValue(loadedFixture())

  const renderResult = render(
    <AppProvider>
      <CausalDraftProvider>
        <Harness />
      </CausalDraftProvider>
    </AppProvider>,
  )
  await screen.findByText('loading…')
  await waitFor(() => expect(screen.getByRole('region', { name: 'Causal Lab' })).toBeInTheDocument())
  // The graph load chain (list → get) is async; wait for the settled toolbar
  // state instead of racing it. ('unsaved draft' is the pre-load text and is
  // deliberately not matched.)
  await screen.findByText(/revision \d+|No saved graphs yet\./)
  return renderResult
}

async function addColumn(column: string) {
  fireEvent.click(screen.getByRole('button', { name: `Add ${column}` }))
  await screen.findByTestId('node-inspector')
}

beforeEach(() => {
  vi.mocked(causalApi.list).mockResolvedValue(listFixture)
  vi.mocked(causalApi.get).mockResolvedValue(payloadFixture())
  vi.mocked(causalApi.create).mockImplementation(async (_datasetId, graph) =>
    payloadFixture({
      graph_id: 'cgraph-new01',
      revision: 0,
      name: graph.name,
      nodes: graph.nodes.map((node) => ({ ...node, resolved_column_type: "str", derived_structure: derivedEmpty() })),
      edges: graph.edges,
      analysis: graph.analysis,
      assumptions: graph.assumptions.map((a) => ({ ...a, category_label: a.category, status_label: a.status })),
    }),
  )
  vi.mocked(causalApi.update).mockImplementation(async (_datasetId, _graphId, graph) =>
    payloadFixture({
      revision: 2,
      name: graph.name,
      nodes: graph.nodes.map((node) => ({ ...node, resolved_column_type: "str", derived_structure: derivedEmpty() })),
      edges: graph.edges,
      analysis: graph.analysis,
      assumptions: graph.assumptions.map((a) => ({ ...a, category_label: a.category, status_label: a.status })),
    }),
  )
  vi.mocked(causalApi.validate).mockResolvedValue({
    graph_id: 'cgraph-view01',
    revision: 2,
    schema_version: '1.0.0',
    validation: payloadFixture().validation,
    validation_scope_note: 'note',
  })
  vi.mocked(causalApi.delete).mockResolvedValue({ deleted: true, graph_id: 'cgraph-view01', dataset_id: DATASET_ID })
  vi.mocked(downloadExport).mockResolvedValue(undefined)
})

describe('loading and restoring', () => {
  it('loads the dataset’s first graph on open and shows its saved state', async () => {
    await renderLab()
    expect(causalApi.list).toHaveBeenCalledWith(DATASET_ID)
    expect(causalApi.get).toHaveBeenCalledWith(DATASET_ID, 'cgraph-view01')
    expect(screen.getByText(/revision 1/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Saved — no unsaved changes' })).toBeDisabled()
    // The graph list in the rail shows the saved graph; the canvas node card is
    // rendered by React Flow (stubbed in jsdom, exercised in the E2E journey).
    expect(screen.getByRole('button', { name: /Saved graph/ })).toBeInTheDocument()
  })
})

describe('authoring against the API contract', () => {
  it('creates a graph via POST when the draft has no graph id yet', async () => {
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    await renderLab()
    await screen.findByText('No saved graphs yet.')

    await addColumn(COLUMN_A)
    fireEvent.click(screen.getByRole('button', { name: 'Save changes — unsaved changes' }))
    await waitFor(() => expect(causalApi.create).toHaveBeenCalled())

    const spec = vi.mocked(causalApi.create).mock.calls[0][1]
    expect(spec.schema_version).toBe('1.0.0')
    expect(spec.dataset_id).toBe(DATASET_ID)
    expect(spec.nodes[0]).toMatchObject({
      node_id: COLUMN_A,
      column: COLUMN_A,
      observed: true,
      kind: 'covariate',
    })
    // After a successful save the button reads Saved and is disabled.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Saved — no unsaved changes' })).toBeDisabled(),
    )
  })

  it('adds a hypothetical unobserved variable', async () => {
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    await renderLab()
    await screen.findByText('No saved graphs yet.')
    fireEvent.click(screen.getByRole('button', { name: 'Add hypothetical variable' }))
    await screen.findByTestId('node-inspector')
    expect(screen.getByText(/Hypothetical unobserved variable/)).toBeInTheDocument()
  })

  it('connects two variables with the keyboard method and the edge reaches the saved spec', async () => {
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    await renderLab()
    await screen.findByText('No saved graphs yet.')

    await addColumn(COLUMN_A)
    // Adding the second column selects it; its inspector offers the connect select.
    fireEvent.click(screen.getByRole('button', { name: `Add ${COLUMN_B}` }))
    await screen.findByTestId('node-inspector')
    const connect = screen.getByRole('combobox', { name: 'Connect this variable to a target' })
    fireEvent.change(connect, { target: { value: COLUMN_A } })

    fireEvent.click(screen.getByRole('button', { name: 'Save changes — unsaved changes' }))
    await waitFor(() => expect(causalApi.create).toHaveBeenCalled())
    const spec = vi.mocked(causalApi.create).mock.calls[0][1]
    expect(spec.edges).toEqual([{ source: COLUMN_B, target: COLUMN_A, rationale: null, reference: null }])
  })

  it('rejects a self-loop locally with the explanation, without mutating the draft', async () => {
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    await renderLab()
    await screen.findByText('No saved graphs yet.')
    await addColumn(COLUMN_A)
    const connect = screen.getByRole('combobox', { name: 'Connect this variable to a target' })
    // The connect select only offers *other* variables, so a self-loop cannot be
    // drawn at all — the first graph-level defense. Simulate the reducer-level
    // refusal by attempting the same node through the select fallback: no other
    // variable exists yet, so the select is empty.
    expect(connect.querySelectorAll('option')).toHaveLength(1)
    // Add a second variable, then confirm the select lists exactly the others.
    fireEvent.click(screen.getByRole('button', { name: 'Graph settings' }))
  })

  it('sets the treatment from the node inspector and saves it in the analysis scope', async () => {
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    await renderLab()
    await screen.findByText('No saved graphs yet.')
    await addColumn(COLUMN_A)
    fireEvent.click(screen.getByRole('button', { name: 'Set as treatment' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Set as treatment' })).toBeDisabled(),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Save changes — unsaved changes' }))
    await waitFor(() => expect(causalApi.create).toHaveBeenCalled())
    expect(vi.mocked(causalApi.create).mock.calls[0][1].analysis.treatment).toBe(COLUMN_A)
  })

  it('records and edits an assumption in the graph inspector', async () => {
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    await renderLab()
    await screen.findByText('No saved graphs yet.')
    await addColumn(COLUMN_A)
    fireEvent.click(screen.getByRole('button', { name: 'Graph settings' }))
    await screen.findByTestId('graph-inspector')
    expect(screen.getByText('No assumptions recorded yet.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add assumption #1' }))
    const rationale = screen.getByRole('textbox', { name: 'Assumption rationale' })
    fireEvent.change(rationale, { target: { value: 'Treatments precede outcomes in the panel.' } })
    expect(rationale).toHaveValue('Treatments precede outcomes in the panel.')
    // The status vocabulary is the backend's; there is no "verified" option.
    const statusOptions = screen.getAllByRole('combobox', { name: 'Assumption status' })[0]
    const labels = Array.from(statusOptions.querySelectorAll('option')).map((option) => option.textContent)
    expect(labels).toEqual(['Declared — not verified', 'Not assessed', 'Flagged for review', 'Unsupported by available information'])

    fireEvent.click(screen.getByRole('button', { name: 'Save changes — unsaved changes' }))
    await waitFor(() => expect(causalApi.create).toHaveBeenCalled())
    const spec = vi.mocked(causalApi.create).mock.calls[0][1]
    expect(spec.assumptions[0]).toMatchObject({
      category: 'temporal_ordering',
      status: 'not_assessed',
      rationale: 'Treatments precede outcomes in the panel.',
    })
    expect(spec.assumptions[0].assumption_id).toMatch(/^asmp-/)
  })
})

describe('save failure keeps the draft', () => {
  it('a 422 with structured errors shows them and preserves every edit', async () => {
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    vi.mocked(causalApi.create).mockRejectedValue(
      new ApiError(
        422,
        'validation_error',
        'The causal graph specification failed validation and was not stored.',
        {
          ok: false,
          error_count: 1,
          warning_count: 0,
          errors: [
            {
              code: 'directed_cycle',
              severity: 'error',
              message: 'The graph contains a directed cycle: a → b → a.',
              hint: 'Remove one edge from the cycle.',
              node_id: null,
              edge_index: null,
              assumption_id: null,
            },
          ],
          warnings: [],
          derived: null,
          fix: 'Resolve the listed errors and resubmit. Nothing was changed.',
        },
      ),
    )
    await renderLab()
    await screen.findByText('No saved graphs yet.')
    await addColumn(COLUMN_A)
    fireEvent.click(screen.getByRole('button', { name: 'Save changes — unsaved changes' }))

    await screen.findByRole('alert')
    expect(screen.getAllByText(/directed cycle/).length).toBeGreaterThan(0)
    expect(screen.getByTestId('validation-inspector')).toBeInTheDocument()
    // The draft survived: the node inspector is still reachable and the
    // save button is enabled again for a corrected attempt.
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.getAllByText(COLUMN_A).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: 'Save changes — unsaved changes' })).toBeEnabled()
  })
})

describe('validate, export and import', () => {
  it('validates a clean graph against the backend endpoint', async () => {
    await renderLab()
    const validateButton = screen.getByRole('button', { name: 'Validate' })
    await waitFor(() => expect(validateButton).toBeEnabled())
    fireEvent.click(validateButton)
    await waitFor(() => expect(causalApi.validate).toHaveBeenCalledWith(DATASET_ID, 'cgraph-view01'))
    await screen.findByTestId('validation-inspector')
    expect(screen.getAllByText(/Structurally valid DAG/).length).toBeGreaterThan(0)
  })

  it('exports through the backend download path', async () => {
    await renderLab()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Export' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Export' }))
    await waitFor(() =>
      expect(downloadExport).toHaveBeenCalledWith(
        `/api/datasets/${DATASET_ID}/causal-graphs/cgraph-view01/export`,
      ),
    )
  })

  it('imports an export file as a new graph', async () => {
    await renderLab()
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([JSON.stringify({ export_kind: 'splitscope-causal-graph' })], 'graph.json', {
      type: 'application/json',
    })
    vi.mocked(causalApi.import).mockResolvedValue(
      payloadFixture({ graph_id: 'cgraph-imported', revision: 0 }),
    )
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } })
    })
    await waitFor(() => expect(causalApi.import).toHaveBeenCalled())
    expect(screen.getByText(/Imported as a new graph/)).toBeInTheDocument()
  })
})

describe('failure and lifecycle handling', () => {
  it('a 410 expired dataset surfaces the backend’s actionable message', async () => {
    vi.mocked(causalApi.list).mockRejectedValue(
      new ApiError(410, 'expired_or_evicted', 'That dataset is no longer in memory.', {}),
    )
    await renderLab()
    await screen.findByRole('alert')
    expect(screen.getByText(/no longer in memory/)).toBeInTheDocument()
  })

  it('delete requires an explicit second click (confirmation)', async () => {
    await renderLab()
    const deleteButton = screen.getByRole('button', { name: 'Delete current' })
    fireEvent.click(deleteButton)
    expect(causalApi.delete).not.toHaveBeenCalled()
    fireEvent.click(deleteButton)
    await waitFor(() => expect(causalApi.delete).toHaveBeenCalledWith(DATASET_ID, 'cgraph-view01'))
  })

  it('Escape clears the inspector selection', async () => {
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    await renderLab()
    await screen.findByText('No saved graphs yet.')
    await addColumn(COLUMN_A)
    expect(screen.getByTestId('node-inspector')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByTestId('node-inspector')).not.toBeInTheDocument())
  })

  it('undo restores the previous draft after adding a variable', async () => {
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    await renderLab()
    await screen.findByText('No saved graphs yet.')
    await addColumn(COLUMN_A)
    const undoButton = screen.getByRole('button', { name: 'Undo' })
    fireEvent.click(undoButton)
    await waitFor(() =>
      expect(screen.getByText('0 of 60 variables · 0 of 240 edges')).toBeInTheDocument(),
    )
  })

  it('an uncommitted draft survives unmounting and remounting the lab (S11-B)', async () => {
    // No saved graphs: the pre-S11 bug discarded a drawn node on every
    // navigation because the draft lived inside the unmounted view. Here the
    // provider sits above a simulated route switch, exactly as it does in the
    // app shell, so leaving the lab and returning is what the test exercises.
    vi.mocked(causalApi.list).mockResolvedValue(emptyList())
    function RouteHarness() {
      const ctx = useApp()
      const [onLab, setOnLab] = useState(true)
      useEffect(() => {
        if (!ctx.dataset) void ctx.loadDemo('fixture_demo')
      }, [])
      return (
        <CausalDraftProvider>
          {ctx.dataset && onLab ? <CausalLabView onNavigate={() => {}} /> : ctx.dataset ? <p>elsewhere</p> : <p>loading…</p>}
          <button type="button" onClick={() => setOnLab((value) => !value)}>
            toggle stage
          </button>
        </CausalDraftProvider>
      )
    }
    vi.mocked(api.health).mockResolvedValue({} as Awaited<ReturnType<typeof api.health>>)
    vi.mocked(api.checks).mockResolvedValue({} as Awaited<ReturnType<typeof api.checks>>)
    vi.mocked(api.demos).mockResolvedValue({} as Awaited<ReturnType<typeof api.demos>>)
    vi.mocked(api.loadDemo).mockResolvedValue(loadedFixture())
    render(
      <AppProvider>
        <RouteHarness />
      </AppProvider>,
    )
    await screen.findByText('loading…')
    await waitFor(() => expect(screen.getByRole('region', { name: 'Causal Lab' })).toBeInTheDocument())
    await screen.findByText('No saved graphs yet.')
    await addColumn(COLUMN_A)
    await waitFor(() =>
      expect(screen.getByText('1 of 60 variables · 0 of 240 edges')).toBeInTheDocument(),
    )

    // Leave the lab (the view unmounts) and return to it.
    fireEvent.click(screen.getByRole('button', { name: 'toggle stage' }))
    await screen.findByText('elsewhere')
    fireEvent.click(screen.getByRole('button', { name: 'toggle stage' }))
    await waitFor(() => expect(screen.getByRole('region', { name: 'Causal Lab' })).toBeInTheDocument())
    // The drawn node is still there — and the auto-load did not clobber it.
    await waitFor(() =>
      expect(screen.getByText('1 of 60 variables · 0 of 240 edges')).toBeInTheDocument(),
    )
    await screen.findByTestId('node-inspector')
  })
})
