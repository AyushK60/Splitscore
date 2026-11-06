/**
 * S9C-B — Robustness & Sensitivity.
 *
 * Three reproducible refutation experiments on the selected study: data
 * subsampling, placebo treatment, and a hypothetical unmeasured-confounder
 * simulation. Every plotted value comes from the backend's recorded
 * computation; failures are reported per repetition; each experiment's own
 * caveats are shown beside it, in the payload's words.
 */

import { useRef, useState, type RefObject } from 'react'

import { estimationApi } from '../api/client'
import type { EstimationRequestPayload, RobustnessRunPayload } from '../api/types'
import { formatInteger, formatNumber } from '../estimation/format'
import { FigureFrame, useMeasuredWidth } from '../estimation/figureFrame'
import type { FigureExportMeta } from '../estimation/estimationExport'
import { toCsv } from '../estimation/format'
import { describeError, type ErrorInfo } from '../estimation/estimationErrors'
import { distributionPlot, scale, sensitivityScale } from './researchModel'

type Experiment = 'subsampling' | 'placebo' | 'unmeasured_confounder'

const EXPERIMENT_LABELS: Record<Experiment, string> = {
  subsampling: 'Data subsampling',
  placebo: 'Placebo treatment',
  unmeasured_confounder: 'Hypothetical unmeasured confounder',
}

const EXPERIMENT_DESCRIPTIONS: Record<Experiment, string> = {
  subsampling:
    'Re-estimate on reproducibly drawn subsets of the same cohort. Variation across subsamples describes sampling variability — never evidence that the estimate is unbiased.',
  placebo:
    'Permute the observed treatment (treated count preserved) and refit. The placebo distribution shows what the estimator produces when assignment carries no structure.',
  unmeasured_confounder:
    'Simulate a binary confounder with stated associations to treatment and outcome, adjust for it, and refit across a γ×κ grid. A hypothetical scenario, explicitly not a bound.',
}

