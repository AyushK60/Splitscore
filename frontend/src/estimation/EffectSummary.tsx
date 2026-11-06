/**
 * View A — Effect Summary.
 *
 * One large dot-and-interval figure comparing the supported estimators on the
 * shared analysis the backend actually ran, followed by the numeric table and
 * the backend's own comparison note.
 *
 * Honesty rules encoded here:
 *  - a failed estimator is a failed row with its reason — never a zero, never a
 *    dot at the origin;
 *  - an unavailable interval is a dot with an explicit "interval unavailable"
 *    label, and the table says why;
 *  - the zero reference line is always drawn, so a sign is never ambiguous;
 *  - estimator agreement is described as a specification signal, never as
 *    evidence that the effect is causal.
 */

import { useMemo, useRef, useState } from 'react'

import type { EstimationResult, EstimationRunPayload, EstimatorName } from '../api/types'
import {
  ESTIMATOR_LABELS,
  ESTIMATOR_ORDER,
  ESTIMATOR_SHORT,
} from './estimationModel'
import type { FigureExportMeta } from './estimationExport'
import {
  estimateWithUnits,
  formatInteger,
  formatNumber,
  niceTicks,
  tickLabel,
  toCsv,
  unitsLabel,
} from './format'
import { FigureFrame, LegendItem, useMeasuredWidth } from './figureFrame'

function intervalText(result: EstimationResult): string {
  const uncertainty = result.uncertainty
  if (!uncertainty || uncertainty.status !== 'available') return 'Interval unavailable'
  if (uncertainty.ci_lower === null || uncertainty.ci_upper === null) return 'Interval unavailable'
  return `${formatNumber(uncertainty.ci_lower)} to ${formatNumber(uncertainty.ci_upper)}`
}

function uncertaintyMethodLabel(result: EstimationResult): string {
  const uncertainty = result.uncertainty
  if (!uncertainty) return 'not reported'
  if (uncertainty.status !== 'available') return uncertainty.unavailable_reason ?? 'unavailable'
  const level = `${Math.round(uncertainty.level * 100)}%`
  if (uncertainty.method === 'bootstrap_percentile') return `${level} percentile bootstrap`
  if (uncertainty.method === 'influence_function') return `${level} influence-function interval`
  return `${level} ${uncertainty.method.replace(/_/g, ' ')}`
}

