/**
 * Adapters between the causal draft (the scientific object) and React Flow's
 * node/edge view models.
 *
 * Direction of authority: the draft is the single source of truth. React Flow
 * receives derived arrays and reports interactions back through the reducer.
 * Positions live in `node.layout` and are display state — the S8A scientific
 * fingerprint intentionally excludes them.
 */

import type { Edge, Node } from '@xyflow/react'

import type { CausalIssue, CausalNodePayload, CausalNodeSpec } from '../api/types'
import type { CausalDraft } from './CausalLabState'

export const NODE_WIDTH = 196
export const NODE_HEIGHT = 58

/** Grid position for nodes the user has never dragged. */
function autoPosition(index: number): { x: number; y: number } {
  const column = index % 4
  const row = Math.floor(index / 4)
  return { x: 60 + column * (NODE_WIDTH + 120), y: 60 + row * (NODE_HEIGHT + 110) }
}

export interface VariableNodeData extends Record<string, unknown> {
  label: string
  kind: CausalNodeSpec['kind']
  observed: boolean
  column: string | null
  isTreatment: boolean
  isOutcome: boolean
  isSelected: boolean
  hasIssue: boolean
  issueCount: number
}

export function toFlowNodes(
  draft: CausalDraft,
  errorsByNode: Map<string, number>,
  selectedNodeId: string | null = null,
): Node<VariableNodeData>[] {
  return draft.nodes.map((node, index) => {
    const position = node.layout ?? autoPosition(index)
    return {
      id: node.node_id,
      type: 'variable',
      position,
      data: {
        label: node.label,
        kind: node.kind,
        observed: node.observed,
        column: node.column,
        isTreatment: draft.analysis.treatment === node.node_id,
        isOutcome: draft.analysis.outcome === node.node_id,
        isSelected: selectedNodeId === node.node_id,
        hasIssue: errorsByNode.has(node.node_id),
        issueCount: errorsByNode.get(node.node_id) ?? 0,
      },
    }
  })
}

export interface CausalEdgeData extends Record<string, unknown> {
  rationale: string | null
  isSelected: boolean
  hasIssue: boolean
}

export function toFlowEdges(
  draft: CausalDraft,
  problemEdgeIndexes: Set<number>,
  selectedEdgeId: string | null = null,
): Edge<CausalEdgeData>[] {
  return draft.edges.map((edge, index) => ({
    id: `${edge.source}->${edge.target}`,
    source: edge.source,
    target: edge.target,
    type: 'causal',
    data: {
      rationale: edge.rationale,
      isSelected: selectedEdgeId === `${edge.source}->${edge.target}`,
      hasIssue: problemEdgeIndexes.has(index),
    },
  }))
}

/** Maps server validation issues onto nodes/edges for on-canvas marking. */
export function issueIndex(issues: CausalIssue[]): {
  byNode: Map<string, number>
  edgeIndexes: Set<number>
} {
  const byNode = new Map<string, number>()
  const edgeIndexes = new Set<number>()
  for (const issue of issues) {
    if (issue.node_id) byNode.set(issue.node_id, (byNode.get(issue.node_id) ?? 0) + 1)
    if (issue.edge_index !== null && issue.edge_index !== undefined) {
      edgeIndexes.add(issue.edge_index)
    }
  }
  return { byNode, edgeIndexes }
}

/**
 * A synthetic teaching example. Every structure is built through the same
 * reducer helpers the UI uses, satisfies the S8A schema exactly, and is
 * labelled a teaching example wherever it is offered — its edges are assumed
 * relationships for instruction, never relationships learned from data.
 */
export function teachingExample(
  kind: 'chain' | 'fork' | 'collider',
): Pick<CausalDraft, 'name' | 'description' | 'nodes' | 'edges' | 'analysis' | 'assumptions'> {
  const observedNode = (
    nodeId: string,
    label: string,
    kind: CausalNodeSpec['kind'] = 'covariate',
  ): CausalNodeSpec => ({
    node_id: nodeId,
    label,
    column: null,
    observed: true,
    kind,
    description: null,
    layout: null,
  })

  if (kind === 'chain') {
    return {
      name: 'Teaching example — chain',
      description:
        'Synthetic teaching example: A → M → B assumes the influence of A on B runs entirely through the mediator M. Edge directions are assumptions for instruction, not relationships learned from data.',
      nodes: [
        { ...observedNode('a', 'Variable A', 'treatment') },
        { ...observedNode('m', 'Mediator M', 'mediator') },
        { ...observedNode('b', 'Variable B', 'outcome') },
      ],
      edges: [
        { source: 'a', target: 'm', rationale: 'Teaching example: assumed direct influence.', reference: null },
        { source: 'm', target: 'b', rationale: 'Teaching example: assumed direct influence.', reference: null },
      ],
      analysis: { treatment: 'a', outcome: 'b' },
      assumptions: [
        {
          assumption_id: 'asmp-chain-temporal',
          category: 'temporal_ordering',
          status: 'declared',
          source: 'teaching example',
          rationale: 'Teaching example: A precedes M, and M precedes B in time.',
        },
      ],
    }
  }
  if (kind === 'fork') {
    return {
      name: 'Teaching example — fork',
      description:
        'Synthetic teaching example: B ← A → C is the classic confounding fork. Conditioning on A is what would block the backdoor path — identification itself belongs to a later stage.',
      nodes: [
        { ...observedNode('a', 'Common cause A') },
        { ...observedNode('b', 'Variable B', 'treatment') },
        { ...observedNode('c', 'Variable C', 'outcome') },
      ],
      edges: [
        { source: 'a', target: 'b', rationale: 'Teaching example: assumed common cause.', reference: null },
        { source: 'a', target: 'c', rationale: 'Teaching example: assumed common cause.', reference: null },
      ],
      analysis: { treatment: 'b', outcome: 'c' },
      assumptions: [
        {
          assumption_id: 'asmp-fork-population',
          category: 'target_population',
          status: 'not_assessed',
          source: 'teaching example',
          rationale: null,
        },
      ],
    }
  }
  return {
    name: 'Teaching example — collider',
    description:
      'Synthetic teaching example: A → C ← B makes C a collider. Conditioning on a collider can induce association where none existed — the structure, not the data, is the lesson here.',
    nodes: [
      { ...observedNode('a', 'Variable A', 'treatment') },
      { ...observedNode('b', 'Variable B') },
      { ...observedNode('c', 'Common effect C', 'outcome') },
    ],
    edges: [
      { source: 'a', target: 'c', rationale: 'Teaching example: assumed direct influence.', reference: null },
      { source: 'b', target: 'c', rationale: 'Teaching example: assumed direct influence.', reference: null },
    ],
    analysis: { treatment: 'a', outcome: 'c' },
    assumptions: [],
  }
}

export function nodeSummary(node: CausalNodePayload): string {
  const parts = [node.label]
  if (node.column) parts.push(`column: ${node.column}`)
  if (!node.observed) parts.push('unobserved')
  return parts.join(' · ')
}
