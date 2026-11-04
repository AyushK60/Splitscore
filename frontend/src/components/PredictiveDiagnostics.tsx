/**
 * S6 predictive diagnostics: PR, reliability, Q–Q, OLS influence and
 * permutation importance. Every value comes from the returned model run; these
 * components only plot or tabulate it and state the partition and method.
 */

import type { JSX } from 'react'

import type {
  PredictionCalibrationEntry,
  PredictionImportance,
  PredictionInfluence,
  PredictionInfluencePoint,
  PredictionPrCurve,
  PredictionQq,
  PredictionSubgroup,
} from '../api/types'

function fmt(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value !== 0 && Math.abs(value) < 0.001) return value.toExponential(2)
  return value.toPrecision(digits)
}

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function pValue(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value < 0.0001) return '< 0.0001'
  return value.toFixed(4)
}

function intervalText(
  low: number | null | undefined,
  high: number | null | undefined,
  format = fmt,
): string {
  if (low === null || low === undefined || high === null || high === undefined) return '—'
  return `${format(low)} – ${format(high)}`
}

export function PrPlot({ curve }: { curve: PredictionPrCurve }): JSX.Element {
  const width = 360
  const height = 270
  const pad = { left: 42, right: 12, top: 12, bottom: 34 }
  const px = (value: number) => pad.left + value * (width - pad.left - pad.right)
  const py = (value: number) => height - pad.bottom - value * (height - pad.top - pad.bottom)
  const ordered = curve.recall
    .map((recall, index) => ({ recall, precision: curve.precision[index] ?? 0 }))
    .sort((left, right) => left.recall - right.recall)
  const points = ordered
    .map((entry) => `${px(entry.recall).toFixed(2)},${py(entry.precision).toFixed(2)}`)
    .join(' ')
  const baseline = curve.prevalence ?? 0
  return (
    <svg
      className="mlab__svg plab__pr"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Precision-recall curve on the sealed test partition"
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
        y1={py(baseline)}
        x2={px(1)}
        y2={py(baseline)}
        stroke="var(--rs-line-strong)"
        strokeDasharray="4 4"
      />
      <polyline points={points} fill="none" stroke="var(--rs-teal)" strokeWidth={2} />
      <text x={(pad.left + width - pad.right) / 2} y={height - 8} textAnchor="middle" className="xpc__tick">
        recall
      </text>
      <text x={12} y={pad.top + 8} className="xpc__tick">
        precision
      </text>
      <text x={width - pad.right} y={pad.top + 12} textAnchor="end" className="xpc__tick">
        AP {fmt(curve.average_precision)}
      </text>
      <text x={px(0.02)} y={py(baseline) - 6} className="xpc__tick">
        prevalence {pct(baseline)}
      </text>
    </svg>
  )
}

export function ReliabilityPlot({
  entries,
}: {
  entries: PredictionCalibrationEntry[]
}): JSX.Element {
  const width = 360
  const height = 280
  const pad = { left: 42, right: 14, top: 14, bottom: 36 }
  const px = (value: number) => pad.left + value * (width - pad.left - pad.right)
  const py = (value: number) => height - pad.bottom - value * (height - pad.top - pad.bottom)
  const used = entries.filter(
    (entry) =>
      entry.count > 0 &&
      entry.mean_predicted !== null &&
      entry.observed_rate !== null &&
      Number.isFinite(entry.mean_predicted) &&
      Number.isFinite(entry.observed_rate),
  )
  if (!used.length) {
    return <p className="mlab__hint">No non-empty calibration bins were returned.</p>
  }
  const points = used
    .map((entry) => `${px(entry.mean_predicted as number)},${py(entry.observed_rate as number)}`)
  return (
    <svg
      className="mlab__svg plab__reliability"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Calibration reliability plot on the sealed test partition"
    >
      <rect
        x={pad.left}
        y={pad.top}
        width={width - pad.left - pad.right}
        height={height - pad.top - pad.bottom}
        fill="none"
        stroke="var(--rs-line)"
      />
      <line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(1)} stroke="var(--rs-line-strong)" strokeDasharray="4 4" />
      {used.map((entry) => {
        const x = px(entry.mean_predicted as number)
        const low = entry.observed_rate_low
        const high = entry.observed_rate_high
        return (
          <g key={`${entry.bin_low}-${entry.bin_high}`}>
            {low !== null && low !== undefined && high !== null && high !== undefined ? (
              <line x1={x} y1={py(low)} x2={x} y2={py(high)} stroke="var(--rs-line-strong)" />
            ) : null}
            <circle
              cx={x}
              cy={py(entry.observed_rate as number)}
              r={3.2}
              fill="var(--rs-teal)"
            >
              <title>
                {`${entry.bin_low.toFixed(1)}–${entry.bin_high.toFixed(1)}: ${entry.count} rows, predicted ${fmt(entry.mean_predicted)}, observed ${fmt(entry.observed_rate)}`}
              </title>
            </circle>
          </g>
        )
      })}
      <polyline points={points.join(' ')} fill="none" stroke="var(--rs-teal)" strokeWidth={1.2} opacity={0.65} />
      <text x={(pad.left + width - pad.right) / 2} y={height - 8} textAnchor="middle" className="xpc__tick">
        mean predicted probability
      </text>
      <text x={12} y={pad.top + 8} className="xpc__tick">
        observed positive rate
      </text>
    </svg>
  )
}

