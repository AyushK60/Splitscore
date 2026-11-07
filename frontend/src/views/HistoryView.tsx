/**
 * Research history (S10-A).
 *
 * One read-only view over every analysis run this session has stored for the
 * loaded dataset: leakage audits, split comparisons, model runs, estimation
 * runs and the S9C subgroup/robustness/what-if analyses. The view is a
 * projection of the server's bounded in-memory run store — it stores nothing
 * itself, never re-runs an analysis, and states plainly when a run is stale,
 * when its data was never recorded, and that expired runs are simply gone.
 *
 * Each run can export a portable, metadata-only reproducibility manifest
 * (canonical JSON with a verifiable hash). No dataset content and no results
 * are embedded in a manifest.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { researchApi } from '../api/client'
import type {
  DatasetLoadedResponse,
  HistoryEntry,
  HistoryResponse,
  RunReproducibilityManifest,
} from '../api/types'
import { formatCompact } from '../estimation/format'
import type { ViewId } from '../lib/router'

const ANALYSIS_LABELS: Record<string, string> = {
  leakage_audit: 'Leakage audit',
  split_comparison: 'Split comparison',
  statistical_model: 'Statistical model',
  prediction_model: 'Predictive model',
  estimation_comparison: 'Effect comparison',
  estimation: 'Effect estimation',
  subgroups: 'Subgroup effects',
  robustness: 'Robustness experiment',
  what_if: 'What-if scenario',
}

function analysisLabel(kind: string): string {
  return ANALYSIS_LABELS[kind] ?? kind
}

function shortHash(value: string | null | undefined, length = 12): string {
  return typeof value === 'string' && value.length > length ? `${value.slice(0, length)}…` : value ?? '—'
}

function describeParameters(entry: HistoryEntry): Array<{ label: string; value: string }> {
  const parameters = entry.parameters as Record<string, unknown>
  const rows: Array<{ label: string; value: string }> = []
  const push = (label: string, value: unknown) => {
    if (value === null || value === undefined || value === '') return
    const text = typeof value === 'string' ? value : JSON.stringify(value)
    if (text.length > 0) rows.push({ label, value: text })
  }
  if (entry.kind === 'estimation') {
    push('Estimand', parameters.estimand)
    push('Treatment → outcome', `${parameters.treatment_node} → ${parameters.outcome_node}`)
    push('Adjustment set', parameters.adjustment_nodes)
    push('Estimators', parameters.estimators)
    push('Cohort rows', parameters.cohort_rows)
    const seed = (entry.reproducibility as Record<string, unknown>).resolved_seed
    push('Seed', seed)
    if (parameters.subgroup) push('Subgroup', parameters.subgroup)
    if (parameters.experiment) push('Experiment', parameters.experiment)
    if (parameters.scenario) push('Scenario', parameters.scenario)
  } else if (entry.kind === 'audit') {
    push('Target', parameters.target)
    push('Split', parameters.split)
    push('Findings', parameters.findings_total)
  } else if (entry.kind === 'comparison') {
    push('Strategies', parameters.strategies)
    push('Target', parameters.target)
  } else {
    push('Task', parameters.task)
    push('Formula', parameters.formula)
    push('Outcome', parameters.outcome)
    push('Predictors', parameters.predictors)
  }
  return rows
}

function downloadManifest(entry: HistoryEntry, manifest: RunReproducibilityManifest) {
  const filename = `splitscope_manifest_${entry.analysis_kind}_${entry.run_id}.json`
  const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export function HistoryView({
  dataset,
  onNavigate,
}: {
  dataset: DatasetLoadedResponse
  onNavigate: (view: ViewId) => void
}) {
  const datasetId = dataset.dataset.dataset_id
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<string>('all')
  const [selected, setSelected] = useState<string | null>(null)
  const [manifestBusy, setManifestBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setHistory(await researchApi.runHistory(datasetId))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The run history could not be loaded.')
    }
  }, [datasetId])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = useMemo(() => {
    if (!history) return []
    if (filter === 'all') return history.runs
    if (filter === 'stale') return history.runs.filter((entry) => entry.stale)
    return history.runs.filter((entry) => entry.analysis_kind === filter)
  }, [history, filter])

  async function exportManifest(entry: HistoryEntry) {
    setManifestBusy(entry.run_id)
    try {
      const manifest = await researchApi.runManifest(datasetId, entry.run_id)
      downloadManifest(entry, manifest)
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'The reproducibility manifest could not be exported.',
      )
    } finally {
      setManifestBusy(null)
    }
  }

  if (!history) {
    return (
      <section className="rs">
        <div className="rs-empty">
          <p className="rs-eyebrow">Research history</p>
          <h1 className="rs-h1">{error ?? 'Loading the run history…'}</h1>
          {error ? (
            <button type="button" className="rs-btn rs-btn--primary" onClick={() => void load()}>
              Try again
            </button>
          ) : null}
        </div>
      </section>
    )
  }

  const kinds = Array.from(new Set(history.runs.map((entry) => entry.analysis_kind)))

  return (
    <section className="rs" data-testid="history-view">
      <header className="rs-head">
        <div>
          <p className="rs-eyebrow">Research history</p>
          <h1 className="rs-h1">Every analysis this session has stored</h1>
          <p className="rs-sub">
            {formatCompact(history.runs.length)} run{history.runs.length === 1 ? '' : 's'} for{' '}
            {history.dataset.name} · {history.stale_count} stale · bounded in-memory store, TTL{' '}
            {Math.round((history.store.limits.ttl_seconds ?? 0) / 60)} min
          </p>
        </div>
        <div className="rs-head__actions">
          <button type="button" className="rs-btn" onClick={() => void load()}>
            Refresh
          </button>
          <button type="button" className="rs-btn" onClick={() => onNavigate('export')}>
            Open Report Studio
          </button>
        </div>
      </header>

      <div className="card hist-note">
        <p>{history.storage_note}</p>
      </div>

      <nav className="rs-tabs" aria-label="History filters">
        {[
          { id: 'all', label: `All (${history.runs.length})` },
          { id: 'stale', label: `Stale (${history.stale_count})` },
          ...kinds.map((kind) => ({
            id: kind,
            label: `${analysisLabel(kind)} (${history.counts_by_analysis_kind[kind] ?? 0})`,
          })),
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`rstab${filter === tab.id ? ' rstab--active' : ''}`}
            onClick={() => setFilter(tab.id)}
          >
            <span className="rstab__label">{tab.label}</span>
          </button>
        ))}
      </nav>

      {filtered.length === 0 ? (
        <div className="card rsempty" aria-label="No runs recorded yet">
          <p className="rs-eyebrow">No runs in this filter</p>
          <p className="rs-sub">
            Run an analysis first — an audit, a model, an estimation or a Causal-research
            experiment — and it will appear here with its identity, parameters and staleness
            state. Runs that expire or are evicted are removed from this history entirely.
          </p>
        </div>
      ) : (
        <ul className="hist-list" aria-label="Stored runs">
          {filtered.map((entry) => (
            <li key={entry.run_id} className="card hist-run" data-testid={`history-run-${entry.run_id}`}>
              <div className="hist-run__head">
                <div>
                  <p className="rs-eyebrow">{analysisLabel(entry.analysis_kind)}</p>
                  <h2 className="hist-run__title">{entry.label || entry.run_id}</h2>
                  <p className="hist-run__meta">
                    <span className="rs-mono">{entry.run_id}</span> ·{' '}
                    {entry.created_at_utc ?? `age ${Math.round(entry.age_seconds)} s`} ·{' '}
                    dataset <span className="rs-mono">{shortHash(entry.dataset.dataset_fingerprint_sha256)}</span>
                    {entry.graph ? (
                      <>
                        {' '}
                        · graph <span className="rs-mono">{shortHash(entry.graph.graph_id)}</span>
                      </>
                    ) : null}
                  </p>
                </div>
                <div className="hist-run__actions">
                  <button
                    type="button"
                    className="rs-btn"
                    onClick={() => setSelected(selected === entry.run_id ? null : entry.run_id)}
                    aria-expanded={selected === entry.run_id}
                  >
                    {selected === entry.run_id ? 'Hide details' : 'Details'}
                  </button>
                  <button
                    type="button"
                    className="rs-btn"
                    onClick={() => void exportManifest(entry)}
                    disabled={manifestBusy === entry.run_id}
                  >
                    {manifestBusy === entry.run_id ? 'Preparing…' : 'Download manifest'}
                  </button>
                </div>
              </div>

              {entry.stale ? (
                <div className="callout callout--warn" role="alert">
                  <strong>Stale.</strong>{' '}
                  <ul className="hist-reasons">
                    {entry.staleness_reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {selected === entry.run_id ? (
                <dl className="hist-params" aria-label="Run parameters">
                  {describeParameters(entry).map((row) => (
                    <div key={row.label} className="hist-params__row">
                      <dt>{row.label}</dt>
                      <dd className="rs-mono">{row.value}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
