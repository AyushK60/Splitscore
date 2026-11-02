/**
 * Split comparison.
 *
 * The whole point of this view is that SplitScope does not nominate a "best"
 * split. It re-runs the same checks on each candidate under the same settings and
 * lays the consequences side by side, including the strategies that could not be
 * built at all and why.
 */

import { useState } from 'react'

import { Badge, Callout, Card, EmptyState, Stat, Table } from '../components/ui'
import { FindingCard } from '../components/FindingCard'
import { SplitVisual } from '../components/SplitVisual'
import type { PlanConfig, SplitConfig } from '../api/types'
import { humanDuration, integer, percent, pluralise } from '../lib/format'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'

const KINDS: Array<{ kind: SplitConfig['kind']; label: string; needs: string | null; blurb: string }> = [
  {
    kind: 'existing',
    label: 'Existing split (from the file)',
    needs: null,
    blurb: 'Audits the split already recorded in the dataset. No new assignment is produced.',
  },
  {
    kind: 'random',
    label: 'Random holdout',
    needs: null,
    blurb: 'Uniformly at random with a fixed seed. Reuses rows freely across splits by design.',
  },
  {
    kind: 'stratified',
    label: 'Stratified holdout',
    needs: 'target',
    blurb: 'Preserves the target class proportions in both splits. Needs a categorical target.',
  },
  {
    kind: 'group',
    label: 'Group holdout',
    needs: 'entity',
    blurb:
      'Keeps every entity wholly inside one split. Achieved row proportions usually differ from the request.',
  },
  {
    kind: 'chronological',
    label: 'Chronological holdout',
    needs: 'timestamp',
    blurb:
      'Splits on a timestamp boundary so test rows are later than train rows. Ties at the boundary are kept together.',
  },
]

const PLAN_KINDS: Array<{
  kind: PlanConfig['kind']
  label: string
  needs: string | null
  blurb: string
}> = [
  {
    kind: 'repeated_stratified_cv',
    label: 'Stratified CV',
    needs: 'target',
    blurb:
      'Repeated stratified k-fold. Every fold preserves class proportions; rows of one entity appear in several folds.',
  },
  {
    kind: 'group_cv',
    label: 'Group CV',
    needs: 'entity',
    blurb:
      'Group k-fold on the entity column: every entity is tested in exactly one fold, so folds measure generalisation to unseen entities.',
  },
  {
    kind: 'rolling_origin',
    label: 'Rolling origin',
    needs: 'timestamp',
    blurb:
      'Expanding-window time validation: each fold trains on the past and tests on the next block, with an optional purge gap.',
  },
]

