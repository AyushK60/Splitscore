/**
 * S9C-C — What-If Explorer.
 *
 * Model-based conditional outcome predictions from the verified
 * g-computation outcome model: one profile scenario (treatment = 1 vs 0)
 * beside the cohort-standardised scenario. Every prediction is labelled as a
 * model expectation under explicit assumptions — never an observed
 * counterfactual, and never interval-bearing. Unset profile fields fall back
 * to disclosed cohort medians/modes, and out-of-support values are answered
 * with the backend's extrapolation warnings.
 */

import { useRef, useState } from 'react'

import { estimationApi } from '../api/client'
import type { EstimationCohortPreview, EstimationRequestPayload, WhatIfRunPayload } from '../api/types'
import { formatInteger, formatNumber } from '../estimation/format'
import { FigureFrame, useMeasuredWidth } from '../estimation/figureFrame'
import type { FigureExportMeta } from '../estimation/estimationExport'
import { toCsv } from '../estimation/format'
import { describeError, type ErrorInfo } from '../estimation/estimationErrors'

export function WhatIfView({
  datasetId,
  graphId,
  graphFingerprint,
  request,
  covariates,
}: {
  datasetId: string
  graphId: string
  graphFingerprint: string
  request: EstimationRequestPayload
  covariates: EstimationCohortPreview['covariates']
}) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ErrorInfo | null>(null)
  const [payload, setPayload] = useState<WhatIfRunPayload | null>(null)

  const setValue = (column: string, value: string) => {
    setValues((current) => ({ ...current, [column]: value }))
  }

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const profile: Record<string, number | string | null> = {}
      for (const covariate of covariates) {
        const raw = values[covariate.column]?.trim() ?? ''
        if (raw === '') {
          profile[covariate.column] = null
        } else if (covariate.kind === 'numeric') {
          profile[covariate.column] = Number(raw)
        } else {
          profile[covariate.column] = raw
        }
      }
      const response = await estimationApi.whatIf(
        datasetId,
        graphId,
        { ...request, expected_spec_fingerprint_sha256: graphFingerprint },
        profile,
        'what-if scenario',
      )
      setPayload(response)
    } catch (caught) {
      setPayload(null)
      setError(describeError(caught, 'The scenario could not be computed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rsview" data-testid="whatif-view">
      <section className="rssetup" aria-label="Scenario configuration">
        <div className="rssetup__grid">
          {covariates.map((covariate) => (
            <label className="rsfield" key={covariate.column}>
              <span className="rsfield__label">
                {covariate.column} ({covariate.kind})
              </span>
              {covariate.kind === 'numeric' ? (
                <input
                  type="number"
                  step="any"
                  value={values[covariate.column] ?? ''}
                  placeholder="cohort median"
                  onChange={(event) => setValue(covariate.column, event.target.value)}
                  data-testid={`whatif-field-${covariate.column}`}
                />
              ) : (
                <select
                  value={values[covariate.column] ?? ''}
                  onChange={(event) => setValue(covariate.column, event.target.value)}
                  data-testid={`whatif-field-${covariate.column}`}
                >
                  <option value="">cohort mode</option>
                  {(covariate.levels ?? []).map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              )}
              <span className="rsfield__hint">
                {covariate.kind === 'categorical'
                  ? `Observed levels: ${(covariate.levels ?? []).join(', ')}`
                  : 'Leave empty to hold at the cohort median (disclosed with the result).'}
              </span>
            </label>
          ))}
          <div className="rsfield rsfield--action">
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy}
              onClick={run}
              data-testid="whatif-run"
            >
              {busy ? 'Predicting…' : 'Predict scenario'}
            </button>
          </div>
        </div>
        {error ? (
          <div className="callout callout--danger" role="alert" data-testid="whatif-error">
            <p className="callout__title">{error.title}</p>
            <p style={{ margin: 0 }}>{error.message}</p>
          </div>
        ) : null}
      </section>

      {payload ? (
        <WhatIfResult payload={payload} />
      ) : (
        <section className="card rsempty" aria-label="No scenario yet">
          <p>
            Set a baseline covariate profile — or leave fields at their disclosed cohort defaults
            — and predict. The treatment state is the only interventional variable; adjusting a
            baseline covariate describes a conditional-model scenario, not an intervention on
            that covariate.
          </p>
        </section>
      )}
    </div>
  )
}

export function WhatIfResult({ payload }: { payload: WhatIfRunPayload }) {
  const scenario = payload.profile_scenario
  const cohort = payload.cohort_scenario
  const units = payload.model_specification.units === 'probability_difference'
    ? 'probability of the coded outcome'
    : 'outcome units'
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const measured = useMeasuredWidth(containerRef, 760)
  const width = Math.max(measured, 520)
  const height = 190
  const labelWidth = 150
  const left = labelWidth + 20
  const right = width - 110
  const maxAbs = Math.max(
    Math.abs(scenario.treated_prediction),
    Math.abs(scenario.control_prediction),
    1e-9,
  )
  const x = (value: number) => left + ((value + maxAbs) / (2 * maxAbs)) * (right - left)
  const zero = x(0)

  const exportMeta: FigureExportMeta = {
    figureId: 's9c_what_if_scenario',
    title: 'Model-based scenario predictions under treatment and control',
    settings: `g-computation outcome model · ${formatInteger(payload.analysis.rows_final)} cohort rows`,
    note: payload.scope_note,
    provenance: [
      `run_id: ${payload.run_id}`,
      `created_at_utc: ${payload.created_at_utc}`,
      `model: ${payload.model_specification.kind}`,
      `profile: ${JSON.stringify(scenario.profile)}`,
    ],
    csv: toCsv(
      ['quantity', 'value'],
      [
        ['profile_treated_prediction', scenario.treated_prediction],
        ['profile_control_prediction', scenario.control_prediction],
        ['profile_contrast', scenario.contrast],
        ['cohort_treated_mean', cohort.treated_mean],
        ['cohort_control_mean', cohort.control_mean],
        ['cohort_contrast', cohort.contrast],
      ],
    ),
    metadata: {
      run_id: payload.run_id,
      created_at_utc: payload.created_at_utc,
      profile_scenario: scenario,
      cohort_scenario: cohort,
    },
  }

  return (
    <>
      <FigureFrame
        eyebrow="What-if explorer"
        title="Expected outcome under treatment and under control"
        description={
          <>
            The fitted g-computation outcome model&apos;s expectation for the stated baseline
            profile under treatment = 1 and treatment = 0, in {units}. These are model-based
            conditional predictions under explicit assumptions — not observed outcomes and not
            individual counterfactuals.
          </>
        }
        svgRef={svgRef}
        exportMeta={exportMeta}
        testId="whatif-figure"
        footnote={
          <>
            <p className="estfig__note">{payload.model_specification.uncertainty}</p>
            {payload.warnings
              .filter((warning) => warning !== payload.scope_note)
              .map((warning) => (
                <p key={warning.slice(0, 48)} className="estfig__note">
                  {warning}
                </p>
              ))}
          </>
        }
      >
        <div className="estchart-scroll" ref={containerRef}>
          <svg
            ref={svgRef}
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={`Model-predicted outcomes: treated ${formatNumber(scenario.treated_prediction)}, control ${formatNumber(scenario.control_prediction)}, contrast ${formatNumber(scenario.contrast)}.`}
            className="estchart"
            data-testid="whatif-chart"
          >
            <line x1={left} x2={right} y1={60} y2={60} className="estchart__axis" />
            <line x1={left} x2={right} y1={120} y2={120} className="estchart__axis" />
            <line x1={zero} x2={zero} y1={44} y2={132} className="estchart__zero" />
            <text x={left - 8} y={64} textAnchor="end" className="estrow__name">
              Treated
            </text>
            <text x={left - 8} y={124} textAnchor="end" className="estrow__name">
              Control
            </text>
            <rect
              x={Math.min(zero, x(scenario.treated_prediction))}
              y={46}
              width={Math.abs(x(scenario.treated_prediction) - zero)}
              height={28}
              className="rsbar rsbar--treated"
              data-testid="whatif-treated-bar"
            >
              <title>Treated: {formatNumber(scenario.treated_prediction)}</title>
            </rect>
            <rect
              x={Math.min(zero, x(scenario.control_prediction))}
              y={106}
              width={Math.abs(x(scenario.control_prediction) - zero)}
              height={28}
              className="rsbar rsbar--control"
              data-testid="whatif-control-bar"
            >
              <title>Control: {formatNumber(scenario.control_prediction)}</title>
            </rect>
            <text
              x={Math.max(x(scenario.treated_prediction), zero) + 10}
              y={64}
              className="estrow__value"
            >
              {formatNumber(scenario.treated_prediction)}
            </text>
            <text
              x={Math.max(x(scenario.control_prediction), zero) + 10}
              y={124}
              className="estrow__value"
            >
              {formatNumber(scenario.control_prediction)}
            </text>
            <text x={(left + right) / 2} y={height - 14} textAnchor="middle" className="estchart__axislabel">
              Modelled expected outcome ({units})
            </text>
          </svg>
        </div>
        <div className="estsum__detail" aria-live="polite">
          <div className="estsum__detailcard">
            <p className="estsum__detailtitle">Scenario contrast</p>
            <p className="estsum__detailvalue" data-testid="whatif-contrast">
              {formatNumber(scenario.contrast)} {units}
            </p>
            <p className="estsum__detailmeta">
              Cohort-standardised contrast on the same model:{' '}
              {formatNumber(cohort.contrast)} {units} — the g-computation ATE the estimation
              studio reports.
            </p>
          </div>
        </div>
      </FigureFrame>

      <section className="esttable-block" aria-label="Scenario specification">
        <div className="esttable-block__head">
          <h3>Profile and disclosures</h3>
          <p className="esttable-block__note">
            Every field is either set explicitly or held at a disclosed cohort default; nothing
            about the profile is silent.
          </p>
        </div>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Scenario profile table">
          <table className="table esttable" data-testid="whatif-profile">
            <caption className="table__caption">Baseline covariate profile</caption>
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Value</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {scenario.disclosures.map((item) => (
                <tr key={item.field}>
                  <th scope="row">{item.field}</th>
                  <td>{String(item.value)}</td>
                  <td>
                    {item.source === 'explicit' ? (
                      'set explicitly'
                    ) : item.source === 'cohort_median' ? (
                      'cohort median (default)'
                    ) : (
                      'cohort mode (default)'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
