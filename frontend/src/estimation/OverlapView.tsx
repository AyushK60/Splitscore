/**
 * View C - Overlap & Propensity.
 *
 * A single overlaid propensity distribution per treatment arm, drawn from the
 * bounded per-arm histograms the estimation diagnostics return (20 fixed bins of width
 * 0.05, counts and within-arm shares - never individual scores). Quantiles,
 * group sizes and extreme-score counts come from the same payload.
 *
 * The figure shows empirical overlap in this dataset. It cannot and does not
 * claim population positivity, and it labels the scores as fitted estimates.
 */

import { useMemo, useRef, useState } from 'react'

import type { EstimationResult } from '../api/types'
import type { FigureExportMeta } from './estimationExport'
import { ESTIMATOR_LABELS } from './estimationModel'
import { formatInteger, formatNumber, formatPercent, tickLabel, toCsv } from './format'
import { FigureFrame, LegendItem, useMeasuredWidth } from './figureFrame'

const QUANTILE_KEYS = ['0.01', '0.05', '0.25', '0.5', '0.75', '0.95', '0.99']

export function OverlapView({
  result,
  provenance,
}: {
  result: EstimationResult
  provenance: string[]
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const measured = useMeasuredWidth(containerRef, 980)
  const [activeBin, setActiveBin] = useState<number | null>(null)

  const overlap = result.diagnostics?.overlap ?? null
  const histogram = overlap?.propensity_histogram ?? null

  const width = Math.max(measured, 620)
  const left = width < 760 ? 52 : 68
  const right = width - (width < 760 ? 18 : 28)
  const top = 44
  const plotHeight = width < 760 ? 220 : 280
  const axisY = top + plotHeight
  const stripTop = axisY + 58
  const height = stripTop + 92

  const maxShare = useMemo(() => {
    if (!histogram) return 0.1
    return Math.max(0.02, ...histogram.treated_share, ...histogram.control_share) * 1.12
  }, [histogram])

  const x = (score: number) => left + score * (right - left)
  const y = (share: number) => axisY - (share / maxShare) * plotHeight

  const supported = overlap && histogram && result.status === 'estimated'
  const treatedRows = overlap?.effective_sample_sizes.treated_rows_unweighted ?? 0
  const controlRows = overlap?.effective_sample_sizes.control_rows_unweighted ?? 0

  const overlapWindow = useMemo(() => {
    if (!overlap) return null
    const t = overlap.propensity_summary.quantiles_treated
    const c = overlap.propensity_summary.quantiles_control
    const low = Math.max(t['0.01'] ?? 0, c['0.01'] ?? 0)
    const high = Math.min(t['0.99'] ?? 1, c['0.99'] ?? 1)
    return { low, high, exists: low <= high }
  }, [overlap])

  const activeBinData =
    histogram && activeBin !== null
      ? {
          low: histogram.bin_edges[activeBin],
          high: histogram.bin_edges[activeBin + 1],
          treated: histogram.treated_counts[activeBin],
          control: histogram.control_counts[activeBin],
          treatedShare: histogram.treated_share[activeBin],
          controlShare: histogram.control_share[activeBin],
        }
      : null

  const exportMeta: FigureExportMeta = {
    figureId: 's9b_propensity_overlap',
    title: 'Fitted propensity score distribution by treatment arm',
    settings: `${ESTIMATOR_LABELS[result.estimator] ?? result.estimator} · ${formatInteger(treatedRows)} treated vs ${formatInteger(controlRows)} control rows · 20 bins of 0.05 · within-arm relative frequency`,
    note:
      'Propensity scores are fitted estimates from the adjustment covariates, not true treatment probabilities. The arms are shown as within-arm relative frequencies so unequal group sizes stay comparable. Empirical overlap in this dataset does not establish population positivity.',
    provenance,
    csv: histogram
      ? toCsv(
          ['bin_lower', 'bin_upper', 'treated_count', 'treated_share', 'control_count', 'control_share'],
          histogram.bin_edges.slice(0, -1).map((edge, index) => [
            edge,
            histogram.bin_edges[index + 1],
            histogram.treated_counts[index],
            histogram.treated_share[index],
            histogram.control_counts[index],
            histogram.control_share[index],
          ]),
        )
      : 'bin_lower,bin_upper,treated_count,treated_share,control_count,control_share',
    metadata: {
      estimator: result.estimator,
      propensity_summary: overlap?.propensity_summary ?? null,
      histogram: histogram ?? null,
      extremes: overlap?.extremes ?? null,
      effective_sample_sizes: overlap?.effective_sample_sizes ?? null,
      warnings: overlap?.warnings ?? [],
      truncation: overlap?.truncation ?? null,
      overlap_window_99: overlapWindow,
    },
  }

  if (!supported) {
    return (
      <section className="estfig estfig--empty" data-testid="overlap-unavailable">
        <h2>Overlap diagnostics are not available for this result</h2>
        <p>
          Propensity scores are only fitted by the IPW and AIPW estimators. Regression adjustment
          uses an outcome model and produces no propensity distribution, so there is nothing
          honest to plot here. Select an IPW or AIPW result in the diagnostics selector above.
        </p>
      </section>
    )
  }

  const treatedPoly = (() => {
    const points: string[] = []
    histogram.treated_share.forEach((share, index) => {
      points.push(`${x(histogram.bin_edges[index])},${y(share)}`)
      points.push(`${x(histogram.bin_edges[index + 1])},${y(share)}`)
    })
    points.push(`${x(1)},${axisY}`)
    points.push(`${x(0)},${axisY}`)
    return points.join(' ')
  })()
  const controlPoly = (() => {
    const points: string[] = []
    histogram.control_share.forEach((share, index) => {
      points.push(`${x(histogram.bin_edges[index])},${y(share)}`)
      points.push(`${x(histogram.bin_edges[index + 1])},${y(share)}`)
    })
    points.push(`${x(1)},${axisY}`)
    points.push(`${x(0)},${axisY}`)
    return points.join(' ')
  })()

  return (
    <>
      <FigureFrame
        eyebrow="Overlap & propensity"
        title="Where do treated and control units actually overlap?"
        description={
          <>
            Fitted propensity distributions for <strong>{ESTIMATOR_LABELS[result.estimator] ?? result.estimator}</strong>,
            drawn as within-arm relative frequencies so the {formatInteger(treatedRows)} treated rows and{' '}
            {formatInteger(controlRows)} control rows are comparable despite their unequal sizes.
          </>
        }
        svgRef={svgRef}
        exportMeta={exportMeta}
        legend={
          <>
            <LegendItem variant="treated">Treated · fitted propensity</LegendItem>
            <LegendItem variant="control">Control · fitted propensity</LegendItem>
            {overlapWindow ? <LegendItem variant="support">Central 99% overlap</LegendItem> : null}
          </>
        }
        aside={
          <div className="estfig__chips">
            <span className="estchip">min {formatNumber(overlap.propensity_summary.min, 3)}</span>
            <span className="estchip">max {formatNumber(overlap.propensity_summary.max, 3)}</span>
            <span className="estchip">
              extremes: {overlap.extremes['below_0.01'] + overlap.extremes['above_0.99']}
            </span>
          </div>
        }
        footnote={
          <>
            <p className="estfig__note">{histogram.definition}</p>
            <p className="estfig__note estfig__note--quiet">{overlap.scope_note}</p>
            {overlap.truncation ? (
              <p className="estfig__note estfig__note--warn" data-testid="overlap-truncation-note">
                <strong>Truncation applied.</strong> Propensities were truncated to [
                {formatNumber(overlap.truncation.lower, 2)}, {formatNumber(overlap.truncation.upper, 2)}] as
                requested. The histogram describes the untruncated fitted scores; the estimate
                describes the truncated estimand.
              </p>
            ) : null}
            {overlap.warnings.length > 0 ? (
              <ul className="estwarnings" data-testid="overlap-warnings">
                {overlap.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : (
              <p className="estfig__note estfig__note--quiet" data-testid="overlap-no-warnings">
                The backend raised no extreme-score or effective-sample-size warning for this fit.
                That is the absence of a warning, not a positivity test.
              </p>
            )}
          </>
        }
        testId="overlap-view"
      >
        <div className="estchart-scroll" ref={containerRef}>
          <svg
            ref={svgRef}
            className="estchart"
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`Overlaid propensity histograms. Treated ${formatInteger(treatedRows)} rows, control ${formatInteger(controlRows)} rows. ${
              overlapWindow?.exists
                ? `Central 99% ranges overlap between ${formatNumber(overlapWindow.low, 2)} and ${formatNumber(overlapWindow.high, 2)}.`
                : 'The central 99% ranges do not overlap.'
            }`}
            data-testid="overlap-chart"
          >
            {overlapWindow?.exists ? (
              <>
                <rect
                  x={x(overlapWindow.low)}
                  y={top - 18}
                  width={Math.max(1, x(overlapWindow.high) - x(overlapWindow.low))}
                  height={axisY - top + 18}
                  className="overlap__support"
                />
                <text
                  x={(x(overlapWindow.low) + x(overlapWindow.high)) / 2}
                  y={top - 24}
                  textAnchor="middle"
                  className="overlap__supportlabel"
                >
                  central 99% ranges overlap
                </text>
              </>
            ) : (
              <text x={(left + right) / 2} y={top - 24} textAnchor="middle" className="overlap__supportlabel overlap__supportlabel--warn">
                the arms’ central 99% ranges do not overlap
              </text>
            )}

            <line x1={left} x2={right} y1={axisY} y2={axisY} className="estchart__axis" />
            <line x1={left} x2={left} y1={top - 12} y2={axisY} className="estchart__axis" />

            {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
              <g key={tick}>
                <line x1={x(tick)} x2={x(tick)} y1={top - 12} y2={axisY} className="estchart__grid" />
                <text x={x(tick)} y={axisY + 18} textAnchor="middle" className="estchart__tick">
                  {tickLabel(tick, 0.25)}
                </text>
              </g>
            ))}

            <polygon points={controlPoly} className="overlap__area overlap__area--control" />
            <polygon points={treatedPoly} className="overlap__area overlap__area--treated" />

            {histogram.bin_edges.slice(0, -1).map((edge, index) => {
              const binWidth = x(histogram.bin_edges[index + 1]) - x(edge)
              return (
                <g
                  key={edge}
                  className={`overlap__bin${activeBin === index ? ' overlap__bin--active' : ''}`}
                  tabIndex={0}
                  role="button"
                  data-testid="overlap-bin"
                  aria-label={`Propensity ${formatNumber(edge, 2)} to ${formatNumber(histogram.bin_edges[index + 1], 2)}: ${histogram.treated_counts[index]} treated (${formatPercent(histogram.treated_share[index], 1)} of the arm), ${histogram.control_counts[index]} control (${formatPercent(histogram.control_share[index], 1)} of the arm).`}
                  onMouseEnter={() => setActiveBin(index)}
                  onMouseLeave={() => setActiveBin(null)}
                  onFocus={() => setActiveBin(index)}
                  onBlur={() => setActiveBin(null)}
                >
                  <title>
                    {formatNumber(edge, 2)}–{formatNumber(histogram.bin_edges[index + 1], 2)}:
                    treated {histogram.treated_counts[index]}, control {histogram.control_counts[index]}
                  </title>
                  <rect
                    x={x(edge)}
                    y={top - 12}
                    width={binWidth}
                    height={axisY - top + 12}
                    className="overlap__hit"
                  />
                </g>
              )
            })}

            {/* Quantile strip: real quantiles, drawn as ticks under the axis. */}
            {(['treated', 'control'] as const).map((arm, rowIndex) => {
              const quantiles =
                arm === 'treated'
                  ? overlap.propensity_summary.quantiles_treated
                  : overlap.propensity_summary.quantiles_control
              const stripY = stripTop + rowIndex * 30
              return (
                <g key={arm}>
                  <text x={left - 10} y={stripY + 4} textAnchor="end" className="overlap__striplabel">
                    {arm === 'treated' ? 'treated' : 'control'}
                  </text>
                  <line x1={x(0)} x2={x(1)} y1={stripY} y2={stripY} className="overlap__stripline" />
                  {QUANTILE_KEYS.map((key) => {
                    const value = quantiles[key]
                    if (typeof value !== 'number') return null
                    return (
                      <g key={key}>
                        <line
                          x1={x(value)}
                          x2={x(value)}
                          y1={stripY - 5}
                          y2={stripY + 5}
                          className={`overlap__quantile overlap__quantile--${arm}`}
                        />
                        {key === '0.5' ? (
                          <text x={x(value)} y={stripY + 19} textAnchor="middle" className="overlap__median">
                            median {formatNumber(value, 2)}
                          </text>
                        ) : null}
                      </g>
                    )
                  })}
                </g>
              )
            })}
            <text x={left} y={stripTop + 74} className="estchart__axislabel">
              1st, 5th, 25th, 50th, 75th, 95th and 99th fitted-propensity quantiles per arm
            </text>
            <text x={(left + right) / 2} y={axisY + 40} textAnchor="middle" className="estchart__axislabel">
              Fitted propensity score (estimated, 0–1)
            </text>
          </svg>
        </div>

        <div className="estsum__detail" aria-live="polite">
          {activeBinData ? (
            <p className="estsum__detailmeta">
              <strong>
                Propensity {formatNumber(activeBinData.low, 2)}–{formatNumber(activeBinData.high, 2)}
              </strong>{' '}
              · treated {formatInteger(activeBinData.treated)} (
              {formatPercent(activeBinData.treatedShare, 1)} of the treated arm) · control{' '}
              {formatInteger(activeBinData.control)} ({formatPercent(activeBinData.controlShare, 1)} of the
              control arm)
            </p>
          ) : (
            <p className="estsum__hint">
              Point at a bin, or focus it with the keyboard, to read both arms' counts and relative
              frequencies.
            </p>
          )}
        </div>
      </FigureFrame>

      <div className="estview-split">
        <section className="esttable-block" aria-label="Propensity distribution table">
          <div className="esttable-block__head">
            <h3>Distribution by bin</h3>
            <p className="esttable-block__note">
              Shares are within-arm relative frequencies; the two arms are never pooled.
            </p>
          </div>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Propensity histogram table">
            <table className="table esttable" data-testid="overlap-table">
              <caption className="table__caption">
                Fitted propensity scores by bin, {ESTIMATOR_LABELS[result.estimator] ?? result.estimator}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Bin</th>
                  <th scope="col">Treated n</th>
                  <th scope="col">Treated share</th>
                  <th scope="col">Control n</th>
                  <th scope="col">Control share</th>
                </tr>
              </thead>
              <tbody>
                {histogram.bin_edges.slice(0, -1).map((edge, index) => (
                  <tr key={edge}>
                    <th scope="row">
                      {formatNumber(edge, 2)} – {formatNumber(histogram.bin_edges[index + 1], 2)}
                    </th>
                    <td>{formatInteger(histogram.treated_counts[index])}</td>
                    <td>{formatPercent(histogram.treated_share[index], 1)}</td>
                    <td>{formatInteger(histogram.control_counts[index])}</td>
                    <td>{formatPercent(histogram.control_share[index], 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="estview-side" aria-label="Group summaries">
          <h3>Group summaries</h3>
          <dl className="estmetrics">
            <div>
              <dt>Treated rows</dt>
              <dd>{formatInteger(treatedRows)}</dd>
            </div>
            <div>
              <dt>Control rows</dt>
              <dd>{formatInteger(controlRows)}</dd>
            </div>
            <div>
              <dt>Median propensity · treated</dt>
              <dd>{formatNumber(overlap.propensity_summary.quantiles_treated['0.5'], 3)}</dd>
            </div>
            <div>
              <dt>Median propensity · control</dt>
              <dd>{formatNumber(overlap.propensity_summary.quantiles_control['0.5'], 3)}</dd>
            </div>
            <div>
              <dt>Treated 5th–95th percentile</dt>
              <dd>
                {formatNumber(overlap.propensity_summary.quantiles_treated['0.05'], 3)} –{' '}
                {formatNumber(overlap.propensity_summary.quantiles_treated['0.95'], 3)}
              </dd>
            </div>
            <div>
              <dt>Control 5th–95th percentile</dt>
              <dd>
                {formatNumber(overlap.propensity_summary.quantiles_control['0.05'], 3)} –{' '}
                {formatNumber(overlap.propensity_summary.quantiles_control['0.95'], 3)}
              </dd>
            </div>
            <div>
              <dt>Below 0.01 / above 0.99</dt>
              <dd>
                {formatInteger(overlap.extremes['below_0.01'])} / {formatInteger(overlap.extremes['above_0.99'])}
              </dd>
            </div>
            <div>
              <dt>Central 99% overlap</dt>
              <dd>
                {overlapWindow?.exists
                  ? `${formatNumber(overlapWindow.low, 3)} – ${formatNumber(overlapWindow.high, 3)}`
                  : 'none'}
              </dd>
            </div>
          </dl>
          <p className="estview-side__note">{overlap.extremes.count_definition}.</p>
          <p className="estview-side__note">
            The strip under the histogram plots these quantiles exactly as reported; nothing is
            interpolated between them.
          </p>
        </aside>
      </div>
    </>
  )
}