export function ComparisonView({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const {
    comparison,
    dataset,
    roles,
    config,
    strategies,
    setStrategies,
    plans,
    setPlans,
    includeExistingSplit,
    setIncludeExistingSplit,
    runComparison,
    busyLabel,
    selectFinding,
    download,
  } = useApp()

  const [testFraction, setTestFraction] = useState(0.25)
  const [seed, setSeed] = useState(12345)

  function addPlan(kind: PlanConfig['kind']) {
    const meta = PLAN_KINDS.find((item) => item.kind === kind)
    if (!meta) return
    if (plans.some((plan) => plan.kind === kind)) return
    setPlans([
      ...plans,
      {
        kind,
        label: meta.label,
        n_folds: 5,
        repeats: kind === 'repeated_stratified_cv' ? 2 : 1,
        gap: 0,
      },
    ])
  }

  function patchPlan(index: number, patch: Partial<PlanConfig>) {
    setPlans(plans.map((plan, i) => (i === index ? { ...plan, ...patch } : plan)))
  }

  if (!dataset) {
    return (
      <Card title="Split comparison">
        <EmptyState
          title="No dataset is loaded"
          action={
            <button type="button" className="btn btn--primary" onClick={() => onNavigate('overview')}>
              Load a demo or upload a CSV
            </button>
          }
        >
          Comparison builds alternative splits from a loaded dataset and re-runs the enabled checks on
          each one.
        </EmptyState>
      </Card>
    )
  }

  function addStrategy(kind: SplitConfig['kind']) {
    const meta = KINDS.find((item) => item.kind === kind)
    if (!meta) return
    if (strategies.some((strategy) => strategy.kind === kind)) return
    setStrategies([
      ...strategies,
      { kind, label: meta.label, test_fraction: testFraction, seed },
    ])
  }

  function patchStrategy(index: number, patch: Partial<SplitConfig>) {
    setStrategies(strategies.map((strategy, i) => (i === index ? { ...strategy, ...patch } : strategy)))
  }

  const comparison_ = comparison

  return (
    <div className="stack">
      <Card title="Candidate splits">
        <Callout tone="info" title="There is no universally best split">
          {comparison?.selection_note ??
            'The right strategy depends on what the model must generalise to. SplitScope shows what each candidate does to the checks; it does not rank them.'}
        </Callout>

        <div className="filters" style={{ marginBottom: 10 }}>
          <div className="field">
            <label htmlFor="cmp-fraction">Test fraction</label>
            <input
              id="cmp-fraction"
              type="number"
              min={0.05}
              max={0.9}
              step={0.05}
              value={testFraction}
              onChange={(event) => {
                const value = Number(event.target.value)
                if (!Number.isNaN(value)) setTestFraction(value)
              }}
            />
          </div>
          <div className="field">
            <label htmlFor="cmp-seed">Random seed</label>
            <input
              id="cmp-seed"
              type="number"
              min={0}
              step={1}
              value={seed}
              onChange={(event) => {
                const value = Number.parseInt(event.target.value, 10)
                if (!Number.isNaN(value)) setSeed(value)
              }}
            />
            <span className="hint">Applies to the randomised strategies. Recorded in the report.</span>
          </div>
        </div>

        <fieldset style={{ marginBottom: 10 }}>
          <legend>Add a strategy</legend>
          <div className="row">
            {KINDS.filter((meta) => meta.kind !== 'existing').map((meta) => {
              const blocked =
                (meta.needs === 'target' && !roles.target) ||
                (meta.needs === 'entity' && !roles.entity) ||
                (meta.needs === 'timestamp' && !roles.timestamp)
              const already = strategies.some((strategy) => strategy.kind === meta.kind)
              return (
                <button
                  key={meta.kind}
                  type="button"
                  className="btn btn--small"
                  disabled={blocked || already}
                  title={
                    blocked
                      ? `Select a ${meta.needs} column in the dataset view to enable this strategy.`
                      : meta.blurb
                  }
                  onClick={() => addStrategy(meta.kind)}
                >
                  + {meta.label}
                  {blocked ? ` (needs a ${meta.needs})` : ''}
                </button>
              )
            })}
          </div>
        </fieldset>

        <fieldset style={{ marginBottom: 10 }}>
          <legend>Add an evaluation plan (multi-fold)</legend>
          <div className="row">
            {PLAN_KINDS.map((meta) => {
              const blocked =
                (meta.needs === 'target' && !roles.target) ||
                (meta.needs === 'entity' && !roles.entity) ||
                (meta.needs === 'timestamp' && !roles.timestamp)
              const already = plans.some((plan) => plan.kind === meta.kind)
              return (
                <button
                  key={meta.kind}
                  type="button"
                  className="btn btn--small"
                  disabled={blocked || already}
                  title={
                    blocked
                      ? `Select a ${meta.needs} column in the dataset view to enable this plan.`
                      : meta.blurb
                  }
                  onClick={() => addPlan(meta.kind)}
                >
                  + {meta.label}
                  {blocked ? ` (needs a ${meta.needs})` : ''}
                </button>
              )
            })}
          </div>
          {plans.length ? (
            <p className="hint" style={{ marginBottom: 0 }}>
              Each fold of a plan is audited with the same checks; the plan reports per-fold facts
              and honest aggregates. A comparison audits at most 20 folds in total.
            </p>
          ) : null}
        </fieldset>

        <Table
          caption="Each candidate is generated from the loaded dataset. The original data is never modified."
          head={
            <tr>
              <th scope="col">Strategy</th>
              <th scope="col" className="num">
                Test fraction
              </th>
              <th scope="col" className="num">
                Seed
              </th>
              <th scope="col">Behaviour</th>
              <th scope="col">Remove</th>
            </tr>
          }
        >
          {roles.split === null ? (
            <tr>
              <th scope="row">Existing split (from the file)</th>
              <td className="num">—</td>
              <td className="num">—</td>
              <td className="small muted">
                Not available: no split column is selected, so the file does not mark train and test
                rows. Pick a split column in the dataset view to compare against it.
              </td>
              <td className="small muted">—</td>
            </tr>
          ) : includeExistingSplit ? (
            <tr>
              <th scope="row">Existing split (from the file)</th>
              <td className="num">—</td>
              <td className="num">—</td>
              <td className="small">{KINDS[0].blurb}</td>
              <td>
                <button
                  type="button"
                  className="btn btn--small"
                  onClick={() => setIncludeExistingSplit(false)}
                >
                  Exclude
                </button>
              </td>
            </tr>
          ) : (
            <tr>
              <th scope="row">Existing split (from the file)</th>
              <td className="num">—</td>
              <td className="num">—</td>
              <td className="small muted">Excluded from this comparison.</td>
              <td>
                <button
                  type="button"
                  className="btn btn--small"
                  onClick={() => setIncludeExistingSplit(true)}
                >
                  Include
                </button>
              </td>
            </tr>
          )}
          {strategies.map((strategy, index) => {
            const meta = KINDS.find((item) => item.kind === strategy.kind)
            return (
              <tr key={`${strategy.kind}-${index}`}>
                <th scope="row">{strategy.label}</th>
                <td className="num">
                  <input
                    type="number"
                    min={0.05}
                    max={0.9}
                    step={0.05}
                    value={strategy.test_fraction}
                    aria-label={`Test fraction for ${strategy.label}`}
                    onChange={(event) => {
                      const value = Number(event.target.value)
                      if (!Number.isNaN(value)) patchStrategy(index, { test_fraction: value })
                    }}
                  />
                </td>
                <td className="num">
                  <input
                    type="number"
                    min={0}
                    step={1}
                    value={strategy.seed}
                    aria-label={`Seed for ${strategy.label}`}
                    onChange={(event) => {
                      const value = Number.parseInt(event.target.value, 10)
                      if (!Number.isNaN(value)) patchStrategy(index, { seed: value })
                    }}
                  />
                </td>
                <td className="small">{meta?.blurb}</td>
                <td>
                  <button
                    type="button"
                    className="btn btn--small"
                    onClick={() => setStrategies(strategies.filter((_, i) => i !== index))}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            )
          })}
          {plans.map((plan, index) => {
            const meta = PLAN_KINDS.find((item) => item.kind === plan.kind)
            return (
              <tr key={`plan-${plan.kind}-${index}`}>
                <th scope="row">
                  {plan.label}
                  <span className="hint mono">{plan.kind}</span>
                </th>
                <td className="num" colSpan={2}>
                  {plan.n_folds} folds
                  {plan.repeats > 1 ? ` × ${plan.repeats} repeats` : ''}
                  {plan.gap > 0 ? `, gap ${plan.gap}` : ''}
                </td>
                <td className="small">{meta?.blurb}</td>
                <td>
                  <button
                    type="button"
                    className="btn btn--small"
                    onClick={() => setPlans(plans.filter((_, i) => i !== index))}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            )
          })}
        </Table>

        {plans.length ? (
          <details className="disclosure" style={{ marginBottom: 10 }}>
            <summary>Plan configuration</summary>
            <div className="stack">
              {plans.map((plan, index) => (
                <div key={`${plan.kind}-${index}`} className="row">
                  <strong style={{ minWidth: 120 }}>{plan.label}</strong>
                  <NumberFieldSmall
                    id={`plan-folds-${index}`}
                    label="Folds"
                    min={2}
                    max={10}
                    value={plan.n_folds}
                    onChange={(value) => patchPlan(index, { n_folds: value })}
                  />
                  {plan.kind === 'repeated_stratified_cv' ? (
                    <NumberFieldSmall
                      id={`plan-repeats-${index}`}
                      label="Repeats"
                      min={1}
                      max={3}
                      value={plan.repeats}
                      onChange={(value) => patchPlan(index, { repeats: value })}
                    />
                  ) : null}
                  {plan.kind === 'rolling_origin' ? (
                    <NumberFieldSmall
                      id={`plan-gap-${index}`}
                      label="Purge gap (rows)"
                      min={0}
                      max={1000}
                      value={plan.gap}
                      onChange={(value) => patchPlan(index, { gap: value })}
                    />
                  ) : null}
                </div>
              ))}
            </div>
          </details>
        ) : null}

        <p style={{ marginBottom: 0 }}>
          <button
            type="button"
            className="btn btn--primary"
            disabled={
              busyLabel !== null ||
              ((!includeExistingSplit || roles.split === null) &&
                strategies.length === 0 &&
                plans.length === 0)
            }
            onClick={async () => {
              await runComparison()
            }}
          >
            {comparison ? 'Re-run the comparison' : 'Run the comparison'}
          </button>
        </p>
      </Card>

      {!comparison_ ? (
        <Card title="Results">
          <EmptyState title="No comparison has been run yet">
            SplitScope will build each candidate, re-run every enabled check on it under the current
            settings, and report the differences — including the checks that could not run at all.
          </EmptyState>
        </Card>
      ) : (
        <>
          <Card
            title="Comparison table"
            actions={
              <span className="tiny muted">
                {comparison_.result.rows.length}{' '}
                {pluralise(comparison_.result.rows.length, 'candidate')} ·{' '}
                {humanDuration(comparison_.result.duration_ms)}
              </span>
            }
          >
            <div className="grid-3">
              <Stat
                label="Candidates evaluated"
                value={comparison_.result.rows.filter((row) => row.supported).length}
                hint={`${comparison_.result.rows.filter((row) => !row.supported).length} unsupported`}
              />
              <Stat
                label="Datasets"
                value={comparison_.result.dataset.row_count.toLocaleString()}
                hint="rows audited per candidate"
              />
              <Stat
                label="Settings held constant"
                value={`${config.max_examples} examples`}
                hint="every candidate is checked under the same thresholds"
              />
            </div>

            <SplitVisual comparison={comparison_.result} />

            <div style={{ overflowX: 'auto', marginTop: 12 }}>
              <table className="table">
                <caption>
                  Every candidate re-runs the same enabled checks. “—” means the check does not apply
                  to that strategy; a real “not evaluated” reason is listed below the row.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Strategy</th>
                    <th scope="col" className="num">
                      Requested
                    </th>
                    <th scope="col" className="num">
                      Achieved
                    </th>
                    <th scope="col" className="num">
                      Train
                    </th>
                    <th scope="col" className="num">
                      Test
                    </th>
                    <th scope="col" className="num">
                      Exact dup. test rows
                    </th>
                    <th scope="col" className="num">
                      Entity overlap
                    </th>
                    <th scope="col">Chronology</th>
                    <th scope="col">Target</th>
                    <th scope="col">Findings</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison_.result.rows.map((row) => (
                    <tr key={row.strategy_id}>
                      <th scope="row">
                        {row.label}
                        <span className="hint mono">{row.kind}</span>
                        {!row.supported ? (
                          <Badge tone="medium">not built</Badge>
                        ) : null}
                      </th>
                      <td className="num">
                        {row.requested_test_fraction === null
                          ? '—'
                          : percent(row.requested_test_fraction)}
                      </td>
                      <td className="num">
                        {row.achieved_test_fraction === null ? '—' : percent(row.achieved_test_fraction)}
                      </td>
                      <td className="num">{integer(row.train_rows)}</td>
                      <td className="num">{integer(row.test_rows)}</td>
                      <td className="num">
                        {row.exact_duplicate_test_rows === null
                          ? '—'
                          : `${integer(row.exact_duplicate_test_rows)} (${percent(
                              row.exact_duplicate_test_share ?? 0,
                            )})`}
                      </td>
                      <td className="num">
                        {row.entity_shared_groups === null
                          ? '—'
                          : `${integer(row.entity_shared_groups)} groups`}
                      </td>
                      <td className="small">{row.chronology_status ?? '—'}</td>
                      <td className="small">{row.target_summary ?? '—'}</td>
                      <td className="small">
                        {Object.keys(row.finding_counts).length === 0 ? (
                          <span className="muted">none</span>
                        ) : (
                          Object.entries(row.finding_counts).map(([severity, count]) => (
                            <div key={severity}>
                              {severity}: {count}
                            </div>
                          ))
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {comparison_.result.rows.map((row) => (
              <div key={row.strategy_id} className="panel" style={{ marginTop: 10 }}>
                <h4 style={{ marginTop: 0 }}>{row.label}</h4>
                {row.unsupported_reason ? (
                  <Callout tone="warn" title="This candidate could not be built">
                    {row.unsupported_reason}
                  </Callout>
                ) : null}
                {row.proportion_note ? <p className="small">{row.proportion_note}</p> : null}
                {row.notes.length ? (
                  <ul className="list-tight small">
                    {row.notes.map((note) => (
                      <li key={note}>{note}</li>
                    ))}
                  </ul>
                ) : null}
                {row.not_evaluated.length ? (
                  <>
                    <p className="small muted" style={{ marginBottom: 2 }}>
                      Checks that did not run for this candidate:
                    </p>
                    <ul className="list-tight small">
                      {row.not_evaluated.map((check) => (
                        <li key={check.rule_id}>
                          <span className="mono tiny">{check.rule_id}</span> — {check.reason}
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
                {comparison_.assignments.some((handle) => handle.strategy_id === row.strategy_id) ? (
                  <p style={{ marginBottom: 0 }}>
                    <button
                      type="button"
                      className="btn btn--small"
                      disabled={busyLabel !== null}
                      onClick={() => {
                        const handle = comparison_.assignments.find(
                          (item) => item.strategy_id === row.strategy_id,
                        )
                        if (handle) void download(handle.download_path)
                      }}
                    >
                      Download this split assignment (CSV)
                    </button>
                    <span className="hint" style={{ display: 'inline' }}>
                      One row per record: the stable internal row id, the split, and the strategy.
                    </span>
                  </p>
                ) : null}
              </div>
            ))}
          </Card>

          {comparison_.result.rows.map((row) => {
            const findings = comparison_.result.per_strategy_findings[row.strategy_id] ?? []
            if (!findings.length) return null
            return (
              <Card key={row.strategy_id} title={`Findings under “${row.label}” (${findings.length})`}>
                <div className="stack">
                  {findings.map((finding) => (
                    <FindingCard
                      key={`${row.strategy_id}-${finding.rule_id}-${finding.title}`}
                      finding={finding}
                      contextLabel={row.label}
                      countsAsZero
                      onOpenEvidence={() => {
                        selectFinding(finding, 'comparison', row.label)
                        onNavigate('evidence')
                      }}
                    />
                  ))}
                </div>
              </Card>
            )
          })}

          <Card title="What a split assignment does and does not fix">
            <Callout tone="warn" title="Splitting is not a repair">
              Producing a group or chronological assignment removes the specific overlap it is
              designed to remove — entity sharing, or future information in train. It does not fix
              duplicate rows, target proxies, or preprocessing that was fitted before the split.
              Re-run the audit on the new assignment and read the remaining findings.
            </Callout>
            <ul className="list-tight">
              {comparison_.result.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  )
}

function NumberFieldSmall({
  id,
  label,
  min,
  max,
  value,
  onChange,
}: {
  id: string
  label: string
  min: number
  max: number
  value: number
  onChange: (value: number) => void
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => {
          const parsed = Number.parseInt(event.target.value, 10)
          if (!Number.isNaN(parsed)) onChange(parsed)
        }}
      />
    </div>
  )
}