export function RobustnessView({
  datasetId,
  graphId,
  graphFingerprint,
  request,
}: {
  datasetId: string
  graphId: string
  graphFingerprint: string
  request: EstimationRequestPayload
}) {
  const [experiment, setExperiment] = useState<Experiment>('subsampling')
  const [estimator, setEstimator] = useState('regression_adjustment')
  const [reps, setReps] = useState(200)
  const [fraction, setFraction] = useState(0.5)
  const [prevalence, setPrevalence] = useState(0.3)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ErrorInfo | null>(null)
  const [payload, setPayload] = useState<RobustnessRunPayload | null>(null)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const parameters: Record<string, unknown> =
        experiment === 'unmeasured_confounder'
          ? { estimator, prevalence }
          : { estimator, reps, ...(experiment === 'subsampling' ? { fraction } : {}) }
      const response = await estimationApi.robustness(
        datasetId,
        graphId,
        { ...request, expected_spec_fingerprint_sha256: graphFingerprint },
        experiment,
        parameters,
        `robustness: ${experiment}`,
      )
      setPayload(response)
    } catch (caught) {
      setPayload(null)
      setError(describeError(caught, 'The robustness experiment could not be run'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rsview" data-testid="robustness-view">
      <section className="rssetup" aria-label="Robustness configuration">
        <div className="rssetup__grid">
          <label className="rsfield">
            <span className="rsfield__label">Experiment</span>
            <select
              value={experiment}
              onChange={(event) => setExperiment(event.target.value as Experiment)}
              data-testid="robustness-experiment"
            >
              {(Object.keys(EXPERIMENT_LABELS) as Experiment[]).map((key) => (
                <option key={key} value={key}>
                  {EXPERIMENT_LABELS[key]}
                </option>
              ))}
            </select>
            <span className="rsfield__hint">{EXPERIMENT_DESCRIPTIONS[experiment]}</span>
          </label>
          <label className="rsfield">
            <span className="rsfield__label">Estimator</span>
            <select value={estimator} onChange={(event) => setEstimator(event.target.value)}>
              <option value="regression_adjustment">Regression adjustment</option>
              <option value="ipw">Inverse propensity weighting</option>
              <option value="aipw">Cross-fitted AIPW</option>
            </select>
            <span className="rsfield__hint">
              The production estimator is refitted from scratch in every repetition.
            </span>
          </label>
          {experiment !== 'unmeasured_confounder' ? (
            <label className="rsfield">
              <span className="rsfield__label">Repetitions (100–1000)</span>
              <input
                type="number"
                min={100}
                max={1000}
                step={50}
                value={reps}
                onChange={(event) => setReps(Number(event.target.value))}
              />
              <span className="rsfield__hint">
                Deterministic: repetition r is seeded with [seed, r], so the whole series
                reproduces.
              </span>
            </label>
          ) : null}
          {experiment === 'subsampling' ? (
            <label className="rsfield">
              <span className="rsfield__label">Subsample fraction (0.1–0.9)</span>
              <input
                type="number"
                min={0.1}
                max={0.9}
                step={0.05}
                value={fraction}
                onChange={(event) => setFraction(Number(event.target.value))}
              />
              <span className="rsfield__hint">
                Each repetition draws a simple random subsample at this fraction without
                replacement.
              </span>
            </label>
          ) : null}
          {experiment === 'unmeasured_confounder' ? (
            <label className="rsfield">
              <span className="rsfield__label">Assumed confounder prevalence (0.05–0.95)</span>
              <input
                type="number"
                min={0.05}
                max={0.95}
                step={0.05}
                value={prevalence}
                onChange={(event) => setPrevalence(Number(event.target.value))}
              />
              <span className="rsfield__hint">
                The γ (treatment association) × κ (outcome association) grid is fixed at 5×5 and
                reported in full.
              </span>
            </label>
          ) : null}
          <div className="rsfield rsfield--action">
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy}
              onClick={run}
              data-testid="robustness-run"
            >
              {busy ? 'Running…' : 'Run experiment'}
            </button>
          </div>
        </div>
        {error ? (
          <div className="callout callout--danger" role="alert" data-testid="robustness-error">
            <p className="callout__title">{error.title}</p>
            <p style={{ margin: 0 }}>{error.message}</p>
          </div>
        ) : null}
      </section>

      {payload ? (
        <RobustnessResult payload={payload} />
      ) : (
        <section className="card rsempty" aria-label="No experiment result yet">
          <p>
            Choose an experiment and run it. Every repetition refits the real estimator on the
            same cohort and adjustment set as the estimation run you selected; nothing is
            simulated except where an experiment says so explicitly.
          </p>
        </section>
      )}
    </div>
  )
}

