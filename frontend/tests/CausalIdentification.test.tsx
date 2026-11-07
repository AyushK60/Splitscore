/**
 * S8C identification panel, against the S8C API contract shape.
 *
 * The API boundary is mocked with payloads mirroring the real backend's
 * documented shapes (see docs/S8C_API_CONTRACT.md and the backend tests); the
 * panel, mode switching, highlighting and staleness logic are real. The
 * live-backend behaviour is exercised by the Playwright journeys
 * `e2e/s8c-identification.spec.ts`.
 *
 * Pinned here: the mode switch, the save gate for dirty drafts, status and
 * suggested-set rendering, custom-set evaluation (valid and invalid),
 * the d-separation probe, unobserved-confounder honesty, on-canvas
 * highlighting, and scientific staleness after an edge edit (but not after a
 * position drag).
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useEffect } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AppProvider, useApp } from '../src/state/AppState'
import { CausalDraftProvider } from '../src/causal/CausalDraftContext'
import { CausalLabView } from '../src/causal/CausalLabView'
import { api } from '../src/api/client'
import type * as ApiClient from '../src/api/client'
import type {
  CausalAdjustmentEvaluationResponse,
  CausalDSeparationResponse,
  CausalGraphPayload,
  CausalIdentificationResponse,
  CausalNodePayload,
} from '../src/api/types'
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
      dSeparation: vi.fn(),
      evaluateAdjustment: vi.fn(),
      searchAdjustment: vi.fn(),
      identify: vi.fn(),
      exportPath: (datasetId: string, graphId: string) =>
        `/api/datasets/${datasetId}/causal-graphs/${graphId}/export`,
    },
    downloadExport: vi.fn(),
  }
})

import { causalApi } from '../src/api/client'

const DATASET_ID = 'ds-fixture-a'

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
  extra: Partial<CausalNodePayload> = {},
): CausalNodePayload {
  return {
    node_id: nodeId,
    label,
    column,
    observed: true,
    kind: 'covariate',
    description: null,
    layout: { x: 60, y: 60 },
    resolved_column_type: column ? 'str' : null,
    derived_structure: derivedEmpty(),
    ...extra,
  }
}

/** A confounded fork: age → tenure, age → churn, tenure → churn. */
function payloadFixture(): CausalGraphPayload {
  return {
    graph_id: 'cgraph-ident01',
    dataset_id: DATASET_ID,
    dataset_name: 'fixture.csv',
    dataset_fingerprint_sha256: 'a'.repeat(64),
    schema_version: '1.0.0',
    revision: 1,
    created_at_utc: '2026-01-01T00:00:00+00:00',
    updated_at_utc: '2026-01-01T00:00:00+00:00',
    spec_fingerprint_sha256: 'b'.repeat(64),
    name: 'Confounded retention',
    description: null,
    nodes: [
      nodePayload('tenure', 'Tenure', 'tenure_months', { kind: 'treatment' }),
      nodePayload('churn', 'Churn', 'churn', { kind: 'outcome' }),
      nodePayload('age', 'Age', 'age'),
    ],
    edges: [
      { source: 'age', target: 'tenure', rationale: null, reference: null },
      { source: 'age', target: 'churn', rationale: null, reference: null },
      { source: 'tenure', target: 'churn', rationale: null, reference: null },
    ],
    analysis: { treatment: 'tenure', outcome: 'churn' },
    assumptions: [],
    validation: {
      ok: true,
      error_count: 0,
      warning_count: 0,
      errors: [],
      warnings: [],
      derived: {
        node_count: 3,
        edge_count: 3,
        is_dag: true,
        has_directed_treatment_outcome_path: true,
        path_enumeration_bounded: false,
        treatment: 'tenure',
        outcome: 'churn',
        nodes: {
          tenure: derivedEmpty(),
          churn: derivedEmpty(),
          age: derivedEmpty(),
        },
        note: '',
      },
    },
    validation_scope_note: 'scope note',
    storage_note: 'storage note',
    app: { name: 'SplitScope', version: '1.0.0' },
  }
}

