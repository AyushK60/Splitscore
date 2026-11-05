/**
 * Causal Lab draft state: a pure reducer over the local, unsaved graph draft.
 *
 * Three layers of state are kept deliberately distinct (see the S8B brief):
 *
 * - `draft` — the user's working copy. Edits are never lost: a failed save or
 *   validation leaves `draft` untouched.
 * - `saved` — the last draft the server confirmed (the successfully saved
 *   revision). `isDirty` compares against this.
 * - `validation` — the backend's structured verdict on either the saved graph
 *   or a rejected save attempt.
 *
 * Every draft mutation funnels through `withHistory`, so undo/redo works over
 * the *draft*, never silently touching server state.
 */

import type {
  CausalAssumptionSpec,
  CausalEdgeSpec,
  CausalGraphPayload,
  CausalGraphSpec,
  CausalIssue,
  CausalNodeSpec,
  CausalValidation,
} from '../api/types'

export interface CausalDraft {
  name: string
  description: string
  nodes: CausalNodeSpec[]
  edges: CausalEdgeSpec[]
  analysis: { treatment: string | null; outcome: string | null }
  assumptions: CausalAssumptionSpec[]
}

export type Selection =
  | { kind: 'node'; id: string }
  | { kind: 'edge'; id: string }
  | { kind: 'graph' }
  | null

export interface CausalLabState {
  graphId: string | null
  revision: number
  saved: CausalDraft | null
  draft: CausalDraft
  validation: CausalValidation | null
  payload: CausalGraphPayload | null
  selected: Selection
  past: CausalDraft[]
  future: CausalDraft[]
  /** Last save/validation failure worth surfacing in the toolbar area. */
  lastError: { title: string; message: string } | null
}

export const ASSUMPTION_CATEGORIES: Array<{ value: CausalAssumptionSpec['category']; label: string }> = [
  { value: 'temporal_ordering', label: 'Temporal ordering' },
  { value: 'causal_relationships', label: 'Hypothesised causal relationships' },
  { value: 'unmeasured_confounding', label: 'Potential unmeasured confounding' },
  { value: 'consistency', label: 'Consistency / defined intervention' },
  { value: 'exchangeability', label: '(Conditional) exchangeability' },
  { value: 'positivity', label: 'Positivity / overlap' },
  { value: 'selection', label: 'Selection or sampling' },
  { value: 'measurement', label: 'Measurement limitations' },
  { value: 'target_population', label: 'Intended target population' },
]

export const ASSUMPTION_STATUSES: Array<{ value: CausalAssumptionSpec['status']; label: string }> = [
  { value: 'declared', label: 'Declared — not verified' },
  { value: 'not_assessed', label: 'Not assessed' },
  { value: 'flagged_for_review', label: 'Flagged for review' },
  { value: 'unsupported', label: 'Unsupported by available information' },
]

export const NODE_KINDS: Array<{ value: CausalNodeSpec['kind']; label: string }> = [
  { value: 'covariate', label: 'Covariate' },
  { value: 'treatment', label: 'Treatment / exposure' },
  { value: 'outcome', label: 'Outcome' },
  { value: 'mediator', label: 'Hypothesised mediator' },
  { value: 'effect_modifier', label: 'Hypothesised effect modifier' },
  { value: 'unobserved', label: 'Unobserved variable' },
]

/** Stable edge identity: duplicates are prevented at the reducer boundary. */
export function edgeKey(source: string, target: string): string {
  return `${source}->${target}`
}

/**
 * Canonical signature of the *scientific* content of a draft (S8C staleness).
 *
 * Identification results are tied to the exact content that produced them.
 * The signature covers edges, the analysis scope and per-node observed status
 * — the things that change what d-separation and the backdoor criterion
 * answer. Deliberately excluded: layout positions (dragging is not a
 * scientific edit), labels, names, descriptions and assumption prose, which
 * the identification mathematics never reads.
 */
export function scientificSignature(draft: CausalDraft): string {
  const nodes = draft.nodes
    .map((node) => ({ id: node.node_id, observed: node.observed }))
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
  const edges = draft.edges
    .map((edge) => `${edge.source}->${edge.target}`)
    .sort()
  return JSON.stringify({
    nodes,
    edges,
    analysis: { treatment: draft.analysis.treatment, outcome: draft.analysis.outcome },
  })
}

export function emptyDraft(datasetId: string): CausalDraft {
  void datasetId // kept for call-site symmetry; the dataset id lives in toSpec
  return {
    name: 'Untitled causal graph',
    description: '',
    nodes: [],
    edges: [],
    analysis: { treatment: null, outcome: null },
    assumptions: [],
  }
}