export function EffectSummary({
  payload,
  studyNote,
  provenance,
}: {
  payload: EstimationRunPayload
  studyNote: string
  provenance: string[]
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const measured = useMeasuredWidth(containerRef, 980)
  const [active, setActive] = useState<number | null>(null)

  const results = useMemo(() => {
    const byName = new Map<string, EstimationResult>()
    for (const result of payload.results) byName.set(result.estimator, result)
    // Named order first, then anything unexpected the backend adds later.
    const named = ESTIMATOR_ORDER.map((name) => byName.get(name)).filter(
      (result): result is EstimationResult => Boolean(result),
    )
    const extra = payload.results.filter(
      (result) => !ESTIMATOR_ORDER.includes(result.estimator as EstimatorName),
    )
    return [...named, ...extra]
  }, [payload.results])

  const units = results.find((result) => result.units)?.units ?? 'outcome_units'
  const unitLabel = unitsLabel(units, payload.analysis.outcome_task)

  const plotted = results.filter(
    (result): result is EstimationResult & { estimate: number } =>
      result.status === 'estimated' && typeof result.estimate === 'number',
  )

  const domain = useMemo(() => {
    const bounds: number[] = [0]
    for (const result of plotted) {
      bounds.push(result.estimate)
      const uncertainty = result.uncertainty
      if (uncertainty?.status === 'available') {
        if (typeof uncertainty.ci_lower === 'number') bounds.push(uncertainty.ci_lower)
        if (typeof uncertainty.ci_upper === 'number') bounds.push(uncertainty.ci_upper)
      }
    }
    let min = Math.min(...bounds)
    let max = Math.max(...bounds)
    if (min === max) {
      min -= 1
      max += 1
    }
    const pad = (max - min) * 0.14
    return { min: min - pad, max: max + pad }
  }, [plotted])

  const width = Math.max(measured, 620)
  // The longest estimator name ("Inverse propensity weighting") is right-aligned
  // against this column; 160 px clipped its first letters on tablet widths.
  const labelWidth = width < 760 ? 206 : 236
  const left = labelWidth + 24
  const right = width - (width < 760 ? 92 : 168)
  const rowHeight = 62
  const top = 46
  const plotHeight = Math.max(1, results.length) * rowHeight
  const axisY = top + plotHeight + 10
  const height = axisY + 52

  const step = (domain.max - domain.min) / 5
  const ticks = niceTicks(domain.min, domain.max, 5)
  const x = (value: number) =>
    left + ((value - domain.min) / (domain.max - domain.min)) * (right - left)

  const activeResult = active !== null ? results[active] : null

  const exportMeta: FigureExportMeta = {
    figureId: 's9b_effect_summary',
    title: 'Average treatment effect by estimator',
    settings: `${results.map((result) => ESTIMATOR_SHORT[result.estimator as EstimatorName] ?? result.estimator).join(' · ')} on one shared analysis · ${formatInteger(payload.analysis.rows_final)} analysed rows · ATE in ${unitLabel}`,
    note:
      'Point estimates and intervals as reported by the S9A estimation engine. Estimator disagreement is a model-specification signal, not a resolved quantity, and agreement between estimators is not evidence that the effect is causal.',
    provenance,
    csv: toCsv(
      ['estimator', 'status', 'estimate', 'units', 'ci_lower', 'ci_upper', 'standard_error', 'uncertainty_method', 'sample_size', 'warnings'],
      results.map((result) => [
        result.estimator,
        result.status,
        result.estimate ?? '',
        result.units ?? '',
        result.uncertainty?.ci_lower ?? '',
        result.uncertainty?.ci_upper ?? '',
        result.uncertainty?.standard_error ?? '',
        result.uncertainty ? uncertaintyMethodLabel(result) : '',
        result.sample_size ?? '',
        (result.warnings ?? []).join(' | '),
      ]),
    ),
    metadata: {
      run_id: payload.run_id,
      created_at_utc: payload.created_at_utc,
      treatment: payload.analysis.treatment_column,
      outcome: payload.analysis.outcome_column,
      adjustment_variables: payload.analysis.adjustment_columns,
      outcomes_units: unitLabel,
      comparison: payload.comparison ?? null,
      estimators: results,
    },
  }

  const legend = (
    <>
      <LegendItem variant="estimate">Point estimate</LegendItem>
      <LegendItem variant="interval">Reported interval</LegendItem>
      <span className="estlegend__item">
        <span className="estlegend__zero" aria-hidden="true" /> Zero (no effect)
      </span>
    </>
  )

  return (
    <>
      <FigureFrame
        eyebrow="Effect summary"
        title="How large is the estimated effect, and how sure are we?"
        description={
          <>
            Average treatment effect on {formatInteger(payload.analysis.rows_final)} analysed rows
            ({formatInteger(payload.analysis.treated_rows)} treated, {formatInteger(payload.analysis.control_rows)} control),
            in {unitLabel}. {ESTIMATOR_LABELS.aipw} and {ESTIMATOR_LABELS.ipw} intervals come from the
            uncertainty method reported beside each estimate; {ESTIMATOR_LABELS.regression_adjustment} reports only what
            the backend computed for it.
          </>
        }
        svgRef={svgRef}
        exportMeta={exportMeta}
        legend={legend}
        testId="effect-summary"
        aside={
          <div className="estfig__chips">
            <span className="estchip">{payload.analysis.outcome_task === 'logistic' ? 'binary outcome' : 'continuous outcome'}</span>
            <span className="estchip">{payload.analysis.missing_data_policy === 'complete_case' ? 'complete-case cohort' : 'median/mode imputation'}</span>
            <span className="estchip">{formatInteger(payload.analysis.rows_final)} rows</span>
          </div>
        }
        footnote={
          <>
            <p className="estfig__note">
              {payload.scope_note}
            </p>
            <p className="estfig__note estfig__note--quiet">
              Agreement between estimators is not a validity check: all three share the same
              adjustment set and the same untestable assumptions. Disagreement is reported by the
              backend as a specification or instability signal and is deliberately not resolved
              into a single score.
            </p>
          </>
        }
      >
        <div className="estchart-scroll" ref={containerRef}>
          {plotted.length === 0 && results.every((result) => result.status === 'failed') ? (
            <div className="estchart-empty" role="status" data-testid="summary-all-failed">
              <p>
                Every estimator failed on this configuration. No effect is displayed, because a
                failed estimate is not a zero effect.
              </p>
            </div>
          ) : (
            <svg
              ref={svgRef}
              className="estchart"
              width={width}
              height={height}
              viewBox={`0 0 ${width} ${height}`}
              role="img"
              aria-label={`Dot and interval plot of the average treatment effect by estimator, in ${unitLabel}. ${results
                .map((result) =>
                  result.status === 'estimated'
                    ? `${ESTIMATOR_LABELS[result.estimator as EstimatorName] ?? result.estimator}: ${formatNumber(result.estimate)} ${unitLabel}, ${intervalText(result)}`
                    : `${ESTIMATOR_LABELS[result.estimator as EstimatorName] ?? result.estimator}: failed, ${result.failure?.reason ?? 'no reason reported'}`,
                )
                .join('. ')}`}
              data-testid="effect-summary-chart"
            >
              {/* Plot frame */}
              <line x1={left} x2={left} y1={top - 12} y2={axisY} className="estchart__axis" />
              <line x1={left} x2={right} y1={axisY} y2={axisY} className="estchart__axis" />

              {/* Zero reference */}
              <line
                x1={x(0)}
                x2={x(0)}
                y1={top - 22}
                y2={axisY}
                className="estchart__zero"
              />
              <text x={x(0)} y={top - 28} textAnchor="middle" className="estchart__zerolabel">
                no effect
              </text>

              {/* Gridlines and ticks */}
              {ticks.map((tick) => (
                <g key={tick}>
                  <line
                    x1={x(tick)}
                    x2={x(tick)}
                    y1={top - 12}
                    y2={axisY}
                    className="estchart__grid"
                  />
                  <text x={x(tick)} y={axisY + 18} textAnchor="middle" className="estchart__tick">
                    {tickLabel(tick, step)}
                  </text>
                </g>
              ))}
              <text x={(left + right) / 2} y={axisY + 40} textAnchor="middle" className="estchart__axislabel">
                Average treatment effect ({unitLabel})
              </text>

              {results.map((result, index) => {
                const y = top + index * rowHeight + rowHeight / 2
                const name = ESTIMATOR_LABELS[result.estimator as EstimatorName] ?? result.estimator
                const failed = result.status === 'failed'
                const estimated = result.status === 'estimated' && typeof result.estimate === 'number'
                const uncertainty = result.uncertainty
                const hasInterval =
                  estimated &&
                  uncertainty?.status === 'available' &&
                  typeof uncertainty.ci_lower === 'number' &&
                  typeof uncertainty.ci_upper === 'number'
                const label =
                  failed
                    ? `${name}: failed — ${result.failure?.reason ?? 'no reason reported'}`
                    : `${name}: ${formatNumber(result.estimate)} ${unitLabel}, ${intervalText(result)}`
                return (
                  <g
                    key={result.estimator}
                    className={`estrow${failed ? ' estrow--failed' : ''}${active === index ? ' estrow--active' : ''}`}
                    tabIndex={0}
                    role="button"
                    aria-label={`${label}. Show details.`}
                    data-testid={`summary-row-${result.estimator}`}
                    data-status={result.status}
                    onMouseEnter={() => setActive(index)}
                    onMouseLeave={() => setActive(null)}
                    onFocus={() => setActive(index)}
                    onBlur={() => setActive(null)}
                  >
                    <title>{label}</title>
                    <rect
                      x={0}
                      y={y - rowHeight / 2 + 6}
                      width={width}
                      height={rowHeight - 12}
                      className="estrow__band"
                    />
                    <text x={labelWidth - 6} y={y - 2} textAnchor="end" className="estrow__name">
                      {name}
                    </text>
                    <text x={labelWidth - 6} y={y + 15} textAnchor="end" className="estrow__meta">
                      {ESTIMATOR_SHORT[result.estimator as EstimatorName] ?? result.estimator}
                      {estimated ? ` · n = ${formatInteger(result.sample_size)}` : ''}
                    </text>

                    {failed ? (
                      <text
                        x={left + 12}
                        y={y + 4}
                        className="estrow__failure"
                        data-testid={`summary-failure-${result.estimator}`}
                      >
                        Failed — {result.failure?.reason ?? 'no reason reported'}
                      </text>
                    ) : null}

                    {estimated && hasInterval ? (
                      <>
                        <line
                          x1={x(uncertainty!.ci_lower as number)}
                          x2={x(uncertainty!.ci_upper as number)}
                          y1={y}
                          y2={y}
                          className="estrow__interval"
                        />
                        <line
                          x1={x(uncertainty!.ci_lower as number)}
                          x2={x(uncertainty!.ci_lower as number)}
                          y1={y - 6}
                          y2={y + 6}
                          className="estrow__cap"
                        />
                        <line
                          x1={x(uncertainty!.ci_upper as number)}
                          x2={x(uncertainty!.ci_upper as number)}
                          y1={y - 6}
                          y2={y + 6}
                          className="estrow__cap"
                        />
                      </>
                    ) : null}

                    {estimated ? (
                      <>
                        <circle
                          cx={x(result.estimate as number)}
                          cy={y}
                          r={6}
                          className="estrow__dot"
                          data-value={result.estimate}
                          data-testid={`summary-dot-${result.estimator}`}
                        />
                        <text
                          x={
                            hasInterval
                              ? x(uncertainty!.ci_upper as number) + 12
                              : x(result.estimate as number) + 14
                          }
                          y={y + 4}
                          className="estrow__value"
                        >
                          {formatNumber(result.estimate)}
                          <tspan className="estrow__valuemeta">
                            {'  '}
                            {hasInterval
                              ? `[${formatNumber(uncertainty!.ci_lower)}, ${formatNumber(uncertainty!.ci_upper)}]`
                              : 'interval unavailable'}
                          </tspan>
                        </text>
                      </>
                    ) : null}
                  </g>
                )
              })}
            </svg>
          )}
        </div>

        <div className="estsum__detail" aria-live="polite">
          {activeResult ? (
            <ResultDetail result={activeResult} unitLabel={unitLabel} />
          ) : (
            <p className="estsum__hint">
              Point at a row, or focus it with the keyboard, to read the estimate, its interval and
              the uncertainty method used.
            </p>
          )}
        </div>
      </FigureFrame>

      <section className="esttable-block" aria-label="Estimator comparison table">
        <div className="esttable-block__head">
          <h3>Estimator comparison</h3>
          <p className="esttable-block__note">
            Values exactly as reported by the estimation engine. A method that failed is shown as
            failed; it is never represented as a zero effect.
          </p>
        </div>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Estimator comparison table">
          <table className="table esttable esttable--wrap" data-testid="effect-summary-table">
            <caption className="table__caption">
              Average treatment effect by estimator on one shared analysis
            </caption>
            <thead>
              <tr>
                <th scope="col">Method</th>
                <th scope="col">ATE ({unitLabel})</th>
                <th scope="col">Analysed rows</th>
                <th scope="col">Uncertainty method</th>
                <th scope="col">Interval</th>
                <th scope="col">Warnings</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {results.map((result) => (
                <tr key={result.estimator} data-testid={`summary-table-${result.estimator}`}>
                  <th scope="row">{ESTIMATOR_LABELS[result.estimator as EstimatorName] ?? result.estimator}</th>
                  <td>
                    {result.status === 'estimated' ? (
                      formatNumber(result.estimate)
                    ) : (
                      <span className="esttable__failed">not estimated</span>
                    )}
                  </td>
                  <td>{result.status === 'estimated' ? formatInteger(result.sample_size) : '—'}</td>
                  <td>{result.status === 'estimated' ? uncertaintyMethodLabel(result) : '—'}</td>
                  <td>
                    {result.status === 'estimated' ? (
                      intervalText(result)
                    ) : (
                      <span className="esttable__failed">—</span>
                    )}
                  </td>
                  <td>
                    {(result.warnings ?? []).length === 0 ? (
                      <span className="esttable__quiet">none</span>
                    ) : (
                      <ul className="esttable__warnings">
                        {(result.warnings ?? []).map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td>
                    {result.status === 'estimated' ? (
                      <span className="eststate eststate--ok">estimated</span>
                    ) : (
                      <span className="eststate eststate--failed">failed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {payload.comparison ? (
        <section className="estcompare" aria-label="Comparison note">
          <h3>Reading the comparison</h3>
          {typeof payload.comparison.max_pairwise_difference === 'number' ? (
            <p className="estcompare__metric">
              Largest pairwise difference:{' '}
              <strong>
                {formatNumber(payload.comparison.max_pairwise_difference)} {unitLabel}
              </strong>
            </p>
          ) : null}
          <p>{payload.comparison.interpretation}</p>
          <p className="estfig__note estfig__note--quiet">{payload.comparison.shared_analysis}</p>
          <p className="estfig__note estfig__note--quiet">{studyNote}</p>
        </section>
      ) : (
        <section className="estcompare" aria-label="Single estimator note">
          <h3>Single-estimator run</h3>
          <p className="estfig__note">{studyNote}</p>
        </section>
      )}
    </>
  )
}

function ResultDetail({ result, unitLabel }: { result: EstimationResult; unitLabel: string }) {
  if (result.status === 'failed') {
    return (
      <div className="estsum__detailcard estsum__detailcard--failed">
        <p className="estsum__detailtitle">
          {ESTIMATOR_LABELS[result.estimator as EstimatorName] ?? result.estimator} failed
        </p>
        <p>{result.failure?.reason ?? 'The backend reported a failure without a reason.'}</p>
        <p className="estsum__detailmeta">
          No estimate exists for this method on this configuration. A failed fit is not evidence of
          no effect.
        </p>
      </div>
    )
  }
  const uncertainty = result.uncertainty
  return (
    <div className="estsum__detailcard">
      <p className="estsum__detailtitle">
        {ESTIMATOR_LABELS[result.estimator as EstimatorName] ?? result.estimator}
      </p>
      <p className="estsum__detailvalue">
        {estimateWithUnits(result.estimate, result.units)}
        {uncertainty?.status === 'available' && uncertainty.ci_lower !== null && uncertainty.ci_upper !== null ? (
          <span className="estsum__detailci">
            {' '}
            · {Math.round(uncertainty.level * 100)}% interval {formatNumber(uncertainty.ci_lower)} to{' '}
            {formatNumber(uncertainty.ci_upper)}
          </span>
        ) : (
          <span className="estsum__detailci"> · interval unavailable</span>
        )}
      </p>
      <p className="estsum__detailmeta">
        {result.units === 'probability_difference' ? 'Probability difference' : `Outcome in ${unitLabel}`} ·
        n = {formatInteger(result.sample_size)} ·{' '}
        {uncertainty?.status === 'available'
          ? uncertaintyMethodLabel(result)
          : uncertainty?.unavailable_reason ?? 'no uncertainty reported'}
        {uncertainty?.standard_error !== null && uncertainty?.standard_error !== undefined
          ? ` · SE ${formatNumber(uncertainty.standard_error)}`
          : ''}
      </p>
    </div>
  )
}
