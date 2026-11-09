/**
 * View E - Methodology & Interpretation.
 *
 * Everything needed to reproduce or criticise the estimate: the estimand, the
 * cohort and every exclusion, the adjustment set, the exact nuisance models,
 * cross-fitting, missing-data policy, interval construction, seeds,
 * fingerprints, software versions and every structured warning.
 *
 * The interpretation paragraph is assembled from verified metadata only, with
 * a fixed template. It never claims that the estimate is the true causal effect.
 */

import type { EstimationRunPayload } from '../api/types'
import { ESTIMATOR_DESCRIPTIONS, ESTIMATOR_LABELS, ESTIMATOR_ORDER } from './estimationModel'
import { formatInteger, formatNumber, formatPercent, unitsLabel } from './format'

function outcomeUnits(payload: EstimationRunPayload): string {
  return unitsLabel(payload.results.find((result) => result.units)?.units, payload.analysis.outcome_task)
}

export function MethodologyView({
  payload,
  knownEffect,
}: {
  payload: EstimationRunPayload
  knownEffect: { value: number; note: string } | null
}) {
  const repro = payload.reproducibility
  const unitLabel = outcomeUnits(payload)
  const successful = payload.results.filter((result) => result.status === 'estimated')
  const failures = payload.results.filter((result) => result.status === 'failed')
  const treatedLabel = payload.analysis.treatment_column
  const outcomeLabel = payload.analysis.outcome_column

  const estimatesSentence = successful
    .map(
      (result) =>
        `${ESTIMATOR_LABELS[result.estimator] ?? result.estimator} ${formatNumber(result.estimate)} ${unitLabel}${result.uncertainty?.status === 'available' && result.uncertainty.ci_lower !== null && result.uncertainty.ci_upper !== null ? ` (${Math.round(result.uncertainty.level * 100)}% interval ${formatNumber(result.uncertainty.ci_lower)} to ${formatNumber(result.uncertainty.ci_upper)})` : ' (interval unavailable)'}`,
    )
    .join('; ')

  return (
    <div className="estmethods" data-testid="methodology-view">
      <section className="estmethods__lead">
        <p className="estfig__eyebrow">Methodology & interpretation</p>
        <h2>What exactly was estimated, and under which assumptions?</h2>
        <p className="estmethods__statement" data-testid="interpretation">
          Under the assumptions encoded in the selected DAG, the supported identification criterion
          (classical backdoor adjustment) and the fitted estimation models, the estimated average
          treatment effect of <strong>{treatedLabel}</strong> ({payload.reproducibility.treatment_mapping.treated} vs{' '}
          {payload.reproducibility.treatment_mapping.control}) on <strong>{outcomeLabel}</strong> is{' '}
          <strong>{estimatesSentence}</strong>, expressed in {unitLabel}, on {formatInteger(payload.analysis.rows_final)}{' '}
          analysed rows. This is a finite-sample estimate from this dataset under those assumptions -
          not a proof that the effect is causal, and not a prediction for any individual unit.
        </p>
        {knownEffect ? (
          <p className="estmethods__synthetic" data-testid="known-effect">
            <strong>Known data-generating effect: {formatNumber(knownEffect.value)} {unitLabel}.</strong>{' '}
            {knownEffect.note}
          </p>
        ) : null}
        {failures.length > 0 ? (
          <p className="estmethods__failure" data-testid="methodology-failures">
            <strong>
              {failures.length} of {payload.results.length} estimators failed:
            </strong>{' '}
            {failures
              .map(
                (result) =>
                  `${ESTIMATOR_LABELS[result.estimator] ?? result.estimator} - ${result.failure?.reason ?? 'no reason reported'}`,
              )
              .join('; ')}
            . A failed estimator contributes no estimate and is never treated as a zero effect.
          </p>
        ) : null}
      </section>

      <div className="estmethods__grid">
        <section className="estmethods__card">
          <h3>Estimand and scope</h3>
          <dl className="estdeflist">
            <div><dt>Estimand</dt><dd>Average treatment effect (ATE), {payload.estimand.toUpperCase()}</dd></div>
            <div><dt>Treatment variable</dt><dd>{treatedLabel} (graph node <code>{repro.treatment_node}</code>)</dd></div>
            <div><dt>Treated / control values</dt><dd>“{repro.treatment_mapping.treated}” vs “{repro.treatment_mapping.control}”</dd></div>
            <div><dt>Outcome variable</dt><dd>{outcomeLabel} (graph node <code>{repro.outcome_node}</code>)</dd></div>
            <div><dt>Outcome units</dt><dd>{unitLabel}</dd></div>
            <div>
              <dt>Outcome handling</dt>
              <dd>{payload.analysis.outcome_task === 'logistic' ? 'binary outcome, reported as a probability difference' : 'continuous outcome'}</dd>
            </div>
            <div>
              <dt>Analysis cohort</dt>
              <dd>
                {repro.cohort.split_assignment_id
                  ? `“${repro.cohort.partition}” partition of split assignment ${repro.cohort.split_assignment_id}`
                  : 'every dataset row surviving preparation'}
              </dd>
            </div>
          </dl>
        </section>

        <section className="estmethods__card">
          <h3>Cohort accounting</h3>
          <dl className="estdeflist">
            <div><dt>Rows in dataset</dt><dd>{formatInteger(payload.analysis.rows_in_dataset)}</dd></div>
            <div><dt>Rows in cohort frame</dt><dd>{formatInteger(payload.analysis.rows_in_analysis_cohort_frame)}</dd></div>
            <div><dt>Rows analysed</dt><dd>{formatInteger(payload.analysis.rows_final)}</dd></div>
            <div><dt>Treated / control</dt><dd>{formatInteger(payload.analysis.treated_rows)} / {formatInteger(payload.analysis.control_rows)}</dd></div>
            <div><dt>Missing-data policy</dt><dd>{payload.analysis.missing_data_policy === 'complete_case' ? 'complete case' : 'fold-fitted median/mode imputation'}</dd></div>
          </dl>
          {payload.analysis.exclusions.length === 0 ? (
            <p className="estmethods__quiet">No rows were excluded from the declared cohort.</p>
          ) : (
            <table className="table esttable esttable--compact">
              <caption className="table__caption">Every exclusion, with its reason</caption>
              <thead>
                <tr><th scope="col">Reason</th><th scope="col">Rows</th><th scope="col">Detail</th></tr>
              </thead>
              <tbody>
                {payload.analysis.exclusions.map((exclusion) => (
                  <tr key={exclusion.reason}>
                    <th scope="row">{exclusion.reason.replace(/_/g, ' ')}</th>
                    <td>{formatInteger(exclusion.count)}</td>
                    <td>{exclusion.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="estmethods__card">
          <h3>Adjustment set</h3>
          <dl className="estdeflist">
            <div>
              <dt>Variables</dt>
              <dd>
                {payload.analysis.adjustment_columns.length === 0
                  ? 'Empty set - nothing adjusted for'
                  : payload.analysis.adjustment_columns.join(', ')}
              </dd>
            </div>
            <div><dt>Graph verdict</dt><dd>{payload.gate.adjustment_set_verification.valid ? 'satisfies the classical backdoor criterion on the assumed DAG' : 'not admissible'}</dd></div>
            <div><dt>Verification note</dt><dd>{payload.gate.adjustment_set_verification.interpretation_note}</dd></div>
          </dl>
          <ul className="estmethods__covariates">
            {payload.analysis.covariates.map((covariate) => (
              <li key={covariate.column}>
                <code>{covariate.column}</code> · {covariate.kind}
                {covariate.levels ? ` (${covariate.levels.join(', ')})` : ''}
                {covariate.missing_in_cohort > 0 ? ` · ${covariate.missing_in_cohort} missing in cohort` : ''}
              </li>
            ))}
          </ul>
        </section>

        <section className="estmethods__card">
          <h3>Estimation and uncertainty</h3>
          <dl className="estdeflist">
            <div><dt>Estimators requested</dt><dd>{repro.estimators.map((name) => ESTIMATOR_LABELS[name] ?? name).join(' · ')}</dd></div>
            {ESTIMATOR_ORDER.filter((name) => repro.estimators.includes(name)).map((name) => {
              const result = payload.results.find((entry) => entry.estimator === name)
              return (
                <div key={name}>
                  <dt>{ESTIMATOR_LABELS[name]}</dt>
                  <dd>
                    {ESTIMATOR_DESCRIPTIONS[name]}
                    {result?.model_specification ? (
                      <>
                        {' '}
                        Fitted specification: <code>{JSON.stringify(result.model_specification)}</code>.
                      </>
                    ) : null}
                    {result?.uncertainty?.status === 'unavailable' ? (
                      <>
                        {' '}
                        Interval unavailable: {result.uncertainty.unavailable_reason}
                      </>
                    ) : null}
                  </dd>
                </div>
              )
            })}
            <div><dt>Cross-fitting</dt><dd>{repro.cross_fitting.splits} folds{repro.cross_fitting.group_column ? `, grouped by ${repro.cross_fitting.group_column}` : ', shuffled rows'}</dd></div>
            <div>
              <dt>Interval construction</dt>
              <dd>
                {repro.uncertainty.method === 'bootstrap'
                  ? `${Math.round(repro.uncertainty.level * 100)}% percentile bootstrap, ${repro.uncertainty.reps} replicates, refitting nuisance models each replicate (resolved seed ${repro.uncertainty.resolved_seed})`
                  : `${Math.round(repro.uncertainty.level * 100)}% influence-function interval (AIPW/IPW only; regression adjustment reports none)`}
              </dd>
            </div>
            <div><dt>Propensity truncation</dt><dd>{repro.propensity_truncation ? `[${formatNumber(repro.propensity_truncation.lower, 2)}, ${formatNumber(repro.propensity_truncation.upper, 2)}]` : 'none'}</dd></div>
            <div><dt>Requested seed</dt><dd>{repro.uncertainty.seed === null ? 'generated by the server' : String(repro.uncertainty.seed)}</dd></div>
          </dl>
        </section>
      </div>

      <section className="estmethods__card estmethods__card--wide">
        <h3>Provenance</h3>
        <dl className="estdeflist estdeflist--two">
          <div><dt>Dataset id</dt><dd><code>{repro.dataset_id}</code></dd></div>
          <div><dt>Dataset fingerprint (sha256)</dt><dd><code className="estmethods__hash">{repro.dataset_fingerprint_sha256}</code></dd></div>
          <div><dt>Graph id</dt><dd><code>{repro.graph_id}</code></dd></div>
          <div><dt>Graph revision</dt><dd>{formatInteger(repro.graph_revision)}</dd></div>
          <div><dt>Graph scientific fingerprint</dt><dd><code className="estmethods__hash">{repro.graph_spec_fingerprint_sha256}</code></dd></div>
          <div><dt>Run id</dt><dd><code>{payload.run_id}</code></dd></div>
          <div><dt>Created (UTC)</dt><dd>{payload.created_at_utc}</dd></div>
          <div><dt>Estimation contract</dt><dd>{repro.estimation_version} · schema {repro.estimation_schema_version}</dd></div>
        </dl>
        <details className="disclosure">
          <summary>Software versions and hard bounds</summary>
          <dl className="estdeflist estdeflist--two">
            {Object.entries(repro.software_versions).map(([name, version]) => (
              <div key={name}><dt>{name}</dt><dd>{version}</dd></div>
            ))}
            {Object.entries(repro.limits).map(([name, value]) => (
              <div key={name}><dt>{name.replace(/_/g, ' ')}</dt><dd>{formatInteger(value)}</dd></div>
            ))}
          </dl>
        </details>
      </section>

      <section className="estmethods__card estmethods__card--wide">
        <h3>Assumptions, warnings and defaults</h3>
        <p className="estmethods__quiet">{payload.scope_note}</p>
        <p className="estmethods__quiet">{payload.gate.caveat}</p>
        <ul className="estlist">
          {repro.uncertainty.method === 'bootstrap' ? (
            <li>
              Intervals assume independent observations. Repeated-measure or clustered data need
              cluster-aware inference this stage does not provide.
            </li>
          ) : null}
          {repro.missing_data_policy === 'median_mode' ? (
            <li>
              Median/mode imputation was fitted inside each fold. Imputation reduces the loss of
              rows but does not remove missing-data bias.
            </li>
          ) : null}
          {payload.results
            .flatMap((result) =>
              (result.uncertainty?.assumptions ?? []).map((assumption) => `${ESTIMATOR_LABELS[result.estimator] ?? result.estimator}: ${assumption}`),
            )
            .map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
        </ul>
        {payload.defaults_applied.length > 0 ? (
          <details className="disclosure" open>
            <summary>Defaults the server applied</summary>
            <ul className="estlist">
              {payload.defaults_applied.map((entry) => (
                <li key={`${entry.field}-${String(entry.value)}`}>
                  <code>{entry.field}</code> = {String(entry.value)} - {entry.meaning}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
        <div className="estmethods__warnings">
          {payload.results.flatMap((result) =>
            (result.warnings ?? []).map((warning) => (
              <p key={`${result.estimator}-${warning}`} className="estmethods__warning">
                <strong>{ESTIMATOR_LABELS[result.estimator] ?? result.estimator}:</strong> {warning}
              </p>
            )),
          )}
          {payload.results.every((result) => (result.warnings ?? []).length === 0) ? (
            <p className="estmethods__quiet">No estimator-level warnings were reported for this run.</p>
          ) : null}
        </div>
      </section>

      <section className="estmethods__card estmethods__card--wide">
        <h3>Limitations of this stage</h3>
        <ul className="estlist">
          <li>Only the average treatment effect is estimated. No ATT, CATE, mediation or instrument-based estimand exists in this stage.</li>
          <li>Nuisance models are deliberately simple and named (logistic regression, linear least squares). No hyperparameter search or Super Learner is used.</li>
          <li>Graphical identification means the drawn DAG blocks every backdoor path. It is not evidence that the DAG is correct.</li>
          <li>Overlap, balance and effective-sample-size diagnostics describe the fitted model and this dataset. None verifies positivity or exchangeability.</li>
          <li>Runs live in a bounded in-memory session store; they expire and are not a permanent archive.</li>
        </ul>
      </section>

      <p className="estmethods__quiet">
        Reproducibility: the same dataset fingerprint, graph fingerprint, request and seeds reproduce
        this analysis. {successful.length > 0 ? `${successful.length} estimator(s) produced an estimate.` : 'No estimator produced an estimate.'}{' '}
        {payload.analysis.rows_in_dataset > 0 && payload.analysis.rows_final > 0
          ? `${formatPercent(payload.analysis.rows_final / payload.analysis.rows_in_dataset, 1)} of dataset rows entered the analysed cohort.`
          : ''}
      </p>
    </div>
  )
}