export function RobustnessResult({ payload }: { payload: RobustnessRunPayload }) {
  const result = payload.result
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const measured = useMeasuredWidth(containerRef, 880)
  const original = payload.original.estimate
  const unitLabel = 'outcome units'
  const width = Math.max(measured, 560)

  const exportMeta: FigureExportMeta = {
    figureId: `s9c_robustness_${result.experiment}`,
    title: `${EXPERIMENT_LABELS[result.experiment === 'placebo_treatment' ? 'placebo' : result.experiment === 'unmeasured_confounder_simulation' ? 'unmeasured_confounder' : 'subsampling']} — estimate distribution`,
    settings: `${result.parameters.estimator ?? ''} · ${formatInteger(payload.analysis.rows_final)} cohort rows`,
    note: result.warnings.join(' '),
    provenance: [
      `run_id: ${payload.run_id}`,
      `created_at_utc: ${payload.created_at_utc}`,
      `experiment: ${result.experiment}`,
      `parameters: ${JSON.stringify(result.parameters)}`,
    ],
    csv: toCsv(
      result.grid
        ? ['gamma_index', 'kappa_index', 'estimate']
        : ['repetition_value', ...(result.failures.length ? ['note'] : [])],
      result.grid
        ? result.grid.flatMap((row, gammaIndex) =>
            row.map((value, kappaIndex) => [gammaIndex, kappaIndex, value ?? '']),
          )
        : result.estimates.map((value) => [value]),
    ),
    metadata: {
      run_id: payload.run_id,
      created_at_utc: payload.created_at_utc,
      original: payload.original,
      result: result,
    },
  }

  return (
    <>
      <section className="card rsorig" aria-label="Original estimate">
        <p>
          Original {payload.original.estimator.replace(/_/g, ' ')} estimate on the full cohort:{' '}
          {original !== null ? (
            <strong data-testid="robustness-original">{formatNumber(original)} {unitLabel}</strong>
          ) : (
            <strong className="esttable__failed">failed — {payload.original.failure}</strong>
          )}
        </p>
      </section>

      {result.grid ? (
        <SensitivityFigure payload={payload} exportMeta={exportMeta} svgRef={svgRef} />
      ) : (
        <FigureFrame
          eyebrow="Robustness"
          title={
            result.experiment === 'placebo_treatment'
              ? 'Placebo estimates under permuted treatment'
              : 'Re-estimates across reproducible subsamples'
          }
          description={result.method_note}
          svgRef={svgRef}
          exportMeta={exportMeta}
          testId="robustness-figure"
          footnote={
            <>
              {result.warnings.map((warning) => (
                <p key={warning.slice(0, 48)} className="estfig__note">
                  {warning}
                </p>
              ))}
              <p className="estfig__note estfig__note--quiet">{payload.scope_note}</p>
            </>
          }
        >
          <div className="estchart-scroll" ref={containerRef}>
            {result.distribution ? (
              <DistributionChart
                estimates={result.estimates}
                original={original}
                width={width}
                isPlacebo={result.experiment === 'placebo_treatment'}
                svgRef={svgRef}
              />
            ) : (
              <p className="estrow__failure">
                No repetition produced an estimate; see the recorded failures below.
              </p>
            )}
          </div>
        </FigureFrame>
      )}

      {result.distribution ? (
        <section className="esttable-block" aria-label="Distribution summary">
          <div className="esttable-block__head">
            <h3>Distribution summary</h3>
            <p className="esttable-block__note">
              {formatInteger(result.estimates.length)} repetition estimates
              {result.failures.length > 0
                ? `; ${result.failures.length} repetition(s) failed and are listed separately`
                : ''}
              .
            </p>
          </div>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Distribution summary table">
            <table className="table esttable" data-testid="robustness-summary">
              <caption className="table__caption">Repetition distribution</caption>
              <thead>
                <tr>
                  <th scope="col">Mean</th>
                  <th scope="col">SD</th>
                  <th scope="col">Min</th>
                  <th scope="col">5%</th>
                  <th scope="col">Median</th>
                  <th scope="col">95%</th>
                  <th scope="col">Max</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td data-testid="robustness-mean">{formatNumber(result.distribution.mean)}</td>
                  <td>{formatNumber(result.distribution.standard_deviation)}</td>
                  <td>{formatNumber(result.distribution.min)}</td>
                  <td>{formatNumber(result.distribution.q05)}</td>
                  <td>{formatNumber(result.distribution.q50)}</td>
                  <td>{formatNumber(result.distribution.q95)}</td>
                  <td>{formatNumber(result.distribution.max)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {result.failures.length > 0 ? (
        <section className="card" aria-label="Repetition failures" data-testid="robustness-failures">
          <p className="estsum__detailtitle">
            {result.failures.length} repetition(s) failed — recorded, not averaged away
          </p>
          <ul className="esttable__warnings">
            {result.failures.slice(0, 8).map((failure) => (
              <li key={failure.rep}>
                Repetition {failure.rep}: {failure.reason}
              </li>
            ))}
          </ul>
          {result.failures.length > 8 ? (
            <p className="esttable__quiet">
              …and {result.failures.length - 8} further failures, all included in the run JSON.
            </p>
          ) : null}
        </section>
      ) : null}
    </>
  )
}

function DistributionChart({
  estimates,
  original,
  width,
  isPlacebo,
  svgRef,
}: {
  estimates: number[]
  original: number | null
  width: number
  isPlacebo: boolean
  svgRef: RefObject<SVGSVGElement | null>
}) {
  const plot = distributionPlot(estimates, original)
  const height = 220
  const top = 24
  const bottom = height - 44
  const left = 56
  const right = width - 24
  const maxCount = Math.max(1, ...plot.bins.map((bin) => bin.count))
  const x = (value: number) => scale(value, plot.domain, left, right)
  const bandHeight = (bottom - top) / maxCount
  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Histogram of ${estimates.length} repetition estimates`}
      className="estchart"
      data-testid="robustness-histogram"
    >
      <line x1={left} x2={right} y1={bottom} y2={bottom} className="estchart__axis" />
      {plot.bins.map((bin, index) => (
        <rect
          key={index}
          x={x(bin.from) + 0.5}
          y={bottom - bin.count * bandHeight}
          width={Math.max(1, x(bin.to) - x(bin.from) - 1)}
          height={bin.count * bandHeight}
          className="rshist__bar"
        >
          <title>
            {formatNumber(bin.from, 2)}–{formatNumber(bin.to, 2)}: {bin.count} repetition(s)
          </title>
        </rect>
      ))}
      {original !== null ? (
        <>
          <line
            x1={x(original)}
            x2={x(original)}
            y1={top - 12}
            y2={bottom}
            className="rszero"
            data-testid="robustness-original-line"
          />
          <text x={x(original)} y={top - 16} textAnchor="middle" className="rszero__label">
            original {formatNumber(original, 2)}
          </text>
        </>
      ) : null}
      {[plot.domain.min, (plot.domain.min + plot.domain.max) / 2, plot.domain.max].map(
        (tick, index) => (
          <text
            key={index}
            x={x(tick)}
            y={bottom + 18}
            textAnchor="middle"
            className="estchart__tick"
          >
            {formatNumber(tick, 2)}
          </text>
        ),
      )}
      <text
        x={(left + right) / 2}
        y={height - 6}
        textAnchor="middle"
        className="estchart__axislabel"
      >
        {isPlacebo ? 'Placebo estimate (outcome units)' : 'Subsample estimate (outcome units)'}
      </text>
    </svg>
  )
}

function SensitivityFigure({
  payload,
  exportMeta,
  svgRef,
}: {
  payload: RobustnessRunPayload
  exportMeta: FigureExportMeta
  svgRef: RefObject<SVGSVGElement | null>
}) {
  const result = payload.result
  const grid = result.grid ?? []
  const gammas = (result.parameters.gamma_values as number[]) ?? []
  const kappas = (result.parameters.kappa_values as number[]) ?? []
  const original = payload.original.estimate ?? 0
  const { cellTone } = sensitivityScale(grid, original)
  return (
    <FigureFrame
      eyebrow="Sensitivity"
      title="Adjusted estimate across the hypothetical-confounder grid"
      description={result.method_note}
      svgRef={svgRef}
      exportMeta={exportMeta}
      testId="robustness-sensitivity"
      footnote={
        <>
          {result.warnings.map((warning) => (
            <p key={warning.slice(0, 48)} className="estfig__note">
              {warning}
            </p>
          ))}
          <p className="estfig__note estfig__note--quiet">{payload.scope_note}</p>
        </>
      }
    >
      <div className="rsgrid-wrap" data-testid="sensitivity-grid">
        <table className="rsgrid">
          <caption className="table__caption">
            γ = treatment association (log-odds shift), κ = outcome association (per outcome SD)
          </caption>
          <thead>
            <tr>
              <th scope="col">γ \ κ</th>
              {kappas.map((kappa) => (
                <th scope="col" key={kappa}>
                  {kappa}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.map((row, gammaIndex) => (
              <tr key={gammaIndex}>
                <th scope="row">{gammas[gammaIndex]}</th>
                {row.map((value, kappaIndex) => (
                  <td
                    key={kappaIndex}
                    data-testid={`sensitivity-cell-${gammaIndex}-${kappaIndex}`}
                    className="rsgrid__cell"
                    style={
                      value === null
                        ? undefined
                        : {
                            background: `color-mix(in srgb, var(--copper) ${Math.abs(cellTone(value)) * 42}%, var(--surface))`,
                          }
                    }
                  >
                    {value === null ? 'failed' : formatNumber(value, 2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="estfig__note estfig__note--quiet">
          Original estimate {formatNumber(original, 2)}. Deeper copper marks larger movement away
          from it within this grid — a descriptive shading of the scenario table, not a statistic.
        </p>
      </div>
    </FigureFrame>
  )
}
