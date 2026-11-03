/**
 * S6 Model Lab — statistical workbench (F09).
 *
 * The lab fits OLS or binary logistic regression on the dataset currently in
 * memory and shows exactly what was fitted: the formula, the coding, the
 * analysed population, coefficients with intervals, fit statistics,
 * diagnostics and warnings. Every number displayed comes from the server's
 * statsmodels result; nothing is estimated or illustrated locally.
 *
 * This sheet is deliberately distinct from the future predictive ML tab: a
 * statistical fit describes coefficients on the analysed rows and does not
 * claim held-out performance. That distinction is stated in the UI.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { JSX } from 'react'

import { ApiError, api, downloadExport, modelsApi } from '../api/client'
import type { StatisticalModelResult, StatisticsTask } from '../api/types'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'
import { PredictiveLabView } from './PredictiveLabView'

interface Props {
  onNavigate: (view: ViewId) => void
}

const MAX_PREDICTORS = 30

function fmt(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value !== 0 && Math.abs(value) < 0.001) return value.toExponential(2)
  return value.toPrecision(digits)
}

function pValue(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value < 0.0001) return '< 0.0001'
  return value.toFixed(4)
}

function severityClass(severity: string): string {
  return severity === 'high' ? 'callout--danger' : severity === 'medium' ? 'callout--warn' : 'callout--info'
}

export function ModelLabView({ onNavigate }: Props) {
  const [mode, setMode] = useState<'statistical' | 'predictive'>('statistical')
  return (
    <div className="mlab-shell">
      <div className="mlab-tabs" role="tablist" aria-label="Model Lab mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'statistical'}
          className={`mlab-tabs__btn${mode === 'statistical' ? ' mlab-tabs__btn--on' : ''}`}
          onClick={() => setMode('statistical')}
        >
          Statistical inference
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'predictive'}
          className={`mlab-tabs__btn${mode === 'predictive' ? ' mlab-tabs__btn--on' : ''}`}
          onClick={() => setMode('predictive')}
        >
          Predictive ML
        </button>
      </div>
      {mode === 'statistical' ? (
        <StatisticalLab onNavigate={onNavigate} />
      ) : (
        <PredictiveLabView onNavigate={onNavigate} />
      )}
    </div>
  )
}

function StatisticalLab({ onNavigate }: Props) {
  const { dataset, roles, audit } = useApp()
  const datasetId = dataset?.dataset.dataset_id ?? null

  const [task, setTask] = useState<StatisticsTask>('ols')
  const [outcome, setOutcome] = useState('')
  const [predictors, setPredictors] = useState<string[]>([])
  const [missingPolicy, setMissingPolicy] = useState<'complete_case' | 'fail'>('complete_case')
  const [intercept, setIntercept] = useState(true)
  const [alpha, setAlpha] = useState(0.05)
  const [positiveLevel, setPositiveLevel] = useState<string | null>(null)
  const [outcomeLevels, setOutcomeLevels] = useState<string[]>([])
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<StatisticalModelResult | null>(null)
  const [error, setError] = useState<{ message: string; code?: string; details?: Record<string, unknown> } | null>(
    null,
  )

  const columns = dataset?.dataset.columns ?? []

  // A new dataset invalidates every prior fit: coefficients describe the data
  // they were fitted on, never whatever file happens to be loaded now.
  useEffect(() => {
    setResult(null)
    setError(null)
    setPositiveLevel(null)
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
        : numeric.filter((column) => column !== defaultOutcome).slice(0, 4),
    )
    setTask(target && dataset.column_types[target] && !dataset.column_types[target].looks_numeric ? 'logistic' : 'ols')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, roles.target])

  // Logistic coding needs the observed levels; they are fetched, not guessed.
  useEffect(() => {
    if (task !== 'logistic' || !datasetId || !outcome) {
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

  const togglePredictor = useCallback((column: string) => {
    setPredictors((previous) =>
      previous.includes(column)
        ? previous.filter((entry) => entry !== column)
        : previous.length >= MAX_PREDICTORS
          ? previous
          : [...previous, column],
    )
  }, [])

  const selectOutcome = (column: string) => {
    setOutcome(column)
    setPredictors((previous) => previous.filter((entry) => entry !== column))
    setResult(null)
  }

  const run = async () => {
    if (!datasetId) return
    setRunning(true)
    setError(null)
    try {
      const response = await modelsApi.fitStatistics(datasetId, {
        task,
        outcome,
        predictors,
        missing_policy: missingPolicy,
        intercept,
        positive_level: task === 'logistic' ? positiveLevel : null,
        categorical_references: {},
        alpha,
      })
      setResult(response)
    } catch (caught) {
      setResult(null)
      setError(
        caught instanceof ApiError
          ? { message: caught.message, code: caught.code, details: caught.details }
          : { message: caught instanceof Error ? caught.message : 'The model could not be fitted.' },
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

  const outcomeIsNumeric = outcome ? Boolean(dataset?.column_types[outcome]?.looks_numeric) : true
  const targetMismatch = Boolean(roles.target && outcome && roles.target !== outcome)

  const coefficientPlot = useMemo(
    () => (result ? buildCoefficientPlot(result.coefficients) : null),
    [result],
  )

  if (!dataset) {
    return (
      <div className="rs xw">
        <p className="rs-eyebrow">Model Lab</p>
        <h1 className="rs-h1">No dataset is loaded</h1>
        <p className="xw__empty">
          The Model Lab fits a model on the dataset currently in memory. Load a bundled demonstration
          or upload a CSV on the Start page, then return here.
        </p>
        <button type="button" className="btn btn--primary" onClick={() => onNavigate('overview')}>
          Go to Start
        </button>
      </div>
    )
  }

  const shortFingerprint = dataset.dataset.fingerprint_sha256.slice(0, 12)

  return (
    <div className="rs xw mlab">
      <header className="xw__header">
        <div>
          <p className="rs-eyebrow">Model Lab — statistical workbench</p>
          <h1 className="rs-h1">Fit a model on an explicit specification</h1>
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
            The Model Lab does not audit the split for you. Run the audit first if this dataset has a
            train/test split and you intend to use these results predictively — a statistical fit
            alone does not detect leakage.
          </p>
        </div>
      ) : null}

      <div className="mlab__grid">
        <section className="mlab__controls" aria-label="Model specification">
          <fieldset className="mlab__group">
            <legend>Task and variables</legend>
            <label className="mlab__field">
              Task
              <select
                className="xselect"
                aria-label="Task"
                value={task}
                onChange={(event) => {
                  setTask(event.target.value as StatisticsTask)
                  setResult(null)
                  setPositiveLevel(null)
                }}
              >
                <option value="ols">Ordinary least squares — numeric outcome</option>
                <option value="logistic">Binary logistic regression — two-level outcome</option>
              </select>
            </label>

            <label className="mlab__field">
              Outcome
              <select
                className="xselect"
                aria-label="Outcome"
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
            <p className="mlab__hint">
              {task === 'ols'
                ? outcomeIsNumeric
                  ? 'OLS needs a numeric outcome. Non-numeric cells are refused rather than coerced.'
                  : 'This outcome is not numeric; OLS will refuse it. Choose a numeric outcome or switch to logistic regression.'
                : 'Logistic regression needs exactly two observed levels and an explicit positive class.'}
            </p>

            {task === 'logistic' ? (
              <label className="mlab__field">
                Positive class (coded 1)
                <select
                  className="xselect"
                  aria-label="Positive class (coded 1)"
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

            <div className="mlab__field">
              <span>
                Predictors — {predictors.length} of {columns.length - 1} available
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
                      onClick={() => {
                        togglePredictor(column)
                        setResult(null)
                      }}
                    >
                      {column}
                    </button>
                  ))}
              </div>
              <p className="mlab__hint">
                Numeric columns enter continuously. Non-numeric columns enter as indicator terms
                against their first observed level; the reference and every level are reported with
                the fit.
              </p>
            </div>
            {targetMismatch ? (
              <p className="mlab__hint mlab__hint--warn">
                The outcome differs from the Study target role ({roles.target}). That is allowed, but
                the result describes this outcome, not the declared study target.
              </p>
            ) : null}
          </fieldset>

          <fieldset className="mlab__group">
            <legend>Estimation</legend>
            <label className="mlab__field">
              Missing-data policy
              <select
                className="xselect"
                aria-label="Missing-data policy"
                value={missingPolicy}
                onChange={(event) => setMissingPolicy(event.target.value as 'complete_case' | 'fail')}
              >
                <option value="complete_case">Complete case — exclude and count rows</option>
                <option value="fail">Refuse if any modelled cell is missing</option>
              </select>
            </label>
            <label className="mlab__check">
              <input type="checkbox" checked={intercept} onChange={(event) => setIntercept(event.target.checked)} />
              Include an intercept
            </label>
            <label className="mlab__field">
              Confidence level
              <select
                className="xselect"
                aria-label="Confidence level"
                value={alpha}
                onChange={(event) => setAlpha(Number(event.target.value))}
              >
                <option value={0.05}>95% intervals (α = 0.05)</option>
                <option value={0.1}>90% intervals (α = 0.10)</option>
                <option value={0.01}>99% intervals (α = 0.01)</option>
              </select>
            </label>
            <button
              type="button"
              className="btn btn--primary mlab__run"
              disabled={running || !outcome || predictors.length === 0}
              onClick={() => void run()}
            >
              {running ? 'Fitting…' : 'Fit model'}
            </button>
            <p className="mlab__hint">
              Classical standard errors. A statistical fit uses the analysed rows; it is not a
              held-out predictive evaluation and does not prove that a feature is safe to deploy.
            </p>
          </fieldset>
        </section>

        <section className="mlab__results" aria-label="Model results" aria-live="polite">
          {error ? (
            <div className="callout callout--danger" role="alert">
              <p className="callout__title">The model was not fitted</p>
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
              <p className="mlab__placeholdertitle">Nothing fitted yet.</p>
              <p>
                Choose an outcome and at least one predictor, then fit. The result will list every
                coefficient with its standard error and interval, the fit statistics that are valid
                for the chosen task, and the diagnostics computed from this fit.
              </p>
            </div>
          ) : null}

          {result ? (
            <>
              <div className="mlab__resulthead">
                <div>
                  <p className="mlab__formula">{result.specification.formula}</p>
                  <p className="mlab__meta">
                    {result.specification.task_label} · {result.population.analyzed.toLocaleString('en-US')}{' '}
                    of {result.population.rows_total.toLocaleString('en-US')} rows analysed · run{' '}
                    <span className="mono">{result.run_id}</span>
                  </p>
                </div>
                <button type="button" className="xbtn" onClick={() => void exportRun()}>
                  Export run JSON
                </button>
              </div>

              <div className="mlab__stats">
                {result.task === 'ols' ? (
                  <>
                    <Stat label="R²" value={fmt(result.fit.r_squared)} />
                    <Stat label="Adjusted R²" value={fmt(result.fit.adjusted_r_squared)} />
                    <Stat label="F statistic" value={fmt(result.fit.f_statistic)} />
                    <Stat label="F p-value" value={pValue(result.fit.f_p_value)} />
                    <Stat label="Residual σ" value={fmt(result.fit.sigma)} />
                    <Stat label="df (model / residual)" value={`${result.fit.df_model ?? '—'} / ${result.fit.df_resid ?? '—'}`} />
                  </>
                ) : (
                  <>
                    <Stat label="McFadden pseudo-R²" value={fmt(result.fit.mcfadden_pseudo_r_squared)} />
                    <Stat label="Log-likelihood" value={fmt(result.fit.log_likelihood)} />
                    <Stat label="Likelihood ratio" value={fmt(result.fit.likelihood_ratio)} />
                    <Stat label="LR p-value" value={pValue(result.fit.likelihood_ratio_p_value)} />
                    <Stat label="AIC" value={fmt(result.fit.aic)} />
                    <Stat label="BIC" value={fmt(result.fit.bic)} />
                  </>
                )}
              </div>

              <h2 className="mlab__h2">Coefficients</h2>
              <div className="mlab__tablewrap">
                <table className="mlab__table">
                  <caption>
                    {result.task === 'logistic'
                      ? 'Log-odds coefficients with odds ratios. Positive coefficients raise the odds of the positive class.'
                      : 'Linear coefficients in outcome units per one-unit increase in the term.'}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Term</th>
                      <th scope="col" className="num">
                        Estimate
                      </th>
                      <th scope="col" className="num">
                        Std. error
                      </th>
                      <th scope="col" className="num">
                        {result.task === 'logistic' ? 'Odds ratio' : '95% interval'}
                      </th>
                      <th scope="col" className="num">
                        Statistic
                      </th>
                      <th scope="col" className="num">
                        p-value
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.coefficients.map((entry) => (
                      <tr key={entry.term}>
                        <th scope="row" className="mono">
                          {entry.term}
                        </th>
                        <td className="num">{fmt(entry.estimate)}</td>
                        <td className="num">{fmt(entry.std_error)}</td>
                        <td className="num">
                          {result.task === 'logistic'
                            ? `${fmt(entry.odds_ratio)} (${fmt(entry.odds_ratio_ci_low)}–${fmt(entry.odds_ratio_ci_high)})`
                            : `${fmt(entry.ci_low)} – ${fmt(entry.ci_high)}`}
                        </td>
                        <td className="num">{fmt(entry.statistic)}</td>
                        <td className="num">{pValue(entry.p_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mlab__hint">
                A p-value is not an effect size, and neither is evidence of causal importance. The
                interval is the stated confidence interval from the fitted model.
              </p>

              {coefficientPlot ? (
                <figure className="mlab__figure">
                  <figcaption>
                    <span className="xfig__title">Coefficient intervals</span>
                    <span className="xfig__sub">
                      Point estimate and the reported confidence interval; the vertical rule is zero.
                    </span>
                  </figcaption>
                  {coefficientPlot}
                </figure>
              ) : null}

              <Diagnostics result={result} />
            </>
          ) : null}
        </section>

        <aside className="mlab__context" aria-label="Model context and warnings">
          <h2 className="mlab__h2">Population</h2>
          {result ? (
            <dl className="mlab__facts">
              <div>
                <dt>Analysed</dt>
                <dd>{result.population.analyzed.toLocaleString('en-US')}</dd>
              </div>
              <div>
                <dt>Excluded</dt>
                <dd>{result.population.excluded.toLocaleString('en-US')}</dd>
              </div>
              <div>
                <dt>Policy</dt>
                <dd>{result.population.policy}</dd>
              </div>
              <div>
                <dt>Intervals</dt>
                <dd>{Math.round((1 - result.specification.alpha) * 100)}%</dd>
              </div>
            </dl>
          ) : (
            <p className="mlab__hint">The analysed population appears here after a fit.</p>
          )}
          {result && Object.keys(result.population.excluded_missing_by_column).length ? (
            <p className="mlab__hint">
              Missing by column:{' '}
              {Object.entries(result.population.excluded_missing_by_column)
                .map(([column, count]) => `${column} ${count}`)
                .join(' · ')}
            </p>
          ) : null}

          <h2 className="mlab__h2">Warnings</h2>
          {result?.warnings.length ? (
            <div className="mlab__warnings">
              {result.warnings.map((warning) => (
                <div key={warning.code + warning.message} className={`callout ${severityClass(warning.severity)}`}>
                  <p className="callout__title">{warning.code.replaceAll('_', ' ')}</p>
                  <p style={{ margin: 0 }}>{warning.message}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="mlab__hint">
              {result ? 'No warnings were raised for this fit. That is not proof of a correct model specification.' : 'Warnings appear after a fit.'}
            </p>
          )}

          {result ? (
            <>
              <h2 className="mlab__h2">Coding</h2>
              <ul className="mlab__coding">
                {result.specification.coding.map((entry) => (
                  <li key={entry.column}>
                    <strong className="mono">{entry.column}</strong> — {entry.kind}
                    {entry.kind === 'categorical'
                      ? `, reference ${entry.reference} (levels: ${entry.levels?.join(', ')})`
                      : ''}
                  </li>
                ))}
              </ul>
              <h2 className="mlab__h2">Provenance</h2>
              <dl className="mlab__facts">
                <div>
                  <dt>Dataset sha256</dt>
                  <dd className="mono tiny break">{result.dataset.sha256}</dd>
                </div>
                <div>
                  <dt>statsmodels</dt>
                  <dd>{result.versions.statsmodels}</dd>
                </div>
                <div>
                  <dt>Run</dt>
                  <dd className="mono tiny break">{result.run_id}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>{result.created_at_utc}</dd>
                </div>
              </dl>
            </>
          ) : null}
        </aside>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="mlab__stat">
      <span className="mlab__statlabel">{label}</span>
      <span className="mlab__statvalue">{value}</span>
    </div>
  )
}

/** Real coefficient intervals — one row per fitted term. */
function buildCoefficientPlot(
  coefficients: StatisticalModelResult['coefficients'],
): JSX.Element | null {
  if (coefficients.length === 0) return null
  const width = 680
  const rowHeight = 30
  const pad = { left: 130, right: 24, top: 12, bottom: 36 }
  const height = pad.top + pad.bottom + coefficients.length * rowHeight
  const domain = coefficients.flatMap((entry) => [entry.ci_low, entry.ci_high, entry.estimate])
  const min = Math.min(0, ...domain)
  const max = Math.max(0, ...domain)
  const span = max - min || 1
  const x = (value: number) => pad.left + ((value - min) / span) * (width - pad.left - pad.right)
  return (
    <svg
      className="mlab__svg"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Coefficient point estimates with confidence intervals, with a zero reference line"
    >
      <line x1={x(0)} y1={pad.top} x2={x(0)} y2={height - pad.bottom} stroke="var(--rs-line-strong)" strokeDasharray="3 3" />
      {coefficients.map((entry, index) => {
        const y = pad.top + index * rowHeight + rowHeight / 2
        return (
          <g key={entry.term}>
            <text x={pad.left - 10} y={y + 3} textAnchor="end" className="xpc__tick">
              {entry.term}
            </text>
            <line x1={x(entry.ci_low)} y1={y} x2={x(entry.ci_high)} y2={y} stroke="var(--rs-teal)" strokeWidth={2} />
            <circle cx={x(entry.estimate)} cy={y} r={3.4} fill="var(--rs-copper)" />
          </g>
        )
      })}
      <text x={x(0)} y={height - 8} textAnchor="middle" className="xpc__tick">
        0
      </text>
      <text x={x(min)} y={height - 8} textAnchor="start" className="xpc__tick">
        {fmt(min, 3)}
      </text>
      <text x={x(max)} y={height - 8} textAnchor="end" className="xpc__tick">
        {fmt(max, 3)}
      </text>
    </svg>
  )
}

