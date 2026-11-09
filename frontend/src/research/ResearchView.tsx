/**
 * estimation - Causal Research stage.
 *
 * One stage with three focused views: Subgroup effects, Robustness
 * and What-If. The stage never re-collects the study by hand:
 * it builds on a stored estimation run, rebuilding that run's exact request
 * from its recorded reproducibility block, so every advanced analysis is
 * computed on the same cohort, adjustment set and graph fingerprint as the
 * estimate it refines. A stale or missing estimation run is an explicit
 * dead-end that points back to the estimation studio - never a silent
 * re-specification.
 */

import { useCallback, useEffect, useState } from 'react'

import { causalApi, estimationApi } from '../api/client'
import type {
  CausalGraphPayload,
  EstimationRequestPayload,
  EstimationRunPayload,
} from '../api/types'
import { formatAgo, formatInteger } from '../estimation/format'
import { useApp } from '../state/AppState'
import { requestFromRun } from './researchModel'
import { RobustnessView } from './RobustnessView'
import { SubgroupView, type SubgroupVariableOption } from './SubgroupView'
import { WhatIfView } from './WhatIfView'

type ResearchTab = 'subgroups' | 'robustness' | 'whatif'

const TABS: Array<{ id: ResearchTab; label: string; hint: string }> = [
  { id: 'subgroups', label: 'Subgroup effects', hint: 'Heterogeneity across a baseline variable' },
  { id: 'robustness', label: 'Robustness', hint: 'Subsampling, placebo and sensitivity' },
  { id: 'whatif', label: 'What-if', hint: 'Model-based scenario predictions' },
]

interface StudyContext {
  run: EstimationRunPayload
  request: EstimationRequestPayload
  graph: CausalGraphPayload | null
}

