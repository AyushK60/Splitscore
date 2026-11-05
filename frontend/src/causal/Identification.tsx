/**
 * The Identification mode (S8C).
 *
 * A focused reasoning panel beside the unchanged canvas: treatment/outcome
 * scope, the backend's graphical-identification status, suggested adjustment
 * sets, a custom set the researcher can test, a d-separation probe, and
 * rule-based explanations that come verbatim from the backend's structured
 * payload — never invented in the frontend.
 *
 * Honesty contracts preserved here:
 * - results are tied to an exact scientific signature; editing the graph's
 *   scientific content marks every displayed result stale, visibly;
 * - a graphically admissible set is never presented as scientifically proven;
 * - an incomplete search is labelled incomplete, never "no set exists";
 * - unobserved variables are never offered as adjustment covariates.
 */

import { useEffect, useMemo, useState } from 'react'

import type {
  CausalAdjustmentEvaluationResponse,
  CausalDSeparationResponse,
  CausalIdentificationResponse,
} from '../api/types'
import type { CausalDraft } from './CausalLabState'

export interface IdentificationResultState {
  graphId: string
  fingerprint: string
  signature: string
  identification: CausalIdentificationResponse
}

const STATUS_TONE: Record<string, { label: string; tone: 'ok' | 'warn' | 'error' | 'quiet' }> = {
  backdoor_adjustment_available: { label: 'Backdoor adjustment available', tone: 'ok' },
  no_eligible_backdoor_set: {
    label: 'No eligible observed backdoor set found',
    tone: 'warn',
  },
  search_incomplete: { label: 'Search incomplete — bounds reached', tone: 'warn' },
  invalid_scope: { label: 'Scope not usable', tone: 'error' },
  missing_dataset_variables: { label: 'Treatment or outcome not measured', tone: 'error' },
  unsupported_identification_method: { label: 'Method not supported', tone: 'error' },
  invalid_graph: { label: 'Graph not valid', tone: 'error' },
}

const VIOLATION_LABELS: Record<string, string> = {
  unknown_variable: 'Not a variable of this graph',
  adjustment_contains_scope: 'Contains the treatment or the outcome',
  unobserved_variable: 'Unobserved — nothing could be conditioned on in the data',
  post_treatment_variable: 'Descendant of the treatment (post-treatment)',
  open_backdoor_path: 'A backdoor path remains open',
}

function chipLabel(nodeId: string, draft: CausalDraft): string {
  return draft.nodes.find((node) => node.node_id === nodeId)?.label ?? nodeId
}

function ScopeSelects({
  draft,
  onSetAnalysis,
}: {
  draft: CausalDraft
  onSetAnalysis: (patch: { treatment?: string | null; outcome?: string | null }) => void
}) {
  return (
    <div className="clab-scope-grid">
      <label className="clab-field">
        <span className="clab-field__label">Treatment / exposure (one)</span>
        <select
          value={draft.analysis.treatment ?? ''}
          onChange={(event) => onSetAnalysis({ treatment: event.target.value || null })}
          aria-label="Identification treatment selection"
        >
          <option value="">Not selected</option>
          {draft.nodes.map((node) => (
            <option key={node.node_id} value={node.node_id}>{node.label}</option>
          ))}
        </select>
      </label>
      <label className="clab-field">
        <span className="clab-field__label">Outcome (one)</span>
        <select
          value={draft.analysis.outcome ?? ''}
          onChange={(event) => onSetAnalysis({ outcome: event.target.value || null })}
          aria-label="Identification outcome selection"
        >
          <option value="">Not selected</option>
          {draft.nodes.map((node) => (
            <option key={node.node_id} value={node.node_id}>{node.label}</option>
          ))}
        </select>
      </label>
    </div>
  )
}

function SetChips({
  variables,
  draft,
  highlighted,
  onToggleHighlight,
}: {
  variables: string[]
  draft: CausalDraft
  highlighted: Set<string>
  onToggleHighlight: (nodeId: string) => void
}) {
  return (
    <div className="clab-chip-row">
      {variables.length === 0 ? (
        <span className="clab-note clab-note--quiet">Empty set — adjust for nothing.</span>
      ) : (
        variables.map((nodeId) => (
          <button
            key={nodeId}
            type="button"
            className={`clab-chip${highlighted.has(nodeId) ? ' clab-chip--on' : ''}`}
            aria-pressed={highlighted.has(nodeId)}
            onClick={() => onToggleHighlight(nodeId)}
            title="Highlight this variable on the graph"
          >
            {chipLabel(nodeId, draft)}
          </button>
        ))
      )}
    </div>
  )
}

