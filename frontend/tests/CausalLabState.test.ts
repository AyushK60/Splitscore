/**
 * Causal Lab reducer and adapter contracts.
 *
 * The reducer is the local-draft authority: these tests pin the invariants the
 * S8B brief demands — invalid structures are refused without mutating the
 * draft, deleting a node cascades to its edges and analysis scope, undo/redo
 * never loses the redo stack ordering, and payloads round-trip with layout
 * coordinates intact. Teaching examples must satisfy the S8A schema exactly.
 */
import { describe, expect, it } from 'vitest'

import type { CausalGraphPayload, CausalNodeSpec } from '../src/api/types'
import {
  causalLabReducer,
  draftFromPayload,
  edgeKey,
  emptyDraft,
  initialLabState,
  isDirty,
  localEdgeProblems,
  slugifyNodeId,
  toSpec,
} from '../src/causal/CausalLabState'
import { teachingExample, toFlowNodes, issueIndex } from '../src/causal/adapter'

function node(nodeId: string, overrides: Partial<CausalNodeSpec> = {}): CausalNodeSpec {
  return {
    node_id: nodeId,
    label: nodeId.toUpperCase(),
    column: null,
    observed: true,
    kind: 'covariate',
    description: null,
    layout: null,
    ...overrides,
  }
}

function payloadFixture(overrides: Partial<CausalGraphPayload> = {}): CausalGraphPayload {
  return {
    graph_id: 'cgraph-fixture01',
    dataset_id: 'ds-test',
    dataset_name: 'fixture.csv',
    dataset_fingerprint_sha256: 'a'.repeat(64),
    schema_version: '1.0.0',
    revision: 2,
    created_at_utc: '2026-01-01T00:00:00+00:00',
    updated_at_utc: '2026-01-01T00:00:00+00:00',
    spec_fingerprint_sha256: 'b'.repeat(64),
    name: 'Retention hypothesis',
    description: null,
    nodes: [
      {
        ...node('tenure', { column: 'tenure_months', kind: 'treatment' }),
        resolved_column_type: 'str',
        derived_structure: {
          parents: ['age'],
          children: ['churn'],
          ancestors: ['age'],
          descendants: ['churn'],
          is_collider: false,
          on_directed_treatment_outcome_path: true,
        },
        layout: { x: 120, y: 40 },
      },
      {
        ...node('churn', { column: 'churn', kind: 'outcome' }),
        resolved_column_type: 'str',
        derived_structure: {
          parents: ['tenure'],
          children: [],
          ancestors: ['tenure', 'age'],
          descendants: [],
          is_collider: false,
          on_directed_treatment_outcome_path: false,
        },
        layout: { x: 400, y: 40 },
      },
    ],
    edges: [{ source: 'tenure', target: 'churn', rationale: 'hypothesised', reference: null }],
    analysis: { treatment: 'tenure', outcome: 'churn' },
    assumptions: [
      {
        assumption_id: 'asmp-1',
        category: 'target_population',
        status: 'declared',
        source: 'study card',
        rationale: 'adult subscribers',
        category_label: 'Intended target population',
        status_label: 'Declared by you; not verified',
      },
    ],
    validation: {
      ok: true,
      error_count: 0,
      warning_count: 0,
      errors: [],
      warnings: [],
      derived: {
        node_count: 2,
        edge_count: 1,
        is_dag: true,
        has_directed_treatment_outcome_path: true,
        path_enumeration_bounded: false,
        treatment: 'tenure',
        outcome: 'churn',
        nodes: {},
        note: 'derived from the drawn edges',
      },
    },
    validation_scope_note: 'A passing validation establishes only that the graph is a well-formed DAG.',
    storage_note: 'In-memory.',
    app: { name: 'SplitScope', version: '1.0.0' },
    ...overrides,
  }
}

