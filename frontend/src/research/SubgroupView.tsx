/**
 * S9C-A — Subgroup Effects.
 *
 * One large forest plot of subgroup ATEs from the cross-fitted AIPW
 * estimating equation, the overall effect as a reference, a supporting table,
 * between-group contrasts with their own uncertainty, and the honest states:
 * unavailable subgroups are listed with their reason, never plotted as zeros,
 * and exploratory vs prespecified intent is labelled in the payload's own words.
 */

import { useMemo, useRef, useState } from 'react'

import type { SubgroupGroup, SubgroupRunPayload } from '../api/types'
import { estimationApi } from '../api/client'
import type { EstimationRequestPayload } from '../api/types'
import { formatInteger, formatNumber, niceTicks, toCsv } from '../estimation/format'
import { FigureFrame, useMeasuredWidth } from '../estimation/figureFrame'
import type { FigureExportMeta } from '../estimation/estimationExport'
import { describeError, type ErrorInfo } from '../estimation/estimationErrors'
import { forestDomain, scale } from './researchModel'

export interface SubgroupVariableOption {
  node_id: string
  label: string
  column: string | null
  kind: 'numeric' | 'categorical' | 'unknown'
}

export function SubgroupView({
  datasetId,
  graphId,
  graphFingerprint,
  request,
  variables,
}: {
  datasetId: string
  graphId: string
  graphFingerprint: string
  request: EstimationRequestPayload
  variables: SubgroupVariableOption[]
}) {
  const [nodeId, setNodeId] = useState('')
  const [binning, setBinning] = useState<'median' | 'tercile' | 'quartile'>('quartile')
  const [intent, setIntent] = useState<'exploratory' | 'prespecified'>('exploratory')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ErrorInfo | null>(null)
  const [payload, setPayload] = useState<SubgroupRunPayload | null>(null)

  const selected = variables.find((variable) => variable.node_id === nodeId) ?? null

  const run = async () => {
    if (!selected) return
    setBusy(true)
    setError(null)
    try {
      const response = await estimationApi.subgroups(
        datasetId,
        graphId,
        { ...request, expected_spec_fingerprint_sha256: graphFingerprint },
        {
          node_id: selected.node_id,
          numeric_binning: binning,
          levels: null,
          intent,
        },
        `subgroups: ${selected.label}`,
      )
      setPayload(response)
    } catch (caught) {
      setPayload(null)
      setError(describeError(caught, 'The subgroup analysis could not be run'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rsview" data-testid="subgroup-view">
      <section className="rssetup" aria-label="Subgroup configuration">
        <div className="rssetup__grid">
          <label className="rsfield">
            <span className="rsfield__label">Subgroup variable (pretreatment)</span>
            <select
              value={nodeId}
              onChange={(event) => setNodeId(event.target.value)}
              data-testid="subgroup-variable"
            >
              <option value="">Choose a baseline variable…</option>
              {variables.map((variable) => (
                <option key={variable.node_id} value={variable.node_id}>
                  {variable.label}
                  {variable.column && variable.column !== variable.label ? ` (${variable.column})` : ''}
                </option>
              ))}
            </select>
            <span className="rsfield__hint">
              A variable measured before treatment. The backend refuses any variable that is a
              descendant of the treatment on the saved graph.
            </span>
          </label>
          <label className="rsfield">
            <span className="rsfield__label">Numeric binning</span>
            <select
              value={binning}
              onChange={(event) => setBinning(event.target.value as typeof binning)}
              disabled={selected !== null && selected.kind !== 'numeric'}
            >
              <option value="median">Median split (2 groups)</option>
              <option value="tercile">Terciles (3 groups)</option>
              <option value="quartile">Quartiles (4 groups)</option>
            </select>
            <span className="rsfield__hint">
              Applies when the variable is numeric; the quantile edges are reported with the result.
            </span>
          </label>
          <label className="rsfield">
            <span className="rsfield__label">Analysis intent</span>
            <select
              value={intent}
              onChange={(event) => setIntent(event.target.value as typeof intent)}
            >
              <option value="exploratory">Exploratory</option>
              <option value="prespecified">Prespecified</option>
            </select>
            <span className="rsfield__hint">
              Mark prespecified only if the subgroup definition was fixed before looking at the
              estimated effects. The default is exploratory, and the result says so.
            </span>
          </label>
          <div className="rsfield rsfield--action">
            <button
              type="button"
              className="btn btn--primary"
              disabled={!selected || busy}
              onClick={run}
              data-testid="subgroup-run"
            >
              {busy ? 'Estimating…' : 'Estimate subgroup effects'}
            </button>
          </div>
        </div>
        {error ? (
          <div className="callout callout--danger" role="alert" data-testid="subgroup-error">
            <p className="callout__title">{error.title}</p>
            <p style={{ margin: 0 }}>{error.message}</p>
            {error.details.length ? (
              <ul style={{ margin: '8px 0 0' }}>
                {error.details.map((detail) => (
                  <li key={detail}>{detail}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </section>

      {payload ? <SubgroupResult payload={payload} /> : (
        <section className="card rsempty" aria-label="No subgroup result yet">
          <p>
            Choose a pretreatment variable and estimate. Subgroup effects are computed from the
            same cross-fitted AIPW estimating equation as the overall effect, on the same cohort
            and adjustment set as the estimation run you selected.
          </p>
        </section>
      )}
    </div>
  )
}

export function SubgroupResult({ payload }: { payload: SubgroupRunPayload }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const measured = useMeasuredWidth(containerRef, 920)
  const [active, setActive] = useState<number | null>(null)

  const unitLabel = 'outcome units'

  const domain = useMemo(
    () => forestDomain(payload.groups, payload.overall.estimate),
    [payload],
  )
  const ticks = useMemo(() => niceTicks(domain.min, domain.max, 5), [domain])

  const width = Math.max(measured, 620)
  const labelWidth = width < 760 ? 180 : 220
  const left = labelWidth + 20
  const right = width - 90
  const rowHeight = 58
  const top = 44
  const plotHeight = Math.max(1, payload.groups.length) * rowHeight
  const axisY = top + plotHeight + 12
  const height = axisY + 56
  const x = (value: number) => scale(value, domain, left, right)

  const activeGroup = active !== null ? payload.groups[active] : null

  const exportMeta: FigureExportMeta = {
    figureId: 's9c_subgroup_forest',
    title: 'Subgroup average treatment effects (forest plot)',
    settings: `AIPW pseudo-outcome averages · subgroup: ${payload.subgroup.column} · ${formatInteger(payload.analysis.rows_final)} cohort rows`,
    note: 'Each subgroup estimate averages the cross-fitted AIPW pseudo-outcome over that subgroup\u2019s rows, with influence-function uncertainty. Heterogeneity is exploratory evidence about this sample under the assumed graph — not a verified mechanism.',
    provenance: [
      `run_id: ${payload.run_id}`,
      `created_at_utc: ${payload.created_at_utc}`,
      `graph_fingerprint: ${payload.reproducibility.graph_spec_fingerprint_sha256}`,
      `dataset_fingerprint: ${payload.reproducibility.dataset_fingerprint_sha256}`,
      `subgroup: ${payload.subgroup.column} (${payload.subgroup.kind})`,
      `intent: ${payload.subgroup.intent}`,
    ],
    csv: toCsv(
      ['group', 'status', 'rows', 'treated_rows', 'control_rows', 'estimate', 'ci_lower', 'ci_upper', 'warnings'],
      payload.groups.map((group) => [
        group.label,
        group.status,
        group.rows,
        group.treated_rows,
        group.control_rows,
        group.estimate ?? '',
        group.ci_lower ?? '',
        group.ci_upper ?? '',
        group.warnings.join(' | '),
      ]),
    ),
    metadata: {
      run_id: payload.run_id,
      created_at_utc: payload.created_at_utc,
      subgroup: payload.subgroup,
      overall: payload.overall,
      groups: payload.groups,
      contrasts: payload.contrasts,
    },
  }

  const legend = (
    <>
      <span className="estlegend__item">
        <span className="rsdot rsdot--group" aria-hidden="true" /> Subgroup effect
      </span>
      <span className="estlegend__item">
        <span className="rsdot rsdot--overall" aria-hidden="true" /> Overall ATE
      </span>
      <span className="estlegend__item">
        <span className="rsline-sample" aria-hidden="true" /> Reported interval
      </span>
    </>
  )

  return (
    <>
      <FigureFrame
        eyebrow="Subgroup effects"
        title={`Average treatment effects across ${payload.subgroup.column}`}
        description={
          <>
            {payload.subgroup.definition}. Subgroup effects average the cross-fitted AIPW
            pseudo-outcome over each subgroup&apos;s rows on the shared cohort of{' '}
            {formatInteger(payload.analysis.rows_final)} rows. Intent:{' '}
            <strong>{payload.subgroup.intent}</strong>.
          </>
        }
        svgRef={svgRef}
        exportMeta={exportMeta}
        legend={legend}
        testId="subgroup-forest"
        footnote={
          <>
            <p className="estfig__note">{payload.scope_note}</p>
            {payload.notes
              .filter((note) => note.code !== 'intent')
              .map((note) => (
                <p key={note.code} className="estfig__note estfig__note--quiet">
                  {note.text}
                </p>
              ))}
          </>
        }
      >
        <div className="estchart-scroll" ref={containerRef}>
          <svg
            ref={svgRef}
            className="estchart"
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`Forest plot of subgroup average treatment effects by ${payload.subgroup.column}, in ${unitLabel}.`}
            data-testid="subgroup-forest-chart"
          >
            <line x1={left} x2={left} y1={top - 10} y2={axisY} className="estchart__axis" />
            <line x1={left} x2={right} y1={axisY} y2={axisY} className="estchart__axis" />
            <line
              x1={x(payload.overall.estimate)}
              x2={x(payload.overall.estimate)}
              y1={top - 20}
              y2={axisY}
              className="rszero"
            />
            <text
              x={x(payload.overall.estimate)}
              y={top - 26}
              textAnchor="middle"
              className="rszero__label"
            >
              overall {formatNumber(payload.overall.estimate)}
            </text>
            {ticks.map((tick) => (
              <g key={tick}>
                <line x1={x(tick)} x2={x(tick)} y1={top - 10} y2={axisY} className="estchart__grid" />
                <text x={x(tick)} y={axisY + 18} textAnchor="middle" className="estchart__tick">
                  {formatNumber(tick, Math.abs(domain.max - domain.min) < 6 ? 1 : 0)}
                </text>
              </g>
            ))}
            <text
              x={(left + right) / 2}
              y={axisY + 40}
              textAnchor="middle"
              className="estchart__axislabel"
            >
              Average treatment effect ({unitLabel})
            </text>

            {payload.groups.map((group, index) => {
              const y = top + index * rowHeight + rowHeight / 2
              const isEstimated =
                group.status === 'estimated' && typeof group.estimate === 'number'
              const hasInterval =
                isEstimated &&
                typeof group.ci_lower === 'number' &&
                typeof group.ci_upper === 'number'
              return (
                <g
                  key={group.label}
                  className={`rsrow${active === index ? ' rsrow--active' : ''}`}
                  tabIndex={0}
                  role="button"
                  aria-label={
                    isEstimated
                      ? `${group.label}: ${formatNumber(group.estimate)} ${unitLabel}, ${formatNumber(group.ci_lower)} to ${formatNumber(group.ci_upper)}`
                      : `${group.label}: not estimated`
                  }
                  data-testid={`forest-row-${index}`}
                  onMouseEnter={() => setActive(index)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(index)}
                  onBlur={() => setActive(null)}
                >
                  <rect
                    x={0}
                    y={y - rowHeight / 2 + 6}
                    width={width}
                    height={rowHeight - 12}
                    className="estrow__band"
                  />
                  <text x={labelWidth - 8} y={y - 2} textAnchor="end" className="estrow__name">
                    {group.label}
                  </text>
                  <text x={labelWidth - 8} y={y + 15} textAnchor="end" className="estrow__meta">
                    {formatInteger(group.rows)} rows · {formatInteger(group.treated_rows)}T/{formatInteger(group.control_rows)}C
                  </text>
                  {isEstimated && hasInterval ? (
                    <>
                      <line
                        x1={x(group.ci_lower as number)}
                        x2={x(group.ci_upper as number)}
                        y1={y}
                        y2={y}
                        className="estrow__interval"
                      />
                      <line
                        x1={x(group.ci_lower as number)}
                        x2={x(group.ci_lower as number)}
                        y1={y - 6}
                        y2={y + 6}
                        className="estrow__cap"
                      />
                      <line
                        x1={x(group.ci_upper as number)}
                        x2={x(group.ci_upper as number)}
                        y1={y - 6}
                        y2={y + 6}
                        className="estrow__cap"
                      />
                      <circle cx={x(group.estimate as number)} cy={y} r={5.5} className="rsdot--group" />
                      <text
                        x={x(group.ci_upper as number) + 12}
                        y={y + 4}
                        className="estrow__value"
                      >
                        {formatNumber(group.estimate)}
                      </text>
                    </>
                  ) : (
                    <text x={left + 12} y={y + 4} className="estrow__failure">
                      Not estimated — {group.unavailable_reason ?? 'unavailable'}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        </div>
        <div className="estsum__detail" aria-live="polite">
          {activeGroup ? (
            <GroupDetail group={activeGroup} />
          ) : (
            <p className="estsum__hint">
              Point at a subgroup row, or focus it with the keyboard, to read its estimate,
              interval, sample accounting and overlap warnings.
            </p>
          )}
        </div>
      </FigureFrame>

      <section className="esttable-block" aria-label="Subgroup table">
        <div className="esttable-block__head">
          <h3>Subgroup details</h3>
          <p className="esttable-block__note">
            Values exactly as reported by the estimation engine. A subgroup that cannot support
            estimation is listed as unavailable; it is never shown as a zero effect.
          </p>
        </div>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Subgroup table">
          <table className="table esttable esttable--wrap" data-testid="subgroup-table">
            <caption className="table__caption">
              Subgroup average treatment effects by {payload.subgroup.column}
            </caption>
            <thead>
              <tr>
                <th scope="col">Group</th>
                <th scope="col">Rows</th>
                <th scope="col">Treated / control</th>
                <th scope="col">ATE ({unitLabel})</th>
                <th scope="col">Interval</th>
                <th scope="col">Warnings</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {payload.groups.map((group) => (
                <tr key={group.label} data-testid={`subgroup-table-${group.label}`}>
                  <th scope="row">{group.label}</th>
                  <td>{formatInteger(group.rows)}</td>
                  <td>
                    {formatInteger(group.treated_rows)} / {formatInteger(group.control_rows)}
                  </td>
                  <td>
                    {group.estimate !== null ? formatNumber(group.estimate) : '—'}
                  </td>
                  <td>
                    {group.ci_lower !== null && group.ci_upper !== null
                      ? `${formatNumber(group.ci_lower)} to ${formatNumber(group.ci_upper)}`
                      : '—'}
                  </td>
                  <td>
                    {group.warnings.length === 0 ? (
                      <span className="esttable__quiet">none</span>
                    ) : (
                      <ul className="esttable__warnings">
                        {group.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td>
                    {group.status === 'estimated' ? (
                      <span className="eststate eststate--ok">estimated</span>
                    ) : (
                      <span className="eststate eststate--failed">unavailable</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {payload.contrasts && payload.contrasts.length > 0 ? (
        <section className="estcompare" aria-label="Between-group contrasts">
          <h3>Between-group contrasts</h3>
          <p className="estfig__note estfig__note--quiet">
            Each contrast is a difference of two subgroup effects with its own influence-function
            interval. A contrast can be precise even when the two intervals overlap; read the
            contrasts, not the interval overlap.
          </p>
          <ul className="rscontrasts" data-testid="subgroup-contrasts">
            {payload.contrasts.map((contrast) => (
              <li key={`${contrast.a}-${contrast.b}`} className="rscontrasts__item">
                <strong>{contrast.a}</strong> − <strong>{contrast.b}</strong> ={' '}
                {formatNumber(contrast.difference)} ({formatNumber(contrast.ci_lower)} to{' '}
                {formatNumber(contrast.ci_upper)})
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  )
}

function GroupDetail({ group }: { group: SubgroupGroup }) {
  if (group.status !== 'estimated') {
    return (
      <div className="estsum__detailcard estsum__detailcard--failed">
        <p className="estsum__detailtitle">{group.label} — not estimated</p>
        <p>{group.unavailable_reason ?? 'No subgroup estimate is available.'}</p>
      </div>
    )
  }
  return (
    <div className="estsum__detailcard">
      <p className="estsum__detailtitle">{group.label}</p>
      <p className="estsum__detailvalue">
        {formatNumber(group.estimate)} outcome units
        {group.ci_lower !== null && group.ci_upper !== null ? (
          <span className="estsum__detailci">
            {' '}
            · {formatNumber(group.ci_lower)} to {formatNumber(group.ci_upper)}
          </span>
        ) : null}
      </p>
      <p className="estsum__detailmeta">
        {formatInteger(group.rows)} rows · {formatInteger(group.treated_rows)} treated ·{' '}
        {formatInteger(group.control_rows)} control · SE {formatNumber(group.standard_error)}
      </p>
      {group.propensity_summary ? (
        <p className="estsum__detailmeta">
          Fitted-propensity ranges inside the group: treated{' '}
          {formatNumber(group.propensity_summary.treated_min, 2)}–
          {formatNumber(group.propensity_summary.treated_max, 2)}, control{' '}
          {formatNumber(group.propensity_summary.control_min, 2)}–
          {formatNumber(group.propensity_summary.control_max, 2)}
          {group.propensity_summary.extreme_rows > 0
            ? ` · ${group.propensity_summary.extreme_rows} extreme score(s)`
            : ''}
        </p>
      ) : null}
      {group.warnings.map((warning) => (
        <p key={warning} className="estsum__detailmeta">
          {warning}
        </p>
      ))}
    </div>
  )
}
