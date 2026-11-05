import type { ReactNode } from 'react'

import type {
  DossierAudit,
  DossierComparison,
  DossierFindings,
  DossierLimitations,
  DossierModels,
  DossierPredictiveModel,
  DossierProvenance,
  DossierReproducibility,
  DossierReport,
  DossierSection,
  DossierStatisticalModel,
  DossierStudy,
  DossierSummary,
  Finding,
  RiskScorecard,
} from '../../api/types'
import { integer } from '../../lib/format'

/**
 * In-app rendering of the exact dossier object returned by the server.
 *
 * This is deliberately a renderer, not a second composition layer: every table
 * cell, count and caveat comes from the API payload. Unavailable requested
 * sections keep their reason rather than disappearing. The same payload feeds
 * the downloaded HTML, so screen and artifact cannot diverge.
 */

function value(input: unknown): string {
  if (input === null || input === undefined || input === '') return '—'
  if (typeof input === 'boolean') return input ? 'yes' : 'no'
  if (Array.isArray(input)) return input.length ? input.map(value).join(', ') : '—'
  if (typeof input === 'object') {
    try {
      return JSON.stringify(input)
    } catch {
      return String(input)
    }
  }
  return String(input)
}

function pct(input: number | null | undefined): string {
  if (input === null || input === undefined || !Number.isFinite(input)) return '—'
  return `${(input * 100).toFixed(1)}%`
}

function number(input: number | null | undefined, digits = 3): string {
  if (input === null || input === undefined || !Number.isFinite(input)) return '—'
  if (Number.isInteger(input)) return integer(input)
  return input.toFixed(digits)
}

function statusLabel(status: string): string {
  return status.replaceAll('_', ' ')
}

function SectionShell({
  section,
  children,
}: {
  section: DossierSection
  children: ReactNode
}) {
  return (
    <section className="report-section" id={`report-${section.id}`}>
      <header className="report-section__head">
        <p className="report-section__kicker">{section.id}</p>
        <h2>{section.title}</h2>
        <p className="report-section__lede">{section.description}</p>
      </header>
      {section.available ? (
        children
      ) : (
        <div className="report-unavailable">
          <strong>Not available in this dossier.</strong>
          <p>{section.reason ?? 'The source analysis was not included.'}</p>
        </div>
      )}
    </section>
  )
}