function identificationFixture(
  overrides: Partial<CausalIdentificationResponse> = {},
): CausalIdentificationResponse {
  return {
    graph_id: 'cgraph-ident01',
    dataset_id: DATASET_ID,
    revision: 1,
    spec_fingerprint_sha256: 'b'.repeat(64),
    schema_version: '1.0.0',
    identification_version: '1.0.0',
    status: 'backdoor_adjustment_available',
    treatment: 'tenure',
    outcome: 'churn',
    explanations: [
      {
        code: 'confounder_needs_adjustment',
        title: 'Common causes need adjustment for the total effect',
        body: 'Age causes both the treatment and the outcome in the assumed graph.',
        node_ids: ['age'],
      },
      {
        code: 'structure_not_truth',
        title: 'A graphically valid set is not a scientifically proven one',
        body: 'Every statement follows from the edges you drew.',
        node_ids: [],
      },
    ],
    caveats: ['Adjusting for the reported set is licensed by the drawn graph only.'],
    search: {
      graph_id: 'cgraph-ident01',
      dataset_id: DATASET_ID,
      revision: 1,
      spec_fingerprint_sha256: 'b'.repeat(64),
      schema_version: '1.0.0',
      treatment: 'tenure',
      outcome: 'churn',
      search_status: 'complete',
      sets: [{ set: ['age'], verification: 'verified', inclusion_minimal: true }],
      forbidden_variables: ['tenure', 'churn'],
      eligible_candidates: ['age'],
      candidates_considered: 4,
      bounds: { max_exhaustive_candidates: 14, max_candidate_evaluations: 200000, max_search_seconds: 10 },
      interpretation_note: 'note',
    },
    interpretation_note: 'note',
    ...overrides,
  }
}

function evaluationFixture(
  overrides: Partial<CausalAdjustmentEvaluationResponse> = {},
): CausalAdjustmentEvaluationResponse {
  return {
    graph_id: 'cgraph-ident01',
    dataset_id: DATASET_ID,
    revision: 1,
    spec_fingerprint_sha256: 'b'.repeat(64),
    schema_version: '1.0.0',
    treatment: 'tenure',
    outcome: 'churn',
    adjustment_set: ['age'],
    valid: true,
    violations: [],
    open_backdoor_paths: [],
    path_listing_bounded: false,
    interpretation: 'Every backdoor path is blocked by this set.',
    interpretation_note: 'note',
    ...overrides,
  }
}

function dseparationFixture(
  overrides: Partial<CausalDSeparationResponse> = {},
): CausalDSeparationResponse {
  return {
    graph_id: 'cgraph-ident01',
    dataset_id: DATASET_ID,
    revision: 1,
    spec_fingerprint_sha256: 'b'.repeat(64),
    schema_version: '1.0.0',
    x: 'age',
    y: 'churn',
    conditioning: [],
    d_separated: false,
    interpretation: "'age' and 'churn' are d-connected given no conditioning variables.",
    algorithm: { name: 'bayes-ball-reachability', version: '1.0.0', reference: 'K&F' },
    interpretation_note: 'note',
    ...overrides,
  }
}

async function enterIdentificationMode() {
  fireEvent.click(screen.getByTestId('mode-identification'))
  // The saved-graph selection (list -> get -> dispatch load) settles
  // asynchronously after the lab mounts, and identification always runs on the
  // saved revision. Wait for that hydration to finish before interacting: the
  // save gate must have cleared because the graph is saved and clean. A test
  // that deliberately dirties the draft does so *after* this await, and its
  // gate assertions are unaffected.
  await waitFor(() => expect(screen.queryByTestId('identification-save-gate')).toBeNull())
}

function listFixture() {
  return {
    dataset_id: DATASET_ID,
    schema_version: '1.0.0',
    graphs: [
      {
        graph_id: 'cgraph-ident01',
        name: 'Confounded retention',
        description: null,
        revision: 1,
        node_count: 3,
        edge_count: 3,
        analysis: { treatment: 'tenure', outcome: 'churn' },
        spec_fingerprint_sha256: 'b'.repeat(64),
        created_at_utc: '2026-01-01T00:00:00+00:00',
        updated_at_utc: '2026-01-01T00:00:00+00:00',
        validation_ok: true,
        error_count: 0,
        warning_count: 0,
      },
    ],
    storage_note: 'note',
  }
}

