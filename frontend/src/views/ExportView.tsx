/**
 * Report / Export Studio.
 *
 * The studio composes one dossier from runs the user actually executed. It
 * keeps two ideas separate: *sources* (named run IDs in the server store) and
 * *sections* (what a reviewer needs to see). Unavailable sections stay visible
 * with their reason. The preview is rendered from the same object that the
 * JSON and HTML downloads return.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { dossierPath, estimationApi, modelsApi, reportsApi } from '../api/client'
import type { DossierReport, DossierRequest, EstimationRunSummary } from '../api/types'
import { ReportPreview } from '../components/report/ReportPreview'
import { Callout } from '../components/ui'
import { bytes, integer, pluralise } from '../lib/format'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'

const SECTION_ORDER = [
  'summary',
  'provenance',
  'study',
  'audit',
  'scorecard',
  'findings',
  'comparison',
  'models',
  'causal_graph',
  'identification',
  'causal_estimation',
  'subgroups',
  'robustness',
  'what_if',
  'methodology',
  'limitations',
  'reproducibility',
] as const

const SECTION_COPY: Record<string, { title: string; note: string }> = {
  summary: { title: 'Executive summary', note: 'Dataset, split, key findings and cautions.' },
  provenance: { title: 'Dataset and provenance', note: 'Identity, fingerprint, profile and columns.' },
  study: { title: 'Study card', note: 'Only the context a user declared.' },
  audit: { title: 'Leakage audit', note: 'Stored run, rule outcomes and not-evaluated list.' },
  scorecard: { title: 'Risk scorecard', note: 'Category states, never a numeric safety score.' },
  findings: { title: 'Findings and evidence', note: 'Counts, denominators and bounded examples.' },
  comparison: { title: 'Split comparison', note: 'Consequences of candidate splits; no winner.' },
  models: { title: 'Model Lab', note: 'Metrics and diagnostics for selected runs.' },
  limitations: { title: 'Limitations', note: 'Scope, assumptions and missing evaluations.' },
  reproducibility: { title: 'Reproducibility', note: 'Run IDs, fingerprint, versions and integrity.' },
  causal_graph: { title: 'Causal graph', note: 'The assumed DAG: nodes, edges, assumptions.' },
  identification: { title: 'Identification', note: 'Backdoor verdicts recorded by the estimation gate.' },
  causal_estimation: { title: 'Effect estimation', note: 'Stored estimation runs: cohort, estimators, intervals.' },
  subgroups: { title: 'Subgroup effects', note: 'Heterogeneity with multiple-comparisons caveats.' },
  robustness: { title: 'Robustness', note: 'One experiment with its parameters and honest scope.' },
  what_if: { title: 'What-if scenario', note: 'Conditional model expectations; never counterfactuals.' },
  methodology: { title: 'Methodology', note: 'Generated methods section; gaps are explicit.' },
}

const ANALYSIS_KIND_LABEL: Record<string, string> = {
  estimation: 'Estimation',
  estimation_comparison: 'Comparison',
  subgroups: 'Subgroups',
  robustness: 'Robustness',
  what_if: 'What-if',
}

interface ModelRun {
  run_id: string
  kind: string
  dataset_id: string
  label: string
  created_seconds_ago: number
}

export function ExportView({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const { dataset, audit, comparison, health, busyLabel, download, refreshHealth } = useApp()
  const [modelRuns, setModelRuns] = useState<ModelRun[] | null>(null)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [estimationRuns, setEstimationRuns] = useState<EstimationRunSummary[] | null>(null)
  const [estimationError, setEstimationError] = useState<string | null>(null)
  const [selectedEstimation, setSelectedEstimation] = useState<string[]>([])
  const [presentation, setPresentation] = useState<'concise' | 'technical'>('concise')
  const [sections, setSections] = useState<string[]>([...SECTION_ORDER])
  const [report, setReport] = useState<DossierReport | null>(null)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const lastAutoSignature = useRef<string | null>(null)
  const sectionsTouched = useRef(false)
  const modelsTouched = useRef(false)
  const estimationTouched = useRef(false)
  const generateRef = useRef<() => Promise<void>>(async () => {})

  useEffect(() => {
    void refreshHealth()
  }, [refreshHealth])

  useEffect(() => {
    if (!dataset) return
    let cancelled = false
    setModelRuns(null)
    setModelsError(null)
    setSelectedModels([])
    setEstimationRuns(null)
    setEstimationError(null)
    setSelectedEstimation([])
    estimationTouched.current = false
    setReport(null)
    setError(null)
    setDirty(false)
    lastAutoSignature.current = null
    modelsTouched.current = false
    sectionsTouched.current = false
    modelsApi
      .runs(dataset.dataset.dataset_id)
      .then((response) => {
        if (cancelled) return
        const runs = response.runs.map((run) => ({
          run_id: run.run_id,
          kind: run.kind,
          dataset_id: run.dataset_id,
          label: run.label,
          created_seconds_ago: run.created_seconds_ago,
        }))
        setModelRuns(runs)
        if (!modelsTouched.current) {
          setSelectedModels(runs.map((run) => run.run_id))
        }
      })
      .catch((reason) => {
        if (cancelled) return
        setModelRuns([])
        setModelsError(reason instanceof Error ? reason.message : 'Model runs could not be listed.')
      })
    estimationApi
      .runs(dataset.dataset.dataset_id)
      .then((response) => {
        if (cancelled) return
        const runs = response.runs.map((run) => ({
          run_id: run.run_id,
          kind: run.kind,
          dataset_id: run.dataset_id,
          label: run.label,
          created_seconds_ago: run.created_seconds_ago,
          analysis_kind: run.analysis_kind,
        }))
        setEstimationRuns(runs)
        if (!estimationTouched.current) {
          // Pre-select causal estimation runs only: subgroup/robustness/what-if
          // runs are optional enrichments the user selects deliberately.
          setSelectedEstimation(
            runs
              .filter((run) => run.analysis_kind === 'estimation' || run.analysis_kind === 'estimation_comparison')
              .map((run) => run.run_id),
          )
        }
      })
      .catch((reason) => {
        if (cancelled) return
        setEstimationRuns([])
        setEstimationError(reason instanceof Error ? reason.message : 'Estimation runs could not be listed.')
      })
    return () => {
      cancelled = true
    }
  }, [dataset])

  const request = useMemo<DossierRequest>(
    () => ({
      sections,
      audit_run_id: audit?.run_id ?? null,
      comparison_run_id: comparison?.run_id ?? null,
      model_run_ids: selectedModels,
      estimation_run_ids: selectedEstimation,
      presentation,
    }),
    [sections, audit?.run_id, comparison?.run_id, selectedModels, selectedEstimation, presentation],
  )

  const generate = useCallback(async () => {
    if (!dataset) return
    setGenerating(true)
    setError(null)
    try {
      const result = await reportsApi.generate(dataset.dataset.dataset_id, request)
      setReport(result)
      setDirty(false)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The dossier could not be generated.')
    } finally {
      setGenerating(false)
    }
  }, [dataset, request])
  generateRef.current = generate

  // Generate once the initial source list is known, and again when the named
  // runs change. Section or model toggles stay explicit: they mark the preview
  // stale until the user regenerates.
  useEffect(() => {
    if (!dataset || modelRuns === null) return
    const signature = [
      dataset.dataset.dataset_id,
      audit?.run_id ?? '',
      comparison?.run_id ?? '',
      modelRuns.map((run) => run.run_id).join(','),
    ].join('|')
    if (lastAutoSignature.current === signature) return
    lastAutoSignature.current = signature
    void generateRef.current()
  }, [dataset, modelRuns, audit?.run_id, comparison?.run_id])

  const available: Record<string, boolean> = {
    summary: true,
    provenance: true,
    study: true,
    audit: Boolean(audit),
    scorecard: Boolean(audit),
    findings: Boolean(audit),
    comparison: Boolean(comparison),
    models: Boolean(modelRuns?.length),
    causal_graph: Boolean(selectedEstimation.length),
    identification: Boolean(selectedEstimation.length),
    causal_estimation: Boolean(
      (estimationRuns ?? []).some(
        (run) =>
          selectedEstimation.includes(run.run_id) &&
          (run.analysis_kind === 'estimation' || run.analysis_kind === 'estimation_comparison'),
      ),
    ),
    subgroups: Boolean(
      (estimationRuns ?? []).some(
        (run) => selectedEstimation.includes(run.run_id) && run.analysis_kind === 'subgroups',
      ),
    ),
    robustness: Boolean(
      (estimationRuns ?? []).some(
        (run) => selectedEstimation.includes(run.run_id) && run.analysis_kind === 'robustness',
      ),
    ),
    what_if: Boolean(
      (estimationRuns ?? []).some(
        (run) => selectedEstimation.includes(run.run_id) && run.analysis_kind === 'what_if',
      ),
    ),
    methodology: true,
    limitations: true,
    reproducibility: true,
  }

  const unavailableNote: Record<string, string> = {
    audit: 'Run the leakage audit to add this section.',
    scorecard: 'Run the leakage audit to add this section.',
    findings: 'Run the leakage audit to add this section.',
    comparison: 'Run a split comparison to add this section.',
    models: 'Fit a model in Model Lab to add this section.',
    causal_graph: 'Select a stored estimation run to add its causal graph.',
    identification: 'Select a stored estimation run to add its identification verdicts.',
    causal_estimation: 'Select a stored estimation comparison to add this section.',
    subgroups: 'Run subgroup effects in Causal research, then select the run here.',
    robustness: 'Run a robustness experiment in Causal research, then select the run here.',
    what_if: 'Run a what-if scenario in Causal research, then select the run here.',
  }

  const toggleSection = (section: string) => {
    sectionsTouched.current = true
    setSections((previous) => {
      if (previous.includes(section)) {
        const next = previous.filter((item) => item !== section)
        return next.length ? next : previous
      }
      return SECTION_ORDER.filter((item) => item === section || previous.includes(item))
    })
    setDirty(true)
  }

  const toggleModel = (runId: string) => {
    modelsTouched.current = true
    setSelectedModels((previous) =>
      previous.includes(runId) ? previous.filter((id) => id !== runId) : [...previous, runId],
    )
    setDirty(true)
  }

  const selectAllModels = () => {
    modelsTouched.current = true
    setSelectedModels((modelRuns ?? []).map((run) => run.run_id))
    setDirty(true)
  }

  const activeSections = report?.included_sections.length ?? sections.length
  const canGenerate = Boolean(dataset) && sections.length > 0 && !generating
  const printDisabled = busyLabel !== null || !report

  return (
    <div className="stack report-studio">
      <header className="report-studio__intro">
        <div>
          <p className="report-studio__eyebrow">Publication layer · evidence dossier</p>
          <h1>Compose the evidence you actually produced</h1>
          <p className="report-studio__lede">
            One dossier, built from named runs in this session. Sections you did not run are shown
            as unavailable - never as a clean result. The preview, JSON and printable HTML are all
            generated from the same server payload.
          </p>
        </div>
        <div className="report-studio__identity">
          <span>{dataset ? dataset.dataset.name : 'No dataset loaded'}</span>
          {dataset ? (
            <span className="mono">
              {integer(dataset.dataset.row_count)} × {integer(dataset.dataset.column_count)} ·{' '}
              {dataset.dataset.fingerprint_sha256.slice(0, 12)}…
            </span>
          ) : null}
        </div>
      </header>

      <div className="report-studio__grid">
        <aside className="report-config" aria-label="Dossier composition">
          <section className="report-config__block">
            <div className="report-config__head">
              <h2>Sources</h2>
              <span className="report-config__status">{modelRuns === null ? 'loading…' : 'stored runs'}</span>
            </div>
            {!dataset ? (
              <p className="small muted">Load a dataset to compose a report.</p>
            ) : (
              <>
                <div className="report-source">
                  <span className="report-source__mark report-source__mark--ok" aria-hidden="true" />
                  <div>
                    <strong>{dataset.dataset.name}</strong>
                    <span>Dataset · {integer(dataset.dataset.row_count)} rows</span>
                  </div>
                </div>
                <div className="report-source">
                  <span
                    className={`report-source__mark${audit ? ' report-source__mark--ok' : ''}`}
                    aria-hidden="true"
                  />
                  <div>
                    <strong>Leakage audit</strong>
                    <span className="mono">{audit?.run_id ?? 'not run in this session'}</span>
                  </div>
                </div>
                <div className="report-source">
                  <span
                    className={`report-source__mark${comparison ? ' report-source__mark--ok' : ''}`}
                    aria-hidden="true"
                  />
                  <div>
                    <strong>Split comparison</strong>
                    <span className="mono">{comparison?.run_id ?? 'not run in this session'}</span>
                  </div>
                </div>
                <div className="report-source report-source--stacked">
                  <span
                    className={`report-source__mark${modelRuns?.length ? ' report-source__mark--ok' : ''}`}
                    aria-hidden="true"
                  />
                  <div>
                    <strong>Model Lab runs</strong>
                    <span>
                      {modelsError
                        ? modelsError
                        : modelRuns === null
                          ? 'listing stored runs…'
                          : `${integer(modelRuns.length)} available · ${integer(selectedModels.length)} selected`}
                    </span>
                  </div>
                </div>
                <div className="report-source report-source--stacked">
                  <span
                    className={`report-source__mark${estimationRuns?.length ? ' report-source__mark--ok' : ''}`}
                    aria-hidden="true"
                  />
                  <div>
                    <strong>Causal estimation runs</strong>
                    <span>
                      {estimationError
                        ? estimationError
                        : estimationRuns === null
                          ? 'listing stored runs…'
                          : `${integer(estimationRuns.length)} available · ${integer(selectedEstimation.length)} selected`}
                    </span>
                  </div>
                </div>
                {estimationRuns && estimationRuns.length > 0 ? (
                  <div className="report-models">
                    <div className="report-models__actions">
                      <button
                        type="button"
                        className="report-link"
                        onClick={() => {
                          estimationTouched.current = true
                          setSelectedEstimation(estimationRuns.map((run) => run.run_id))
                          setDirty(true)
                        }}
                        disabled={selectedEstimation.length === estimationRuns.length}
                      >
                        Include all
                      </button>
                      <span>{selectedEstimation.length} of {estimationRuns.length}</span>
                    </div>
                    {estimationRuns.map((run) => (
                      <label key={run.run_id} className="report-model-toggle">
                        <input
                          type="checkbox"
                          checked={selectedEstimation.includes(run.run_id)}
                          onChange={() => {
                            estimationTouched.current = true
                            setSelectedEstimation((previous) =>
                              previous.includes(run.run_id)
                                ? previous.filter((id) => id !== run.run_id)
                                : [...previous, run.run_id],
                            )
                            setDirty(true)
                          }}
                        />
                        <span>
                          <strong>{ANALYSIS_KIND_LABEL[run.analysis_kind ?? 'estimation'] ?? 'Estimation'} · {run.label || run.run_id}</strong>
                          <span className="mono">{run.run_id}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                ) : null}
                {modelRuns && modelRuns.length > 0 ? (
                  <div className="report-models">
                    <div className="report-models__actions">
                      <button
                        type="button"
                        className="report-link"
                        onClick={selectAllModels}
                        disabled={selectedModels.length === modelRuns.length}
                      >
                        Include all
                      </button>
                      <span>{selectedModels.length} of {modelRuns.length}</span>
                    </div>
                    {modelRuns.map((run) => (
                      <label key={run.run_id} className="report-model-toggle">
                        <input
                          type="checkbox"
                          checked={selectedModels.includes(run.run_id)}
                          onChange={() => toggleModel(run.run_id)}
                        />
                        <span>
                          <strong>{run.label || run.kind}</strong>
                          <span className="mono">{run.run_id}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                ) : null}
              </>
            )}
          </section>

          <section className="report-config__block">
            <div className="report-config__head">
              <h2>Sections</h2>
              <span className="report-config__status">
                {sections.length} of {SECTION_ORDER.length}
              </span>
            </div>
            <div className="report-sections">
              {SECTION_ORDER.map((section) => {
                const isAvailable = available[section]
                return (
                  <label
                    key={section}
                    className={`report-section-toggle${isAvailable ? '' : ' report-section-toggle--unavailable'}`}
                    title={isAvailable ? SECTION_COPY[section].note : unavailableNote[section]}
                  >
                    <input
                      type="checkbox"
                      checked={sections.includes(section)}
                      onChange={() => toggleSection(section)}
                    />
                    <span>
                      <strong>{SECTION_COPY[section].title}</strong>
                      <span>{isAvailable ? SECTION_COPY[section].note : unavailableNote[section]}</span>
                    </span>
                  </label>
                )
              })}
            </div>
            <p className="report-config__note">
              Unavailable sections remain selected so the dossier records the gap; uncheck one to
              omit it. The report never turns a missing analysis into a clean result.
            </p>
          </section>

          <section className="report-config__block report-config__actions">
            <div className="report-config__head">
              <h2>Preview &amp; export</h2>
              <span className="report-config__status">{report ? 'ready' : 'not composed'}</span>
            </div>
            <label className="report-config__presentation">
              <span>Methodology presentation</span>
              <select
                value={presentation}
                onChange={(event) => {
                  setPresentation(event.target.value === 'technical' ? 'technical' : 'concise')
                  setDirty(true)
                }}
              >
                <option value="concise">Concise</option>
                <option value="technical">Technical</option>
              </select>
            </label>
            <button
              type="button"
              className="btn btn--primary report-config__generate"
              disabled={!canGenerate}
              onClick={() => void generate()}
            >
              {generating ? 'Composing dossier…' : report ? 'Update preview' : 'Generate dossier'}
            </button>
            {dirty && report ? (
              <p className="report-config__dirty" role="status">
                Sources or sections changed. Update the preview before exporting.
              </p>
            ) : null}
            <div className="report-export-actions">
              <button
                type="button"
                className="btn btn--small"
                disabled={busyLabel !== null || !report}
                onClick={() =>
                  dataset
                    ? void download(dossierPath(dataset.dataset.dataset_id, 'json'), request)
                    : undefined
                }
              >
                Download dossier JSON
              </button>
              <button
                type="button"
                className="btn btn--small"
                disabled={busyLabel !== null || !report}
                onClick={() =>
                  dataset
                    ? void download(dossierPath(dataset.dataset.dataset_id, 'html'), request)
                    : undefined
                }
              >
                Download self-contained HTML
              </button>
              <button
                type="button"
                className="btn btn--small"
                disabled={printDisabled}
                onClick={() => window.print()}
              >
                Print / Save as PDF
              </button>
            </div>
            <p className="report-config__note">
              PDF is produced by the browser’s print dialog from the same print stylesheet as the
              HTML download. SplitScope does not claim a separate PDF library.
            </p>
            <p className="report-config__note">
              {report
                ? `Preview built ${report.generated_at_utc} · schema ${report.schema_version} · ${activeSections} sections requested.`
                : 'Generate once to inspect the evidence package.'}
            </p>
          </section>
        </aside>

        <div className="report-preview-column">
          {error ? (
            <Callout tone="danger" title="The dossier could not be generated">
              <p>{error}</p>
            </Callout>
          ) : null}
          {!dataset ? (
            <div className="report-empty">
              <h2>No dataset in this session</h2>
              <p>
                The studio can only report runs attached to a loaded dataset. Start with the bundled
                demo or upload a CSV.
              </p>
              <button type="button" className="btn btn--primary" onClick={() => onNavigate('overview')}>
                Go to Start
              </button>
            </div>
          ) : generating && !report ? (
            <div className="report-empty report-empty--busy" role="status">
              <span className="spinner" aria-hidden="true" />
              <p>Assembling the sections you selected…</p>
            </div>
          ) : report ? (
            <>
              {dirty ? (
                <div className="report-stale" role="status">
                  The preview reflects the previous composition. Update it to include your latest
                  selections.
                </div>
              ) : null}
              <div className="report-paper-shell">
                <ReportPreview report={report} />
              </div>
            </>
          ) : (
            <div className="report-empty">
              <h2>No dossier generated yet</h2>
              <p>
                Choose the sections and model runs you want a reviewer to see, then compose the
                dossier. The preview will state any run that is missing.
              </p>
            </div>
          )}
        </div>
      </div>

      <section className="report-archive" aria-labelledby="run-archive-title">
        <div className="report-archive__head">
          <div>
            <p className="report-studio__eyebrow">Run archive</p>
            <h2 id="run-archive-title">Single-run reports and assignments</h2>
          </div>
          <p>
            These are the original per-run artifacts. They remain available alongside the dossier
            and are unchanged by the sections above.
          </p>
        </div>

        <div className="report-archive__grid">
          <article className="report-archive__card">
            <h3>Audit run</h3>
            {!audit ? (
              <div>
                <p className="muted">No audit run in this session.</p>
                <button type="button" className="btn btn--primary btn--small" onClick={() => onNavigate('dataset')}>
                  Run the audit
                </button>
              </div>
            ) : (
              <>
                <dl className="report-kv report-kv--compact">
                  <dt>Run</dt>
                  <dd className="mono">{audit.run_id}</dd>
                  <dt>Split</dt>
                  <dd>{audit.result.split.label}</dd>
                  <dt>Findings</dt>
                  <dd>{integer(audit.result.evaluation.findings_total)}</dd>
                  <dt>Generated</dt>
                  <dd className="mono">{audit.result.generated_at_utc}</dd>
                  <dt>Fingerprint</dt>
                  <dd className="mono report-break">{audit.result.dataset.fingerprint_sha256}</dd>
                </dl>
                {audit.assignment ? (
                  <p className="small">
                    <button
                      type="button"
                      className="btn btn--small"
                      disabled={busyLabel !== null}
                      onClick={() => void download(audit.assignment?.download_path ?? '')}
                    >
                      Download split assignment CSV
                    </button>{' '}
                    <span className="muted">
                      {audit.assignment.label} - every row’s side as the audit used it, keyed by the
                      internal row id.
                    </span>
                  </p>
                ) : null}
                <div className="report-archive__buttons">
                  <button
                    type="button"
                    className="btn btn--primary btn--small"
                    disabled={busyLabel !== null}
                    onClick={() => void download('/api/reports/json', { run_id: audit.run_id })}
                  >
                    Download JSON report
                  </button>
                  <button
                    type="button"
                    className="btn btn--small"
                    disabled={busyLabel !== null}
                    onClick={() => void download('/api/reports/html', { run_id: audit.run_id })}
                  >
                    Download self-contained HTML report
                  </button>
                </div>
              </>
            )}
          </article>

          <article className="report-archive__card">
            <h3>Split comparison run</h3>
            {!comparison ? (
              <div>
                <p className="muted">No comparison run in this session.</p>
                <button
                  type="button"
                  className="btn btn--primary btn--small"
                  onClick={() => onNavigate('comparison')}
                >
                  Compare splits
                </button>
              </div>
            ) : (
              <>
                <dl className="report-kv report-kv--compact">
                  <dt>Run</dt>
                  <dd className="mono">{comparison.run_id}</dd>
                  <dt>Candidates</dt>
                  <dd>{integer(comparison.result.rows.length)}</dd>
                  <dt>Generated</dt>
                  <dd className="mono">{comparison.result.generated_at_utc}</dd>
                </dl>
                <div className="report-archive__buttons">
                  <button
                    type="button"
                    className="btn btn--primary btn--small"
                    disabled={busyLabel !== null}
                    onClick={() => void download('/api/reports/json', { run_id: comparison.run_id })}
                  >
                    Download comparison JSON
                  </button>
                  <button
                    type="button"
                    className="btn btn--small"
                    disabled={busyLabel !== null}
                    onClick={() => void download('/api/reports/html', { run_id: comparison.run_id })}
                  >
                    Download comparison HTML
                  </button>
                </div>
                {comparison.assignments.length ? (
                  <div className="report-archive__assignments">
                    <h4>Split assignments</h4>
                    <p className="small muted">{comparison.sanitization_note}</p>
                    <div className="report-table-wrap">
                      <table className="report-table report-table--assignments">
                        <caption className="sr-only">Per-strategy split assignment downloads</caption>
                        <thead>
                          <tr>
                            <th scope="col">Assignment</th>
                            <th scope="col" className="num">
                              Train
                            </th>
                            <th scope="col" className="num">
                              Test
                            </th>
                            <th scope="col">
                              <span className="sr-only">Download</span>
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {comparison.assignments.map((handle) => (
                            <tr key={handle.assignment_id}>
                              <th scope="row">{handle.label}</th>
                              <td className="num">{integer(handle.train_rows)}</td>
                              <td className="num">{integer(handle.test_rows)}</td>
                              <td className="num">
                                <button
                                  type="button"
                                  className="btn btn--small"
                                  disabled={busyLabel !== null}
                                  onClick={() => void download(handle.download_path)}
                                >
                                  Download CSV
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </article>
        </div>
      </section>

      <details className="report-runtime disclosure">
        <summary>Runtime state and export limits</summary>
        {health ? (
          <>
            <dl className="report-kv report-kv--compact">
              <dt>This process holds</dt>
              <dd>
                {integer(health.store.datasets)} {pluralise(health.store.datasets, 'dataset')},{' '}
                {integer(health.store.runs)} {pluralise(health.store.runs, 'run')},{' '}
                {integer(health.store.assignments)}{' '}
                {pluralise(health.store.assignments, 'split assignment')}
              </dd>
              <dt>Memory used by the store</dt>
              <dd>
                {bytes(health.store.total_bytes)} of {bytes(health.store.limits.max_total_bytes ?? 0)}
              </dd>
              <dt>Evictions / expirations</dt>
              <dd>
                {integer(health.store.evictions)} / {integer(health.store.expirations)}
              </dd>
              <dt>Store TTL</dt>
              <dd>
                {health.store.limits.ttl_seconds ?? '—'} seconds. {health.storage_note}
              </dd>
              <dt>Upload limits</dt>
              <dd>
                {bytes(health.limits.max_upload_bytes)} per file · {integer(health.limits.max_rows)}{' '}
                rows · {integer(health.limits.max_columns)} columns
              </dd>
            </dl>
            <p className="small muted">
              The store lives in the server process: reports can be regenerated only while their
              named runs remain stored. Downloaded JSON and HTML artifacts are the durable copies.
            </p>
          </>
        ) : (
          <p className="muted">The health endpoint has not answered yet.</p>
        )}
      </details>
    </div>
  )
}