export function QqPlot({ qq }: { qq: PredictionQq }): JSX.Element {
  const theoretical = qq.theoretical ?? []
  const sample = qq.sample ?? []
  if (theoretical.length < 2 || theoretical.length !== sample.length) {
    return <p className="mlab__hint">Q–Q coordinates were not returned.</p>
  }
  const width = 360
  const height = 280
  const pad = { left: 46, right: 14, top: 14, bottom: 38 }
  const slope = qq.reference_slope ?? 1
  const intercept = qq.reference_intercept ?? 0
  const reference = theoretical.map((value) => intercept + slope * value)
  const xMin = Math.min(...theoretical)
  const xMax = Math.max(...theoretical)
  const yMin = Math.min(...sample, ...reference)
  const yMax = Math.max(...sample, ...reference)
  const px = (value: number) =>
    pad.left + (xMax === xMin ? 0.5 : (value - xMin) / (xMax - xMin)) * (width - pad.left - pad.right)
  const py = (value: number) =>
    height - pad.bottom - (yMax === yMin ? 0.5 : (value - yMin) / (yMax - yMin)) * (height - pad.top - pad.bottom)
  return (
    <svg
      className="mlab__svg plab__qq"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Normal Q-Q plot of test residuals"
    >
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} stroke="var(--rs-line)" />
      <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} stroke="var(--rs-line)" />
      <line
        x1={px(xMin)}
        y1={py(intercept + slope * xMin)}
        x2={px(xMax)}
        y2={py(intercept + slope * xMax)}
        stroke="var(--rs-line-strong)"
        strokeDasharray="4 4"
      />
      {theoretical.map((value, index) => (
        <circle
          key={`${value}-${index}`}
          cx={px(value)}
          cy={py(sample[index])}
          r={2.3}
          fill="var(--rs-teal)"
          opacity={0.65}
        />
      ))}
      <text x={(pad.left + width - pad.right) / 2} y={height - 8} textAnchor="middle" className="xpc__tick">
        theoretical normal quantile
      </text>
      <text x={12} y={pad.top + 8} className="xpc__tick">
        ordered residual
      </text>
    </svg>
  )
}

export function InfluencePlot({
  influence,
}: {
  influence: PredictionInfluence
}): JSX.Element {
  const points = influence.points ?? []
  if (!points.length) return <p className="mlab__hint">No influence points were returned.</p>
  const width = 440
  const height = 270
  const pad = { left: 48, right: 16, top: 14, bottom: 38 }
  const xMax = Math.max(...points.map((point) => point.leverage), influence.thresholds?.leverage_2p_over_n ?? 0)
  const yLimit = Math.max(1e-9, ...points.map((point) => Math.abs(point.standardized_residual)))
  const maxCooks = Math.max(1e-9, ...points.map((point) => point.cooks_distance))
  const px = (value: number) =>
    pad.left + (xMax === 0 ? 0.5 : value / xMax) * (width - pad.left - pad.right)
  const py = (value: number) =>
    (pad.top + height - pad.bottom) / 2 - (value / yLimit) * ((height - pad.top - pad.bottom) / 2)
  const threshold = influence.thresholds?.leverage_2p_over_n
  return (
    <svg
      className="mlab__svg plab__influence"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Leverage versus standardized residual with Cook's distance"
    >
      <line x1={pad.left} y1={py(0)} x2={width - pad.right} y2={py(0)} stroke="var(--rs-line-strong)" />
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} stroke="var(--rs-line)" />
      {threshold !== undefined ? (
        <line
          x1={px(threshold)}
          y1={pad.top}
          x2={px(threshold)}
          y2={height - pad.bottom}
          stroke="var(--rs-line-strong)"
          strokeDasharray="4 4"
        />
      ) : null}
      {points.map((point) => (
        <circle
          key={point.row_id}
          cx={px(point.leverage)}
          cy={py(point.standardized_residual)}
          r={2 + 5 * Math.sqrt(point.cooks_distance / maxCooks)}
          fill="var(--rs-teal)"
          opacity={0.55}
        >
          <title>
            {`${point.row_id}: leverage ${fmt(point.leverage)}, standardized residual ${fmt(point.standardized_residual)}, Cook's D ${fmt(point.cooks_distance)}`}
          </title>
        </circle>
      ))}
      <text x={(pad.left + width - pad.right) / 2} y={height - 8} textAnchor="middle" className="xpc__tick">
        leverage
      </text>
      <text x={12} y={pad.top + 8} className="xpc__tick">
        standardized residual
      </text>
      <text x={width - pad.right} y={height - 20} textAnchor="end" className="xpc__tick">
        circle area ∝ Cook&apos;s D
      </text>
    </svg>
  )
}

