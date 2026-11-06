/**
 * View B — Covariate Balance.
 *
 * One large Love plot: standardized mean differences before adjustment, and
 * after weighting only when the selected estimator actually applied weights.
 * Regression adjustment applies none, and this view says so instead of borrowing
 * another estimator's weighted values.
 *
 * The 0.1 reference is drawn and labelled as a conventional heuristic. No
 * threshold on an SMD tests exchangeability, and the footnote says so.
 */

import { useMemo, useRef, useState } from 'react'

import type { EstimationBalanceCovariate, EstimationResult } from '../api/types'
import type { FigureExportMeta } from './estimationExport'
import { ESTIMATOR_LABELS } from './estimationModel'
import { formatNumber, niceTicks, tickLabel, toCsv } from './format'
import { FigureFrame, LegendItem, useMeasuredWidth } from './figureFrame'

const MAX_PLOTTED_ROWS = 22

interface BalanceRow {
  key: string
  label: string
  kind: string
  level: string | null
  unweighted: number | null
  weighted: number | null
  magnitude: number
}

function toRows(covariates: EstimationBalanceCovariate[]): BalanceRow[] {
  return covariates.map((covariate) => {
    const unweighted = covariate.smd_unweighted
    const weighted = covariate.smd_weighted
    return {
      key: `${covariate.column}::${covariate.level ?? ''}`,
      label: covariate.level === null ? covariate.column : `${covariate.column} · ${covariate.level}`,
      kind: covariate.kind,
      level: covariate.level,
      unweighted,
      weighted,
      magnitude: Math.max(
        Math.abs(unweighted ?? 0),
        Math.abs(weighted ?? 0),
      ),
    }
  })
}

