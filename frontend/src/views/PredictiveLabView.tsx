/**
 * Model Lab - predictive evaluation (F10).
 *
 * Everything shown here comes from a fitted server run: candidates compared on
 * a validation partition, one selected model refitted on fit+validation, and a
 * single evaluation on the sealed test partition. The screen never estimates a
 * metric, never tunes on test, and states that a predictive metric is not a
 * causal effect.
 */

import { useCallback, useEffect, useState } from 'react'
import type { JSX } from 'react'

import { ApiError, api, downloadExport, modelsApi } from '../api/client'
import type {
  GeneratedSplitStrategy,
  PredictionRequest,
  PredictionResult,
  PredictionTask,
} from '../api/types'
import {
  ImportanceSection,
  InfluenceSection,
  PrPlot,
  QqPlot,
  ReliabilityPlot,
  SubgroupTable,
} from '../components/PredictiveDiagnostics'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'

interface Props {
  onNavigate: (view: ViewId) => void
}

const MAX_PREDICTORS = 30

const FAMILIES: Record<PredictionTask, Array<{ id: string; label: string }>> = {
  classification: [
    { id: 'baseline', label: 'Dummy prior' },
    { id: 'logistic', label: 'Logistic regression' },
    { id: 'random_forest', label: 'Random forest' },
  ],
  regression: [
    { id: 'baseline', label: 'Dummy mean' },
    { id: 'linear', label: 'Linear regression' },
    { id: 'ridge', label: 'Ridge regression' },
    { id: 'random_forest', label: 'Random forest' },
  ],
}

function fmt(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value !== 0 && Math.abs(value) < 0.001) return value.toExponential(2)
  return value.toPrecision(digits)
}

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function intervalText(low: number | null | undefined, high: number | null | undefined, format = fmt): string {
  if (low === null || low === undefined || high === null || high === undefined) return '—'
  return `${format(low)} – ${format(high)}`
}

function severityClass(severity: string): string {
  return severity === 'high' ? 'callout--danger' : severity === 'medium' ? 'callout--warn' : 'callout--info'
}

function defaultFamilies(task: PredictionTask): string[] {
  return FAMILIES[task].map((entry) => entry.id)
}