/** Residual-versus-fitted diagnostics from the fitted sample. */
function Diagnostics({ result }: { result: StatisticalModelResult }) {
  const rows = result.diagnostics.sample.rows
  if (result.task === 'logistic') {
    return (
      <section className="mlab__diagnostics" aria-label="Model diagnostics">
        <h2 className="mlab__h2">Diagnostics</h2>
        <p className="mlab__hint">
          {result.diagnostics.sample.description}. Predicted probabilities are shown in the sample
          table below; calibration and ROC/PR curves belong to the S6 diagnostics workspace and are
          not shown here.
        </p>
        <div className="mlab__tablewrap">
          <table className="mlab__table mlab__table--compact">
            <caption>Evaluated rows — observed class and fitted probability.</caption>
            <thead>
              <tr>
                <th scope="col">Row</th>
                <th scope="col" className="num">
                  Observed
                </th>
                <th scope="col" className="num">
                  Predicted probability
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 12).map((row) => (
                <tr key={row.row_id}>
                  <th scope="row" className="mono">
                    {row.row_id}
                  </th>
                  <td className="num">{row.observed}</td>
                  <td className="num">{fmt(row.probability, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    )
  }

  const width = 680
  const height = 280
  const pad = { left: 56, right: 18, top: 14, bottom: 34 }
  const fitted = rows.map((row) => row.fitted)
  const residuals = rows.map((row) => row.residual ?? 0)
  const xMin = Math.min(...fitted)
  const xMax = Math.max(...fitted)
  const yLimit = Math.max(1e-9, ...residuals.map((value) => Math.abs(value)))
  const px = (value: number) => pad.left + ((value - xMin) / (xMax - xMin || 1)) * (width - pad.left - pad.right)
  const py = (value: number) =>
    pad.top + (height - pad.top - pad.bottom) / 2 - (value / yLimit) * ((height - pad.top - pad.bottom) / 2)

  return (
    <section className="mlab__diagnostics" aria-label="Model diagnostics">
      <h2 className="mlab__h2">Diagnostics</h2>
      <figure className="mlab__figure">
        <figcaption>
          <span className="xfig__title">Residual versus fitted</span>
          <span className="xfig__sub">
            {result.diagnostics.sample.description}. Residual = observed − fitted, in outcome units.
          </span>
        </figcaption>
        <svg
          className="mlab__svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="Residuals plotted against fitted values for the analysed sample"
        >
          <line x1={pad.left} y1={py(0)} x2={width - pad.right} y2={py(0)} stroke="var(--rs-line-strong)" />
          <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} stroke="var(--rs-line)" />
          {rows.map((row) => (
            <circle
              key={row.row_id}
              cx={px(row.fitted)}
              cy={py(row.residual ?? 0)}
              r={2.1}
              fill="var(--rs-teal)"
              opacity={0.55}
            />
          ))}
          <text x={(pad.left + width - pad.right) / 2} y={height - 20} textAnchor="middle" className="xpc__tick">
            fitted value
          </text>
          <text x={pad.left} y={height - 8} textAnchor="start" className="xpc__tick">
            {fmt(xMin, 3)}
          </text>
          <text x={width - pad.right} y={height - 8} textAnchor="end" className="xpc__tick">
            {fmt(xMax, 3)}
          </text>
          <text x={pad.left - 8} y={pad.top + 8} textAnchor="end" className="xpc__tick">
            {fmt(yLimit, 2)}
          </text>
          <text x={pad.left - 8} y={height - pad.bottom} textAnchor="end" className="xpc__tick">
            {fmt(-yLimit, 2)}
          </text>
          <text x={12} y={pad.top + 8} className="xpc__tick">
            residual
          </text>
        </svg>
      </figure>
      {result.diagnostics.residual_summary ? (
        <dl className="mlab__facts">
          <div>
            <dt>Residual mean</dt>
            <dd>{fmt(result.diagnostics.residual_summary.mean)}</dd>
          </div>
          <div>
            <dt>Residual SD</dt>
            <dd>{fmt(result.diagnostics.residual_summary.std)}</dd>
          </div>
          <div>
            <dt>Min / max</dt>
            <dd>
              {fmt(result.diagnostics.residual_summary.min)} / {fmt(result.diagnostics.residual_summary.max)}
            </dd>
          </div>
        </dl>
      ) : null}
      <p className="mlab__hint">
        VIF is computed from the design matrix; values above 10 raise a warning. The plot shows the
        systematic sample stated above, never a fabricated curve.
      </p>
    </section>
  )
}