describe('draft <-> payload round-trip', () => {
  it('restores the draft from a payload with layout coordinates intact', () => {
    const draft = draftFromPayload(payloadFixture())
    expect(draft.name).toBe('Retention hypothesis')
    expect(draft.nodes).toHaveLength(2)
    expect(draft.nodes[0].layout).toEqual({ x: 120, y: 40 })
    expect(draft.nodes[1].node_id).toBe('churn')
    expect(draft.analysis).toEqual({ treatment: 'tenure', outcome: 'churn' })
    expect(draft.assumptions[0].assumption_id).toBe('asmp-1')
  })

  it('loads a graph and marks it clean; any edit makes it dirty', () => {
    let state = initialLabState()
    state = causalLabReducer(state, { type: 'load', payload: payloadFixture() })
    expect(isDirty(state)).toBe(false)
    state = causalLabReducer(state, {
      type: 'updateNode',
      nodeId: 'tenure',
      patch: { label: 'Tenure (renamed)' },
    })
    expect(isDirty(state)).toBe(true)
    // Undo returns to a clean draft.
    state = causalLabReducer(state, { type: 'undo' })
    expect(isDirty(state)).toBe(false)
    expect(state.draft.nodes[0].label).toBe('TENURE')
  })

  it('toSpec produces exactly the S8A create/update body contract', () => {
    const draft = draftFromPayload(payloadFixture())
    const spec = toSpec(draft, 'ds-test', 'cgraph-fixture01')
    expect(spec.schema_version).toBe('1.0.0')
    expect(spec.dataset_id).toBe('ds-test')
    expect(spec.name).toBe('Retention hypothesis')
    expect(spec.nodes[0].node_id).toBe('tenure')
    expect(spec.edges[0]).toEqual({
      source: 'tenure',
      target: 'churn',
      rationale: 'hypothesised',
      reference: null,
    })
  })
})

describe('structure rules mirrored from the backend', () => {
  it('refuses a self-loop without mutating the draft', () => {
    const state = initialLabState()
    const next = causalLabReducer(state, {
      type: 'addEdge',
      edge: { source: 'a', target: 'a', rationale: null, reference: null },
    })
    expect(next.draft.edges).toHaveLength(0)
    expect(next.lastError?.title).toBe('Self-loop rejected')
    expect(localEdgeProblems(next.draft, 'a', 'a')).toMatch(/loop from a variable back to itself/)
  })

  it('refuses a duplicate directed edge', () => {
    let state = initialLabState()
    state = causalLabReducer(state, {
      type: 'addEdge',
      edge: { source: 'a', target: 'b', rationale: null, reference: null },
    })
    const next = causalLabReducer(state, {
      type: 'addEdge',
      edge: { source: 'a', target: 'b', rationale: 'again', reference: null },
    })
    expect(next.draft.edges).toHaveLength(1)
    expect(next.lastError?.title).toBe('Duplicate edge rejected')
    expect(localEdgeProblems(next.draft, 'a', 'b')).toMatch(/already exists/)
  })

  it('refuses a duplicate node id and reports it', () => {
    let state = initialLabState()
    state = causalLabReducer(state, { type: 'addNode', node: node('age') })
    const next = causalLabReducer(state, { type: 'addNode', node: node('age') })
    expect(next.draft.nodes).toHaveLength(1)
    expect(next.lastError?.title).toBe('Duplicate node id')
  })

  it('deleting a node cascades to connected edges and the analysis scope', () => {
    let state = initialLabState()
    state = causalLabReducer(state, { type: 'addNode', node: node('tenure') })
    state = causalLabReducer(state, { type: 'addNode', node: node('churn') })
    state = causalLabReducer(state, { type: 'addNode', node: node('age') })
    state = causalLabReducer(state, { type: 'addEdge', edge: { source: 'age', target: 'tenure', rationale: null, reference: null } })
    state = causalLabReducer(state, { type: 'addEdge', edge: { source: 'tenure', target: 'churn', rationale: null, reference: null } })
    state = causalLabReducer(state, { type: 'setAnalysis', patch: { treatment: 'tenure', outcome: 'churn' } })

    state = causalLabReducer(state, { type: 'removeNode', nodeId: 'tenure' })
    expect(state.draft.nodes.map((n) => n.node_id)).toEqual(['churn', 'age'])
    expect(state.draft.edges).toHaveLength(0)
    expect(state.draft.analysis).toEqual({ treatment: null, outcome: 'churn' })
    expect(state.selected).toBeNull()
  })

  it('edge keys are stable and directional', () => {
    expect(edgeKey('a', 'b')).toBe('a->b')
    expect(edgeKey('b', 'a')).not.toBe(edgeKey('a', 'b'))
  })

  it('slugifyNodeId produces schema-valid, unique ids', () => {
    const taken = new Set(['tenure_months'])
    expect(slugifyNodeId('Tenure Months', taken)).toBe('tenure_months_2')
    expect(slugifyNodeId('Tenure Months', new Set())).toBe('tenure_months')
    expect(slugifyNodeId('###', new Set())).toBe('variable')
    expect(slugifyNodeId('a'.repeat(100), new Set()).length).toBeLessThanOrEqual(60)
  })
})

