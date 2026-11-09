/**
 * The contextual inspector (right rail).
 *
 * Opens only when something is selected: a node, a directed edge, the graph
 * itself, or when the validation summary is requested from the toolbar. An
 * empty canvas shows no permanent right panel.
 *
 * Distinctions preserved everywhere:
 * - what the user *declares* (kind, assumptions, rationales) is editable;
 * - what the graph *structure implies* (parents, colliders, on-path status)
 *   is read-only and labelled as derived from the drawn edges;
 * - statuses like `declared` are never presented as verified.
 */

import { useEffect, useMemo, useState } from 'react'

import type { CausalStructureNode } from '../api/types'

import type { CausalIssue } from '../api/types'
import {
  ASSUMPTION_CATEGORIES,
  ASSUMPTION_STATUSES,
  NODE_KINDS,
  type CausalDraft,
  type Selection,
} from './CausalLabState'

export type InspectorView = { kind: 'node'; id: string } | { kind: 'edge'; id: string } | { kind: 'graph' } | { kind: 'validation' }

export interface InspectorProps {
  view: InspectorView
  draft: CausalDraft
  issues: CausalIssue[]
  payloadRevision: number | null
  /** Node ids → structural facts derived by the graph backend from the drawn edges. */
  structure: Record<string, CausalStructureNode> | null
  onPatchNode: (nodeId: string, patch: Record<string, unknown>) => void
  onPatchEdge: (source: string, target: string, patch: Record<string, unknown>) => void
  onPatchMeta: (patch: { name?: string; description?: string }) => void
  onSetAnalysis: (patch: { treatment?: string | null; outcome?: string | null }) => void
  onConnectNodes: (source: string, target: string) => void
  onRemoveNode: (nodeId: string) => void
  onRemoveEdge: (source: string, target: string) => void
  onAddAssumption: (category: string) => void
  onPatchAssumption: (id: string, patch: Record<string, unknown>) => void
  onRemoveAssumption: (id: string) => void
  onSelect: (selection: Selection) => void
  localError: string | null
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="clab-field">
      <span className="clab-field__label">{label}</span>
      {children}
    </label>
  )
}

function DerivedFacts({ nodeId, structure }: { nodeId: string; structure: Record<string, CausalStructureNode> | null }) {
  const facts = structure?.[nodeId]
  if (!facts) {
    return (
      <p className="clab-derived clab-derived--empty">
        Save the graph to see structure-derived facts (ancestors, colliders, path status) computed
        by the backend.
      </p>
    )
  }
  return (
    <div className="clab-derived">
      <p className="clab-derived__note">
        Derived from the drawn edges only - these describe the assumed structure, not the data.
      </p>
      <ul className="clab-derived__list">
        <li><span>Parents</span><code>{facts.parents.join(', ') || '—'}</code></li>
        <li><span>Children</span><code>{facts.children.join(', ') || '—'}</code></li>
        <li><span>Ancestors</span><code>{facts.ancestors.join(', ') || '—'}</code></li>
        <li><span>Descendants</span><code>{facts.descendants.join(', ') || '—'}</code></li>
        <li>
          <span>Collider</span>
          <code>{facts.is_collider ? 'yes - two or more parents' : 'no'}</code>
        </li>
        <li>
          <span>On a treatment→outcome path</span>
          <code>{facts.on_directed_treatment_outcome_path ? 'yes' : 'no'}</code>
        </li>
      </ul>
    </div>
  )
}