interface IdentificationPanelProps {
  draft: CausalDraft
  datasetId: string | null
  graphId: string | null
  dirty: boolean
  busy: string | null
  result: IdentificationResultState | null
  stale: boolean
  highlighted: Set<string>
  /** Increments on every identification run so widget state resets cleanly. */
  runId: number
  onSetAnalysis: (patch: { treatment?: string | null; outcome?: string | null }) => void
  onRunIdentification: () => void
  onSaveRequest: () => void
  onEvaluateSet: (variables: string[]) => Promise<CausalAdjustmentEvaluationResponse>
  onProbeDSeparation: (x: string, y: string, conditioning: string[]) => Promise<CausalDSeparationResponse>
  onHighlight: (variables: string[]) => void
  onToggleHighlight: (nodeId: string) => void
}

export function IdentificationPanel(props: IdentificationPanelProps) {
  const { draft, result, stale, highlighted } = props
  const [customSet, setCustomSet] = useState<Set<string>>(new Set())
  const [evaluation, setEvaluation] = useState<CausalAdjustmentEvaluationResponse | null>(null)
  const [probeX, setProbeX] = useState('')
  const [probeY, setProbeY] = useState('')
  const [probeZ, setProbeZ] = useState<Set<string>>(new Set())
  const [probeResult, setProbeResult] = useState<CausalDSeparationResponse | null>(null)
  const [widgetError, setWidgetError] = useState<string | null>(null)
  const [widgetBusy, setWidgetBusy] = useState(false)
  const [openExplanation, setOpenExplanation] = useState<string | null>(null)

  // A fresh identification run resets the interactive widgets: results from a
  // previous run must never silently blend into a new one.
  useEffect(() => {
    setCustomSet(new Set())
    setEvaluation(null)
    setProbeX('')
    setProbeY('')
    setProbeZ(new Set())
    setProbeResult(null)
    setWidgetError(null)
    setOpenExplanation(null)
  }, [props.runId])

  const status = result ? STATUS_TONE[result.identification.status] ?? { label: result.identification.status, tone: 'quiet' as const } : null
  const search = result?.identification.search

  const candidateList = useMemo(() => {
    if (search) return search.eligible_candidates
    // Before any run, offer every observed node that is not the scope pair —
    // the backend remains the authority on eligibility.
    return draft.nodes
      .filter(
        (node) =>
          node.observed &&
          node.node_id !== draft.analysis.treatment &&
          node.node_id !== draft.analysis.outcome,
      )
      .map((node) => node.node_id)
  }, [search, draft])

  const canRun = Boolean(props.datasetId && props.graphId) && !props.dirty && !props.busy
  const treatment = draft.analysis.treatment
  const outcome = draft.analysis.outcome

  const toggleCustom = (nodeId: string) => {
    setCustomSet((current) => {
      const next = new Set(current)
      if (next.has(nodeId)) next.delete(nodeId)
      else next.add(nodeId)
      return next
    })
  }

  const applySet = (variables: string[]) => {
    setCustomSet(new Set(variables))
    setEvaluation(null)
    props.onHighlight(variables)
  }

  const runEvaluation = async () => {
    if (!props.datasetId || !props.graphId) return
    setWidgetBusy(true)
    setWidgetError(null)
    try {
      const payload = await props.onEvaluateSet([...customSet].sort())
      setEvaluation(payload)
    } catch (caught) {
      setEvaluation(null)
      setWidgetError(caught instanceof Error ? caught.message : 'The evaluation failed.')
    } finally {
      setWidgetBusy(false)
    }
  }

  const runProbe = async () => {
    if (!props.datasetId || !props.graphId || !probeX || !probeY) return
    setWidgetBusy(true)
    setWidgetError(null)
    try {
      const payload = await props.onProbeDSeparation(probeX, probeY, [...probeZ].sort())
      setProbeResult(payload)
    } catch (caught) {
      setProbeResult(null)
      setWidgetError(caught instanceof Error ? caught.message : 'The probe failed.')
    } finally {
      setWidgetBusy(false)
    }
  }

  const explanations = result?.identification.explanations ?? []

  return (
    <div className="clab-inspector__content" data-testid="identification-panel">
      <p className="clab-inspector__eyebrow">Identification</p>
      <h3 className="clab-inspector__title">Backdoor identification</h3>
      <p className="clab-note">
        Graphical identification on the <strong>saved</strong> graph: which observed sets block
        every backdoor path under the assumed structure. No causal effect is estimated, and an
        admissible set is not a proven one.
      </p>

      <ScopeSelects draft={draft} onSetAnalysis={props.onSetAnalysis} />

      {props.dirty || !props.graphId ? (
        <div className="clab-stale" data-testid="identification-save-gate" role="status">
          <p>
            {props.graphId
              ? 'The graph has unsaved changes. Identification always runs on the saved revision — save first, then run.'
              : 'Save this graph first; identification runs against the backend’s stored structure.'}
          </p>
          <button type="button" className="btn btn--small" onClick={props.onSaveRequest}>
            Save graph
          </button>
        </div>
      ) : null}

      <div className="clab-actions">
        <button
          type="button"
          className="btn btn--small"
          data-testid="run-identification"
          onClick={props.onRunIdentification}
          disabled={!canRun || !treatment || !outcome || treatment === outcome}
          title="Runs the backend identification engine on the saved graph"
        >
          Run identification
        </button>
      </div>
      {(!treatment || !outcome) && (
        <p className="clab-inline-error" role="status">
          Select a treatment and an outcome to identify.
        </p>
      )}
      {treatment && treatment === outcome && (
        <p className="clab-inline-error" role="alert">
          The treatment and the outcome must be distinct variables.
        </p>
      )}

      {stale && result ? (
        <div className="clab-stale clab-stale--active" data-testid="identification-stale" role="alert">
          <strong>Results are stale.</strong> The graph’s scientific content changed since this
          run (edges, scope or observed status). Re-run identification before trusting anything
          shown below.
        </div>
      ) : null}

      {result && status ? (
        <section
          className={`clab-ident-status clab-ident-status--${status.tone}`}
          data-testid="identification-status"
        >
          <h4>{status.label}</h4>
          {search?.search_status === 'incomplete' && search.status_reason ? (
            <p className="clab-note clab-note--warn">{search.status_reason}</p>
          ) : null}
          {result.identification.status === 'no_eligible_backdoor_set' && (
            <p className="clab-note">
              The search finished within all bounds and found no observed set satisfying the
              classical backdoor criterion. This is specific to the backdoor criterion on this
              assumed graph — it does <em>not</em> prove the effect is unidentifiable by every
              method (front-door and instrumental-variable strategies are outside S8C).
            </p>
          )}
        </section>
      ) : null}

      {search ? (
        <section className="clab-ident-section" aria-label="Suggested adjustment sets">
          <h4>Suggested sets (inclusion-minimal, verified)</h4>
          {search.sets.length === 0 ? (
            <p className="clab-note clab-note--quiet">None reported{search.search_status === 'incomplete' ? ' — and the search is incomplete.' : '.'}</p>
          ) : (
            search.sets.map((candidate, index) => (
              <div key={index} className="clab-ident-set" data-testid="suggested-set">
                <SetChips
                  variables={candidate.set}
                  draft={draft}
                  highlighted={highlighted}
                  onToggleHighlight={props.onToggleHighlight}
                />
                <div className="clab-actions clab-actions--end">
                  <button
                    type="button"
                    className="btn btn--small"
                    onClick={() => applySet(candidate.set)}
                    title="Load this set into the custom tester and highlight it on the graph"
                  >
                    Inspect this set
                  </button>
                </div>
              </div>
            ))
          )}
          <p className="clab-note clab-note--quiet">
            Inclusion-minimal: no proper subset of a reported set also satisfies the criterion.
            Minimal does not mean smallest overall — several minimal sets of different sizes can
            exist.
          </p>
        </section>
      ) : null}

      <section className="clab-ident-section" aria-label="Custom adjustment set">
        <h4>Test a custom adjustment set</h4>
        {candidateList.length === 0 ? (
          <p className="clab-note clab-note--quiet">No eligible observed candidates in this graph.</p>
        ) : (
          <div className="clab-check-grid" data-testid="adjustment-candidates">
            {candidateList.map((nodeId) => (
              <label key={nodeId} className="clab-check">
                <input
                  type="checkbox"
                  checked={customSet.has(nodeId)}
                  onChange={() => {
                    toggleCustom(nodeId)
                    setEvaluation(null)
                  }}
                  aria-label={`Adjust for ${chipLabel(nodeId, draft)}`}
                />
                <span>{chipLabel(nodeId, draft)}</span>
              </label>
            ))}
          </div>
        )}
        <div className="clab-actions">
          <button
            type="button"
            className="btn btn--small"
            data-testid="evaluate-set"
            onClick={() => void runEvaluation()}
            disabled={!props.datasetId || !props.graphId || widgetBusy || !treatment || !outcome}
          >
            Evaluate this set
          </button>
          {customSet.size > 0 ? (
            <button
              type="button"
              className="btn btn--small"
              onClick={() => {
                setCustomSet(new Set())
                setEvaluation(null)
                props.onHighlight([])
              }}
            >
              Clear set
            </button>
          ) : null}
        </div>
        {evaluation ? (
          <div
            className={`clab-ident-verdict clab-ident-verdict--${evaluation.valid ? 'ok' : 'error'}`}
            data-testid="adjustment-verdict"
          >
            <h4>{evaluation.valid ? 'Set admissible (graphically)' : 'Set not admissible'}</h4>
            {evaluation.violations.map((violation, index) => (
              <p key={index} className="clab-ident-violation">
                <strong>{VIOLATION_LABELS[violation.code] ?? violation.code}</strong>
                {violation.node_id ? ` — ${chipLabel(violation.node_id, draft)}` : ''}: {violation.message}
              </p>
            ))}
            {evaluation.open_backdoor_paths.length > 0 && (
              <p className="clab-note">
                Open backdoor path(s):{' '}
                {evaluation.open_backdoor_paths
                  .map((path) => path.map((id) => chipLabel(id, draft)).join(' → '))
                  .join('; ')}
                {evaluation.path_listing_bounded ? ' (listing truncated at the bound)' : ''}
              </p>
            )}
            <p className="clab-note clab-note--quiet">{evaluation.interpretation}</p>
          </div>
        ) : null}
        {widgetError ? (
          <p className="clab-inline-error" role="alert">{widgetError}</p>
        ) : null}
      </section>

      <section className="clab-ident-section" aria-label="d-separation probe">
        <h4>Probe a conditional independence</h4>
        <p className="clab-note clab-note--quiet">
          Ask the assumed graph whether two variables are d-separated given a set. This is a
          property of the graph, not an empirical independence in the data.
        </p>
        <div className="clab-scope-grid">
          <label className="clab-field">
            <span className="clab-field__label">Variable X</span>
            <select
              value={probeX}
              onChange={(event) => setProbeX(event.target.value)}
              aria-label="d-separation variable X"
            >
              <option value="">Choose…</option>
              {draft.nodes.map((node) => (
                <option key={node.node_id} value={node.node_id}>{node.label}</option>
              ))}
            </select>
          </label>
          <label className="clab-field">
            <span className="clab-field__label">Variable Y</span>
            <select
              value={probeY}
              onChange={(event) => setProbeY(event.target.value)}
              aria-label="d-separation variable Y"
            >
              <option value="">Choose…</option>
              {draft.nodes.map((node) => (
                <option key={node.node_id} value={node.node_id}>{node.label}</option>
              ))}
            </select>
          </label>
        </div>
        {probeX && probeY ? (
          <div className="clab-check-grid" data-testid="d-separation-conditioning">
            {draft.nodes
              .filter((node) => node.node_id !== probeX && node.node_id !== probeY)
              .map((node) => (
                <label key={node.node_id} className="clab-check">
                  <input
                    type="checkbox"
                    checked={probeZ.has(node.node_id)}
                    onChange={() => {
                      setProbeZ((current) => {
                        const next = new Set(current)
                        if (next.has(node.node_id)) next.delete(node.node_id)
                        else next.add(node.node_id)
                        return next
                      })
                    }}
                    aria-label={`Condition on ${node.label}`}
                  />
                  <span>{node.label}</span>
                </label>
              ))}
          </div>
        ) : null}
        <div className="clab-actions">
          <button
            type="button"
            className="btn btn--small"
            data-testid="run-d-separation"
            onClick={() => void runProbe()}
            disabled={!probeX || !probeY || !props.datasetId || !props.graphId || widgetBusy}
          >
            Test d-separation
          </button>
        </div>
        {probeResult ? (
          <div
            className={`clab-ident-verdict clab-ident-verdict--${probeResult.d_separated ? 'ok' : 'warn'}`}
            data-testid="d-separation-verdict"
          >
            <h4>
              {probeResult.d_separated ? 'd-separated' : 'd-connected'} given{' '}
              {probeResult.conditioning.length === 0 ? 'nothing' : probeResult.conditioning.map((id) => chipLabel(id, draft)).join(', ')}
            </h4>
            <p className="clab-note clab-note--quiet">{probeResult.interpretation}</p>
          </div>
        ) : null}
      </section>

      {explanations.length > 0 ? (
        <section className="clab-ident-section" aria-label="Scientific explanations">
          <h4>Why the graph answers this way</h4>
          {explanations.map((explanation, index) => {
            const open = openExplanation === explanation.code || (openExplanation === null && index === 0)
            return (
              <div key={explanation.code} className="clab-ident-explanation" data-testid="explanation">
                <button
                  type="button"
                  className="clab-ident-explanation__toggle"
                  aria-expanded={open}
                  onClick={() => setOpenExplanation(open ? null : explanation.code)}
                >
                  {explanation.title}
                </button>
                {open ? (
                  <div className="clab-ident-explanation__body">
                    <p>{explanation.body}</p>
                  </div>
                ) : null}
              </div>
            )
          })}
        </section>
      ) : null}

      {result?.identification.caveats.length ? (
        <section className="clab-issue-list clab-issue-list--warnings" aria-label="Scientific caveats">
          <h4>Caveats</h4>
          {result.identification.caveats.map((caveat, index) => (
            <p key={index} className="clab-issue">
              {caveat}
            </p>
          ))}
        </section>
      ) : null}
    </div>
  )
}
