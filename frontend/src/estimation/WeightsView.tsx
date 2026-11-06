/**
 * View D — Weights & Reliability.
 *
 * One chart (raw versus Kish effective sample size per arm) and one compact
 * diagnostic table. The S9A payload reports weight *summaries* only, so this
 * view plots summaries only: no invented per-row weight distribution.
 */

import { useMemo, useRef } from 'react'

import type { EstimationResult } from '../api/types'
import type { FigureExportMeta } from './estimationExport'
import { ESTIMATOR_LABELS } from './estimationModel'
import { formatInteger, formatNumber, formatPercent, niceTicks, tickLabel, toCsv } from './format'
import { FigureFrame, LegendItem, useMeasuredWidth } from './figureFrame'

export function WeightsView({
  result,
  provenance,
}: {
  result: EstimationResult
  provenance: string[]
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const measured = useMeasuredWidth(containerRef, 980)

  const overlap = result.diagnostics?.overlap ?? null
  const ess = overlap?.effective_sample_sizes ?? null
  const weightSummary = overlap?.weight_summary ?? null
  const truncation = result.truncation ?? overlap?.truncation ?? null

  const arms = useMemo(
    () =>
      ess
        ? [
            {
              key: 'treated' as const,
              label: 'Treated',
              raw: ess.treated_rows_unweighted,
              effective: ess.treated_ess_weighted,
            },
            {
              key: 'control' as const,
              label: 'Control',
              raw: ess.control_rows_unweighted,
              effective: ess.control_ess_weighted,
            },
          ]
        : [],
    [ess],
  )

  const width = Math.max(measured, 560)
  const left = 64
  const right = width - 32
  const top = 38
  const plotHeight = width < 760 ? 190 : 240
  const axisY = top + plotHeight
  const height = axisY + 66

  const maxRows = Math.max(1, ...arms.map((arm) => arm.raw))
  const step = (maxRows * 1.1) / 4
  const ticks = niceTicks(0, maxRows * 1.1, 4)
  const y = (value: number) => axisY - (value / (maxRows * 1.1)) * plotHeight

  const bandWidth = (right - left) / Math.max(1, arms.length)
  const barWidth = Math.min(64, bandWidth * 0.22)

  const exportMeta: FigureExportMeta = {
    figureId: 's9b_weight_reliability',
    title: 'Raw and effective sample size by treatment arm',
    settings: `${ESTIMATOR_LABELS[result.estimator] ?? result.estimator} · Hájek weights · Kish effective sample size`,
    note:
      'The effective sample size is the number of equally weighted observations that would carry the same information under these weights. A small ESS is a statistical consequence of variable weights, not a software error, and it widens the uncertainty of every weighted estimate.',
    provenance,
    csv: toCsv(
      ['arm', 'rows_unweighted', 'effective_sample_size', 'retained_fraction', 'max_individual_weight', 'weight_p50', 'weight_p95', 'weight_p99'],
      arms.map((arm) => [
        arm.key,
        arm.raw,
        arm.effective,
        arm.raw > 0 ? arm.effective / arm.raw : '',
        weightSummary?.max_individual_weight ?? '',
        weightSummary?.quantiles_total_weight['0.5'] ?? '',
        weightSummary?.quantiles_total_weight['0.95'] ?? '',
        weightSummary?.quantiles_total_weight['0.99'] ?? '',
      ]),
    ),
    metadata: {
      estimator: result.estimator,
      effective_sample_sizes: ess,
      weight_summary: weightSummary,
      truncation,
      warnings: overlap?.warnings ?? [],
      definition:
        'Kish effective sample size = (Σw)² / Σw², computed per arm on the inverse-propensity weights.',
    },
  }

  if (!overlap || !ess) {
    return (
      <section className="estfig estfig--empty" data-testid="weights-unavailable">
        <h2>Weighting diagnostics are not available for this result</h2>
        <p>
          Regression adjustment does not weight observations, so there is no weight distribution and
          no weighted effective sample size to report. The analysis still has its full row count, but
          that is not the same quantity and is not shown here as a substitute.
        </p>
      </section>
    )
  }

  return (
    <>
      <FigureFrame
        eyebrow="Weights & reliability"
        title="How much information survives the weights?"
        description={
          <>
            Raw row counts beside the Kish effective sample size each arm actually contributes under
            the fitted <strong>{ESTIMATOR_LABELS[result.estimator] ?? result.estimator}</strong> weights.
          </>
        }
        svgRef={svgRef}
        exportMeta={exportMeta}
        legend={
          <>
            <LegendItem variant="raw">Rows analysed</LegendItem>
            <LegendItem variant="effective">Effective sample size</LegendItem>
          </>
        }
        aside={
          <div className="estfig__chips">
            {truncation ? (
              <span className="estchip estchip--warn">
                truncated [{formatNumber(truncation.lower, 2)}, {formatNumber(truncation.upper, 2)}]
              </span>
            ) : (
              <span className="estchip">untruncated propensities</span>
            )}
            <span className="estchip">max weight {formatNumber(weightSummary?.max_individual_weight, 2)}</span>
          </div>
        }
        footnote={
          <>
            <p className="estfig__note">
              The effective sample size is the number of equally weighted observations that would
              carry the same information as these weights: (Σw)² / Σw², computed per arm. It is a
              property of the weighting scheme, not a defect in the data or the software — a small
              value means the estimate leans on fewer rows than its row count suggests.
            </p>
            {truncation ? (
              <p className="estfig__note estfig__note--warn" data-testid="weights-truncation-note">
                <strong>Truncation disclosure.</strong> Propensities were truncated to [
                {formatNumber(truncation.lower, 2)}, {formatNumber(truncation.upper, 2)}] exactly as
                requested. Truncation trades bias for variance control and changes the estimand; the
                backend reports it on every affected result.
              </p>
            ) : (
              <p className="estfig__note estfig__note--quiet" data-testid="weights-untruncated-note">
                No propensity truncation was requested for this run.
              </p>
            )}
            {overlap.warnings.length > 0 ? (
              <ul className="estwarnings" data-testid="weights-warnings">
                {overlap.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : (
              <p className="estfig__note estfig__note--quiet">
                The backend raised no unstable-weight warning for this fit.
              </p>
            )}
            {result.warnings && result.warnings.length > 0 ? (
              <ul className="estwarnings" data-testid="weights-estimator-warnings">
                {result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
          </>
        }
        testId="weights-view"
      >
        <div className="estchart-scroll" ref={containerRef}>
          <svg
            ref={svgRef}
            className="estchart"
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`Effective sample size by arm. ${arms
              .map(
                (arm) =>
                  `${arm.label}: ${formatInteger(arm.raw)} rows, effective sample size ${formatNumber(arm.effective, 1)} (${formatPercent(arm.raw > 0 ? arm.effective / arm.raw : null, 0)} retained)`,
              )
              .join('. ')}`}
            data-testid="ess-chart"
          >
            <line x1={left} x2={left} y1={top - 10} y2={axisY} className="estchart__axis" />
            <line x1={left} x2={right} y1={axisY} y2={axisY} className="estchart__axis" />

            {ticks.map((tick) => (
              <g key={tick}>
                <line x1={left} x2={right} y1={y(tick)} y2={y(tick)} className="estchart__grid" />
                <text x={left - 10} y={y(tick) + 4} textAnchor="end" className="estchart__tick">
                  {tickLabel(tick, step)}
                </text>
              </g>
            ))}

            {arms.map((arm, index) => {
              const center = left + bandWidth * index + bandWidth / 2
              const rawX = center - barWidth - 4
              const effectiveX = center + 4
              const retained = arm.raw > 0 ? arm.effective / arm.raw : 0
              return (
                <g key={arm.key} data-testid={`ess-arm-${arm.key}`}>
                  <rect
                    x={rawX}
                    y={y(arm.raw)}
                    width={barWidth}
                    height={Math.max(1, axisY - y(arm.raw))}
                    className="essbar essbar--raw"
                  />
                  <rect
                    x={effectiveX}
                    y={y(arm.effective)}
                    width={barWidth}
                    height={Math.max(1, axisY - y(arm.effective))}
                    className={`essbar essbar--effective${retained < 0.5 ? ' essbar--low' : ''}`}
                  />
                  <text x={rawX + barWidth / 2} y={y(arm.raw) - 8} textAnchor="middle" className="essbar__value">
                    {formatInteger(arm.raw)}
                  </text>
                  <text
                    x={effectiveX + barWidth / 2}
                    y={y(arm.effective) - 8}
                    textAnchor="middle"
                    className="essbar__value essbar__value--effective"
                  >
                    {formatNumber(arm.effective, 1)}
                  </text>
                  <text x={center} y={axisY + 22} textAnchor="middle" className="essbar__label">
                    {arm.label}
                  </text>
                  <text x={center} y={axisY + 38} textAnchor="middle" className="essbar__retained">
                    {formatPercent(retained, 0)} of rows retained
                  </text>
                </g>
              )
            })}

            <text x={left} y={top - 16} className="estchart__axislabel">
              Rows / effective sample size
            </text>
          </svg>
        </div>
      </FigureFrame>

      <div className="estview-split">
        <section className="esttable-block" aria-label="Weight summary">
          <div className="esttable-block__head">
            <h3>Weight summary</h3>
            <p className="esttable-block__note">
              The S9A diagnostics report weight summaries for the whole cohort, not per-row weights,
              so no individual weight can be inspected or reconstructed here.
            </p>
          </div>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Weight summary table">
            <table className="table esttable" data-testid="weights-table">
              <caption className="table__caption">Weighting diagnostics, {ESTIMATOR_LABELS[result.estimator] ?? result.estimator}</caption>
              <thead>
                <tr>
                  <th scope="col">Quantity</th>
                  <th scope="col">Value</th>
                  <th scope="col">Reading</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Treated rows (unweighted)</th>
                  <td>{formatInteger(ess.treated_rows_unweighted)}</td>
                  <td>Analysed treated rows.</td>
                </tr>
                <tr>
                  <th scope="row">Control rows (unweighted)</th>
                  <td>{formatInteger(ess.control_rows_unweighted)}</td>
                  <td>Analysed control rows.</td>
                </tr>
                <tr>
                  <th scope="row">Treated effective n</th>
                  <td>{formatNumber(ess.treated_ess_weighted, 1)}</td>
                  <td>
                    {formatPercent(
                      ess.treated_rows_unweighted > 0
                        ? ess.treated_ess_weighted / ess.treated_rows_unweighted
                        : null,
                      0,
                    )}{' '}
                    of the treated rows' information.
                  </td>
                </tr>
                <tr>
                  <th scope="row">Control effective n</th>
                  <td>{formatNumber(ess.control_ess_weighted, 1)}</td>
                  <td>
                    {formatPercent(
                      ess.control_rows_unweighted > 0
                        ? ess.control_ess_weighted / ess.control_rows_unweighted
                        : null,
                      0,
                    )}{' '}
                    of the control rows' information.
                  </td>
                </tr>
                <tr>
                  <th scope="row">Largest individual weight</th>
                  <td>{formatNumber(weightSummary?.max_individual_weight, 3)}</td>
                  <td>A few rows carrying large weights shrink the effective sample.</td>
                </tr>
                <tr>
                  <th scope="row">Weight p50 / p95 / p99</th>
                  <td>
                    {formatNumber(weightSummary?.quantiles_total_weight['0.5'], 2)} /{' '}
                    {formatNumber(weightSummary?.quantiles_total_weight['0.95'], 2)} /{' '}
                    {formatNumber(weightSummary?.quantiles_total_weight['0.99'], 2)}
                  </td>
                  <td>Distribution of the total (inverse-propensity) weight per row.</td>
                </tr>
                <tr>
                  <th scope="row">Truncation</th>
                  <td>
                    {truncation
                      ? `[${formatNumber(truncation.lower, 2)}, ${formatNumber(truncation.upper, 2)}]`
                      : 'none requested'}
                  </td>
                  <td>
                    {truncation
                      ? 'Applied as explicitly requested; changes the estimand.'
                      : 'Propensities were used untruncated.'}
                  </td>
                </tr>
                <tr>
                  <th scope="row">Propensity extremes</th>
                  <td>
                    {formatInteger(overlap.extremes['below_0.01'])} below 0.01 ·{' '}
                    {formatInteger(overlap.extremes['above_0.99'])} above 0.99
                  </td>
                  <td>{overlap.extremes.count_definition}.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <aside className="estview-side" aria-label="Reliability reading">
          <h3>How to read this</h3>
          <ul className="estlist">
            <li>
              Effective sample size is not a quality score. It tells you how much independent
              information the weighted mean carries.
            </li>
            <li>
              A large drop in effective n widens the interval; it does not invalidate the estimate
              by itself.
            </li>
            <li>
              Truncation reduces the influence of extreme weights but shifts the estimand — the two
              effects are reported together on purpose.
            </li>
            <li>
              These diagnostics describe the fitted weights only. Positivity in the population
              remains an assumption.
            </li>
          </ul>
        </aside>
      </div>
    </>
  )
}