describe('undo / redo', () => {
  it('restores intermediate drafts and keeps redo working after an undo', () => {
    let state = initialLabState()
    state = causalLabReducer(state, { type: 'addNode', node: node('a') })
    state = causalLabReducer(state, { type: 'addNode', node: node('b') })
    expect(state.draft.nodes).toHaveLength(2)
    state = causalLabReducer(state, { type: 'undo' })
    expect(state.draft.nodes).toHaveLength(1)
    state = causalLabReducer(state, { type: 'undo' })
    expect(state.draft.nodes).toHaveLength(0)
    state = causalLabReducer(state, { type: 'redo' })
    expect(state.draft.nodes).toHaveLength(1)
    state = causalLabReducer(state, { type: 'redo' })
    expect(state.draft.nodes).toHaveLength(2)
  })

  it('undo does nothing when history is empty', () => {
    const state = causalLabReducer(initialLabState(), { type: 'undo' })
    expect(state.draft.nodes).toHaveLength(0)
    expect(state.past).toHaveLength(0)
  })
})

describe('saved vs draft separation', () => {
  it('saving replaces the saved snapshot without touching undo history', () => {
    let state = initialLabState()
    state = causalLabReducer(state, { type: 'addNode', node: node('a') })
    // The server echoes the draft it actually stored: same content, revision 3.
    const savedPayload = payloadFixture({
      revision: 3,
      name: 'Untitled causal graph',
      nodes: [
        {
          ...node('a'),
          resolved_column_type: null,
          derived_structure: {
            parents: [],
            children: [],
            ancestors: [],
            descendants: [],
            is_collider: false,
            on_directed_treatment_outcome_path: false,
          },
          layout: null,
        },
      ],
      edges: [],
      assumptions: [],
      analysis: { treatment: null, outcome: null },
    })
    const afterSave = causalLabReducer(state, { type: 'saved', payload: savedPayload })
    expect(afterSave.saved).not.toBeNull()
    expect(isDirty(afterSave)).toBe(false)
    expect(afterSave.revision).toBe(3)
    // The save itself is not an undoable edit.
    expect(afterSave.past).toHaveLength(state.past.length)
  })
})

describe('canvas adapters', () => {
  it('toFlowNodes positions undragged nodes on the auto grid and marks scope roles', () => {
    const draft = {
      ...emptyDraft('ds-test'),
      nodes: [
        node('tenure', { kind: 'treatment' }),
        node('churn', { kind: 'outcome' }),
        node('u1', { observed: false, kind: 'unobserved' }),
      ],
      analysis: { treatment: 'tenure', outcome: 'churn' },
    }
    const flowNodes = toFlowNodes(draft, new Map())
    expect(flowNodes[0].position).toEqual(expect.objectContaining({ x: expect.any(Number), y: expect.any(Number) }))
    expect(flowNodes[0].data.isTreatment).toBe(true)
    expect(flowNodes[1].data.isOutcome).toBe(true)
    expect(flowNodes[2].data.observed).toBe(false)
    // The scientific draft is untouched.
    expect(draft.nodes.every((n) => n.layout === null)).toBe(true)
  })

  it('issueIndex counts node issues for on-canvas marking', () => {
    const { byNode } = issueIndex([
      { code: 'x', severity: 'error', message: 'm', hint: null, node_id: 'a', edge_index: null, assumption_id: null },
      { code: 'y', severity: 'warning', message: 'm2', hint: null, node_id: 'a', edge_index: null, assumption_id: null },
    ])
    expect(byNode.get('a')).toBe(2)
  })
})

describe('teaching examples satisfy the S8A schema', () => {
  const examples = ['chain', 'fork', 'collider'] as const

  for (const kind of examples) {
    it(`the ${kind} example references only defined nodes and is labelled synthetic`, () => {
      const example = teachingExample(kind)
      const ids = new Set(example.nodes.map((n) => n.node_id))
      expect(example.name.toLowerCase()).toContain('teaching example')
      expect(example.description).toMatch(/not relationships learned from data|assumed|synthetic/i)
      for (const edge of example.edges) {
        expect(ids.has(edge.source)).toBe(true)
        expect(ids.has(edge.target)).toBe(true)
        expect(edge.source).not.toBe(edge.target)
      }
      for (const nodeSpec of example.nodes) {
        expect(nodeSpec.node_id).toMatch(/^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$/)
      }
      const nodeCount = example.nodes.length
      expect(example.edges.length).toBeLessThanOrEqual((nodeCount * (nodeCount - 1)) / 2)
    })
  }
})