function NodeInspector(props: InspectorProps & { nodeId: string }) {
  const node = props.draft.nodes.find((item) => item.node_id === props.nodeId)
  const [connectTarget, setConnectTarget] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const nodeIssues = props.issues.filter((issue) => issue.node_id === props.nodeId)

  useEffect(() => {
    setConnectTarget('')
    setConfirmDelete(false)
  }, [props.nodeId])

  if (!node) return null
  const candidates = props.draft.nodes.filter((item) => item.node_id !== node.node_id)

  return (
    <div className="clab-inspector__content" data-testid="node-inspector">
      <p className="clab-inspector__eyebrow">Variable</p>
      <h3 className="clab-inspector__title">{node.label}</h3>
      <p className="clab-inspector__mono">{node.node_id}</p>

      <Field label="Display label">
        <input
          value={node.label}
          maxLength={120}
          onChange={(event) => props.onPatchNode(node.node_id, { label: event.target.value })}
          aria-label="Variable display label"
        />
      </Field>
      <Field label="Conceptual role (your declaration)">
        <select
          value={node.kind}
          onChange={(event) =>
            props.onPatchNode(node.node_id, {
              kind: event.target.value,
              observed: event.target.value === 'unobserved' ? false : node.observed,
            })
          }
          aria-label="Variable conceptual role"
        >
          {NODE_KINDS.map((kind) => (
            <option key={kind.value} value={kind.value}>{kind.label}</option>
          ))}
        </select>
      </Field>
      <Field label="Description">
        <textarea
          rows={3}
          value={node.description ?? ''}
          maxLength={1000}
          placeholder="What this variable measures, and why it belongs here."
          onChange={(event) => props.onPatchNode(node.node_id, { description: event.target.value })}
          aria-label="Variable description"
        />
      </Field>
      <p className="clab-note">
        {node.column ? (
          <>Anchored to dataset column <code>{node.column}</code>. The identifier and column
          reference stay stable when you rename the label.</>
        ) : node.observed ? (
          'Not anchored to a dataset column.'
        ) : (
          'Hypothetical unobserved variable - no measured column exists for it, so its role cannot be checked against data.'
        )}
      </p>

      <div className="clab-actions">
        <button
          type="button"
          className="btn btn--small"
          disabled={props.draft.analysis.treatment === node.node_id}
          onClick={() => props.onSetAnalysis({ treatment: node.node_id })}
        >
          Set as treatment
        </button>
        <button
          type="button"
          className="btn btn--small"
          disabled={props.draft.analysis.outcome === node.node_id}
          onClick={() => props.onSetAnalysis({ outcome: node.node_id })}
        >
          Set as outcome
        </button>
      </div>

      <Field label="Draw an edge from this variable (keyboard method)">
        <select
          value={connectTarget}
          onChange={(event) => {
            const target = event.target.value
            setConnectTarget(target)
            if (target) props.onConnectNodes(node.node_id, target)
          }}
          aria-label="Connect this variable to a target"
        >
          <option value="">Choose a target…</option>
          {candidates.map((item) => (
            <option key={item.node_id} value={item.node_id}>{item.label}</option>
          ))}
        </select>
      </Field>
      {props.localError ? (
        <p className="clab-inline-error" role="alert">{props.localError}</p>
      ) : null}

      <DerivedFacts nodeId={node.node_id} structure={props.structure} />

      {nodeIssues.length ? (
        <div className="clab-issue-list clab-issue-list--errors">
          {nodeIssues.map((issue, index) => (
            <p key={index} className="clab-issue">
              <strong>{issue.message}</strong>
              {issue.hint ? <span>{issue.hint}</span> : null}
            </p>
          ))}
        </div>
      ) : null}

      <div className="clab-actions clab-actions--end">
        {confirmDelete ? (
          <>
            <span className="clab-confirm-text">Also removes connected edges.</span>
            <button
              type="button"
              className="btn btn--small btn--danger"
              onClick={() => {
                props.onRemoveNode(node.node_id)
                setConfirmDelete(false)
              }}
            >
              Confirm delete
            </button>
            <button type="button" className="btn btn--small" onClick={() => setConfirmDelete(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn btn--small" onClick={() => setConfirmDelete(true)}>
            Delete variable
          </button>
        )}
      </div>
    </div>
  )
}

function EdgeInspector(props: InspectorProps & { edgeId: string }) {
  const [source, target] = props.edgeId.split('->')
  const edge = props.draft.edges.find((item) => item.source === source && item.target === target)
  const sourceNode = props.draft.nodes.find((item) => item.node_id === source)
  const targetNode = props.draft.nodes.find((item) => item.node_id === target)
  const [confirmDelete, setConfirmDelete] = useState(false)
  useEffect(() => setConfirmDelete(false), [props.edgeId])

  if (!edge || !sourceNode || !targetNode) return null
  const edgeIssues = props.issues.filter((issue) => issue.edge_index !== null)

  return (
    <div className="clab-inspector__content" data-testid="edge-inspector">
      <p className="clab-inspector__eyebrow">Assumed causal relationship</p>
      <h3 className="clab-inspector__title">
        {sourceNode.label} <span aria-hidden="true">→</span> {targetNode.label}
      </h3>
      <p className="clab-note">
        This edge records your assumption that the source influences the target. It is not a
        relationship the dataset established, and it carries no strength or confidence value.
      </p>
      <Field label="Rationale">
        <textarea
          rows={4}
          maxLength={1000}
          value={edge.rationale ?? ''}
          placeholder="Why do you assume this relationship exists? Cite subject knowledge or prior work."
          onChange={(event) => props.onPatchEdge(source, target, { rationale: event.target.value })}
          aria-label="Edge rationale"
        />
      </Field>
      <Field label="Supporting reference (optional)">
        <input
          value={edge.reference ?? ''}
          maxLength={500}
          placeholder="e.g. a DOI, paper, or study note"
          onChange={(event) => props.onPatchEdge(source, target, { reference: event.target.value })}
          aria-label="Edge supporting reference"
        />
      </Field>
      {edgeIssues.length ? (
        <div className="clab-issue-list clab-issue-list--errors">
          {edgeIssues.map((issue, index) => (
            <p key={index} className="clab-issue">
              <strong>{issue.message}</strong>
              {issue.hint ? <span>{issue.hint}</span> : null}
            </p>
          ))}
        </div>
      ) : null}
      <div className="clab-actions clab-actions--end">
        {confirmDelete ? (
          <>
            <button
              type="button"
              className="btn btn--small btn--danger"
              onClick={() => {
                props.onRemoveEdge(source, target)
                setConfirmDelete(false)
              }}
            >
              Confirm remove
            </button>
            <button type="button" className="btn btn--small" onClick={() => setConfirmDelete(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button type="button" className="btn btn--small" onClick={() => setConfirmDelete(true)}>
            Remove relationship
          </button>
        )}
      </div>
    </div>
  )
}

function GraphInspector(props: InspectorProps) {
  const [newCategory, setNewCategory] = useState<(typeof ASSUMPTION_CATEGORIES)[number]['value']>('temporal_ordering')
  const nextAssumptionNumber = props.draft.assumptions.length + 1

  return (
    <div className="clab-inspector__content" data-testid="graph-inspector">
      <p className="clab-inspector__eyebrow">Graph &amp; analysis scope</p>
      <h3 className="clab-inspector__title">{props.draft.name}</h3>

      <Field label="Graph name">
        <input
          value={props.draft.name}
          maxLength={120}
          onChange={(event) => props.onPatchMeta({ name: event.target.value })}
          aria-label="Graph name"
        />
      </Field>
      <Field label="Graph description">
        <textarea
          rows={3}
          maxLength={2000}
          value={props.draft.description ?? ''}
          placeholder="What this graph hypothesises, and for which study."
          onChange={(event) => props.onPatchMeta({ description: event.target.value })}
          aria-label="Graph description"
        />
      </Field>

      <Field label="Treatment / exposure (one)">
        <select
          value={props.draft.analysis.treatment ?? ''}
          onChange={(event) => props.onSetAnalysis({ treatment: event.target.value || null })}
          aria-label="Treatment selection"
        >
          <option value="">Not selected</option>
          {props.draft.nodes.map((node) => (
            <option key={node.node_id} value={node.node_id}>{node.label}</option>
          ))}
        </select>
      </Field>
      <Field label="Outcome (one)">
        <select
          value={props.draft.analysis.outcome ?? ''}
          onChange={(event) => props.onSetAnalysis({ outcome: event.target.value || null })}
          aria-label="Outcome selection"
        >
          <option value="">Not selected</option>
          {props.draft.nodes.map((node) => (
            <option key={node.node_id} value={node.node_id}>{node.label}</option>
          ))}
        </select>
      </Field>
      {props.draft.analysis.treatment && props.draft.analysis.treatment === props.draft.analysis.outcome ? (
        <p className="clab-inline-error" role="alert">
          The treatment and the outcome are the same variable. A causal effect needs two distinct
          variables - the backend will reject this.
        </p>
      ) : null}

      <div className="clab-assumptions">
        <div className="clab-assumptions__head">
          <h4>Assumption registry</h4>
          <p className="clab-note">
            Recorded claims, not verified facts. Statuses are yours; SplitScope never upgrades one.
          </p>
        </div>
        {props.draft.assumptions.length === 0 ? (
          <p className="clab-note clab-note--quiet">No assumptions recorded yet.</p>
        ) : (
          props.draft.assumptions.map((assumption) => (
            <div key={assumption.assumption_id} className="clab-assumption" data-testid="assumption-record">
              <div className="clab-assumption__row">
                <select
                  value={assumption.category}
                  aria-label="Assumption category"
                  onChange={(event) =>
                    props.onPatchAssumption(assumption.assumption_id, { category: event.target.value })
                  }
                >
                  {ASSUMPTION_CATEGORIES.map((category) => (
                    <option key={category.value} value={category.value}>{category.label}</option>
                  ))}
                </select>
                <select
                  value={assumption.status}
                  aria-label="Assumption status"
                  onChange={(event) =>
                    props.onPatchAssumption(assumption.assumption_id, { status: event.target.value })
                  }
                >
                  {ASSUMPTION_STATUSES.map((status) => (
                    <option key={status.value} value={status.value}>{status.label}</option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn btn--small"
                  aria-label={`Remove assumption ${assumption.assumption_id}`}
                  onClick={() => props.onRemoveAssumption(assumption.assumption_id)}
                >
                  ✕
                </button>
              </div>
              <textarea
                rows={2}
                maxLength={1000}
                value={assumption.rationale ?? ''}
                placeholder="Rationale - why you believe this holds for this study."
                aria-label="Assumption rationale"
                onChange={(event) =>
                  props.onPatchAssumption(assumption.assumption_id, { rationale: event.target.value })
                }
              />
            </div>
          ))
        )}
        <div className="clab-actions">
          <button
            type="button"
            className="btn btn--small"
            onClick={() => props.onAddAssumption(newCategory)}
          >
            Add assumption #{nextAssumptionNumber}
          </button>
        </div>
        <Field label="Category for the next assumption">
          <select
            value={newCategory}
            aria-label="Next assumption category"
            onChange={(event) => setNewCategory(event.target.value as typeof newCategory)}
          >
            {ASSUMPTION_CATEGORIES.map((category) => (
              <option key={category.value} value={category.value}>{category.label}</option>
            ))}
          </select>
        </Field>
      </div>
    </div>
  )
}

function ValidationInspector(props: InspectorProps & { issues: CausalIssue[] }) {
  const errors = props.issues.filter((issue) => issue.severity === 'error')
  const warnings = props.issues.filter((issue) => issue.severity === 'warning')
  return (
    <div className="clab-inspector__content" data-testid="validation-inspector">
      <p className="clab-inspector__eyebrow">Backend validation</p>
      <h3 className="clab-inspector__title">
        {errors.length === 0 ? 'Structurally valid DAG' : 'Not a valid DAG yet'}
      </h3>
      <p className="clab-note">
        {errors.length === 0
          ? 'The graph is well-formed. That means its structure passes the rules - it does not mean the assumed relationships are true, and no causal effect has been estimated.'
          : 'The backend refused these structural problems. Your draft is preserved; fix the errors and save again.'}
      </p>

      {errors.length ? (
        <section className="clab-issue-list clab-issue-list--errors" aria-label="Blocking errors">
          <h4>{errors.length} blocking {errors.length === 1 ? 'error' : 'errors'}</h4>
          {errors.map((issue, index) => (
            <button
              key={index}
              type="button"
              className="clab-issue clab-issue--link"
              onClick={() => {
                if (issue.node_id) props.onSelect({ kind: 'node', id: issue.node_id })
                else props.onSelect({ kind: 'graph' })
              }}
            >
              <strong>{issue.message}</strong>
              {issue.hint ? <span>{issue.hint}</span> : null}
            </button>
          ))}
        </section>
      ) : null}

      {warnings.length ? (
        <section className="clab-issue-list clab-issue-list--warnings" aria-label="Scientific warnings">
          <h4>{warnings.length} scientific {warnings.length === 1 ? 'warning' : 'warnings'}</h4>
          {warnings.map((issue, index) => (
            <button
              key={index}
              type="button"
              className="clab-issue clab-issue--link"
              onClick={() => {
                if (issue.node_id) props.onSelect({ kind: 'node', id: issue.node_id })
                else props.onSelect({ kind: 'graph' })
              }}
            >
              <strong>{issue.message}</strong>
              {issue.hint ? <span>{issue.hint}</span> : null}
            </button>
          ))}
        </section>
      ) : null}

      {errors.length === 0 && warnings.length === 0 ? (
        <p className="clab-note clab-note--quiet">No issues reported by the backend.</p>
      ) : null}
    </div>
  )
}

export function CausalInspector(props: InspectorProps) {
  const view = props.view
  const body = useMemo(() => {
    switch (view.kind) {
      case 'node':
        return <NodeInspector {...props} nodeId={view.id} />
      case 'edge':
        return <EdgeInspector {...props} edgeId={view.id} />
      case 'graph':
        return <GraphInspector {...props} />
      case 'validation':
        return <ValidationInspector {...props} issues={props.issues} />
    }
  }, [view, props])

  return (
    <aside className="clab__inspector" aria-label="Inspector">
      <div className="clab-inspector">{body}</div>
    </aside>
  )
}

/** Maps a reducer Selection to an inspector view; `graph` selection opens the graph panel. */
export function selectionToView(selection: Selection): InspectorView | null {
  if (!selection) return null
  if (selection.kind === 'node') return { kind: 'node', id: selection.id }
  if (selection.kind === 'edge') return { kind: 'edge', id: selection.id }
  return { kind: 'graph' }
}