export function ResearchView({ onNavigate }: { onNavigate: (view: 'estimation' | 'causal') => void }) {
  const { dataset } = useApp()
  const datasetId = dataset?.dataset?.dataset_id ?? null

  const [runs, setRuns] = useState<Array<{ run_id: string; label: string; created_seconds_ago: number }>>([])
  const [runsBusy, setRunsBusy] = useState(false)
  const [runsError, setRunsError] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string>('')
  const [study, setStudy] = useState<StudyContext | null>(null)
  const [studyError, setStudyError] = useState<string | null>(null)
  const [studyBusy, setStudyBusy] = useState(false)
  const [tab, setTab] = useState<ResearchTab>('subgroups')

  const refreshRuns = useCallback(async () => {
    if (!datasetId) return
    setRunsBusy(true)
    setRunsError(null)
    try {
      const listing = await estimationApi.runs(datasetId)
      setRuns(listing.runs)
    } catch {
      setRunsError('Run history could not be loaded. The backend may have restarted.')
    } finally {
      setRunsBusy(false)
    }
  }, [datasetId])

  useEffect(() => {
    void refreshRuns()
  }, [refreshRuns])

  // Load the selected stored run and its graph; refuse a stale run as the
  // study context - the numbers it would propagate are labelled not current.
  useEffect(() => {
    if (!datasetId || !selectedRunId) {
      setStudy(null)
      return
    }
    let cancelled = false
    const sequence = ++loadSequence
    const load = async () => {
      setStudyBusy(true)
      setStudyError(null)
      try {
        const run = await estimationApi.runDetail(datasetId, selectedRunId)
        if (cancelled || sequence !== loadSequence) return
        if (run.stale) {
          setStudy(null)
          setStudyError(
            'That estimation run is stale: the dataset or the graph changed after it was computed. Re-run the comparison in the Effect Estimation Studio, then build on the new result.',
          )
          return
        }
        const graph = await causalApi.get(datasetId, run.reproducibility.graph_id)
        if (cancelled || sequence !== loadSequence) return
        setStudy({ run, request: requestFromRun(run.reproducibility), graph })
      } catch (caught) {
        if (cancelled || sequence !== loadSequence) return
        setStudy(null)
        setStudyError(
          caught instanceof Error ? caught.message : 'The stored run could not be loaded.',
        )
      } finally {
        if (!cancelled && sequence === loadSequence) setStudyBusy(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [datasetId, selectedRunId])

  if (!datasetId) {
    return (
      <section className="card rsempty" aria-label="No dataset">
        <h2>Causal research</h2>
        <p>Load a dataset first. Advanced analyses are computed from that dataset on the server.</p>
      </section>
    )
  }

  const variables: SubgroupVariableOption[] = (study?.graph?.nodes ?? [])
    .filter(
      (node) =>
        node.observed &&
        node.column &&
        node.node_id !== study?.request.treatment_node &&
        node.node_id !== study?.request.outcome_node,
    )
    .map((node) => ({
      node_id: node.node_id,
      label: node.label,
      column: node.column,
      // resolved_column_type is the pandas dtype name from the registry.
      kind: /int|float/.test(node.resolved_column_type ?? '')
        ? ('numeric' as const)
        : /category|bool|object/.test(node.resolved_column_type ?? '')
          ? ('categorical' as const)
          : ('unknown' as const),
    }))

  return (
    <div className="rs-stage">
      <header className="rsheader">
        <p className="rsheader__eyebrow">Causal research</p>
        <h1>Subgroups, robustness and what-if scenarios</h1>
        <p className="rsheader__lede">
          Advanced analyses build on a completed estimation run: they reuse its verified
          adjustment set, cohort and graph fingerprint, so every number here is computed on the
          same study - never re-specified silently.
        </p>
      </header>

      <section className="card rsrunpick" aria-label="Study context">
        <div className="rsrunpick__row">
          <label className="rsfield rsfield--grow">
            <span className="rsfield__label">Build on this estimation run</span>
            <select
              value={selectedRunId}
              onChange={(event) => setSelectedRunId(event.target.value)}
              disabled={runsBusy || runs.length === 0}
              data-testid="research-run-select"
            >
              <option value="">
                {runs.length === 0 ? 'No stored estimation runs yet' : 'Choose a stored run…'}
              </option>
              {runs.map((run) => (
                <option key={run.run_id} value={run.run_id}>
                  {run.label} · {formatAgo(run.created_seconds_ago)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn"
            onClick={() => void refreshRuns()}
            disabled={runsBusy}
          >
            Refresh
          </button>
          <button type="button" className="btn" onClick={() => onNavigate('estimation')}>
            Open the estimation studio
          </button>
        </div>
        {runsError ? <p className="estrow__failure">{runsError}</p> : null}
        {runs.length === 0 && !runsBusy ? (
          <p className="estsum__hint" data-testid="research-no-runs">
            No estimation run exists for this dataset yet. Run a comparison in the Effect
            Estimation Studio first; subgroup, robustness and what-if analyses reuse its study.
          </p>
        ) : null}
        {studyBusy ? <p className="muted" role="status">Loading the stored run…</p> : null}
        {studyError ? (
          <div className="callout callout--warn" role="alert" data-testid="research-study-error">
            <p style={{ margin: 0 }}>{studyError}</p>
          </div>
        ) : null}
        {study ? (
          <dl className="rsstudymeta" data-testid="research-study-meta">
            <div>
              <dt>Treatment</dt>
              <dd>{study.run.reproducibility.treatment_node}</dd>
            </div>
            <div>
              <dt>Outcome</dt>
              <dd>{study.run.reproducibility.outcome_node}</dd>
            </div>
            <div>
              <dt>Adjustment set</dt>
              <dd>
                {study.run.reproducibility.adjustment_nodes.length === 0
                  ? 'empty (randomised on this graph)'
                  : study.run.reproducibility.adjustment_nodes.join(', ')}
              </dd>
            </div>
            <div>
              <dt>Cohort</dt>
              <dd>
                {formatInteger(study.run.analysis.rows_final)} rows ·{' '}
                {study.run.reproducibility.cohort.split_assignment_id
                  ? `${study.run.reproducibility.cohort.partition} partition`
                  : 'all rows'}
              </dd>
            </div>
            <div>
              <dt>Graph</dt>
              <dd>
                {study.graph?.name ?? study.run.reproducibility.graph_id} ·{' '}
                {study.run.reproducibility.graph_spec_fingerprint_sha256.slice(0, 12)}…
              </dd>
            </div>
          </dl>
        ) : null}
      </section>

      {study ? (
        <>
          <nav className="rstabs" aria-label="Research views">
            {TABS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                className={`rstab${tab === entry.id ? ' rstab--active' : ''}`}
                aria-current={tab === entry.id ? 'page' : undefined}
                onClick={() => setTab(entry.id)}
                data-testid={`research-tab-${entry.id}`}
              >
                <span className="rstab__label">{entry.label}</span>
                <span className="rstab__hint">{entry.hint}</span>
              </button>
            ))}
          </nav>

          {tab === 'subgroups' ? (
            <SubgroupView
              key={`subgroups-${study.run.run_id}`}
              datasetId={datasetId}
              graphId={study.run.reproducibility.graph_id}
              graphFingerprint={study.request.expected_spec_fingerprint_sha256 ?? ''}
              request={study.request}
              variables={variables}
            />
          ) : null}
          {tab === 'robustness' ? (
            <RobustnessView
              key={`robustness-${study.run.run_id}`}
              datasetId={datasetId}
              graphId={study.run.reproducibility.graph_id}
              graphFingerprint={study.request.expected_spec_fingerprint_sha256 ?? ''}
              request={study.request}
            />
          ) : null}
          {tab === 'whatif' ? (
            <WhatIfView
              key={`whatif-${study.run.run_id}`}
              datasetId={datasetId}
              graphId={study.run.reproducibility.graph_id}
              graphFingerprint={study.request.expected_spec_fingerprint_sha256 ?? ''}
              request={study.request}
              covariates={study.run.analysis.covariates}
            />
          ) : null}
        </>
      ) : null}
    </div>
  )
}

let loadSequence = 0
