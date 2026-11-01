/**
 * Audit results.
 *
 * Three things are deliberately kept visually separate:
 *   1. Findings the enabled checks produced, with their evidence.
 *   2. Checks that did not run, with the reason the engine gave.
 *   3. Supporting distribution diagnostics, which are not findings.
 *
 * Severity buckets are never combined into a single score.
 */

import { useMemo, useState } from 'react'

import { FindingCard } from '../components/FindingCard'
import { BarPairChart, categoriesToBars, histogramToBars } from '../components/charts'
import { Badge, Callout, Card, EmptyState, Stat, StatusBadge, Table } from '../components/ui'
import type { CheckStatus, Severity } from '../api/types'
import {
  SEVERITY_ORDER,
  humanDuration,
  integer,
  number,
  percent,
  pluralise,
  severityLabel,
} from '../lib/format'
import type { ViewId } from '../lib/router'
import { settingsForRule } from '../lib/explain'
import { readiness } from '../lib/readiness'
import { useApp } from '../state/AppState'

export function AuditView({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const {
    audit,
    dataset,
    roles,
    validation,
    validationPending,
    suggestionsConfirmed,
    splitMode,
    generateSplit,
    selectFinding,
    runAudit,
    download,
    busyLabel,
  } = useApp()
  const [severities, setSeverities] = useState<Severity[]>([])
  const [rules, setRules] = useState<string[]>([])
  const [showDiagnostics, setShowDiagnostics] = useState(false)

  // The Results view must never offer a run whose prerequisites are missing;
  // the same derivation that gates the Data view gates this button.
  const ready = dataset
    ? readiness({
        roles,
        validation,
        validationPending,
        suggestionsConfirmed,
        splitMode,
        generate: generateSplit,
        columnTypes: dataset.column_types,
      })
    : null

  const findings = audit?.result.findings ?? []

  const ruleOptions = useMemo(() => {
    const seen = new Map<string, { ruleId: string; title: string; count: number }>()
    for (const outcome of audit?.result.rule_outcomes ?? []) {
      seen.set(outcome.rule_id, {
        ruleId: outcome.rule_id,
        title: outcome.title,
        count: outcome.findings.length,
      })
    }
    return [...seen.values()]
  }, [audit])

  const visible = findings.filter((finding) => {
    if (severities.length && !severities.includes(finding.severity)) return false
    if (rules.length && !rules.includes(finding.rule_id)) return false
    return true
  })

  if (!audit) {
    return (
      <Card title="Audit results">
        <EmptyState
          title="No audit has been run in this session"
          action={
            ready?.ready ? (
              <>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={busyLabel !== null}
                  onClick={async () => {
                    await runAudit()
                  }}
                >
                  Run the audit now
                </button>{' '}
                <button type="button" className="btn" onClick={() => onNavigate('dataset')}>
                  Review the setup
                </button>
              </>
            ) : (
              <button type="button" className="btn btn--primary" onClick={() => onNavigate('dataset')}>
                Finish the dataset setup first
              </button>
            )
          }
        >
          {!dataset
            ? 'Load a dataset or demo first.'
            : ready && ready.ready
              ? `${dataset.dataset.name} is set up: ${ready.splitDescription}. Running the audit applies every enabled check to that split and returns findings, skipped checks and diagnostics.`
              : `${dataset.dataset.name} is loaded, but the setup is not finished yet. What still needs an answer:`}
          {ready && ready.blockers.length ? (
            <ul className="list-tight" style={{ marginTop: 8, marginBottom: 0 }}>
              {ready.blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          ) : null}
        </EmptyState>
      </Card>
    )
  }

  const { result } = audit
  const diagnostics = result.diagnostics

  // Run-level context for the "Technical details" explanation level: the
  // columns the audit resolved, the settings that applied to each rule, that
  // rule's recorded metrics, and the checks that did not run in this run.
  const technicalColumns = [
    {
      label: 'Target',
      value: result.resolved_roles.target_column ?? 'no target column selected',
    },
    {
      label: 'Entity',
      value: result.resolved_roles.entity_column ?? 'no entity column selected',
    },
    {
      label: 'Timestamp',
      value: result.resolved_roles.timestamp_column ?? 'no timestamp column selected',
    },
    {
      label: 'Split',
      value: result.split.split_column
        ? `${result.split.split_column} (train = ${result.split.train_value}, test = ${result.split.test_value})`
        : 'derived by the strategy (not a data column)',
    },
    {
      label: 'Features',
      value: result.resolved_roles.feature_columns.join(', ') || 'none selected',
    },
  ]

  const technicalFor = (ruleId: string) => ({
    columns: technicalColumns,
    settings: settingsForRule(ruleId, result.audit_config),
    metrics: result.rule_outcomes.find((outcome) => outcome.rule_id === ruleId)?.metrics ?? [],
    notRun: result.evaluation.not_evaluated,
  })

  // A plain-language summary built from the structured counts. The backend
  // headline exists too, but its "1 finding(s)" phrasing reads like a debug
  // string; the counts themselves are never aggregated or scored.
  const evaluatedCount = result.evaluation.evaluated_rule_ids.length
  const notRunCount = result.evaluation.not_evaluated.length
  const notRunSentence = notRunCount
    ? ` ${integer(notRunCount)} ${pluralise(notRunCount, 'check')} did not run and ${
        notRunCount === 1 ? 'is' : 'are'
      } listed separately below.`
    : ''
  const severitySummary = SEVERITY_ORDER.filter(
    (severity) => result.evaluation.findings_by_severity[severity],
  )
    .map(
      (severity) =>
        `${result.evaluation.findings_by_severity[severity]} ${severityLabel(
          severity,
        ).toLowerCase()}`,
    )
    .join(', ')
  const headline = result.findings.length
    ? `${integer(result.findings.length)} ${pluralise(
        result.findings.length,
        'finding',
      )} across ${integer(evaluatedCount)} ${pluralise(evaluatedCount, 'check')}: ${
        severitySummary
      }.${notRunSentence}`
    : `No findings from ${integer(evaluatedCount)} enabled ${pluralise(
        evaluatedCount,
        'check',
      )}.${notRunSentence}`

  return (
    <div className="stack">
      <Card
        title="Audit summary"
        actions={
          <button
            type="button"
            className="btn btn--small"
            disabled={busyLabel !== null}
            onClick={() => void runAudit()}
          >
            Re-run with current settings
          </button>
        }
      >
        <Callout tone={result.findings.length ? 'warn' : 'ok'} title={headline}>
          {result.findings.length
            ? 'Read each finding with its counts and limitations before drawing a conclusion. A finding is evidence about this split and this configuration, not a verdict on the dataset.'
            : 'Only the enabled checks ran. This result says nothing about leakage types outside the supported set, and nothing about model performance.'}
        </Callout>

        <div className="grid-3">
          <Stat
            label="Findings"
            value={integer(result.evaluation.findings_total)}
            hint={SEVERITY_ORDER.filter((severity) => result.evaluation.findings_by_severity[severity])
              .map(
                (severity) =>
                  `${severityLabel(severity)}: ${result.evaluation.findings_by_severity[severity]}`,
              )
              .join(' · ') || 'None'}
          />
          <Stat
            label="Checks evaluated"
            value={`${result.evaluation.evaluated_rule_ids.length} of ${
              result.evaluation.evaluated_rule_ids.length + result.evaluation.not_evaluated.length
            }`}
            hint={
              result.evaluation.not_evaluated.length
                ? `${integer(result.evaluation.not_evaluated.length)} did not run`
                : 'Every applicable check ran'
            }
          />
          <Stat
            label="Audit duration"
            value={humanDuration(result.duration_ms)}
            hint="How long the checks took to run"
          />
        </div>

        <div className="kv" style={{ marginTop: 12 }}>
          <dt>Split audited</dt>
          <dd>{result.split.label}</dd>
          <dt>Train / test</dt>
          <dd>
            {integer(result.split.train_rows)} / {integer(result.split.test_rows)} rows · achieved test
            fraction {percent(result.split.achieved_test_fraction)}
            {result.split.requested_test_fraction !== null
              ? ` (requested ${percent(result.split.requested_test_fraction)})`
              : ''}
          </dd>
          <dt>Split column</dt>
          <dd className="mono">
            {result.split.split_column
              ? `${result.split.split_column}: ${result.split.train_value} → train, ${result.split.test_value} → test`
              : '—'}
          </dd>
          {result.split.seed !== null ? (
            <>
              <dt>Seed</dt>
              <dd className="mono">{result.split.seed}</dd>
            </>
          ) : null}
          {audit.assignment ? (
            <>
              <dt>Row assignment</dt>
              <dd>
                <span className="small">
                  {audit.assignment.label}: every row's side, as the audit used it.{' '}
                </span>
                <button
                  type="button"
                  className="btn btn--small"
                  disabled={busyLabel !== null}
                  onClick={() => void download(audit.assignment?.download_path ?? '')}
                >
                  Download split assignment CSV
                </button>
              </dd>
            </>
          ) : null}
          <dt>Column roles used</dt>
          <dd className="small">
            {result.resolved_roles.feature_columns.length}{' '}
            {pluralise(result.resolved_roles.feature_columns.length, 'feature')} · Target:{' '}
            {result.resolved_roles.target_column ?? 'none'} · Entity:{' '}
            {result.resolved_roles.entity_column ?? 'none'} · Timestamp:{' '}
            {result.resolved_roles.timestamp_column ?? 'none'} ·{' '}
            {result.resolved_roles.metadata_excluded.length}{' '}
            {pluralise(result.resolved_roles.metadata_excluded.length, 'metadata column')} excluded
          </dd>
        </div>

        <p className="small" style={{ marginTop: 12, marginBottom: 0 }}>
          <span className="muted">Next steps:</span>{' '}
          <button type="button" className="btn btn--primary btn--small" onClick={() => onNavigate('comparison')}>
            Compare other ways to split this data
          </button>{' '}
          <button type="button" className="btn btn--small" onClick={() => onNavigate('dataset')}>
            Review or adjust configuration
          </button>{' '}
          <button type="button" className="btn btn--small" onClick={() => onNavigate('export')}>
            Export a report
          </button>{' '}
          <button type="button" className="btn btn--ghost btn--small" onClick={() => onNavigate('overview')}>
            Try another demo
          </button>
        </p>

        <details className="disclosure" style={{ marginTop: 8 }}>
          <summary>Technical details of this run</summary>
          <div className="kv">
            <dt>Run id</dt>
            <dd className="mono tiny">{audit.run_id}</dd>
            <dt>Split kind</dt>
            <dd className="mono tiny">{result.split.kind}</dd>
            {result.split.strategy_id ? (
              <>
                <dt>Strategy id</dt>
                <dd className="mono tiny">{result.split.strategy_id}</dd>
              </>
            ) : null}
            <dt>Generated</dt>
            <dd>{result.generated_at_utc}</dd>
            <dt>Schema / app version</dt>
            <dd className="tiny">
              {result.schema_version} / {result.app_version}
            </dd>
            <dt>Input fingerprint</dt>
            <dd className="mono tiny break">{result.dataset.fingerprint_sha256}</dd>
          </div>
          {result.split.proportion_note ? (
            <p className="small muted">{result.split.proportion_note}</p>
          ) : null}
          {result.split.notes.length ? (
            <ul className="list-tight small">
              {result.split.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </details>
      </Card>

      <Card title={`Findings and check outcomes (${findings.length})`}>
        <details className="disclosure" style={{ marginBottom: 12 }}>
          <summary>Filter findings</summary>
          <div className="filters">
            <span className="small muted">Severity:</span>
            {SEVERITY_ORDER.map((severity) => {
              const on = severities.includes(severity)
              const count = result.evaluation.findings_by_severity[severity] ?? 0
              return (
                <label key={severity} className={`filter-chip${on ? ' filter-chip--on' : ''}`}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() =>
                      setSeverities((current) =>
                        current.includes(severity)
                          ? current.filter((item) => item !== severity)
                          : [...current, severity],
                      )
                    }
                  />
                  {severityLabel(severity)} ({count})
                </label>
              )
            })}
            <span className="small muted" style={{ marginLeft: 8 }}>
              Check:
            </span>
            {ruleOptions.map((option) => {
              const on = rules.includes(option.ruleId)
              return (
                <label key={option.ruleId} className={`filter-chip${on ? ' filter-chip--on' : ''}`}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() =>
                      setRules((current) =>
                        current.includes(option.ruleId)
                          ? current.filter((item) => item !== option.ruleId)
                          : [...current, option.ruleId],
                      )
                    }
                  />
                  {option.title} ({option.count})
                </label>
              )
            })}
            {severities.length || rules.length ? (
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => {
                  setSeverities([])
                  setRules([])
                }}
              >
                Clear filters
              </button>
            ) : null}
          </div>
        </details>

        <div className="stack">
          {visible.map((finding) => (
            <FindingCard
              key={finding.rule_id + finding.title}
              finding={finding}
              contextLabel={result.split.achieved_test_fraction !== null ? result.split.label : 'audit'}
              technical={technicalFor(finding.rule_id)}
              onOpenEvidence={() => {
                selectFinding(finding, 'audit', result.split.label)
                onNavigate('evidence')
              }}
            />
          ))}
        </div>
        {!visible.length ? (
          <EmptyState title={findings.length ? 'No findings match the filters' : 'No findings'}>
            {findings.length
              ? 'Clear or widen the filters to see the rest.'
              : 'The enabled checks found no supported issue in this configuration. That is not a statement that the data is safe.'}
          </EmptyState>
        ) : null}

        <details className="disclosure">
          <summary>Check-by-check outcome (technical)</summary>
          <Table
            caption="Every check the engine considered, including the ones that did not run. “Not evaluated” is never the same as “clean”."
            head={
              <tr>
                <th scope="col">Check</th>
                <th scope="col">Status</th>
                <th scope="col" className="num">
                  Findings
                </th>
                <th scope="col" className="num">
                  Time
                </th>
                <th scope="col">Reason / key numbers</th>
              </tr>
            }
          >
            {result.rule_outcomes.map((outcome) => (
              <tr key={outcome.rule_id}>
                <th scope="row">
                  {outcome.title}
                  <span className="hint mono">{outcome.rule_id}</span>
                </th>
                <td>
                  <StatusBadge status={outcome.status as CheckStatus} />
                </td>
                <td className="num">{outcome.findings.length}</td>
                <td className="num">{humanDuration(outcome.duration_ms)}</td>
                <td className="small">
                  {outcome.not_evaluated ? (
                    <span>{outcome.not_evaluated.reason}</span>
                  ) : outcome.metrics.length ? (
                    <ul className="list-tight" style={{ margin: 0 }}>
                      {outcome.metrics.map((metric) => (
                        <li key={metric.key}>
                          {metric.label}: <span className="mono">{String(metric.value)}</span>
                          {metric.unit ? ` ${metric.unit}` : ''}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <span className="muted">No metrics recorded.</span>
                  )}
                </td>
              </tr>
            ))}
          </Table>
        </details>
      </Card>

      {result.evaluation.not_evaluated.length ? (
        <Card title={`Checks that did not run (${result.evaluation.not_evaluated.length})`}>
          <Callout tone="warn" title="These are not passing results">
            A check appears here because a role was missing, a documented minimum was not met, or the
            check was disabled. Read the reason; do not read the blank as a clean bill of health.
          </Callout>
          <Table
            head={
              <tr>
                <th scope="col">Check</th>
                <th scope="col">Status</th>
                <th scope="col">Reason</th>
                <th scope="col">Details</th>
              </tr>
            }
          >
            {result.evaluation.not_evaluated.map((check) => (
              <tr key={check.rule_id}>
                <th scope="row">
                  {check.title}
                  <span className="hint mono">{check.rule_id}</span>
                </th>
                <td>
                  <StatusBadge status={check.status} />
                </td>
                <td className="small">{check.reason}</td>
                <td className="small">
                  {Object.keys(check.details).length ? (
                    <dl className="evidence-details">
                      {Object.entries(check.details).map(([key, value]) => (
                        <div key={key} style={{ display: 'contents' }}>
                          <dt>{key}</dt>
                          <dd>{value}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    '—'
                  )}
                </td>
              </tr>
            ))}
          </Table>
        </Card>
      ) : null}

      <Card
        title="Supporting distribution diagnostics"
        actions={
          <button
            type="button"
            className="btn btn--small"
            aria-expanded={showDiagnostics}
            onClick={() => setShowDiagnostics((value) => !value)}
          >
            {showDiagnostics ? 'Hide' : 'Show'}
          </button>
        }
      >
        <Callout tone="info" title="Diagnostics are not findings">
          {diagnostics.disclaimer} A distribution shift or a class imbalance is a property of the
          split, not automatically leakage. Nothing on this panel changes the findings above.
        </Callout>
        {showDiagnostics ? (
          <>
            <div className="grid-3">
              <Stat label="Train rows" value={integer(diagnostics.counts.train_rows)} />
              <Stat label="Test rows" value={integer(diagnostics.counts.test_rows)} />
              <Stat label="Total rows" value={integer(diagnostics.counts.total_rows)} />
            </div>

            {diagnostics.target ? (
              <>
                <h3>Target column: {diagnostics.target.column}</h3>
                <p className="small muted">{diagnostics.target.note}</p>
                {diagnostics.target.kind === 'categorical' ? (
                  <>
                    <BarPairChart
                      title={`Target proportions in ${diagnostics.target.column}`}
                      description="Share of each split’s rows falling in each category. Shown as proportions because the two splits differ in size."
                      data={categoriesToBars(diagnostics.target.categories)}
                    />
                    <Table
                      head={
                        <tr>
                          <th scope="col">Category</th>
                          <th scope="col" className="num">
                            Train count
                          </th>
                          <th scope="col" className="num">
                            Train share
                          </th>
                          <th scope="col" className="num">
                            Test count
                          </th>
                          <th scope="col" className="num">
                            Test share
                          </th>
                          <th scope="col" className="num">
                            Absolute gap
                          </th>
                        </tr>
                      }
                    >
                      {diagnostics.target.categories.map((category) => (
                        <tr key={category.category}>
                          <th scope="row">
                            {category.category === '' ? '(empty)' : category.category}
                            {category.is_other_bucket ? (
                              <Badge tone="neutral">aggregated</Badge>
                            ) : null}
                          </th>
                          <td className="num">{integer(category.train_count)}</td>
                          <td className="num">{percent(category.train_ratio)}</td>
                          <td className="num">{integer(category.test_count)}</td>
                          <td className="num">{percent(category.test_ratio)}</td>
                          <td className="num">{percent(Math.abs(category.ratio_gap))}</td>
                        </tr>
                      ))}
                    </Table>
                  </>
                ) : diagnostics.target.kind === 'continuous' ? (
                  <>
                    <BarPairChart
                      title={`Target distribution in ${diagnostics.target.column}`}
                      description="Share of each split’s rows per histogram bin. Bin edges are chosen over the combined train and test values; each unique value is not treated as a class."
                      data={histogramToBars(
                        diagnostics.target.histogram_edges,
                        diagnostics.target.train_histogram,
                        diagnostics.target.test_histogram,
                        diagnostics.counts.train_rows,
                        diagnostics.counts.test_rows,
                      )}
                    />
                    <Table
                      head={
                        <tr>
                          <th scope="col">Statistic</th>
                          <th scope="col" className="num">
                            Train
                          </th>
                          <th scope="col" className="num">
                            Test
                          </th>
                          <th scope="col" className="num">
                            Difference
                          </th>
                        </tr>
                      }
                    >
                      {Object.keys(diagnostics.target.train_stats).map((key) => {
                        const trainValue = diagnostics.target?.train_stats[key] ?? 0
                        const testValue = diagnostics.target?.test_stats[key] ?? 0
                        return (
                          <tr key={key}>
                            <th scope="row">{key}</th>
                            <td className="num">{number(trainValue)}</td>
                            <td className="num">{number(testValue)}</td>
                            <td className="num">{number(testValue - trainValue)}</td>
                          </tr>
                        )
                      })}
                    </Table>
                  </>
                ) : (
                  <p className="small muted">No distribution summary is available for this target.</p>
                )}
              </>
            ) : (
              <EmptyState title="No target column selected">
                Select a target to see its train/test distribution. The diagnostics are descriptive
                only.
              </EmptyState>
            )}

            <h3>Missingness by column</h3>
            <p className="small muted">{diagnostics.missingness_note}</p>
            <Table
              caption="Columns are ordered by the size of the train/test missingness gap."
              head={
                <tr>
                  <th scope="col">Column</th>
                  <th scope="col" className="num">
                    Train missing
                  </th>
                  <th scope="col" className="num">
                    Train %
                  </th>
                  <th scope="col" className="num">
                    Test missing
                  </th>
                  <th scope="col" className="num">
                    Test %
                  </th>
                  <th scope="col" className="num">
                    Gap (pp)
                  </th>
                </tr>
              }
            >
              {diagnostics.missingness.map((row) => (
                <tr key={row.column}>
                  <th scope="row" className="mono tiny">
                    {row.column}
                  </th>
                  <td className="num">{integer(row.train_missing)}</td>
                  <td className="num">{percent(row.train_missing_ratio)}</td>
                  <td className="num">{integer(row.test_missing)}</td>
                  <td className="num">{percent(row.test_missing_ratio)}</td>
                  <td className="num">{percent(Math.abs(row.missing_ratio_gap))}</td>
                </tr>
              ))}
            </Table>
          </>
        ) : null}
      </Card>

      <details className="disclosure">
        <summary>Limitations and assumptions recorded with this result</summary>
        <ul className="list-tight">
          {result.limitations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <h3>Assumptions</h3>
        <ul className="list-tight">
          {result.assumptions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
