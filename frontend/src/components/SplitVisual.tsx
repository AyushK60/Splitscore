/**
 * F05 — evidence-based split comparison visuals.
 *
 * Every mark is computed from the actual audited assignments and folds:
 * allocation bars from achieved train/test row counts, entity-overlap bars
 * from the entity-overlap shares the checks measured, fold strips from plan
 * fold facts, and risk-category rows from the finding counts per rule. Nothing
 * here ranks strategies or implies model performance — no such engine exists.
 */

import type { ComparisonResult, Finding } from '../api/types'
import { integer, percent } from '../lib/format'

/** Mirrors CATEGORY_BY_RULE in backend/app/audit/rules/__init__.py. */
const CATEGORY_BY_RULE: Record<string, string> = {
  'SS-DUP-001': 'duplicate',
  'SS-NEAR-001': 'duplicate',
  'SS-ENT-001': 'entity',
  'SS-ENT-002': 'entity',
  'SS-CHR-001': 'time',
  'SS-CHR-002': 'time',
  'SS-TGT-001': 'target',
  'SS-TGT-002': 'target',
  'SS-PPF-001': 'pipeline',
  'SS-VRU-001': 'reuse',
  'SS-AVL-001': 'availability',
}

const CATEGORY_LABELS: Array<[string, string]> = [
  ['duplicate', 'Duplicate / Similarity'],
  ['entity', 'Entity'],
  ['time', 'Time'],
  ['target', 'Target'],
  ['pipeline', 'Pipeline'],
  ['reuse', 'Validation Reuse'],
  ['availability', 'Availability'],
]

function ruleFindings(result: ComparisonResult, strategyId: string): Record<string, number> {
  const findings: Finding[] = result.per_strategy_findings[strategyId] ?? []
  const byRule: Record<string, number> = {}
  for (const finding of findings) {
    byRule[finding.rule_id] = (byRule[finding.rule_id] ?? 0) + 1
  }
  return byRule
}

function categoryCounts(result: ComparisonResult, strategyId: string): Map<string, number> {
  const byRule = ruleFindings(result, strategyId)
  const byCategory = new Map<string, number>()
  for (const [ruleId, count] of Object.entries(byRule)) {
    const key = CATEGORY_BY_RULE[ruleId] ?? 'other'
    byCategory.set(key, (byCategory.get(key) ?? 0) + count)
  }
  return byCategory
}