/** Payload → draft. Layout coordinates round-trip unchanged. */
export function draftFromPayload(payload: CausalGraphPayload): CausalDraft {
  return {
    name: payload.name,
    description: payload.description ?? '',
    nodes: payload.nodes.map((node) => ({
      node_id: node.node_id,
      label: node.label,
      column: node.column,
      observed: node.observed,
      kind: node.kind,
      description: node.description,
      layout: node.layout ? { ...node.layout } : null,
    })),
    edges: payload.edges.map((edge) => ({ ...edge })),
    analysis: { ...payload.analysis },
    assumptions: payload.assumptions.map((assumption) => ({
      assumption_id: assumption.assumption_id,
      category: assumption.category,
      status: assumption.status,
      source: assumption.source,
      rationale: assumption.rationale,
    })),
  }
}

export function isDirty(state: CausalLabState): boolean {
  if (state.saved === null) return true
  return JSON.stringify(state.draft) !== JSON.stringify(state.saved)
}

/** The scientific spec exactly as the S8A backend expects it. */
export function toSpec(
  draft: CausalDraft,
  datasetId: string,
  _graphId: string | null,
): CausalGraphSpec {
  void _graphId
  return {
    schema_version: '1.0.0',
    name: draft.name.trim() || 'Untitled causal graph',
    description: draft.description?.trim() ? draft.description.trim() : null,
    dataset_id: datasetId,
    nodes: draft.nodes,
    edges: draft.edges,
    analysis: draft.analysis,
    assumptions: draft.assumptions,
  }
}

export type LabAction =
  | { type: 'load'; payload: CausalGraphPayload }
  | { type: 'reset'; datasetId: string }
  | { type: 'addNode'; node: CausalNodeSpec }
  | { type: 'updateNode'; nodeId: string; patch: Partial<CausalNodeSpec> }
  | { type: 'moveNode'; nodeId: string; x: number; y: number }
  | { type: 'removeNode'; nodeId: string }
  | { type: 'addEdge'; edge: CausalEdgeSpec }
  | { type: 'updateEdge'; source: string; target: string; patch: Partial<CausalEdgeSpec> }
  | { type: 'removeEdge'; source: string; target: string }
  | { type: 'setAnalysis'; patch: Partial<CausalDraft['analysis']> }
  | { type: 'addAssumption'; assumption: CausalAssumptionSpec }
  | { type: 'updateAssumption'; assumptionId: string; patch: Partial<CausalAssumptionSpec> }
  | { type: 'removeAssumption'; assumptionId: string }
  | { type: 'setMeta'; patch: Partial<Pick<CausalDraft, 'name' | 'description'>> }
  | { type: 'saved'; payload: CausalGraphPayload }
  | { type: 'validation'; validation: CausalValidation }
  | { type: 'validationRejected'; issues: CausalIssue[]; message: string }
  | { type: 'error'; title: string; message: string }
  | { type: 'clearError' }
  | { type: 'select'; selection: Selection }
  | { type: 'undo' }
  | { type: 'redo' }

function withHistory(state: CausalLabState, next: CausalDraft): CausalLabState {
  return {
    ...state,
    draft: next,
    past: [...state.past.slice(-49), state.draft],
    future: [],
  }
}

/** Unique, schema-valid node id derived from a column name or a counter. */
export function slugifyNodeId(base: string, taken: Set<string>): string {
  const root = base
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60) || 'variable'
  let candidate = root
  let counter = 2
  while (taken.has(candidate)) {
    candidate = `${root}_${counter}`
    counter += 1
  }
  return candidate
}

