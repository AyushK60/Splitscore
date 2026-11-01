/**
 * Finding card with three explanation levels.
 *
 * Every finding can be read at three depths — Quick explanation (default),
 * More context, Technical details — through one accessible control. Exactly one
 * level is rendered at a time; the levels never repeat the same paragraph.
 *
 * Findings come from the backend verbatim: title, severity and its rationale,
 * description, counts with explicit denominators, a bounded example list, the
 * recommended action and the stated limitations. Nothing here is invented by the
 * UI and nothing is aggregated into a score. The level control only decides
 * which of the real values are on screen.
 */

import { useId, useState } from 'react'

import type { EvidenceExample, Finding, NotEvaluatedCheck, RuleMetric } from '../api/types'
import { integer, pluralise } from '../lib/format'
import {
  NOT_RUN_NOTE,
  getPersistedLevel,
  mechanismCopy,
  persistLevel,
  quickCountLine,
  whyCareCopy,
  type ExplanationLevel,
} from '../lib/explain'
import { SeverityBadge } from './ui'

/**
 * Optional run-level context for the technical level, supplied by the view that
 * holds the audit result. When absent (e.g. a bare rendering), the technical
 * level says so rather than guessing.
 */
export type FindingTechnical = {
  columns?: Array<{ label: string; value: string }>
  settings?: Array<{ label: string; value: string }>
  metrics?: RuleMetric[]
  notRun?: NotEvaluatedCheck[]
}

const LEVELS: Array<{ id: ExplanationLevel; label: string }> = [
  { id: 'quick', label: 'Quick explanation' },
  { id: 'context', label: 'More context' },
  { id: 'technical', label: 'Technical details' },
]

