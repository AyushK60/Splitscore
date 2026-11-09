/**
 * F06 - category-based leakage risk scorecard.
 *
 * A category is either carrying findings, clean under the checks that ran, in
 * error, not applicable, or not checked - never a number. Every rule row keeps
 * its own state and reason, because "not checked" with a reason is evidence
 * while "green" would be a claim. Affected-row figures link to the findings
 * that carry the exact counts and denominators.
 */

import type { AuditResult, Finding, ScorecardCategory, ScorecardStatus } from '../api/types'
import { Card } from './ui'

const STATUS_LABEL: Record<ScorecardStatus, string> = {
  finding_present: 'Finding present',
  evaluated_no_finding: 'Evaluated - no finding',
  error: 'Error',
  not_applicable: 'Not applicable',
  not_checked: 'Not checked',
}

const SEVERITY_LABEL: Record<string, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
}

function statusTone(status: ScorecardStatus): string {
  switch (status) {
    case 'finding_present':
      return 'scorecard__status--finding'
    case 'evaluated_no_finding':
      return 'scorecard__status--clean'
    case 'error':
      return 'scorecard__status--error'
    default:
      return 'scorecard__status--unchecked'
  }
}

function affectedLabel(category: ScorecardCategory): string | null {
  if (category.status !== 'finding_present' || category.affected_rows === null) return null
  return `${category.affected_rows.toLocaleString('en-US')} row(s) - exact counts and denominators in the linked findings`
}

export function RiskScorecard({
  scorecard,
  findings,
  onOpenFinding,
}: {
  scorecard: NonNullable<AuditResult['risk_scorecard']>
  findings: Finding[]
  onOpenFinding?: (finding: Finding) => void
}) {
  return (
    <Card title="Risk scorecard by category">
      <p className="small muted" style={{ marginTop: 0 }}>
        {scorecard.note}
      </p>
      <div className="scorecard" role="table" aria-label="Risk scorecard by category">
        {scorecard.categories.map((category) => {
          const linked = findings.filter((finding) =>
            category.rules.some((rule) => rule.rule_id === finding.rule_id && rule.finding_count > 0),
          )
          const affected = affectedLabel(category)
          return (
            <section key={category.key} className="scorecard__row" role="row">
              <div className="scorecard__main">
                <span className="scorecard__label">{category.label}</span>
                <span className={`scorecard__status ${statusTone(category.status)}`}>
                  {STATUS_LABEL[category.status]}
                  {category.max_severity ? ` · ${SEVERITY_LABEL[category.max_severity]}` : ''}
                </span>
                {affected ? <span className="scorecard__affected">{affected}</span> : null}
              </div>
              <ul className="scorecard__rules">
                {category.rules.map((rule) => (
                  <li key={rule.rule_id} className="scorecard__rule">
                    <span className="mono tiny">{rule.rule_id}</span>
                    {rule.finding_count > 0 ? (
                      <span>
                        {rule.finding_count} finding(s)
                        {rule.max_severity ? ` · ${SEVERITY_LABEL[rule.max_severity]}` : ''}
                      </span>
                    ) : rule.not_evaluated_reason ? (
                      <span className="scorecard__reason">{rule.not_evaluated_reason}</span>
                    ) : (
                      <span className="scorecard__reason">{rule.status}</span>
                    )}
                  </li>
                ))}
              </ul>
              {linked.length > 0 && onOpenFinding ? (
                <div className="scorecard__links">
                  {linked.map((finding, index) => (
                    <button
                      key={`${finding.rule_id}-${index}`}
                      type="button"
                      className="btn btn--small"
                      onClick={() => onOpenFinding(finding)}
                    >
                      Open evidence: {finding.rule_id}
                    </button>
                  ))}
                </div>
              ) : null}
            </section>
          )
        })}
      </div>
    </Card>
  )
}