export function BalanceView({
  result,
  provenance,
  staleNote,
}: {
  result: EstimationResult
  provenance: string[]
  staleNote: string | null
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const measured = useMeasuredWidth(containerRef, 980)
  const [active, setActive] = useState<string | null>(null)
  const [sort, setSort] = useState<'imbalance' | 'order'>('imbalance')

  const balance = result.diagnostics?.balance
  const allRows = useMemo(() => (balance ? toRows(balance.covariates) : []), [balance])
  const sorted = useMemo(() => {
    const rows = [...allRows]
    if (sort === 'imbalance') rows.sort((a, b) => b.magnitude - a.magnitude || a.label.localeCompare(b.label))
    return rows
  }, [allRows, sort])
  const plotted = sorted.slice(0, MAX_PLOTTED_ROWS)
  const weightedApplied = Boolean(balance?.weighted)
  const undefinedCount = allRows.filter(
    (row) => row.unweighted === null || (weightedApplied && row.weighted === null),
  ).length

  const width = Math.max(measured, 620)
  const labelWidth = width < 760 ? 150 : 210
  const left = labelWidth + 26
  const right = width - (width < 760 ? 64 : 96)
  const rowHeight = 30
  const top = 40
  const plotHeight = Math.max(1, plotted.length) * rowHeight
  const axisY = top + plotHeight + 12
  const height = axisY + 50

  const maxAbs = useMemo(() => {
    const magnitudes = allRows.flatMap((row) => [
      Math.abs(row.unweighted ?? 0),
      Math.abs(row.weighted ?? 0),
    ])
    const observed = Math.max(0.1, ...magnitudes)
    return Math.min(2, Math.ceil(observed * 10) / 10 + 0.05)
  }, [allRows])

  const domain = { min: -maxAbs, max: maxAbs }
  const step = (domain.max - domain.min) / 5
  const ticks = niceTicks(domain.min, domain.max, 4)
  const x = (value: number) =>
    left + ((value - domain.min) / (domain.max - domain.min)) * (right - left)

  const activeRow = plotted.find((row) => row.key === active) ?? null
  const estimatorName = ESTIMATOR_LABELS[result.estimator] ?? result.estimator
  const weightedRows = allRows.filter((row) => row.weighted !== null).length

  const exportMeta: FigureExportMeta = {
    figureId: 's9b_covariate_balance',
    title: 'Standardized mean differences before and after weighting',
    settings: `${estimatorName} · ${weightedApplied ? 'unweighted vs Hájek-weighted' : 'unweighted only — this estimator applies no weights'} · ${allRows.length} covariate comparisons · ${result.sample_size ?? '—'} analysed rows`,
    note:
      'Standardized mean differences (treated minus control) computed on the analysed cohort. The 0.1 guide is a conventional heuristic, not a test: balance on measured covariates cannot establish exchangeability or the absence of unmeasured confounding.',
    provenance,
    csv: toCsv(
      ['covariate', 'kind', 'level', 'smd_unweighted', 'smd_weighted', 'weighted_diagnostics_applied'],
      allRows.map((row) => [
        row.label,
        row.kind,
        row.level ?? '',
        row.unweighted ?? '',
        row.weighted ?? '',
        weightedApplied ? 'yes' : 'no',
      ]),
    ),
    metadata: {
      estimator: result.estimator,
      balance_weighted: weightedApplied,
      diagnostic_imputation: balance?.diagnostic_imputation ?? null,
      interpretation_note: balance?.interpretation_note ?? null,
      covariates: balance?.covariates ?? [],
    },
  }

  if (!balance) {
    return (
      <section className="estfig estfig--empty" data-testid="balance-unavailable">
        <h2>No balance table for this result</h2>
        <p>
          The selected estimator returned no covariate-balance diagnostics, so there is nothing to
          draw. Balance is not inferred from another estimator's run.
        </p>
      </section>
    )
  }

  return (
    <>
      <FigureFrame
        eyebrow="Covariate balance"
        title="Did the analysis equalise the measured covariates?"
        description={
          <>
            Standardized mean differences per covariate for <strong>{estimatorName}</strong>. Filled
            marks are post-weighting values from the weights this estimator actually applied;
            hollow marks are the unweighted comparison.
          </>
        }
        svgRef={svgRef}
        exportMeta={exportMeta}
        legend={
          <>
            <LegendItem variant="unweighted">Unadjusted</LegendItem>
            {weightedApplied ? <LegendItem variant="weighted">Weighted (Hájek)</LegendItem> : null}
            <span className="estlegend__item">
              <span className="estlegend__guide" aria-hidden="true" /> 0.1 heuristic guide
            </span>
            <span className="estlegend__item">
              <span className="estlegend__zero" aria-hidden="true" /> Zero difference
            </span>
          </>
        }
        aside={
          <label className="estfig__control">
            <span>Sort</span>
            <select
              value={sort}
              onChange={(event) => setSort(event.target.value === 'order' ? 'order' : 'imbalance')}
              aria-label="Sort covariates"
            >
              <option value="imbalance">Largest imbalance first</option>
              <option value="order">Covariate order</option>
            </select>
          </label>
        }
        footnote={
          <>
            <p className="estfig__note">{balance.interpretation_note}</p>
            {balance.diagnostic_imputation ? (
              <p className="estfig__note estfig__note--warn" data-testid="balance-imputation-note">
                <strong>Imputation disclosure.</strong> {balance.diagnostic_imputation}
              </p>
            ) : null}
            {!weightedApplied ? (
              <p className="estfig__note" data-testid="balance-not-weighted">
                <strong>No post-weighting values are shown.</strong> Regression adjustment predicts
                potential outcomes from an outcome model and applies no propensity weights, so the
                backend reports no weighted SMDs for it. Selecting an IPW or AIPW result shows their
                weighted balance instead — that is a different estimator's diagnostics, never an
                estimate for this one.
              </p>
            ) : null}
            {undefinedCount > 0 ? (
              <p className="estfig__note estfig__note--warn" data-testid="balance-undefined-note">
                {undefinedCount} comparison{undefinedCount === 1 ? '' : 's'} could not be computed
                because the standardizing denominator is degenerate (both arms constant). They are
                listed as undefined, not as zero.
              </p>
            ) : null}
            <p className="estfig__note estfig__note--quiet">
              Better balance on measured covariates is a description of this sample. It does not
              establish that unmeasured confounding is absent, and graphical admissibility of the
              adjustment set is an assumption of the drawn DAG, not a result of this figure.
            </p>
          </>
        }
        testId="balance-view"
      >
        {plotted.length === 0 ? (
          <div className="estchart-empty" role="status">
            <p>This run reported no covariates to compare.</p>
          </div>
        ) : (
          <div className="estchart-scroll" ref={containerRef}>
            <svg
              ref={svgRef}
              className="estchart"
              width={width}
              height={height}
              viewBox={`0 0 ${width} ${height}`}
              role="img"
              aria-label={`Love plot. ${plotted
                .map(
                  (row) =>
                    `${row.label}: unadjusted ${row.unweighted === null ? 'undefined' : formatNumber(row.unweighted)}, ${
                      weightedApplied
                        ? `weighted ${row.weighted === null ? 'undefined' : formatNumber(row.weighted)}`
                        : 'no weighted value for this estimator'
                    }`,
                )
                .join('. ')}`}
              data-testid="love-plot"
            >
              <line x1={left} x2={left} y1={top - 16} y2={axisY} className="estchart__axis" />
              <line x1={left} x2={right} y1={axisY} y2={axisY} className="estchart__axis" />

              {ticks.map((tick) => (
                <g key={tick}>
                  <line x1={x(tick)} x2={x(tick)} y1={top - 12} y2={axisY} className="estchart__grid" />
                  <text x={x(tick)} y={axisY + 18} textAnchor="middle" className="estchart__tick">
                    {tickLabel(tick, step)}
                  </text>
                </g>
              ))}

              <line x1={x(0)} x2={x(0)} y1={top - 16} y2={axisY} className="estchart__zero" />
              <text x={x(0)} y={top - 24} textAnchor="middle" className="estchart__zerolabel">
                zero
              </text>

              {[0.1, -0.1].map((guide) => (
                <g key={guide}>
                  <line
                    x1={x(guide)}
                    x2={x(guide)}
                    y1={top - 8}
                    y2={axisY}
                    className="estchart__guide"
                  />
                  <text x={x(guide)} y={axisY + 34} textAnchor="middle" className="estchart__guidance">
                    {guide > 0 ? '+0.1' : '−0.1'}
                  </text>
                </g>
              ))}

              <text x={(left + right) / 2} y={axisY + 44} textAnchor="middle" className="estchart__axislabel">
                Standardized mean difference (treated − control)
              </text>

              {plotted.map((row, index) => {
                const y = top + index * rowHeight + rowHeight / 2
                const hasBoth =
                  weightedApplied && row.unweighted !== null && row.weighted !== null
                return (
                  <g
                    key={row.key}
                    className={`balrow${active === row.key ? ' balrow--active' : ''}`}
                    tabIndex={0}
                    role="button"
                    data-testid="love-row"
                    aria-label={`${row.label}: unadjusted ${row.unweighted === null ? 'undefined' : formatNumber(row.unweighted)}${
                      weightedApplied
                        ? `, weighted ${row.weighted === null ? 'undefined' : formatNumber(row.weighted)}`
                        : ', no weighted values'
                    }. Show details.`}
                    onMouseEnter={() => setActive(row.key)}
                    onMouseLeave={() => setActive(null)}
                    onFocus={() => setActive(row.key)}
                    onBlur={() => setActive(null)}
                  >
                    <title>
                      {row.label}: unadjusted {row.unweighted === null ? 'undefined' : formatNumber(row.unweighted)}
                      {weightedApplied
                        ? `, weighted ${row.weighted === null ? 'undefined' : formatNumber(row.weighted)}`
                        : ''}
                    </title>
                    <rect x={0} y={y - rowHeight / 2 + 4} width={width} height={rowHeight - 8} className="estrow__band" />
                    <text x={labelWidth - 8} y={y + 4} textAnchor="end" className="balrow__label">
                      {row.label}
                    </text>
                    <text x={labelWidth - 8} y={y + 16} textAnchor="end" className="balrow__kind">
                      {row.kind === 'categorical' ? 'category level' : 'numeric'}
                    </text>

                    {row.unweighted === null ? (
                      <text x={x(0) + 8} y={y + 4} className="balrow__undefined">
                        undefined
                      </text>
                    ) : (
                      <circle
                        cx={x(row.unweighted)}
                        cy={y}
                        r={5}
                        className="balrow__unweighted"
                        data-testid="love-unweighted"
                      />
                    )}

                    {hasBoth ? (
                      <line
                        x1={x(row.unweighted as number)}
                        x2={x(row.weighted as number)}
                        y1={y}
                        y2={y}
                        className="balrow__shift"
                      />
                    ) : null}

                    {weightedApplied ? (
                      row.weighted === null ? (
                        <text x={x(0) + 8} y={y + 16} className="balrow__undefined">
                          weighted undefined
                        </text>
                      ) : (
                        <rect
                          x={x(row.weighted) - 4.5}
                          y={y - 4.5}
                          width={9}
                          height={9}
                          transform={`rotate(45 ${x(row.weighted)} ${y})`}
                          className="balrow__weighted"
                          data-testid="love-weighted"
                        />
                      )
                    ) : null}
                  </g>
                )
              })}
            </svg>
          </div>
        )}
      </FigureFrame>

      <div className="estview-split">
        <section className="esttable-block" aria-label="Balance details">
          <div className="esttable-block__head">
            <h3>Covariate detail</h3>
            {activeRow ? (
              <p className="esttable-block__note" aria-live="polite">
                <strong>{activeRow.label}</strong> · unadjusted{' '}
                {activeRow.unweighted === null ? 'undefined' : formatNumber(activeRow.unweighted)}
                {weightedApplied
                  ? ` · weighted ${activeRow.weighted === null ? 'undefined' : formatNumber(activeRow.weighted)}`
                  : ' · no weighted value (no weights applied)'}
              </p>
            ) : (
              <p className="esttable-block__note">
                Hover or focus a row in the plot, or read the full table below.
              </p>
            )}
          </div>
          {sorted.length > plotted.length ? (
            <p className="tiny muted" data-testid="balance-row-cap">
              Showing the {plotted.length} largest imbalances of {sorted.length} comparisons in the
              figure. Every comparison is listed below and exported.
            </p>
          ) : null}
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Covariate balance table">
            <table className="table esttable" data-testid="balance-table">
              <caption className="table__caption">
                Standardized mean differences, {estimatorName}
                {weightedApplied ? '' : ' (unweighted; this estimator applies no weights)'}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Covariate</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Unadjusted SMD</th>
                  <th scope="col">Weighted SMD</th>
                  <th scope="col">Movement</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.label}</th>
                    <td>{row.kind === 'categorical' ? 'category level' : 'numeric'}</td>
                    <td>{row.unweighted === null ? <span className="esttable__quiet">undefined</span> : formatNumber(row.unweighted)}</td>
                    <td>
                      {!weightedApplied ? (
                        <span className="esttable__quiet">not applicable</span>
                      ) : row.weighted === null ? (
                        <span className="esttable__quiet">undefined</span>
                      ) : (
                        formatNumber(row.weighted)
                      )}
                    </td>
                    <td>
                      {!weightedApplied || row.weighted === null || row.unweighted === null
                        ? '—'
                        : `${formatNumber(Math.abs(row.unweighted) - Math.abs(row.weighted))}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="estview-side" aria-label="Balance interpretation">
          <h3>What this figure can and cannot show</h3>
          <ul className="estlist">
            <li>
              SMDs are descriptive summaries of this analysed cohort, computed from the covariate
              values the fitted models saw.
            </li>
            <li>
              The 0.1 guide is a reporting convention. Crossing it proves nothing; failing to cross
              it proves nothing either.
            </li>
            <li>
              Weighted values exist only for estimators that weight. {weightedRows} of{' '}
              {allRows.length} comparisons carry a weighted value in this result.
            </li>
            <li>
              Balance cannot see unmeasured confounding. A perfectly balanced table is compatible
              with a badly biased estimate.
            </li>
          </ul>
          {staleNote ? <p className="estview-side__stale">{staleNote}</p> : null}
        </aside>
      </div>
    </>
  )
}