function ExampleBlock({ example, index }: { example: EvidenceExample; index: number }) {
  const entries = Object.entries(example.details)
  return (
    <div className="panel" style={{ marginTop: 8 }}>
      <p className="tiny muted" style={{ margin: 0 }}>
        Example {index + 1}: {example.label}
      </p>
      <p className="rowids" style={{ marginTop: 4 }}>
        <strong>row ids:</strong> {example.row_ids.join(', ')}
      </p>
      {entries.length ? (
        <dl className="evidence-details">
          {entries.map(([key, value]) => (
            <div key={key} style={{ display: 'contents' }}>
              <dt>{key}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  )
}

function CountsTable({ finding }: { finding: Finding }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Measure</th>
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
            <tr key={count.label}>
              <th scope="row" style={{ fontWeight: 500 }}>
                {count.label}
                {count.note ? (
                  <span className="hint" style={{ display: 'block' }}>
                    {count.note}
                  </span>
                ) : null}
              </th>
              <td className="num">{integer(count.affected)}</td>
              <td className="num">{count.denominator === 0 ? '—' : integer(count.denominator)}</td>
              <td>{count.unit}</td>
              <td className="small">{count.scope}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function FindingCard({
  finding,
  contextLabel,
  countsAsZero,
  technical,
  onOpenEvidence,
}: {
  finding: Finding
  contextLabel: string
  /** True when this finding was produced by a non-default configuration. */
  countsAsZero?: boolean
  /** Run-level columns/settings/metrics for the technical level. */
  technical?: FindingTechnical
  onOpenEvidence?: () => void
}) {
  const [open, setOpen] = useState(false)
  const [level, setLevel] = useState<ExplanationLevel>(() => getPersistedLevel())
  const bodyId = useId()
  const levelsId = useId()

  const chooseLevel = (next: ExplanationLevel) => {
    persistLevel(next)
    setLevel(next)
  }

  const whyCare = finding.severity_rationale || whyCareCopy(finding.rule_id)
  const firstExample = finding.examples[0]

  return (
    <article className={`finding finding--${finding.severity}`}>
      <div className="finding__summary">
        <button
          type="button"
          className="finding__toggle"
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen((value) => !value)}
        >
          <span className="finding__headline">{finding.title}</span>
          <span className="tiny muted" style={{ display: 'block', marginTop: 2 }}>
            {finding.rule_id} · {contextLabel}
          </span>
          {/* When collapsed this line is the finding's preview; once expanded,
              the Quick explanation opens with the same sentence, so it is shown
              once rather than twice. */}
          {open ? null : (
            <span className="small" style={{ display: 'block', marginTop: 4 }}>
              {finding.evidence_summary}
            </span>
          )}
        </button>
        <div className="row" style={{ alignItems: 'center', gap: 8 }}>
          <SeverityBadge severity={finding.severity} />
          <span className="chevron" aria-hidden="true">
            {open ? '▾' : '▸'}
          </span>
        </div>
      </div>

      {open ? (
        <div className="finding__body" id={bodyId}>
          <div className="segmented" role="group" aria-label="Explanation level" id={levelsId}>
            {LEVELS.map((option) => (
              <button
                key={option.id}
                type="button"
                className="segmented__option"
                aria-pressed={level === option.id}
                onClick={() => chooseLevel(option.id)}
              >
                <span className="segmented__dot" aria-hidden="true" />
                {option.label}
              </button>
            ))}
          </div>

          {level === 'quick' ? (
            <div className="explain" data-level="quick">
              <p className="explain__lede">{finding.evidence_summary}</p>
              <h4>Why this matters</h4>
              <p className="small" style={{ marginTop: 0 }}>
                {whyCare}
              </p>
              <ul className="explain__counts">
                {finding.counts.map((count) => (
                  <li key={count.label}>{quickCountLine(count)}</li>
                ))}
              </ul>
              <p className="tiny muted" style={{ margin: '8px 0 0' }}>
                “More context” explains the mechanism with an example from this finding and a next
                step. “Technical details” shows the rule id, the columns and settings used, and every
                count and metric behind it.
              </p>
            </div>
          ) : null}

          {level === 'context' ? (
            <div className="explain" data-level="context">
              <h4>How this happens</h4>
              <p className="small" style={{ marginTop: 0 }}>
                {mechanismCopy(finding.rule_id)}
              </p>

              <h4>An example from this finding</h4>
              {firstExample ? (
                <>
                  <ExampleBlock example={firstExample} index={0} />
                  {finding.examples.length > 1 ? (
                    <p className="tiny muted" style={{ marginBottom: 0 }}>
                      First of {finding.examples.length} attached examples — switch to “Technical
                      details” to see all of them.
                    </p>
                  ) : null}
                </>
              ) : (
                <p className="small muted" style={{ marginTop: 0 }}>
                  This finding reports counts only; no example rows are attached.
                </p>
              )}

              <h4>What you can try next</h4>
              <p className="small" style={{ marginTop: 0 }}>
                {finding.recommended_action}
              </p>

              {finding.limitations.length ? (
                <>
                  <h4>Limitations of this check</h4>
                  <ul className="list-tight small">
                    {finding.limitations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          ) : null}

          {level === 'technical' ? (
            <div className="explain" data-level="technical">
              <dl className="kv">
                <dt>Rule id</dt>
                <dd className="mono">{finding.rule_id}</dd>
                <dt>What was found</dt>
                <dd className="small">{finding.description}</dd>
                <dt>Evaluated columns</dt>
                <dd className="small">
                  {technical?.columns?.length
                    ? technical.columns.map((column) => `${column.label}: ${column.value}`).join(' · ')
                    : 'Column details were not recorded with this finding.'}
                </dd>
                <dt>Settings applied</dt>
                <dd className="small">
                  {technical?.settings?.length
                    ? technical.settings
                        .map((setting) => `${setting.label} = ${setting.value}`)
                        .join(' · ')
                    : 'No rule-specific settings were recorded for this view.'}
                </dd>
                <dt>Split audited</dt>
                <dd className="small">{contextLabel}</dd>
              </dl>

              <h4>Counting definitions</h4>
              <CountsTable finding={finding} />

              <h4>Metrics recorded by the check</h4>
              {technical?.metrics?.length ? (
                <ul className="list-tight small" style={{ marginTop: 0 }}>
                  {technical.metrics.map((metric) => (
                    <li key={metric.key}>
                      {`${metric.label}: ${
                        typeof metric.value === 'number' ? integer(metric.value) : metric.value
                      }${metric.unit ? ` ${metric.unit}` : ''}`}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="small muted" style={{ marginTop: 0 }}>
                  This run recorded no metrics for this check.
                </p>
              )}

              <h4>
                Evidence examples{' '}
                <span className="muted small" style={{ fontWeight: 400 }}>
                  ({finding.examples.length} of {integer(finding.example_total)} shown
                  {finding.examples_truncated ? ', truncated to the configured maximum' : ''})
                </span>
              </h4>
              {finding.examples.length === 0 ? (
                <p className="small muted">
                  This finding reports counts only; no example rows are attached.
                </p>
              ) : (
                finding.examples.map((example, index) => (
                  <ExampleBlock key={`${example.label}-${index}`} example={example} index={index} />
                ))
              )}

              <h4>Assumptions</h4>
              {finding.assumptions.length ? (
                <ul className="list-tight small">
                  {finding.assumptions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="small muted" style={{ marginTop: 0 }}>
                  None recorded for this check.
                </p>
              )}

              <h4>Limitations of this check</h4>
              {finding.limitations.length ? (
                <ul className="list-tight small">
                  {finding.limitations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="small muted" style={{ marginTop: 0 }}>
                  None recorded for this check.
                </p>
              )}

              <h4>Checks that did not run</h4>
              <p className="small" style={{ marginTop: 0 }}>
                {NOT_RUN_NOTE}
              </p>
              {technical?.notRun?.length ? (
                <ul className="list-tight small">
                  {technical.notRun.map((check) => (
                    <li key={check.rule_id}>
                      <strong>{check.title}</strong>{' '}
                      <span className="hint mono">{check.rule_id}</span> — {check.reason}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="tiny muted" style={{ marginTop: 0 }}>
                  They are listed on the results page under “Checks that did not run”, each with the
                  reason the engine gave.
                </p>
              )}

              {countsAsZero ? (
                <p className="tiny muted">
                  This finding came from a candidate split, not from the dataset’s existing split.
                </p>
              ) : null}
            </div>
          ) : null}

          {onOpenEvidence ? (
            <p style={{ marginBottom: 0 }}>
              <button type="button" className="btn btn--ghost" onClick={onOpenEvidence}>
                Open in evidence view →
              </button>
            </p>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

export function FindingSummaryLine({ findings }: { findings: Finding[] }) {
  if (!findings.length) {
    return <span className="muted">No findings from the enabled checks.</span>
  }
  const counts = findings.reduce<Record<string, number>>((accumulator, finding) => {
    accumulator[finding.severity] = (accumulator[finding.severity] ?? 0) + 1
    return accumulator
  }, {})
  return (
    <span>
      {findings.length} {pluralise(findings.length, 'finding')}:{' '}
      {(['high', 'medium', 'low', 'info'] as const)
        .filter((severity) => counts[severity])
        .map((severity) => `${counts[severity]} ${severity}`)
        .join(', ')}
    </span>
  )
}