export function PredictiveLabView({ onNavigate }: Props): JSX.Element {
  const { dataset, roles, audit } = useApp()
  const datasetId = dataset?.dataset.dataset_id ?? null

  const [task, setTask] = useState<PredictionTask>('classification')
  const [outcome, setOutcome] = useState('')
  const [predictors, setPredictors] = useState<string[]>([])
  const [positiveLevel, setPositiveLevel] = useState<string | null>(null)
  const [outcomeLevels, setOutcomeLevels] = useState<string[]>([])
  const [splitSource, setSplitSource] = useState<'existing' | 'generated'>('existing')
  const [splitStrategy, setSplitStrategy] = useState<GeneratedSplitStrategy>('stratified')
  const [testFraction, setTestFraction] = useState(0.25)
  const [seed, setSeed] = useState(12345)
  const [validationFraction, setValidationFraction] = useState(0.2)
  const [families, setFamilies] = useState<string[]>(defaultFamilies('classification'))
  const [subgroupColumn, setSubgroupColumn] = useState('')
  const [subgroupBins, setSubgroupBins] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<PredictionResult | null>(null)
  const [error, setError] = useState<{ message: string; code?: string; details?: Record<string, unknown> } | null>(
    null,
  )

  const columns = dataset?.dataset.columns ?? []

  useEffect(() => {
    setResult(null)
    setError(null)
    setPositiveLevel(null)
    setSubgroupColumn('')
    setSubgroupBins('')
    if (!dataset) return
    const available = dataset.dataset.columns
    const numeric = available.filter((column) => dataset.column_types[column]?.looks_numeric)
    const target = roles.target && available.includes(roles.target) ? roles.target : null
    const defaultOutcome = target ?? numeric[0] ?? available[0] ?? ''
    const features = roles.features.filter(
      (column) => available.includes(column) && column !== defaultOutcome,
    )
    setOutcome(defaultOutcome)
    setPredictors(
      features.length
        ? features.slice(0, MAX_PREDICTORS)
        : numeric.filter((column) => column !== defaultOutcome).slice(0, 5),
    )
    const initialTask: PredictionTask =
      target && dataset.column_types[target] && !dataset.column_types[target].looks_numeric
        ? 'classification'
        : 'regression'
    setTask(initialTask)
    setFamilies(defaultFamilies(initialTask))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, roles.target])

  useEffect(() => {
    if (task !== 'classification' || !datasetId || !outcome) {
      setOutcomeLevels([])
      return
    }
    let cancelled = false
    api
      .columnValues(datasetId, outcome)
      .then((response) => {
        if (cancelled) return
        const levels = response.values.map((entry) => entry.value)
        setOutcomeLevels(levels)
        setPositiveLevel((previous) => (previous && levels.includes(previous) ? previous : null))
      })
      .catch(() => {
        if (!cancelled) setOutcomeLevels([])
      })
    return () => {
      cancelled = true
    }
  }, [task, datasetId, outcome])

  const selectOutcome = (column: string) => {
    setOutcome(column)
    setPredictors((previous) => previous.filter((entry) => entry !== column))
    setResult(null)
  }

  const selectTask = (next: PredictionTask) => {
    setTask(next)
    setFamilies(defaultFamilies(next))
    setPositiveLevel(null)
    setResult(null)
  }

  const togglePredictor = useCallback((column: string) => {
    setPredictors((previous) =>
      previous.includes(column)
        ? previous.filter((entry) => entry !== column)
        : previous.length >= MAX_PREDICTORS
          ? previous
          : [...previous, column],
    )
    setResult(null)
  }, [])

  const toggleFamily = (family: string) => {
    setFamilies((previous) =>
      previous.includes(family) ? previous.filter((entry) => entry !== family) : [...previous, family],
    )
    setResult(null)
  }

  const subgroupIsNumeric = subgroupColumn
    ? Boolean(dataset?.column_types[subgroupColumn]?.looks_numeric)
    : false

  const run = async () => {
    if (!datasetId) return
    let bins: number[] = []
    if (subgroupColumn && subgroupIsNumeric) {
      bins = subgroupBins
        .split(',')
        .map((entry) => entry.trim())
        .filter(Boolean)
        .map(Number)
      if (bins.length < 2 || bins.some((entry) => !Number.isFinite(entry))) {
        setError({
          message:
            'A numeric subgroup needs at least two comma-separated bin edges, for example 0, 10, 20.',
        })
        return
      }
    }
    const body: PredictionRequest = {
      task,
      outcome,
      predictors,
      positive_level: task === 'classification' ? positiveLevel : null,
      split_source: splitSource,
      split_strategy: splitStrategy,
      test_fraction: testFraction,
      seed,
      validation_fraction: validationFraction,
      models: families,
      subgroup_column: subgroupColumn || null,
      subgroup_bins: bins,
    }
    setRunning(true)
    setError(null)
    try {
      const response = await modelsApi.fitPrediction(datasetId, body)
      setResult(response)
    } catch (caught) {
      setResult(null)
      setError(
        caught instanceof ApiError
          ? { message: caught.message, code: caught.code, details: caught.details }
          : { message: caught instanceof Error ? caught.message : 'The model could not be evaluated.' },
      )
    } finally {
      setRunning(false)
    }
  }

  const exportRun = async () => {
    if (!result) return
    try {
      await downloadExport(modelsApi.runExportPath(result.run_id))
    } catch (caught) {
      setError({
        message: caught instanceof Error ? caught.message : 'The model run could not be exported.',
      })
    }
  }

  if (!dataset) {
    return (
      <div className="rs xw">
        <p className="rs-eyebrow">Model Lab - predictive evaluation</p>
        <h1 className="rs-h1">No dataset is loaded</h1>
        <p className="xw__empty">
          Predictive evaluation needs a dataset, a declared outcome and a split. Load a bundled
          demonstration or upload a CSV on the Start page, then return here.
        </p>
        <button type="button" className="btn btn--primary" onClick={() => onNavigate('overview')}>
          Go to Start
        </button>
      </div>
    )
  }

  const shortFingerprint = dataset.dataset.fingerprint_sha256.slice(0, 12)
  const isClassification = task === 'classification'

  return (
    <div className="rs xw mlab">
      <header className="xw__header">
        <div>
          <p className="rs-eyebrow">Model Lab - predictive evaluation</p>
          <h1 className="rs-h1">Compare candidates, then evaluate once on held-out data</h1>
        </div>
        <div className="xw__identity" aria-label="Dataset identity">
          <span className="xw__identityname">{dataset.dataset.name}</span>
          <span className="xw__identitymeta">
            {dataset.dataset.row_count.toLocaleString('en-US')} rows × {dataset.dataset.column_count}{' '}
            columns
          </span>
          <span className="xw__identitymeta" title={dataset.dataset.fingerprint_sha256}>
            sha256:{shortFingerprint}…
          </span>
        </div>
      </header>

      {!audit ? (
        <div className="callout callout--warn" role="status">
          <p className="callout__title">No audit in this session</p>
          <p style={{ margin: 0 }}>
            The Model Lab does not audit the split for you. A predictive metric computed on a leaking
            split can look excellent and mean nothing. Run the audit before relying on these numbers.
          </p>
        </div>
      ) : null}

      <div className="mlab__grid">
        <section className="mlab__controls" aria-label="Predictive specification">
          <fieldset className="mlab__group">
            <legend>Task and variables</legend>
            <label className="mlab__field">
              Task
              <select
                className="xselect"
                aria-label="Prediction task"
                value={task}
                onChange={(event) => selectTask(event.target.value as PredictionTask)}
              >
                <option value="classification">Classification - categorical outcome</option>
                <option value="regression">Regression - numeric outcome</option>
              </select>
            </label>

            <label className="mlab__field">
              Outcome
              <select
                className="xselect"
                aria-label="Prediction outcome"
                value={outcome}
                onChange={(event) => selectOutcome(event.target.value)}
              >
                {columns.map((column) => (
                  <option key={column} value={column}>
                    {column}
                    {dataset.column_types[column]?.looks_numeric ? '' : ' (non-numeric)'}
                  </option>
                ))}
              </select>
            </label>

            {isClassification ? (
              <label className="mlab__field">
                Positive class (coded 1)
                <select
                  className="xselect"
                  aria-label="Positive class"
                  value={positiveLevel ?? ''}
                  onChange={(event) => setPositiveLevel(event.target.value || null)}
                >
                  <option value="">Choose a level…</option>
                  {outcomeLevels.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <p className="mlab__hint">
              {isClassification
                ? 'Classification reports held-out accuracy, balanced accuracy, confusion counts and, for a binary outcome, ROC and PR curves. The positive class is never inferred.'
                : 'Regression reports held-out MAE, RMSE and R² with residual diagnostics. R² is marked undefined when the test outcome has no variance.'}
            </p>

            <div className="mlab__field">
              <span>
                Predictors - {predictors.length} of {columns.length - 1} available
              </span>
              <div className="xw__chips">
                {columns
                  .filter((column) => column !== outcome)
                  .map((column) => (
                    <button
                      key={column}
                      type="button"
                      className={`xchip${predictors.includes(column) ? ' xchip--on' : ''}`}
                      aria-pressed={predictors.includes(column)}
                      disabled={!predictors.includes(column) && predictors.length >= MAX_PREDICTORS}
                      onClick={() => togglePredictor(column)}
                    >
                      {column}
                    </button>
                  ))}
              </div>
              <p className="mlab__hint">
                Numeric predictors are median-imputed and (for linear models) standardised;
                categorical predictors are most-frequent-imputed and one-hot encoded. Those
                transformations learn only from training rows.
              </p>
            </div>
          </fieldset>

          <fieldset className="mlab__group">
            <legend>Evaluation design</legend>
            <label className="mlab__field">
              Split
              <select
                className="xselect"
                aria-label="Split source"
                value={splitSource}
                onChange={(event) => {
                  setSplitSource(event.target.value as 'existing' | 'generated')
                  setResult(null)
                }}
              >
                <option value="existing">Existing study split</option>
                <option value="generated">Generate a holdout for this run</option>
              </select>
            </label>
            {splitSource === 'existing' ? (
              <p className="mlab__hint">
                Uses the confirmed split column and labels from the Study step. It is never
                replaced or re-drawn silently.
              </p>
            ) : (
              <>
                <label className="mlab__field">
                  Strategy
                  <select
                    className="xselect"
                    aria-label="Split strategy"
                    value={splitStrategy}
                    onChange={(event) => {
                      setSplitStrategy(event.target.value as GeneratedSplitStrategy)
                      setResult(null)
                    }}
                  >
                    <option value="stratified">Stratified by outcome</option>
                    <option value="random">Random holdout</option>
                    <option value="group">Grouped by entity</option>
                    <option value="chronological">Chronological by timestamp</option>
                  </select>
                </label>
                <div className="mlab__row">
                  <label className="mlab__field">
                    Test fraction
                    <input
                      className="xinput"
                      type="number"
                      min={0.1}
                      max={0.5}
                      step={0.05}
                      value={testFraction}
                      onChange={(event) => setTestFraction(Number(event.target.value))}
                    />
                  </label>
                  <label className="mlab__field">
                    Seed
                    <input
                      className="xinput"
                      type="number"
                      min={0}
                      step={1}
                      value={seed}
                      onChange={(event) => setSeed(Number(event.target.value))}
                    />
                  </label>
                </div>
              </>
            )}
            <label className="mlab__field">
              Validation fraction (carved from training rows)
              <input
                className="xinput"
                type="number"
                min={0.05}
                max={0.5}
                step={0.05}
                value={validationFraction}
                onChange={(event) => setValidationFraction(Number(event.target.value))}
              />
            </label>
            <p className="mlab__hint">
              Candidates are compared on validation. The winner is refitted on fit + validation and
              evaluated once on test; test values never drive selection.
            </p>
          </fieldset>

          <fieldset className="mlab__group">
            <legend>Candidates</legend>
            {FAMILIES[task].map((family) => (
              <label className="mlab__check" key={family.id}>
                <input
                  type="checkbox"
                  checked={families.includes(family.id)}
                  onChange={() => toggleFamily(family.id)}
                />
                {family.label}
              </label>
            ))}
            <p className="mlab__hint">
              No hyperparameter search is performed. Each candidate uses fixed, reported settings.
            </p>
          </fieldset>

          <fieldset className="mlab__group">
            <legend>Preliminary subgroups (optional)</legend>
            <label className="mlab__field">
              Subgroup column
              <select
                className="xselect"
                aria-label="Subgroup column"
                value={subgroupColumn}
                onChange={(event) => {
                  setSubgroupColumn(event.target.value)
                  setResult(null)
                }}
              >
                <option value="">No subgroup breakdown</option>
                {columns.map((column) => (
                  <option key={column} value={column}>
                    {column}
                  </option>
                ))}
              </select>
            </label>
            {subgroupIsNumeric ? (
              <label className="mlab__field">
                Bin edges (comma-separated)
                <input
                  className="xinput"
                  aria-label="Subgroup bin edges"
                  value={subgroupBins}
                  onChange={(event) => setSubgroupBins(event.target.value)}
                  placeholder="0, 10, 20"
                />
              </label>
            ) : null}
            <p className="mlab__hint">
              Subgroups are descriptive held-out error rates with explicit denominators. Small
              groups are flagged; they are not a test of causal effect heterogeneity.
            </p>
          </fieldset>

          <button
            type="button"
            className="btn btn--primary mlab__run"
            disabled={
              running ||
              !outcome ||
              predictors.length === 0 ||
              (isClassification && outcomeLevels.length === 2 && !positiveLevel) ||
              families.length === 0
            }
            onClick={() => void run()}
          >
            {running ? 'Evaluating…' : 'Evaluate predictions'}
          </button>
        </section>

        <section className="mlab__results" aria-label="Predictive results" aria-live="polite">
          {error ? (
            <div className="callout callout--danger" role="alert">
              <p className="callout__title">The evaluation was refused</p>
              <p style={{ marginTop: 0 }}>{error.message}</p>
              {error.details && Object.keys(error.details).length ? (
                <details className="disclosure" style={{ marginBottom: 0 }}>
                  <summary>What you can change</summary>
                  <pre className="mlab__details">{JSON.stringify(error.details, null, 2)}</pre>
                </details>
              ) : null}
            </div>
          ) : null}

          {!result && !error ? (
            <div className="mlab__placeholder">
              <p className="mlab__placeholdertitle">No predictive evaluation yet.</p>
              <p>
                Choose an outcome, predictors, an evaluation design and at least one candidate. The
                result will show validation comparison, the selected model, its sealed-test metrics
                and diagnostics, and every warning that applies.
              </p>
            </div>
          ) : null}

          {result ? <PredictionReport result={result} onExport={() => void exportRun()} /> : null}
        </section>

        {result ? (
          <aside className="mlab__context" aria-label="Run provenance">
            <h2 className="mlab__h2">Provenance</h2>
            <dl className="mlab__facts">
              <div>
                <dt>Run</dt>
                <dd className="mono">{result.run_id}</dd>
              </div>
              <div>
                <dt>Dataset sha256</dt>
                <dd className="mono" title={result.dataset.sha256}>
                  {result.dataset.sha256.slice(0, 12)}…
                </dd>
              </div>
              <div>
                <dt>Split</dt>
                <dd>
                  {result.split.source} / {result.split.strategy}
                  {result.split.seed !== null ? ` / seed ${result.split.seed}` : ''}
                </dd>
              </div>
              <div>
                <dt>Rows</dt>
                <dd>
                  fit {result.split.partitions.fit.toLocaleString('en-US')} · validation{' '}
                  {result.split.partitions.validation.toLocaleString('en-US')} · test{' '}
                  {result.split.partitions.test.toLocaleString('en-US')}
                </dd>
              </div>
              <div>
                <dt>Selected</dt>
                <dd>{result.selected.label}</dd>
              </div>
              <div>
                <dt>Test evaluations</dt>
                <dd>{result.specification.test_evaluations}</dd>
              </div>
            </dl>

            <h2 className="mlab__h2">Learned preprocessing</h2>
            <p className="mlab__hint">
              Fitted on {result.design.preprocessing.learned_on_rows.toLocaleString('en-US')} rows,{' '}
              {result.design.preprocessing.fit_partition}.
            </p>
            <dl className="mlab__facts">
              {Object.entries(result.design.preprocessing.learned.numeric_medians).map(
                ([column, value]) => (
                  <div key={column}>
                    <dt>{column} median</dt>
                    <dd>{fmt(value, 6)}</dd>
                  </div>
                ),
              )}
              {Object.entries(result.design.preprocessing.learned.categorical_modes).map(
                ([column, value]) => (
                  <div key={column}>
                    <dt>{column} mode</dt>
                    <dd>{value ?? '—'}</dd>
                  </div>
                ),
              )}
            </dl>

            <h2 className="mlab__h2">Versions</h2>
            <dl className="mlab__facts">
              {Object.entries(result.versions).map(([name, version]) => (
                <div key={name}>
                  <dt>{name}</dt>
                  <dd>{version}</dd>
                </div>
              ))}
            </dl>

            <p className="mlab__hint">
              Row-membership digests:
              <br />
              fit {result.split.partition_row_ids_sha256.fit.slice(0, 12)}…
              <br />
              validation {result.split.partition_row_ids_sha256.validation.slice(0, 12)}…
              <br />
              test {result.split.partition_row_ids_sha256.test.slice(0, 12)}…
            </p>
          </aside>
        ) : null}
      </div>
    </div>
  )
}

function PredictionReport({ result, onExport }: { result: PredictionResult; onExport: () => void }): JSX.Element {
  const metrics = result.evaluation.metrics
  const classification = result.task === 'classification'
  const roc = result.evaluation.diagnostics.roc_curve
  const pr = result.evaluation.diagnostics.pr_curve ?? metrics.pr_curve ?? null
  const calibration = result.evaluation.diagnostics.calibration
  const calibrationSummary = result.evaluation.diagnostics.calibration_summary ?? null
  const nonEmptyCalibrationBins = (calibration ?? []).filter((entry) => entry.count > 0).length
  const qq = result.evaluation.diagnostics.qq ?? null
  const influence = result.evaluation.diagnostics.influence ?? null
  const importance = result.evaluation.diagnostics.permutation_importance ?? null
  const errors = result.evaluation.diagnostics.errors ?? []
  const classes = metrics.classes ?? []
  const matrix = metrics.confusion_matrix ?? []
  const residuals = result.evaluation.diagnostics.sample?.rows ?? []
  const subgroup = result.subgroups

  return (
    <>
      <div className="mlab__resulthead">
        <div>
          <p className="mlab__formula">
            {result.specification.outcome} ~ {result.specification.predictors.join(' + ')}
          </p>
          <p className="mlab__meta">
            {classification ? 'Classification' : 'Regression'} · {result.selected.label} ·{' '}
            {result.evaluation.n.toLocaleString('en-US')} test rows · run{' '}
            <span className="mono">{result.run_id}</span>
          </p>
        </div>
        <button type="button" className="xbtn" onClick={onExport}>
          Export run JSON
        </button>
      </div>

      <p className="mlab__hint plab__partition">
        Fit {result.split.partitions.fit.toLocaleString('en-US')} · validation{' '}
        {result.split.partitions.validation.toLocaleString('en-US')} · test{' '}
        {result.split.partitions.test.toLocaleString('en-US')}. The test partition was evaluated once,
        after selection.
      </p>

      <p className="mlab__hint plab__diagcontext">
        Diagnostic curves and tables describe the sealed test partition unless a section says
        otherwise. The only in-sample diagnostic is the OLS influence panel, which is labelled
        explicitly. No diagnostic below was used to select the model.
      </p>

      <div className="mlab__stats plab__teststats">
        {classification ? (
          <>
            <Stat label="Test accuracy" value={pct(metrics.accuracy)} />
            <Stat label="Balanced accuracy" value={pct(metrics.balanced_accuracy)} />
            <Stat label="ROC-AUC" value={fmt(metrics.roc_auc)} />
            <Stat label="PR-AUC" value={fmt(metrics.pr_auc)} />
            <Stat label="Test rows" value={String(metrics.n)} />
          </>
        ) : (
          <>
            <Stat label="Test MAE" value={fmt(metrics.mae)} />
            <Stat label="Test RMSE" value={fmt(metrics.rmse)} />
            <Stat label="Test R²" value={fmt(metrics.r2)} />
            <Stat label="Test rows" value={String(metrics.n)} />
            <Stat label="Selected" value={result.selected.label} />
          </>
        )}
      </div>

      {metrics.undefined.length ? (
        <div className="callout callout--info" role="status">
          <p className="callout__title">Metrics that are undefined here</p>
          <ul style={{ margin: 0 }}>
            {metrics.undefined.map((entry) => (
              <li key={`${entry.metric}-${entry.reason}`}>
                <strong>{entry.metric}</strong> - {entry.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <h2 className="mlab__h2">Candidate comparison</h2>
      <p className="mlab__hint">
        Selection rule: {result.specification.selection_rule}. Only validation scores appear in this
        table.
      </p>
      <div className="mlab__tablewrap">
        <table className="mlab__table mlab__table--compact">
          <caption>Every candidate was fitted on the fit partition and scored on validation.</caption>
          <thead>
            <tr>
              <th scope="col">Candidate</th>
              <th scope="col">Status</th>
              <th scope="col" className="num">
                Validation score
              </th>
              <th scope="col" className="num">
                Secondary
              </th>
            </tr>
          </thead>
          <tbody>
            {result.candidates.map((candidate) => (
              <tr key={candidate.family}>
                <th scope="row">
                  {candidate.label}
                  {candidate.family === result.selected.family ? ' (selected)' : ''}
                </th>
                <td>{candidate.status}</td>
                <td className="num">
                  {candidate.selection_metric ? `${candidate.selection_metric} ` : ''}
                  {fmt(candidate.selection_score)}
                </td>
                <td className="num">
                  {candidate.validation
                    ? Object.entries(candidate.validation)
                        .map(([name, value]) => `${name} ${fmt(value)}`)
                        .join(' · ')
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="disclosure plab__settings">
        <summary>Candidate settings</summary>
        <ul>
          {result.candidates.map((candidate) => (
            <li key={candidate.family}>
              <strong>{candidate.label}</strong>:{' '}
              {candidate.parameters
                ? Object.entries(candidate.parameters)
                    .map(([name, value]) => `${name}=${String(value)}`)
                    .join(', ')
                : (candidate.error ?? 'no settings reported')}
            </li>
          ))}
        </ul>
      </details>

      {classification ? (
        <>
          <h2 className="mlab__h2">Confusion matrix</h2>
          <div className="mlab__tablewrap">
            <table className="mlab__table plab__matrix">
              <caption>
                Test partition. Rows are observed classes; columns are predicted classes.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Observed \ Predicted</th>
                  {classes.map((label) => (
                    <th key={label} scope="col" className="num">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.map((row, rowIndex) => (
                  <tr key={classes[rowIndex] ?? rowIndex}>
                    <th scope="row">{classes[rowIndex] ?? rowIndex}</th>
                    {row.map((count, columnIndex) => (
                      <td key={`${rowIndex}-${columnIndex}`} className="num">
                        {count.toLocaleString('en-US')}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 className="mlab__h2">Per-class test metrics</h2>
          <div className="mlab__tablewrap">
            <table className="mlab__table mlab__table--compact">
              <caption>Precision, recall and F1 use the observed class support as denominator.</caption>
              <thead>
                <tr>
                  <th scope="col">Class</th>
                  <th scope="col" className="num">
                    Support
                  </th>
                  <th scope="col" className="num">
                    Predicted
                  </th>
                  <th scope="col" className="num">
                    Precision
                  </th>
                  <th scope="col" className="num">
                    Recall
                  </th>
                  <th scope="col" className="num">
                    F1
                  </th>
                </tr>
              </thead>
              <tbody>
                {(metrics.per_class ?? []).map((entry) => (
                  <tr key={entry.label}>
                    <th scope="row">{entry.label}</th>
                    <td className="num">{entry.support}</td>
                    <td className="num">{entry.predicted}</td>
                    <td className="num">{fmt(entry.precision)}</td>
                    <td className="num">{fmt(entry.recall)}</td>
                    <td className="num">{fmt(entry.f1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {roc ? (
            <>
              <h2 className="mlab__h2">ROC curve</h2>
              <figure className="mlab__figure">
                <RocPlot curve={roc} />
                <figcaption>
                  Test partition only. AUC = {fmt(roc.auc)}. The diagonal is chance.
                </figcaption>
              </figure>
            </>
          ) : null}

          <h2 className="mlab__h2">Precision–recall curve</h2>
          {pr ? (
            <figure className="mlab__figure">
              <PrPlot curve={pr} />
              <figcaption>
                Test partition, positive class {result.outcome.positive_class ?? '—'}. Average
                precision (AP) = {fmt(pr.average_precision)}; prevalence = {pct(pr.prevalence)};{' '}
                {pr.positive_count ?? '—'} positive and {pr.negative_count ?? '—'} negative rows.{' '}
                {metrics.pr_auc_definition ??
                  'AP is the step-wise area under the precision–recall curve.'}
              </figcaption>
            </figure>
          ) : (
            <p className="mlab__hint">
              Not computed for this outcome. A precision–recall curve requires a binary outcome and
              predicted probabilities.
            </p>
          )}

          {calibration ? (
            <>
              <h2 className="mlab__h2">Calibration and reliability</h2>
              <figure className="mlab__figure">
                <ReliabilityPlot entries={calibration} />
                <figcaption>
                  Test partition. Points are equal-width probability bins; vertical lines are
                  Wilson 95% intervals for the observed positive rate. The diagonal is perfect
                  calibration. Empty bins are omitted.
                  {nonEmptyCalibrationBins < 2
                    ? ' Only one non-empty bin was returned, so the shape of the calibration curve cannot be assessed.'
                    : ''}
                </figcaption>
              </figure>
              {calibrationSummary ? (
                <dl className="mlab__facts plab__calibrationsummary">
                  <div>
                    <dt>Prevalence</dt>
                    <dd>{pct(calibrationSummary.prevalence)}</dd>
                  </div>
                  <div>
                    <dt>Expected calibration error</dt>
                    <dd>{fmt(calibrationSummary.expected_calibration_error)}</dd>
                  </div>
                  <div>
                    <dt>Maximum bin gap</dt>
                    <dd>{fmt(calibrationSummary.max_calibration_error)}</dd>
                  </div>
                  <div>
                    <dt>Brier score</dt>
                    <dd>{fmt(calibrationSummary.brier_score)}</dd>
                  </div>
                </dl>
              ) : null}
              <div className="mlab__tablewrap">
                <table className="mlab__table mlab__table--compact">
                  <caption>
                    Predicted positive-class probability binned in ten equal-width bins. Empty bins
                    are shown with a dash rather than filled in.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Probability bin</th>
                      <th scope="col" className="num">
                        Rows
                      </th>
                      <th scope="col" className="num">
                        Mean predicted
                      </th>
                      <th scope="col" className="num">
                        Observed rate
                      </th>
                      <th scope="col" className="num">
                        95% interval
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {calibration.map((entry) => (
                      <tr key={`${entry.bin_low}-${entry.bin_high}`}>
                        <th scope="row">
                          {entry.bin_low.toFixed(1)}–{entry.bin_high.toFixed(1)}
                        </th>
                        <td className="num">{entry.count}</td>
                        <td className="num">{fmt(entry.mean_predicted)}</td>
                        <td className="num">{fmt(entry.observed_rate)}</td>
                        <td className="num">
                          {intervalText(entry.observed_rate_low, entry.observed_rate_high, pct)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {calibrationSummary ? (
                <p className="mlab__hint">{calibrationSummary.method} {calibrationSummary.note}</p>
              ) : null}
            </>
          ) : (
            <p className="mlab__hint">
              Calibration is not available because this run has no binary predicted probabilities.
            </p>
          )}

          <h2 className="mlab__h2">Error cohort</h2>
          <p className="mlab__hint">
            {result.evaluation.diagnostics.error_count ?? 0} test row(s) were misclassified. The
            first {Math.min(25, errors.length)} are listed with stored probabilities.
          </p>
          {errors.length ? (
            <div className="mlab__tablewrap">
              <table className="mlab__table mlab__table--compact">
                <thead>
                  <tr>
                    <th scope="col">Row</th>
                    <th scope="col">Observed</th>
                    <th scope="col">Predicted</th>
                    <th scope="col" className="num">
                      P(positive)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {errors.map((entry) => (
                    <tr key={entry.row_id}>
                      <th scope="row" className="mono">
                        {entry.row_id}
                      </th>
                      <td>{entry.observed}</td>
                      <td>{entry.predicted}</td>
                      <td className="num">{fmt(entry.probability_positive)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="mlab__hint">No test row was misclassified.</p>
          )}
        </>
      ) : (
        <>
          <h2 className="mlab__h2">Residual diagnostics</h2>
          {residuals.length ? (
            <>
              <figure className="mlab__figure">
                <ResidualPlot rows={residuals} />
                <figcaption>
                  {result.evaluation.diagnostics.sample?.description ?? 'Test rows'}; residual =
                  observed − predicted.
                </figcaption>
              </figure>
              {qq?.applicable ? (
                <figure className="mlab__figure">
                  <QqPlot qq={qq} />
                  <figcaption>
                    Normal Q–Q of raw test residuals (n = {qq.n}). The reference line uses the
                    residual mean and SD; a straight line indicates approximate normality. This is a
                    visual check, not a formal test, and it is not required for predictive accuracy.
                  </figcaption>
                </figure>
              ) : (
                <p className="mlab__hint">
                  Q–Q not computed: {qq?.reason ?? 'no residual diagnostic was returned.'}
                </p>
              )}
              <div className="mlab__tablewrap">
                <table className="mlab__table mlab__table--compact">
                  <caption>Largest absolute test residuals from the stored sample.</caption>
                  <thead>
                    <tr>
                      <th scope="col">Row</th>
                      <th scope="col" className="num">
                        Observed
                      </th>
                      <th scope="col" className="num">
                        Predicted
                      </th>
                      <th scope="col" className="num">
                        Residual
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...residuals]
                      .sort((left, right) => Math.abs(right.residual) - Math.abs(left.residual))
                      .slice(0, 15)
                      .map((entry) => (
                        <tr key={entry.row_id}>
                          <th scope="row" className="mono">
                            {entry.row_id}
                          </th>
                          <td className="num">{fmt(entry.observed)}</td>
                          <td className="num">{fmt(entry.predicted)}</td>
                          <td className="num">{fmt(entry.residual)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="mlab__hint">No residual sample was returned.</p>
          )}
          {metrics.residual_summary ? (
            <dl className="mlab__facts">
              <div>
                <dt>Residual mean</dt>
                <dd>{fmt(metrics.residual_summary.mean)}</dd>
              </div>
              <div>
                <dt>Residual SD</dt>
                <dd>{fmt(metrics.residual_summary.std)}</dd>
              </div>
              <div>
                <dt>Min / max</dt>
                <dd>
                  {fmt(metrics.residual_summary.min)} / {fmt(metrics.residual_summary.max)}
                </dd>
              </div>
            </dl>
          ) : null}
          <InfluenceSection influence={influence} />
        </>
      )}

      <ImportanceSection importance={importance} />

      {subgroup ? (
        <>
          <h2 className="mlab__h2">Preliminary subgroups</h2>
          <p className="mlab__hint">{subgroup.note}</p>
          {subgroup.comparison_note ? <p className="mlab__hint">{subgroup.comparison_note}</p> : null}
          <SubgroupTable subgroup={subgroup} />
        </>
      ) : null}

      <h2 className="mlab__h2">Warnings</h2>
      <div className="mlab__warnings">
        {result.warnings.map((warning) => (
          <div className={`callout ${severityClass(warning.severity)}`} key={warning.code}>
            <p className="callout__title">{warning.code.replaceAll('_', ' ')}</p>
            <p style={{ margin: 0 }}>{warning.message}</p>
          </div>
        ))}
      </div>

      <p className="mlab__hint">
        A predictive metric describes this split and these rows. It is not a causal effect, and a good
        test score does not establish that the model is safe to deploy.
      </p>
    </>
  )
}

function Stat({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="mlab__stat">
      <span className="mlab__statlabel">{label}</span>
      <span className="mlab__statvalue">{value}</span>
    </div>
  )
}

function RocPlot({ curve }: { curve: { fpr: number[]; tpr: number[]; auc: number } }): JSX.Element {
  const width = 340
  const height = 260
  const pad = { left: 36, right: 12, top: 12, bottom: 32 }
  const px = (value: number) => pad.left + value * (width - pad.left - pad.right)
  const py = (value: number) => height - pad.bottom - value * (height - pad.top - pad.bottom)
  const points = curve.fpr
    .map((value, index) => `${px(value).toFixed(2)},${py(curve.tpr[index] ?? 0).toFixed(2)}`)
    .join(' ')
  return (
    <svg
      className="mlab__svg plab__roc"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Receiver operating characteristic curve on the test partition"
    >
      <rect
        x={pad.left}
        y={pad.top}
        width={width - pad.left - pad.right}
        height={height - pad.top - pad.bottom}
        fill="none"
        stroke="var(--rs-line)"
      />
      <line
        x1={px(0)}
        y1={py(0)}
        x2={px(1)}
        y2={py(1)}
        stroke="var(--rs-line-strong)"
        strokeDasharray="4 4"
      />
      <polyline points={points} fill="none" stroke="var(--rs-teal)" strokeWidth={2} />
      <text x={(pad.left + width - pad.right) / 2} y={height - 8} textAnchor="middle" className="xpc__tick">
        false positive rate
      </text>
      <text
        x={12}
        y={pad.top + 8}
        textAnchor="start"
        className="xpc__tick"
      >
        true positive rate
      </text>
      <text x={px(0.02)} y={py(0.94)} className="xpc__tick">
        AUC {fmt(curve.auc)}
      </text>
    </svg>
  )
}

function ResidualPlot({
  rows,
}: {
  rows: Array<{ row_id: string; observed: number; predicted: number }>
}): JSX.Element {
  const width = 460
  const height = 250
  const pad = { left: 44, right: 12, top: 12, bottom: 32 }
  const values = rows.map((row) => ({ predicted: row.predicted, residual: row.observed - row.predicted }))
  const xValues = values.map((entry) => entry.predicted)
  const yValues = values.map((entry) => entry.residual)
  const xMin = Math.min(...xValues)
  const xMax = Math.max(...xValues)
  const yLimit = Math.max(1e-9, ...yValues.map((value) => Math.abs(value)))
  const px = (value: number) =>
    pad.left + (xMax === xMin ? 0.5 : (value - xMin) / (xMax - xMin)) * (width - pad.left - pad.right)
  const py = (value: number) =>
    (pad.top + height - pad.bottom) / 2 - (value / yLimit) * ((height - pad.top - pad.bottom) / 2)
  return (
    <svg
      className="mlab__svg plab__residuals"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Residuals plotted against predicted values on the test partition"
    >
      <line x1={pad.left} y1={py(0)} x2={width - pad.right} y2={py(0)} stroke="var(--rs-line-strong)" />
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} stroke="var(--rs-line)" />
      {values.map((entry, index) => (
        <circle
          key={rows[index].row_id}
          cx={px(entry.predicted)}
          cy={py(entry.residual)}
          r={2.2}
          fill="var(--rs-teal)"
          opacity={0.6}
        />
      ))}
      <text x={(pad.left + width - pad.right) / 2} y={height - 8} textAnchor="middle" className="xpc__tick">
        predicted value
      </text>
      {xMax === xMin ? (
        <text x={(pad.left + width - pad.right) / 2} y={height - 18} textAnchor="middle" className="xpc__tick">
          {fmt(xMin, 3)} (constant prediction)
        </text>
      ) : (
        <>
          <text x={pad.left} y={height - 18} textAnchor="start" className="xpc__tick">
            {fmt(xMin, 3)}
          </text>
          <text x={width - pad.right} y={height - 18} textAnchor="end" className="xpc__tick">
            {fmt(xMax, 3)}
          </text>
        </>
      )}
      <text x={pad.left - 6} y={pad.top + 8} textAnchor="end" className="xpc__tick">
        {fmt(yLimit, 2)}
      </text>
      <text x={pad.left - 6} y={height - pad.bottom} textAnchor="end" className="xpc__tick">
        {fmt(-yLimit, 2)}
      </text>
      <text x={12} y={pad.top + 8} className="xpc__tick">
        residual
      </text>
    </svg>
  )
}