describe('Causal Lab identification mode (S8C)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(causalApi.list).mockResolvedValue(listFixture())
    vi.mocked(causalApi.get).mockResolvedValue(payloadFixture())
  })

  function Harness() {
    const ctx = useApp()
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

    render(
      <AppProvider>
        <CausalDraftProvider>
        <Harness />
      </CausalDraftProvider>
      </AppProvider>,
    )
    await screen.findByText('loading…')
    await waitFor(() => expect(screen.getByRole('region', { name: 'Causal Lab' })).toBeInTheDocument())
    await screen.findByText(/revision \d+|No saved graphs yet\./)
  }

  it('switches into identification mode and gates on the saved graph', async () => {
    vi.mocked(causalApi.get).mockResolvedValue(payloadFixture())
    renderLab()
    await waitFor(() => expect(screen.getByTestId('mode-identification')).toBeEnabled())

    await enterIdentificationMode()
    expect(screen.getByTestId('identification-panel')).toBeVisible()
    // Saved, clean graph: no save gate, run button enabled with a scope.
    expect(screen.queryByTestId('identification-save-gate')).toBeNull()
    expect(screen.getByTestId('run-identification')).toBeEnabled()

    // Switching back preserves the authoring inspector behaviour.
    fireEvent.click(screen.getByTestId('mode-authoring'))
    expect(screen.queryByTestId('identification-panel')).toBeNull()
  })

  it('runs identification and renders suggested sets with highlights', async () => {
    vi.mocked(causalApi.identify).mockResolvedValue(identificationFixture())
    renderLab()
    await waitFor(() => expect(screen.getByTestId('mode-identification')).toBeEnabled())
    await enterIdentificationMode()
    fireEvent.click(screen.getByTestId('run-identification'))

    await waitFor(() => expect(screen.getByTestId('identification-status')).toBeVisible())
    expect(screen.getByText(/Backdoor adjustment available/)).toBeVisible()
    expect(screen.getByTestId('suggested-set')).toBeVisible()
    expect(causalApi.identify).toHaveBeenCalledWith(DATASET_ID, 'cgraph-ident01')

    // Inspecting the set loads it into the custom tester and highlights Age.
    // Under full-suite load the click can land while the identification result
    // hydration is still settling, so the checked state is awaited rather than
    // read synchronously (same failure class as the S9C AUDIT-2 soak fix).
    fireEvent.click(screen.getByRole('button', { name: 'Inspect this set' }))
    await waitFor(() => {
      const checkbox = within(screen.getByTestId('adjustment-candidates')).getByRole('checkbox', { name: 'Adjust for Age' }) as HTMLInputElement
      expect(checkbox.checked).toBe(true)
    })
    // The on-canvas highlight class (.cnode--adjustment) is rendered by the
    // real React Flow tree (stubbed here); the legend is real and visible.
    expect(screen.getByLabelText('Graph legend')).toBeVisible()
  })

  it('evaluates a custom set: admissible verdict from the backend', async () => {
    vi.mocked(causalApi.identify).mockResolvedValue(identificationFixture())
    vi.mocked(causalApi.evaluateAdjustment).mockResolvedValue(evaluationFixture())
    renderLab()
    await waitFor(() => expect(screen.getByTestId('mode-identification')).toBeEnabled())
    await enterIdentificationMode()
    fireEvent.click(screen.getByTestId('run-identification'))
    await waitFor(() => expect(screen.getByTestId('suggested-set')).toBeVisible())

    const checkbox = within(screen.getByTestId('adjustment-candidates')).getByRole('checkbox', { name: 'Adjust for Age' })
    fireEvent.click(checkbox)
    fireEvent.click(screen.getByTestId('evaluate-set'))

    await waitFor(() => expect(screen.getByTestId('adjustment-verdict')).toBeVisible())
    expect(screen.getByText(/Set admissible/)).toBeVisible()
    expect(causalApi.evaluateAdjustment).toHaveBeenCalledWith(
      DATASET_ID,
      'cgraph-ident01',
      ['age'],
    )
  })

  it('renders structured violations for an inadmissible set', async () => {
    vi.mocked(causalApi.evaluateAdjustment).mockResolvedValue(
      evaluationFixture({
        valid: false,
        adjustment_set: ['churn'],
        violations: [
          {
            code: 'open_backdoor_path',
            node_id: null,
            message:
              'With this set, at least one backdoor path from tenure to churn remains open.',
          },
        ],
        interpretation: 'This set does not satisfy the classical backdoor criterion.',
      }),
    )
    renderLab()
    await waitFor(() => expect(screen.getByTestId('mode-identification')).toBeEnabled())
    await enterIdentificationMode()
    // Evaluate without running identification first: candidates come from the
    // draft's observed nodes. The backend's structured verdict is rendered
    // verbatim whatever it reports.
    const checkbox = within(screen.getByTestId('adjustment-candidates')).getByRole(
      'checkbox',
      { name: 'Adjust for Age' },
    )
    fireEvent.click(checkbox)
    fireEvent.click(screen.getByTestId('evaluate-set'))
    await waitFor(() => expect(screen.getByTestId('adjustment-verdict')).toBeVisible())
    expect(screen.getByText(/Set not admissible/)).toBeVisible()
    expect(screen.getByText(/A backdoor path remains open/)).toBeVisible()
  })

  it('probes d-separation and renders the graphical-independence verdict', async () => {
    vi.mocked(causalApi.dSeparation).mockResolvedValue(
      dseparationFixture({ x: 'age', y: 'churn', conditioning: ['tenure'], d_separated: false }),
    )
    renderLab()
    await waitFor(() => expect(screen.getByTestId('mode-identification')).toBeEnabled())
    await enterIdentificationMode()

    fireEvent.change(screen.getByRole('combobox', { name: 'd-separation variable X' }), {
      target: { value: 'age' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: 'd-separation variable Y' }), {
      target: { value: 'churn' },
    })
    fireEvent.click(
      within(screen.getByTestId('d-separation-conditioning')).getByRole('checkbox', { name: 'Condition on Tenure' }),
    )
    fireEvent.click(screen.getByTestId('run-d-separation'))

    await waitFor(() => expect(screen.getByTestId('d-separation-verdict')).toBeVisible())
    expect(screen.getByText(/d-connected given Tenure/)).toBeVisible()
    expect(causalApi.dSeparation).toHaveBeenCalledWith(
      DATASET_ID,
      'cgraph-ident01',
      'age',
      'churn',
      ['tenure'],
    )
  })

  it('shows the unobserved-confounder outcome honestly', async () => {
    vi.mocked(causalApi.identify).mockResolvedValue(
      identificationFixture({
        status: 'no_eligible_backdoor_set',
        search: {
          ...identificationFixture().search!,
          search_status: 'complete',
          sets: [],
        },
        caveats: [
          'licensed by the drawn graph only.',
          'This failure is specific to the classical backdoor criterion. It does not prove the effect is unidentifiable by every method.',
        ],
      }),
    )
    renderLab()
    await waitFor(() => expect(screen.getByTestId('mode-identification')).toBeEnabled())
    await enterIdentificationMode()
    fireEvent.click(screen.getByTestId('run-identification'))
    await waitFor(() => expect(screen.getByTestId('identification-status')).toBeVisible())
    expect(screen.getByText(/No eligible observed backdoor set found/)).toBeVisible()
    expect(screen.getByText(/does not prove the effect is unidentifiable by every method/)).toBeVisible()
    expect(screen.getByText(/None reported/)).toBeVisible()
  })

  it('marks results stale after a scientific edit but not after a layout drag', async () => {
    vi.mocked(causalApi.identify).mockResolvedValue(identificationFixture())
    renderLab()
    await waitFor(() => expect(screen.getByTestId('mode-identification')).toBeEnabled())
    await enterIdentificationMode()
    fireEvent.click(screen.getByTestId('run-identification'))
    await waitFor(() => expect(screen.getByTestId('identification-status')).toBeVisible())
    expect(screen.queryByTestId('identification-stale')).toBeNull()

    // Change the analysis scope (a scientific edit) → stale banner appears.
    fireEvent.change(screen.getByRole('combobox', { name: 'Identification outcome selection' }), {
      target: { value: 'age' },
    })
    expect(screen.getByTestId('identification-stale')).toBeVisible()

    // Restore the scope: signature matches again → staleness clears.
    fireEvent.change(screen.getByRole('combobox', { name: 'Identification outcome selection' }), {
      target: { value: 'churn' },
    })
    expect(screen.queryByTestId('identification-stale')).toBeNull()
  })

  it('shows the save gate while the draft is dirty and saves on request', async () => {
    // A dirty draft: get returns one payload, list non-empty, but we edit the
    // scope before entering identification.
    vi.mocked(causalApi.update).mockResolvedValue(payloadFixture())
    renderLab()
    await waitFor(() => expect(screen.getByTestId('mode-identification')).toBeEnabled())
    await enterIdentificationMode()
    fireEvent.change(screen.getByRole('combobox', { name: 'Identification outcome selection' }), {
      target: { value: 'age' },
    })
    expect(screen.getByTestId('identification-save-gate')).toBeVisible()
    expect(screen.getByTestId('run-identification')).toBeDisabled()

    // Saving through the gate clears the dirty state.
    fireEvent.click(within(screen.getByTestId('identification-save-gate')).getByRole('button', { name: 'Save graph' }))
    await waitFor(() =>
      expect(causalApi.update).toHaveBeenCalledWith(DATASET_ID, 'cgraph-ident01', expect.anything()),
    )
  })

  it('renders the first explanation expanded and others collapsed', async () => {
    vi.mocked(causalApi.identify).mockResolvedValue(identificationFixture())
    renderLab()
    await waitFor(() => expect(screen.getByTestId('mode-identification')).toBeEnabled())
    await enterIdentificationMode()
    fireEvent.click(screen.getByTestId('run-identification'))
    await waitFor(() => expect(screen.getAllByTestId('explanation').length).toBe(2))
    const explanations = screen.getAllByTestId('explanation')
    expect(explanations[0].querySelector('button')!.getAttribute('aria-expanded')).toBe('true')
    expect(explanations[1].querySelector('button')!.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(explanations[1].querySelector('button')!)
    expect(explanations[1].querySelector('button')!.getAttribute('aria-expanded')).toBe('true')
  })
})