export function causalLabReducer(state: CausalLabState, action: LabAction): CausalLabState {
  switch (action.type) {
    case 'load': {
      const draft = draftFromPayload(action.payload)
      return {
        ...state,
        graphId: action.payload.graph_id,
        revision: action.payload.revision,
        saved: draft,
        draft,
        validation: action.payload.validation,
        payload: action.payload,
        selected: null,
        past: [],
        future: [],
        lastError: null,
      }
    }
    case 'reset': {
      return {
        ...initialLabState(),
        draft: { ...emptyDraft(action.datasetId), description: '' },
        saved: null,
      }
    }
    case 'addNode': {
      if (state.draft.nodes.some((node) => node.node_id === action.node.node_id)) {
        return { ...state, lastError: { title: 'Duplicate node id', message: `A variable with id ${action.node.node_id} already exists.` } }
      }
      return withHistory(state, { ...state.draft, nodes: [...state.draft.nodes, action.node] })
    }
    case 'updateNode':
      return withHistory(state, {
        ...state.draft,
        nodes: state.draft.nodes.map((node) =>
          node.node_id === action.nodeId ? { ...node, ...action.patch } : node,
        ),
      })
    case 'moveNode':
      // Position changes are recorded without polluting undo history: dragging
      // is continuous, and each intermediate frame is not a scientific edit.
      return {
        ...state,
        draft: {
          ...state.draft,
          nodes: state.draft.nodes.map((node) =>
            node.node_id === action.nodeId
              ? { ...node, layout: { x: action.x, y: action.y } }
              : node,
          ),
        },
      }
    case 'removeNode': {
      const remaining = state.draft.nodes.filter((node) => node.node_id !== action.nodeId)
      const edges = state.draft.edges.filter(
        (edge) => edge.source !== action.nodeId && edge.target !== action.nodeId,
      )
      const analysis = { ...state.draft.analysis }
      if (analysis.treatment === action.nodeId) analysis.treatment = null
      if (analysis.outcome === action.nodeId) analysis.outcome = null
      const selected = state.selected
      const nextSelected: Selection =
        selected && selected.kind === 'node' && selected.id === action.nodeId ? null : selected
      return {
        ...withHistory(state, { ...state.draft, nodes: remaining, edges, analysis }),
        selected: nextSelected,
      }
    }
    case 'addEdge': {
      const key = edgeKey(action.edge.source, action.edge.target)
      if (action.edge.source === action.edge.target) {
        return {
          ...state,
          lastError: {
            title: 'Self-loop rejected',
            message: 'A causal graph cannot contain an edge from a variable to itself.',
          },
        }
      }
      if (
        state.draft.edges.some(
          (edge) => edgeKey(edge.source, edge.target) === key,
        )
      ) {
        return {
          ...state,
          lastError: {
            title: 'Duplicate edge rejected',
            message: `The directed edge ${key} already exists.`,
          },
        }
      }
      return withHistory(state, { ...state.draft, edges: [...state.draft.edges, action.edge] })
    }
    case 'updateEdge':
      return withHistory(state, {
        ...state.draft,
        edges: state.draft.edges.map((edge) =>
          edge.source === action.source && edge.target === action.target
            ? { ...edge, ...action.patch }
            : edge,
        ),
      })
    case 'removeEdge': {
      const edges = state.draft.edges.filter(
        (edge) => !(edge.source === action.source && edge.target === action.target),
      )
      const selected =
        state.selected?.kind === 'edge' && state.selected.id === edgeKey(action.source, action.target)
          ? null
          : state.selected
      return { ...withHistory(state, { ...state.draft, edges }), selected }
    }
    case 'setAnalysis':
      return withHistory(state, { ...state.draft, analysis: { ...state.draft.analysis, ...action.patch } })
    case 'addAssumption':
      return withHistory(state, {
        ...state.draft,
        assumptions: [...state.draft.assumptions, action.assumption],
      })
    case 'updateAssumption':
      return withHistory(state, {
        ...state.draft,
        assumptions: state.draft.assumptions.map((assumption) =>
          assumption.assumption_id === action.assumptionId
            ? { ...assumption, ...action.patch }
            : assumption,
        ),
      })
    case 'removeAssumption':
      return withHistory(state, {
        ...state.draft,
        assumptions: state.draft.assumptions.filter(
          (assumption) => assumption.assumption_id !== action.assumptionId,
        ),
      })
    case 'setMeta':
      return withHistory(state, { ...state.draft, ...action.patch })
    case 'saved': {
      const draft = draftFromPayload(action.payload)
      return {
        ...state,
        graphId: action.payload.graph_id,
        revision: action.payload.revision,
        saved: draft,
        validation: action.payload.validation,
        payload: action.payload,
        lastError: null,
      }
    }
    case 'validation':
      return { ...state, validation: action.validation, lastError: null }
    case 'validationRejected':
      // A rejected save keeps the draft exactly as it was: the user's work is
      // never erased by a failed validation.
      return {
        ...state,
        lastError: { title: 'Validation failed', message: action.message },
      }
    case 'error':
      return { ...state, lastError: { title: action.title, message: action.message } }
    case 'clearError':
      return { ...state, lastError: null }
    case 'select':
      return { ...state, selected: action.selection }
    case 'undo': {
      if (!state.past.length) return state
      const previous = state.past[state.past.length - 1]
      return {
        ...state,
        draft: previous,
        past: state.past.slice(0, -1),
        future: [state.draft, ...state.future.slice(0, 49)],
      }
    }
    case 'redo': {
      if (!state.future.length) return state
      const next = state.future[0]
      return {
        ...state,
        draft: next,
        past: [...state.past, state.draft],
        future: state.future.slice(1),
      }
    }
    default:
      return state
  }
}

export function initialLabState(): CausalLabState {
  return {
    graphId: null,
    revision: 0,
    saved: null,
    draft: {
      name: 'Untitled causal graph',
      description: '',
      nodes: [],
      edges: [],
      analysis: { treatment: null, outcome: null },
      assumptions: [],
    },
    validation: null,
    payload: null,
    selected: null,
    past: [],
    future: [],
    lastError: null,
  }
}

/**
 * Local, non-blocking pre-checks mirroring the backend schema. They exist only
 * to give instant feedback while drawing; the backend validation remains the
 * sole authority (the reducer refuses the same structures the S8A engine
 * rejects, so a draft can never drift into something the backend would accept
 * silently).
 */
export function localEdgeProblems(
  draft: CausalDraft,
  source: string,
  target: string,
): string | null {
  if (source === target) return 'A causal edge cannot loop from a variable back to itself.'
  if (draft.edges.some((edge) => edge.source === source && edge.target === target)) {
    return `The directed edge ${source} → ${target} already exists.`
  }
  return null
}