export function InfluenceSection({
  influence,
}: {
  influence: PredictionInfluence | null
}): JSX.Element {
  if (!influence) return <></>
  if (!influence.applicable) {
    return (
      <div className="callout callout--info" role="status">
        <p className="callout__title">Influence diagnostics not applicable</p>
        <p style={{ margin: 0 }}>{influence.reason ?? 'This model does not support OLS influence diagnostics.'}</p>
      </div>
    )
  }
  const coefficients = influence.coefficients ?? []
  const top = influence.top_influence ?? []
  return (
    <>
      <h2 className="mlab__h2">OLS influence (in-sample)</h2>
      <p className="mlab__hint">
        {influence.method} {influence.note}
      </p>
      <dl className="mlab__facts">
        <div>
          <dt>Partition</dt>
          <dd>{influence.partition ?? '—'}</dd>
        </div>
        <div>
          <dt>n / parameters / residual df</dt>
          <dd>
            {influence.n ?? '—'} / {influence.parameters ?? '—'} / {influence.residual_df ?? '—'}
          </dd>
        </div>
        <div>
          <dt>Max leverage</dt>
          <dd>{fmt(influence.max_leverage)}</dd>
        </div>
        <div>
          <dt>Max Cook&apos;s D</dt>
          <dd>{fmt(influence.max_cooks)}</dd>
        </div>
        <div>
          <dt>Above 2p/n / Cook&apos;s &gt; 1</dt>
          <dd>
            {influence.counts?.above_leverage_2p ?? '—'} / {influence.counts?.above_cooks_1 ?? '—'}
          </dd>
        </div>
      </dl>
      <figure className="mlab__figure">
        <InfluencePlot influence={influence} />
        <figcaption>
          Refit rows only (fit + validation). Dashed vertical line: leverage threshold 2p/n ={' '}
          {fmt(influence.thresholds?.leverage_2p_over_n)}. Circle area is proportional to Cook&apos;s
          distance. This is an in-sample OLS diagnostic, not held-out performance.
        </figcaption>
      </figure>
      <div className="mlab__tablewrap">
        <table className="mlab__table mlab__table--compact">
          <caption>
            Classical OLS coefficients and 95% intervals on the transformed refit design. Inference
            assumes independent, homoskedastic errors.
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
                95% interval
              </th>
              <th scope="col" className="num">
                p-value
              </th>
            </tr>
          </thead>
          <tbody>
            {coefficients.map((entry) => (
              <tr key={entry.term}>
                <th scope="row" className="mono">
                  {entry.term}
                </th>
                <td className="num">{fmt(entry.estimate)}</td>
                <td className="num">{fmt(entry.std_error)}</td>
                <td className="num">{intervalText(entry.ci_low, entry.ci_high)}</td>
                <td className="num">{pValue(entry.p_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mlab__tablewrap">
        <table className="mlab__table mlab__table--compact">
          <caption>Largest Cook&apos;s distances among the refit rows.</caption>
          <thead>
            <tr>
              <th scope="col">Row</th>
              <th scope="col" className="num">
                Leverage
              </th>
              <th scope="col" className="num">
                Std. residual
              </th>
              <th scope="col" className="num">
                Cook&apos;s D
              </th>
            </tr>
          </thead>
          <tbody>
            {top.map((entry: PredictionInfluencePoint) => (
              <tr key={entry.row_id}>
                <th scope="row" className="mono">
                  {entry.row_id}
                </th>
                <td className="num">{fmt(entry.leverage)}</td>
                <td className="num">{fmt(entry.standardized_residual)}</td>
                <td className="num">{fmt(entry.cooks_distance)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export function ImportanceSection({
  importance,
}: {
  importance: PredictionImportance | null
}): JSX.Element {
  if (!importance) return <></>
  if (!importance.applicable) {
    return (
      <div className="callout callout--info" role="status">
        <p className="callout__title">Permutation importance not computed</p>
        <p style={{ margin: 0 }}>{importance.reason ?? 'This run does not support permutation importance.'}</p>
      </div>
    )
  }
  const rows = importance.rows ?? []
  const maxAbs = Math.max(1e-12, ...rows.map((row) => Math.abs(row.importance_mean)))
  const baselineLabel = importance.metric === 'rmse_increase' ? 'RMSE' : 'balanced accuracy'
  const changeLabel =
    importance.metric === 'rmse_increase' ? 'Mean RMSE increase' : 'Mean balanced-accuracy drop'
  return (
    <>
      <h2 className="mlab__h2">Permutation importance — test partition</h2>
      <p className="mlab__hint">
        {importance.method} Baseline {baselineLabel} = {fmt(importance.baseline_score)}. Higher
        values mean the model&apos;s score got worse when that predictor was permuted.
      </p>
      <div className="mlab__tablewrap">
        <table className="mlab__table mlab__table--compact plab__importance">
          <caption>
            {importance.n ?? '—'} test rows, {importance.repeats ?? '—'} repeats. Descriptive only;
            correlated predictors can share or mask importance. Not a causal effect.
          </caption>
          <thead>
            <tr>
              <th scope="col">Predictor</th>
              <th scope="col" className="num">
                {changeLabel}
              </th>
              <th scope="col" className="num">
                SD
              </th>
              <th scope="col">Relative magnitude</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.feature}>
                <th scope="row">{row.feature}</th>
                <td className="num">{fmt(row.importance_mean)}</td>
                <td className="num">{fmt(row.importance_sd)}</td>
                <td>
                  <span
                    className={`plab__importancebar${row.importance_mean < 0 ? ' plab__importancebar--neg' : ''}`}
                    style={{ width: `${Math.max(2, (Math.abs(row.importance_mean) / maxAbs) * 100)}%` }}
                    aria-hidden="true"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

export function SubgroupTable({ subgroup }: { subgroup: PredictionSubgroup }): JSX.Element {
  return (
    <div className="mlab__tablewrap">
      <table className="mlab__table plab__subgroups">
        <caption>
          {subgroup.column} on the test partition: {subgroup.grouped_rows} grouped of{' '}
          {subgroup.test_rows} rows
          {subgroup.outside_bins
            ? `; ${subgroup.outside_bins} row(s) fell outside the stated bins`
            : ''}
          . Each n is the denominator for that row.
        </caption>
        <thead>
          <tr>
            <th scope="col">Group</th>
            <th scope="col" className="num">
              n
            </th>
            <th scope="col" className="num">
              Share
            </th>
            <th scope="col" className="num">
              Test metric
            </th>
            <th scope="col" className="num">
              95% interval
            </th>
            <th scope="col" className="num">
              {subgroup.outcome_measure ?? 'Outcome mean'}
            </th>
            <th scope="col">Warning</th>
          </tr>
        </thead>
        <tbody>
          {subgroup.rows.map((entry) => (
            <tr key={entry.group}>
              <th scope="row">{entry.group}</th>
              <td className="num">{entry.n}</td>
              <td className="num">{pct(entry.share)}</td>
              <td className="num">
                {entry.metric_name ? `${entry.metric_name} ` : ''}
                {entry.metric_name === 'accuracy' ? pct(entry.metric) : fmt(entry.metric)}
              </td>
              <td className="num" title={entry.ci_method ?? undefined}>
                {entry.metric_name === 'accuracy'
                  ? intervalText(entry.ci_low, entry.ci_high, pct)
                  : intervalText(entry.ci_low, entry.ci_high)}
              </td>
              <td className="num">
                {entry.outcome_measure === 'positive-class rate'
                  ? pct(entry.outcome_mean)
                  : fmt(entry.outcome_mean)}
              </td>
              <td>{entry.warning ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