function SummarySection({ summary }: { summary: DossierSummary }) {
  const split = summary.split
  return (
    <>
      <div className="report-stats">
        <div>
          <b>{integer(summary.findings_total)}</b>
          <span>findings</span>
        </div>
        <div>
          <b>{integer(summary.evaluated_rule_count)}</b>
          <span>checks evaluated</span>
        </div>
        <div>
          <b>{integer(summary.not_evaluated_count)}</b>
          <span>not evaluated</span>
        </div>
        <div>
          <b>{integer(summary.model_count)}</b>
          <span>model runs</span>
        </div>
      </div>

      <div className="report-splitline">
        <div>
          <span className="report-label">Study</span>
          <p>{summary.study_title}</p>
          {summary.objective ? <p className="report-muted">{summary.objective}</p> : null}
        </div>
        <div>
          <span className="report-label">Audited split</span>
          <p>{split ? split.label : 'No audit run included'}</p>
          <p className="report-muted">
            {split
              ? `${integer(split.train_rows)} train / ${integer(split.test_rows)} test rows · ${pct(split.achieved_test_fraction)} test`
              : 'Run the audit to add a split and its rule outcomes.'}
          </p>
        </div>
      </div>

      <div className="report-callout">
        <span className="report-label">Audit headline</span>
        <p>{summary.audit_headline ?? 'No audit run is included, so no leakage verdict is stated.'}</p>
      </div>

      <h3>Analyses included</h3>
      <div className="report-analyses">
        {summary.analyses.map((analysis) => (
          <div key={analysis.key} className={`report-analysis report-analysis--${analysis.status}`}>
            <strong>{analysis.label}</strong>
            <span className="mono">{analysis.run_id ?? 'not run'}</span>
            <span className="report-analysis__status">{statusLabel(analysis.status)}</span>
          </div>
        ))}
      </div>

      <div className="report-two-col">
        <div>
          <h3>Key findings</h3>
          {summary.key_findings.length ? (
            <ul className="report-finding-list">
              {summary.key_findings.map((finding) => (
                <li key={finding.rule_id}>
                  <span className={`sev sev--${finding.severity}`}>{finding.severity}</span>
                  <span>
                    <span className="mono">{finding.rule_id}</span> · {finding.title}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="report-muted">No findings are present in the included audit run.</p>
          )}
        </div>
        <div>
          <h3>Cautions for a reviewer</h3>
          <ul className="report-cautions">
            {summary.cautions.map((caution) => (
              <li key={caution}>{caution}</li>
            ))}
          </ul>
        </div>
      </div>
      <p className="report-note">{summary.note}</p>
    </>
  )
}

function ProvenanceSection({ data }: { data: DossierProvenance }) {
  return (
    <>
      <dl className="report-kv">
        <dt>Dataset</dt>
        <dd>{data.dataset.name}</dd>
        <dt>Source</dt>
        <dd>
          {data.dataset.source}
          {data.dataset.is_synthetic ? ' · synthetic demonstration' : ''}
        </dd>
        <dt>Rows × columns</dt>
        <dd>
          {integer(data.dataset.row_count)} × {integer(data.dataset.column_count)}
        </dd>
        <dt>SHA-256</dt>
        <dd className="mono report-break">{data.dataset.sha256}</dd>
        <dt>Loaded at</dt>
        <dd className="mono">{data.dataset.created_at_utc}</dd>
        <dt>Profile</dt>
        <dd>
          {integer(data.profile.numeric_columns ?? 0)} numeric ·{' '}
          {integer(data.profile.datetime_columns ?? 0)} datetime ·{' '}
          {integer(data.profile.duplicate_rows ?? 0)} exact duplicate rows
        </dd>
      </dl>

      <h3>Column dictionary</h3>
      <div className="report-table-wrap">
        <table className="report-table">
          <thead>
            <tr>
              <th scope="col">Column</th>
              <th scope="col">Detected</th>
              <th scope="col">Declared</th>
              <th scope="col">Roles</th>
              <th scope="col" className="num">
                Missing
              </th>
              <th scope="col" className="num">
                Distinct
              </th>
              <th scope="col">Unit</th>
            </tr>
          </thead>
          <tbody>
            {data.columns.map((column) => (
              <tr key={column.column}>
                <th scope="row">{column.column}</th>
                <td>{column.detected_type}</td>
                <td>{column.declared_type ?? '—'}</td>
                <td>{column.roles.length ? column.roles.join(', ') : '—'}</td>
                <td className="num">{integer(column.missing_count)}</td>
                <td className="num">{integer(column.distinct_count)}</td>
                <td>{column.unit ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.profile.warnings.length ? (
        <>
          <h3>Profile warnings</h3>
          <ul>
            {data.profile.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="report-note">{data.role_note}</p>
    </>
  )
}

function StudySection({ data }: { data: DossierStudy }) {
  const completion = data.completion
  const roles = data.roles.assignments ?? {}
  return (
    <>
      <dl className="report-kv">
        <dt>Study id</dt>
        <dd className="mono">{data.study_id ?? '—'}</dd>
        <dt>Revision</dt>
        <dd>{value(data.revision)}</dd>
        <dt>Required fields declared</dt>
        <dd>
          {completion
            ? `${integer(completion.declared)} / ${integer(completion.required)}`
            : '—'}
        </dd>
        <dt>Missing required fields</dt>
        <dd>{completion?.missing.length ? completion.missing.join(', ') : 'none'}</dd>
        <dt>Updated</dt>
        <dd className="mono">{data.updated_at_utc ?? '—'}</dd>
      </dl>

      <h3>Declared study fields</h3>
      {data.declared_fields.length ? (
        <div className="report-table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Declared value</th>
              </tr>
            </thead>
            <tbody>
              {data.declared_fields.map((field) => (
                <tr key={field.name}>
                  <th scope="row">{field.label}</th>
                  <td>{value(field.value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="report-muted">
          No study fields were declared. Missing values remain missing; nothing is filled in.
        </p>
      )}

      <h3>Role declarations</h3>
      {Object.keys(roles).length ? (
        <div className="report-table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                <th scope="col">Column</th>
                <th scope="col">Research roles</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(roles)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([column, assigned]) => (
                  <tr key={column}>
                    <th scope="row">{column}</th>
                    <td>{assigned.length ? assigned.join(', ') : '—'}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="report-muted">No roles were declared.</p>
      )}

      {data.issues.length ? (
        <>
          <h3>Study issues</h3>
          <ul>
            {data.issues.map((issue) => (
              <li key={`${issue.code}-${issue.message}`}>
                <span className={`sev sev--${issue.severity}`}>{issue.severity}</span> {issue.message}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="report-note">{data.note}</p>
    </>
  )
}

function AuditSection({ data }: { data: DossierAudit }) {
  return (
    <>
      <dl className="report-kv">
        <dt>Run id</dt>
        <dd className="mono">{data.run_id ?? '—'}</dd>
        <dt>Generated</dt>
        <dd className="mono">{data.generated_at_utc}</dd>
        <dt>Split</dt>
        <dd>
          {data.split.label} · {data.split.kind}
        </dd>
        <dt>Train / test</dt>
        <dd>
          {integer(data.split.train_rows)} / {integer(data.split.test_rows)} rows ·{' '}
          {pct(data.split.achieved_test_fraction)} test
        </dd>
        <dt>Seed</dt>
        <dd className="mono">{data.split.seed ?? 'not a generated split'}</dd>
        <dt>Headline</dt>
        <dd>{data.evaluation.headline}</dd>
      </dl>

      <h3>Rule outcomes</h3>
      <div className="report-table-wrap">
        <table className="report-table">
          <thead>
            <tr>
              <th scope="col">Rule</th>
              <th scope="col">Title</th>
              <th scope="col">Status</th>
              <th scope="col" className="num">
                Findings
              </th>
              <th scope="col" className="num">
                Duration
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rule_outcomes.map((outcome) => (
              <tr key={outcome.rule_id}>
                <th scope="row" className="mono">
                  {outcome.rule_id}
                </th>
                <td>{outcome.title}</td>
                <td>{statusLabel(outcome.status)}</td>
                <td className="num">{integer(outcome.finding_count)}</td>
                <td className="num">{number(outcome.duration_ms, 1)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Not evaluated</h3>
      {data.not_evaluated.length ? (
        <div className="report-unavailable report-unavailable--soft">
          <p>
            These checks did not run. Their absence from the findings is not evidence of
            absence.
          </p>
          <ul>
            {data.not_evaluated.map((check) => (
              <li key={check.rule_id}>
                <span className="mono">{check.rule_id}</span> · {check.title} — {check.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="report-muted">Every enabled check was evaluated.</p>
      )}

      <h3>Audit limitations</h3>
      <ul>
        {data.limitations.map((limitation) => (
          <li key={limitation}>{limitation}</li>
        ))}
      </ul>
    </>
  )
}

function ScorecardSection({ data }: { data: RiskScorecard }) {
  return (
    <>
      <div className="report-scorecard">
        {data.categories.map((category) => (
          <article key={category.key} className={`report-score report-score--${category.status}`}>
            <header>
              <h3>{category.label}</h3>
              <span className="report-score__status">{statusLabel(category.status)}</span>
            </header>
            <p className="report-muted">
              {integer(category.finding_count)} finding(s)
              {category.affected_rows !== null
                ? ` · ${integer(category.affected_rows)} affected rows (best effort)`
                : ''}
            </p>
            <ul>
              {category.rules.map((rule) => (
                <li key={rule.rule_id}>
                  <span className="mono">{rule.rule_id}</span> — {statusLabel(rule.status)}
                  {rule.finding_count ? ` · ${integer(rule.finding_count)} finding(s)` : ''}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
      <p className="report-note">{data.note}</p>
    </>
  )
}

function FindingCard({ finding }: { finding: Finding }) {
  return (
    <article className={`report-finding report-finding--${finding.severity}`}>
      <header>
        <span className={`sev sev--${finding.severity}`}>{finding.severity}</span>
        <span className="mono report-muted">{finding.rule_id}</span>
      </header>
      <h3>{finding.title}</h3>
      <p>{finding.description}</p>
      <p>
        <strong>Evidence:</strong> {finding.evidence_summary}
      </p>
      <p>
        <strong>Why this severity:</strong> {finding.severity_rationale}
      </p>
      <div className="report-table-wrap">
        <table className="report-table">
          <thead>
            <tr>
              <th scope="col">Count</th>
              <th scope="col" className="num">
                Affected
              </th>
              <th scope="col" className="num">
                Denominator
              </th>
              <th scope="col">Unit</th>
              <th scope="col">Scope</th>
            </tr>
          </thead>
          <tbody>
            {finding.counts.map((count) => (
              <tr key={`${count.label}-${count.scope}`}>
                <th scope="row">{count.label}</th>
                <td className="num">{integer(count.affected)}</td>
                <td className="num">{integer(count.denominator)}</td>
                <td>{count.unit}</td>
                <td>{count.scope}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="report-details" open>
        <summary>
          Bounded evidence · {finding.examples.length} of {finding.example_total} example group(s)
        </summary>
        {finding.examples.map((example) => (
          <div key={example.label} className="report-example">
            <h4>{example.label}</h4>
            <p className="mono report-muted">Row IDs: {example.row_ids.join(', ') || '—'}</p>
            <dl className="report-kv report-kv--compact">
              {Object.entries(example.details).map(([key, detail]) => (
                <div key={key} className="report-kv__row">
                  <dt>{key}</dt>
                  <dd>{detail}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </details>
      <p>
        <strong>Recommended action:</strong> {finding.recommended_action}
      </p>
      <div className="report-two-col">
        <div>
          <h4>Limitations</h4>
          <ul>
            {finding.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>Assumptions</h4>
          <ul>
            {finding.assumptions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </article>
  )
}

function FindingsSection({ data }: { data: DossierFindings }) {
  if (!data.items.length) {
    return (
      <div className="report-callout report-callout--ok">
        <strong>No findings were produced by this audit.</strong>
        <p>
          That is not proof that the dataset or split is free of leakage. Inspect the
          not-evaluated list and the audit limitations before drawing a conclusion.
        </p>
      </div>
    )
  }
  return (
    <>
      <p className="report-muted">
        {integer(data.total)} finding(s), each with its own counts and denominators. Evidence is
        bounded to the examples stored in the audit run.
      </p>
      {data.items.map((finding) => (
        <FindingCard key={finding.rule_id} finding={finding} />
      ))}
    </>
  )
}

function ComparisonSection({ data }: { data: DossierComparison }) {
  return (
    <>
      <dl className="report-kv">
        <dt>Run id</dt>
        <dd className="mono">{data.run_id ?? '—'}</dd>
        <dt>Generated</dt>
        <dd className="mono">{data.generated_at_utc}</dd>
        <dt>Candidates</dt>
        <dd>{integer(data.rows.length)}</dd>
      </dl>
      <div className="report-table-wrap">
        <table className="report-table">
          <thead>
            <tr>
              <th scope="col">Strategy</th>
              <th scope="col">Kind</th>
              <th scope="col" className="num">
                Train
              </th>
              <th scope="col" className="num">
                Test
              </th>
              <th scope="col" className="num">
                Achieved test
              </th>
              <th scope="col" className="num">
                Duplicate test share
              </th>
              <th scope="col" className="num">
                Entity overlap
              </th>
              <th scope="col">Chronology</th>
              <th scope="col" className="num">
                Findings
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.strategy_id}>
                <th scope="row">{row.label}</th>
                <td>{row.kind}</td>
                <td className="num">{integer(row.train_rows)}</td>
                <td className="num">{integer(row.test_rows)}</td>
                <td className="num">{pct(row.achieved_test_fraction)}</td>
                <td className="num">{pct(row.exact_duplicate_test_share)}</td>
                <td className="num">{pct(row.entity_overlap_test_share)}</td>
                <td>{row.chronology_status ?? '—'}</td>
                <td className="num">
                  {integer(Object.values(row.finding_counts).reduce((sum, count) => sum + count, 0))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="report-callout">
        <p>{data.selection_note}</p>
      </div>
      <h3>Comparison limitations</h3>
      <ul>
        {data.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </>
  )
}

function StatisticalModelCard({ model }: { model: DossierStatisticalModel }) {
  return (
    <article className="report-model">
      <header>
        <div>
          <span className="report-label">Statistical model</span>
          <h3>{model.label || model.run_id}</h3>
        </div>
        <p className="mono report-muted">{model.run_id}</p>
      </header>
      <dl className="report-kv">
        <dt>Formula</dt>
        <dd className="mono">{model.specification.formula}</dd>
        <dt>Task</dt>
        <dd>{model.specification.task_label}</dd>
        <dt>Analysed rows</dt>
        <dd>
          {integer(model.population.analyzed)} of {integer(model.population.rows_total)} ·{' '}
          {integer(model.population.excluded)} excluded
        </dd>
        <dt>Fit</dt>
        <dd>
          {model.fit.method} · R² {number(model.fit.r_squared ?? null)} · adjusted R²{' '}
          {number(model.fit.adjusted_r_squared ?? null)} · AIC {number(model.fit.aic ?? null)}
        </dd>
        <dt>Condition number</dt>
        <dd>{number(model.diagnostics.condition_number)}</dd>
      </dl>
      <div className="report-table-wrap">
        <table className="report-table">
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
                95% low
              </th>
              <th scope="col" className="num">
                95% high
              </th>
              <th scope="col" className="num">
                p-value
              </th>
            </tr>
          </thead>
          <tbody>
            {model.coefficients.map((coefficient) => (
              <tr key={coefficient.term}>
                <th scope="row" className="mono">
                  {coefficient.term}
                </th>
                <td className="num">{number(coefficient.estimate)}</td>
                <td className="num">{number(coefficient.std_error)}</td>
                <td className="num">{number(coefficient.ci_low)}</td>
                <td className="num">{number(coefficient.ci_high)}</td>
                <td className="num">{number(coefficient.p_value, 4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {model.warnings.length ? (
        <>
          <h4>Warnings</h4>
          <ul>
            {model.warnings.map((warning) => (
              <li key={`${warning.code}-${warning.message}`}>{warning.message}</li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="report-note">{model.note}</p>
    </article>
  )
}

function PredictiveModelCard({ model }: { model: DossierPredictiveModel }) {
  const metrics = model.evaluation.metrics
  const metricRows = [
    ['Accuracy', metrics.accuracy],
    ['Balanced accuracy', metrics.balanced_accuracy],
    ['ROC AUC', metrics.roc_auc],
    ['Average precision', metrics.average_precision],
    ['Prevalence', metrics.prevalence],
    ['MAE', metrics.mae],
    ['RMSE', metrics.rmse],
    ['R²', metrics.r2],
  ].filter(([, metricValue]) => metricValue !== undefined)
  const subgroupRows = model.subgroups?.rows ?? []
  return (
    <article className="report-model">
      <header>
        <div>
          <span className="report-label">Predictive model</span>
          <h3>{model.label || model.run_id}</h3>
        </div>
        <p className="mono report-muted">{model.run_id}</p>
      </header>
      <dl className="report-kv">
        <dt>Outcome</dt>
        <dd>{model.specification.outcome}</dd>
        <dt>Selected model</dt>
        <dd>{model.selected.label}</dd>
        <dt>Split</dt>
        <dd>
          {model.split.source} · {integer(model.split.partitions.fit)} fit /{' '}
          {integer(model.split.partitions.validation)} validation /{' '}
          {integer(model.split.partitions.test)} test
        </dd>
        <dt>Held-out rows</dt>
        <dd>{integer(model.evaluation.n)}</dd>
        <dt>Validation rule</dt>
        <dd>{model.specification.selection_rule}</dd>
      </dl>
      <h4>Held-out metrics</h4>
      <div className="report-table-wrap">
        <table className="report-table report-table--narrow">
          <thead>
            <tr>
              <th scope="col">Metric</th>
              <th scope="col" className="num">
                Value
              </th>
            </tr>
          </thead>
          <tbody>
            {metricRows.map(([label, metricValue]) => (
              <tr key={String(label)}>
                <th scope="row">{label}</th>
                <td className="num">{number(metricValue as number | undefined, 4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>Diagnostics</h4>
      <ul>
        <li>
          Calibration summary:{' '}
          {model.diagnostics.calibration_summary
            ? `Brier ${number(model.diagnostics.calibration_summary.brier_score, 4)} · ECE ${number(
                model.diagnostics.calibration_summary.expected_calibration_error,
                4,
              )}`
            : 'not available for this task'}
        </li>
        <li>
          Q–Q diagnostic:{' '}
          {model.diagnostics.qq?.applicable
            ? 'available in the Model Lab run'
            : model.diagnostics.qq?.reason ?? 'not applicable'}
        </li>
        <li>
          Influence diagnostic:{' '}
          {model.diagnostics.influence.applicable
            ? `${model.diagnostics.influence.n ?? 0} test rows reviewed`
            : model.diagnostics.influence.reason ?? 'not applicable'}
        </li>
        <li>
          Permutation importance:{' '}
          {model.diagnostics.permutation_importance.applicable
            ? `${model.diagnostics.permutation_importance.rows?.length ?? 0} predictors ranked on the ${
                model.diagnostics.permutation_importance.partition ?? 'test'
              } partition`
            : model.diagnostics.permutation_importance.reason ?? 'not applicable'}
        </li>
      </ul>
      {subgroupRows.length ? (
        <>
          <h4>Subgroup caveats</h4>
          <div className="report-table-wrap">
            <table className="report-table">
              <thead>
                <tr>
                  <th scope="col">Group</th>
                  <th scope="col" className="num">
                    n
                  </th>
                  <th scope="col" className="num">
                    Metric
                  </th>
                  <th scope="col" className="num">
                    95% low
                  </th>
                  <th scope="col" className="num">
                    95% high
                  </th>
                  <th scope="col">Caveat</th>
                </tr>
              </thead>
              <tbody>
                {subgroupRows.map((row) => (
                  <tr key={row.group}>
                    <th scope="row">{row.group}</th>
                    <td className="num">{integer(row.n)}</td>
                    <td className="num">{number(row.metric, 4)}</td>
                    <td className="num">{number(row.ci_low, 4)}</td>
                    <td className="num">{number(row.ci_high, 4)}</td>
                    <td>{row.warning ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {model.subgroups?.comparison_note ? (
            <p className="report-note">{model.subgroups.comparison_note}</p>
          ) : null}
        </>
      ) : null}
      {model.warnings.length ? (
        <>
          <h4>Warnings</h4>
          <ul>
            {model.warnings.map((warning) => (
              <li key={`${warning.code}-${warning.message}`}>{warning.message}</li>
            ))}
          </ul>
        </>
      ) : null}
      <p className="report-note">{model.note}</p>
    </article>
  )
}

function ModelsSection({ data }: { data: DossierModels }) {
  return (
    <>
      <p className="report-muted">
        {integer(data.total)} model run(s) selected. Metrics are shown only for the partition named
        by the run; this report does not re-fit or re-evaluate anything.
      </p>
      {data.runs.map((model) => {
        if (model.kind === 'statistical_model') {
          return <StatisticalModelCard key={model.run_id} model={model as DossierStatisticalModel} />
        }
        if (model.kind === 'prediction_model') {
          return <PredictiveModelCard key={model.run_id} model={model as DossierPredictiveModel} />
        }
        return (
          <article key={model.run_id} className="report-model">
            <h3>{model.label || model.run_id}</h3>
            <p className="report-muted">
              {'note' in model ? model.note : 'This run kind is not summarised.'}
            </p>
          </article>
        )
      })}
    </>
  )
}

function LimitationsSection({ data }: { data: DossierLimitations }) {
  return (
    <>
      <h3>Audit limitations</h3>
      <ul>{data.audit_limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      <h3>Audit assumptions</h3>
      <ul>{data.audit_assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
      <h3>Comparison limitations</h3>
      {data.comparison_limitations.length ? (
        <ul>{data.comparison_limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      ) : (
        <p className="report-muted">No comparison run is included.</p>
      )}
      <h3>Dataset and profile warnings</h3>
      {data.dataset_warnings.length || data.profile_warnings.length ? (
        <ul>
          {[...data.dataset_warnings, ...data.profile_warnings].map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="report-muted">No dataset or profile warnings were recorded.</p>
      )}
      <h3>Model warnings</h3>
      {data.model_warnings.length ? (
        <ul>
          {data.model_warnings.map((entry) => (
            <li key={entry.run_id}>
              <span className="mono">{entry.run_id}</span> —{' '}
              {entry.warnings.map((warning) => warning.message).join(' ')}
            </li>
          ))}
        </ul>
      ) : (
        <p className="report-muted">No model warnings were recorded for the included runs.</p>
      )}
      <h3>Not evaluated</h3>
      {data.not_evaluated.length ? (
        <ul>
          {data.not_evaluated.map((check) => (
            <li key={check.rule_id}>
              <span className="mono">{check.rule_id}</span> — {check.reason}
            </li>
          ))}
        </ul>
      ) : (
        <p className="report-muted">No not-evaluated checks were recorded.</p>
      )}
      <h3>General scope</h3>
      <ul>{data.general.map((item) => <li key={item}>{item}</li>)}</ul>
    </>
  )
}

function ReproducibilitySection({ data }: { data: DossierReproducibility }) {
  return (
    <>
      <dl className="report-kv">
        <dt>Report schema</dt>
        <dd className="mono">{data.report_schema_version}</dd>
        <dt>Application</dt>
        <dd>
          {data.app.name} {data.app.version}
        </dd>
        <dt>Generated</dt>
        <dd className="mono">{data.generated_at_utc}</dd>
        <dt>Dataset id</dt>
        <dd className="mono">{data.dataset_id}</dd>
        <dt>Dataset SHA-256</dt>
        <dd className="mono report-break">{data.dataset_sha256}</dd>
        <dt>Rows × columns</dt>
        <dd>
          {integer(data.row_count)} × {integer(data.column_count)}
        </dd>
        <dt>Audit run</dt>
        <dd className="mono">{data.audit_run_id ?? 'not included'}</dd>
        <dt>Comparison run</dt>
        <dd className="mono">{data.comparison_run_id ?? 'not included'}</dd>
        <dt>Model runs</dt>
        <dd className="mono">{data.model_run_ids.join(', ') || 'not included'}</dd>
      </dl>
      <p>{data.deterministic_note}</p>
      <p className="report-note">{data.storage_note}</p>
    </>
  )
}

const RENDERERS: Record<string, (section: DossierSection) => ReactNode> = {
  summary: (section) => <SummarySection summary={section.data as DossierSummary} />,
  provenance: (section) => <ProvenanceSection data={section.data as DossierProvenance} />,
  study: (section) => <StudySection data={section.data as DossierStudy} />,
  audit: (section) => <AuditSection data={section.data as DossierAudit} />,
  scorecard: (section) => <ScorecardSection data={section.data as RiskScorecard} />,
  findings: (section) => <FindingsSection data={section.data as DossierFindings} />,
  comparison: (section) => <ComparisonSection data={section.data as DossierComparison} />,
  models: (section) => <ModelsSection data={section.data as DossierModels} />,
  limitations: (section) => <LimitationsSection data={section.data as DossierLimitations} />,
  reproducibility: (section) => (
    <ReproducibilitySection data={section.data as DossierReproducibility} />
  ),
}

export function ReportPreview({ report }: { report: DossierReport }) {
  const sections = report.included_sections
    .map((id) => report.sections[id])
    .filter((section): section is DossierSection => Boolean(section))
  return (
    <article className="report-paper" id="report-paper" aria-label="Evidence dossier preview">
      <header className="report-cover">
        <p className="report-eyebrow">
          Evidence dossier · {report.schema_version} · {report.app.name} {report.app.version}
        </p>
        <h1>{report.dataset.name}</h1>
        <p className="report-cover__lede">
          {report.summary.objective ??
            'A structured review of the audited split, its evidence and the analyses that were actually run.'}
        </p>
        <div className="report-cover__meta">
          <span>
            {integer(report.dataset.row_count)} rows × {integer(report.dataset.column_count)} columns
          </span>
          <span className="mono report-break">SHA-256 {report.dataset.sha256}</span>
          <span className="mono">{report.generated_at_utc}</span>
          <span>{report.dataset.is_synthetic ? 'Synthetic demonstration' : 'Uploaded data'}</span>
        </div>
        <nav className="report-toc" aria-label="Dossier sections">
          {sections.map((section) => (
            <a
              key={section.id}
              href={`#report-${section.id}`}
              onClick={(event) => {
                // SplitScope routes on the URL hash; a raw `#report-…` link
                // would be read as a route change instead of an in-page jump.
                // Scroll the section directly so the contents link works in
                // the app without changing the active workspace route.
                event.preventDefault()
                document.getElementById(`report-${section.id}`)?.scrollIntoView({
                  block: 'start',
                  behavior: 'auto',
                })
              }}
            >
              {section.title}
            </a>
          ))}
        </nav>
      </header>

      <div className="report-body">
        {sections.map((section) => (
          <SectionShell key={section.id} section={section}>
            {RENDERERS[section.id]?.(section)}
          </SectionShell>
        ))}
      </div>

      <footer className="report-footer">
        <strong>Evidence integrity.</strong> {report.integrity.note}
        <p>
          SplitScope audits splits, not models. Findings are evidence about the selected split, never
          a guarantee that data is safe or that a model will perform. This dossier is not a causal
          analysis, an IRB approval or a consent record.
        </p>
      </footer>
    </article>
  )
}