export function SplitVisual({ comparison }: { comparison: ComparisonResult }) {
  const supported = comparison.rows.filter((row) => row.supported)
  if (!supported.length && !comparison.plans.length) return null

  return (
    <div className="splitviz">
      <h3 className="splitviz__title">What each candidate actually does</h3>
      <p className="splitviz__note">
        Bars are computed from the audited assignments and folds. Longer test or overlap bars are
        not better or worse — they are consequences of the strategy choice.
      </p>

      {supported.map((row) => {
        const total = row.train_rows + row.test_rows
        const testPct = total ? (row.test_rows / total) * 100 : 0
        const overlap = row.entity_overlap_test_share
        const categories = categoryCounts(comparison, row.strategy_id)
        return (
          <section key={row.strategy_id} className="splitviz__row" aria-label={`Visual summary for ${row.label}`}>
            <div className="splitviz__head">
              <strong>{row.label}</strong>
              <span className="tiny muted mono">
                {integer(row.train_rows)} train / {integer(row.test_rows)} test
              </span>
            </div>
            <div className="splitviz__barrow">
              <span className="splitviz__barlabel">Allocation</span>
              <div className="splitviz__bar" role="img"
                aria-label={`Train ${percent(1 - testPct / 100)}, test ${percent(testPct / 100)}`}>
                <div className="splitviz__seg splitviz__seg--train" style={{ width: `${100 - testPct}%` }} />
                <div className="splitviz__seg splitviz__seg--test" style={{ width: `${testPct}%` }} />
              </div>
            </div>
            <div className="splitviz__barrow">
              <span className="splitviz__barlabel">Entity overlap</span>
              <div className="splitviz__bar">
                <div
                  className={`splitviz__seg splitviz__seg--overlap${overlap && overlap > 0.1 ? ' splitviz__seg--hot' : ''}`}
                  style={{ width: `${overlap === null ? 0 : Math.min(100, (overlap ?? 0) * 100)}%` }}
                />
              </div>
              <span className="splitviz__value">
                {overlap === null || overlap === undefined
                  ? 'not evaluated'
                  : `${(overlap * 100).toFixed(1)}% of test rows`}
              </span>
            </div>
            <div className="splitviz__cats">
              {CATEGORY_LABELS.map(([key, label]) => {
                const count = categories.get(key) ?? 0
                return (
                  <span
                    key={key}
                    className={`splitviz__cat${count ? ' splitviz__cat--on' : ''}`}
                    title={count ? `${count} finding(s) in this category` : 'no findings in this category'}
                  >
                    {label}
                    {count ? ` · ${count}` : ''}
                  </span>
                )
              })}
            </div>
          </section>
        )
      })}

      {comparison.plans.map((plan) => {
        const folds = plan.folds
        const maxOverlap = Math.max(
          0.001,
          ...folds.map((fold) => fold.entity_overlap_test_share ?? 0),
        )
        return (
          <section key={plan.plan_id} className="splitviz__row" aria-label={`Visual summary for ${plan.label}`}>
            <div className="splitviz__head">
              <strong>{plan.label}</strong>
              <span className="tiny muted mono">
                {plan.n_folds} folds{plan.repeats > 1 ? ` × ${plan.repeats}` : ''}
                {plan.gap ? ` · purge ${plan.gap}` : ''}
                {plan.seed !== null ? ` · seed ${plan.seed}` : ''}
              </span>
            </div>
            {!plan.supported ? (
              <p className="small splitviz__unsupported">{plan.unsupported_reason}</p>
            ) : (
              <>
                <div className="splitviz__folds">
                  {folds.map((fold) => {
                    const total = fold.train_rows + fold.test_rows
                    const testPct = total ? (fold.test_rows / total) * 100 : 0
                    const overlap = fold.entity_overlap_test_share ?? 0
                    return (
                      <div
                        key={`${fold.repeat}.${fold.fold_index}`}
                        className="splitviz__fold"
                        title={`Fold ${fold.fold_index}: ${fold.train_rows} train / ${fold.test_rows} test; ${
                          fold.entity_shared_groups ?? 0
                        } shared entity groups; ${fold.findings_total} finding(s)`}
                      >
                        <div className="splitviz__bar splitviz__bar--fold">
                          <div className="splitviz__seg splitviz__seg--train" style={{ width: `${100 - testPct}%` }} />
                          <div className="splitviz__seg splitviz__seg--test" style={{ width: `${testPct}%` }} />
                          <div
                            className={`splitviz__seg splitviz__seg--overlap${overlap > 0.1 ? ' splitviz__seg--hot' : ''}`}
                            style={{ width: `${(overlap / maxOverlap) * 100}%` }}
                          />
                        </div>
                        <span className="splitviz__foldlabel">
                          f{fold.fold_index}
                          {fold.findings_total ? ` ·${fold.findings_total}` : ''}
                        </span>
                      </div>
                    )
                  })}
                </div>
                <div className="splitviz__planfacts">
                  <span>
                    folds with findings: {plan.aggregate.folds_with_findings ?? 0}/
                    {plan.aggregate.folds_audited ?? folds.length}
                  </span>
                  {plan.aggregate.mean_entity_overlap_test_share !== null &&
                  plan.aggregate.mean_entity_overlap_test_share !== undefined ? (
                    <span>
                      mean entity overlap: {(plan.aggregate.mean_entity_overlap_test_share * 100).toFixed(1)}% of
                      test rows
                    </span>
                  ) : null}
                  {plan.aggregate.folds_with_chronology_violation ? (
                    <span>
                      folds with chronology violations: {plan.aggregate.folds_with_chronology_violation}
                    </span>
                  ) : null}
                  <span>mean test fraction: {percent(plan.aggregate.mean_test_fraction ?? 0)}</span>
                </div>
                {plan.notes.length ? (
                  <ul className="list-tight small splitviz__plannotes">
                    {plan.notes.slice(0, 3).map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                ) : null}
              </>
            )}
          </section>
        )
      })}
    </div>
  )
}
