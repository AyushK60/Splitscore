/**
 * Guided column-role editor.
 *
 * Each role is asked as a question a beginner can answer: what should the
 * model predict, do rows repeat per person/device, does the file record time,
 * and which columns are features. The role state is a single source of truth —
 * the "advanced" affordances below the questions edit exactly the same state,
 * and the backend's own validation issues are rendered verbatim next to the
 * controls.
 *
 * Suggestions (name- and type-based for uploads, manifest-based for demos) are
 * shown with their reason and applied only when the user accepts them or edits
 * the control; nothing is silently trusted.
 *
 * The split mapping deliberately uses the values observed in the column, with
 * their row counts, rather than free text: a label that does not exist in the
 * file can never be submitted by a typo. Values other than the two mapped
 * labels are named, counted and explained — never folded into either side.
 */

import type {
  ColumnRoles,
  ColumnTypeInfo,
  ColumnValuesResponse,
  DatasetLoadedResponse,
  RoleIssue,
  RoleValidationResult,
} from '../api/types'
import { integer, percent, pluralise } from '../lib/format'
import { Callout } from './ui'

const NONE = '__none__'

function typeHint(info: ColumnTypeInfo | undefined): string {
  if (!info) return ''
  const parts: string[] = []
  if (info.looks_datetime) parts.push(`${percent(info.datetime_parse_ratio, 0)} parse as dates`)
  else if (info.looks_numeric) parts.push(`${percent(info.numeric_parse_ratio, 0)} numeric`)
  if (info.looks_identifier) parts.push('looks like a row identifier')
  parts.push(`${info.distinct_values.toLocaleString()} distinct`)
  if (info.missing_count > 0) parts.push(`${percent(info.missing_ratio, 1)} missing`)
  else parts.push('no missing values')
  return parts.join(' · ')
}

/** Which checks a role unlocks, phrased for the person answering the question. */
const ENABLES: Record<'target' | 'entity' | 'timestamp', string> = {
  target: 'Enables the target-copy check (SS-TGT-001), stratified splits and the target diagnostics.',
  entity: 'Enables the entity-overlap check (SS-ENT-001) and the group holdout strategy.',
  timestamp: 'Enables the chronology check (SS-CHR-001) and the chronological holdout strategy.',
}

const NOT_SURE = '— not applicable / I don’t know —'

/** Codes about the split mapping; rendered next to the mapping controls. */
function isSplitIssue(issue: RoleIssue): boolean {
  return issue.code.startsWith('split_') || issue.code === 'missing_split_values'
}

export function RoleEditor({
  loaded,
  roles,
  onChange,
  validation,
  validationPending = false,
  observedValues,
  showSplit = true,
}: {
  loaded: DatasetLoadedResponse
  roles: ColumnRoles
  onChange: (patch: Partial<ColumnRoles>) => void
  /** Live validation from the server; undefined falls back to the upload-time payload. */
  validation?: RoleValidationResult | null
  /** True while the server has not yet seen the current roles. */
  validationPending?: boolean
  /** Observed values of the split column, when they have been fetched. */
  observedValues?: ColumnValuesResponse | null
  /** Whether the file's own split column is part of this run (the entry path). */
  showSplit?: boolean
}) {
  const columns = loaded.dataset.columns
  const types = loaded.column_types
  const suggested = loaded.suggested_roles
  const reasons = loaded.role_suggestions?.reasons ?? {}
  const metadataReason = loaded.role_suggestions?.metadata_reason

  // A column already used by a role is not offered for the roles it would clash with.
  const takenByRole = new Set(
    [roles.target, roles.entity, roles.timestamp, roles.split].filter(Boolean) as string[],
  )
  const metadata = new Set(roles.metadata_excluded)

  // Prefer the live validation; the upload-time payload is only a fallback for
  // the instant before the first debounced re-check lands. While a re-check is
  // pending nothing stale is shown — the previous issues describe roles the
  // user has since edited.
  const effective = validationPending
    ? null
    : validation === undefined
      ? loaded.validation
      : validation
  const splitIssues = effective?.issues.filter(isSplitIssue) ?? []
  const errors =
    effective?.issues.filter((issue) => issue.severity === 'error' && !isSplitIssue(issue)) ?? []
  const warnings =
    effective?.issues.filter((issue) => issue.severity === 'warning' && !isSplitIssue(issue)) ?? []

  const splitColumn = roles.split
  const splitInfo = splitColumn ? types[splitColumn] : undefined
  const observed =
    observedValues && observedValues.column === splitColumn ? observedValues : null
  const observedSet = new Set(observed?.values.map((item) => item.value) ?? [])

  const trainValue = roles.split_train_value
  const testValue = roles.split_test_value
  const trainObserved = trainValue !== null && observedSet.has(trainValue)
  const testObserved = testValue !== null && observedSet.has(testValue)

  // Row counts implied by the current label mapping, from observed values only.
  const labelCounts = (() => {
    if (!observed || !trainValue || !testValue) return null
    const byValue = new Map(observed.values.map((item) => [item.value, item.count]))
    const train = byValue.get(trainValue)
    const test = byValue.get(testValue)
    const unmappedValues = observed.values
      .filter((item) => item.value !== '' && item.value !== trainValue && item.value !== testValue)
      .map((item) => ({ value: item.value, count: item.count }))
    const unmapped = unmappedValues.reduce((sum, item) => sum + item.count, 0)
    return {
      // A missing key means the label does not occur in the file at all.
      train: train ?? 0,
      test: test ?? 0,
      trainPresent: train !== undefined,
      testPresent: test !== undefined,
      unmappedValues,
      unmapped,
      missing: observed.missing_count,
    }
  })()

  // Labels that were typed into (or carried over to) a column where they do not
  // occur. The selects make this rare; the explicit check keeps a stale mapping
  // from ever looking valid.
  const absentLabels = [
    trainValue !== null && !trainObserved && observed ? trainValue : null,
    testValue !== null && !testObserved && observed ? testValue : null,
  ].filter((value): value is string => value !== null)
  const labelsEqual = trainValue !== null && trainValue === testValue

  // The inline mapping messages below are the same facts, in plainer words and
  // with the observed counts. Do not repeat those backend issues in the callout;
  // keep any issue the client cannot reproduce (e.g. labels beyond the observed
  // list that was truncated).
  const visibleSplitIssues = splitIssues.filter((issue) => {
    if (!observed) return true
    if (issue.code === 'split_values_equal' && labelsEqual) return false
    if (issue.code === 'split_value_absent' && absentLabels.length) return false
    return true
  })

  function toggleFeature(column: string, checked: boolean) {
    const next = checked
      ? [...roles.features, column]
      : roles.features.filter((name) => name !== column)
    onChange({ features: next })
  }

  function selectAllVisible() {
    const visible = columns.filter(
      (column) => !takenByRole.has(column) && !metadata.has(column),
    )
    onChange({ features: [...new Set([...roles.features, ...visible])] })
  }

  function clearFeatures() {
    onChange({ features: [] })
  }

  function move(feature: string, delta: number) {
    const index = roles.features.indexOf(feature)
    const next = [...roles.features]
    const target = index + delta
    if (index < 0 || target < 0 || target >= next.length) return
    next.splice(index, 1)
    next.splice(target, 0, feature)
    onChange({ features: next })
  }

  /** A suggestion the user can accept in one click, with the reason shown. */
  function suggestionFor(
    role: 'target' | 'entity' | 'timestamp' | 'split',
    accept: Record<string, string | null>,
  ) {
    const column = suggested[role]
    const reason = reasons[role]
    if (!column) return null
    const current =
      role === 'split' ? roles.split : roles[role as 'target' | 'entity' | 'timestamp']
    if (current === column) return null
    return (
      <p className="suggestion small" style={{ margin: '6px 0 0' }}>
        Suggestion: <span className="mono">{column}</span>
        {reason ? ` — ${reason}` : ''}{' '}
        <button
          type="button"
          className="btn btn--small"
          onClick={() => onChange(accept)}
          aria-label={`Use suggestion for ${role}: ${column}`}
        >
          Use this column
        </button>
      </p>
    )
  }

  /**
   * A label selector built from the values the file actually contains. When the
   * observed values are unavailable (the request failed), a text input keeps
   * the mapping usable without pretending a value was observed.
   */
  function labelControl(kind: 'train' | 'test') {
    const id = kind === 'train' ? 'role-train-value' : 'role-test-value'
    const value = kind === 'train' ? trainValue : testValue
    const other = kind === 'train' ? testValue : trainValue
    const label = kind === 'train' ? 'Train value' : 'Test value'
    if (!observed) {
      return (
        <input
          id={id}
          type="text"
          value={value ?? ''}
          aria-label={label}
          onChange={(event) => onChange({ [`split_${kind}_value`]: event.target.value || null })}
        />
      )
    }
    const values = observed.values.filter((item) => item.value !== '')
    const valueIsListed = value === null || observedSet.has(value)
    return (
      <select
        id={id}
        aria-label={label}
        value={value ?? NONE}
        onChange={(event) =>
          onChange({
            [`split_${kind}_value`]: event.target.value === NONE ? null : event.target.value,
          })
        }
      >
        <option value={NONE}>— choose a value —</option>
        {values.map((item) => (
          <option key={item.value} value={item.value} disabled={item.value === other}>
            {item.value} — {integer(item.count)} {pluralise(item.count, 'row')}
          </option>
        ))}
        {!valueIsListed ? (
          <option value={value}>{value} — not found in this column</option>
        ) : null}
      </select>
    )
  }

  const visibleFeatures = columns.filter(
    (column) =>
      (!takenByRole.has(column) && !metadata.has(column)) || roles.features.includes(column),
  )

  return (
    <div className="stack">
      {showSplit ? (
        <fieldset className="role-question role-question--split">
          <legend>Which column says whether each row is training or testing?</legend>
          <p className="small muted" style={{ marginTop: 0 }}>
            Pick the column that holds the labels — for example <span className="mono">split</span>{' '}
            with values <span className="mono">train</span> / <span className="mono">test</span> —
            then map two of its observed values to the two sides. SplitScope audits exactly that
            split; the file itself is never modified.
          </p>
          <label htmlFor="role-split">Split column</label>
          <select
            id="role-split"
            aria-label="Split column"
            value={roles.split ?? NONE}
            onChange={(event) =>
              onChange({
                split: event.target.value === NONE ? null : event.target.value,
                split_train_value: null,
                split_test_value: null,
              })
            }
          >
            <option value={NONE}>— not selected —</option>
            {columns.map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
          {suggestionFor('split', {
            split: suggested.split,
            split_train_value: suggested.split_train_value,
            split_test_value: suggested.split_test_value,
          })}

          {roles.split ? (
            <div className="split-mapping">
              <div className="row" style={{ marginTop: 8, alignItems: 'flex-start', gap: 12 }}>
                <div className="field">
                  <label htmlFor="role-train-value">Train value</label>
                  {labelControl('train')}
                </div>
                <div className="field">
                  <label htmlFor="role-test-value">Test value</label>
                  {labelControl('test')}
                </div>
              </div>

              {observed ? (
                <>
                  <p className="small muted" style={{ margin: '10px 0 4px' }}>
                    Values observed in {observed.column} ({integer(observed.distinct_count)} distinct
                    {observed.truncated ? ', most frequent shown' : ''}):
                  </p>
                  <ul className="split-values small">
                    {observed.values
                      .filter((item) => item.value !== '')
                      .slice(0, 12)
                      .map((item) => {
                        const isTrain = item.value === trainValue
                        const isTest = item.value === testValue
                        const isUnmapped = !isTrain && !isTest
                        return (
                          <li key={item.value}>
                            <span className="mono">{item.value}</span>
                            <span className="muted"> — {integer(item.count)} rows</span>{' '}
                            {isTrain ? <span className="badge badge--info">train</span> : null}
                            {isTest ? <span className="badge badge--info">test</span> : null}
                            {isUnmapped ? (
                              <span className="badge badge--neutral">not mapped</span>
                            ) : null}
                            <button
                              type="button"
                              className="btn btn--small"
                              disabled={isTrain}
                              aria-pressed={isTrain}
                              onClick={() => onChange({ split_train_value: item.value })}
                              aria-label={`Use ${item.value} as the train label`}
                            >
                              Train
                            </button>
                            <button
                              type="button"
                              className="btn btn--small"
                              disabled={isTest}
                              aria-pressed={isTest}
                              onClick={() => onChange({ split_test_value: item.value })}
                              aria-label={`Use ${item.value} as the test label`}
                            >
                              Test
                            </button>
                          </li>
                        )
                      })}
                  </ul>

                  {labelsEqual ? (
                    <p className="mapping-error" role="alert">
                      Train and test cannot both be “{trainValue}”. Choose a different value for one
                      side.
                    </p>
                  ) : null}
                  {absentLabels.length ? (
                    <p className="mapping-error" role="alert">
                      No row in {observed.column} carries{' '}
                      {absentLabels.map((value) => `“${value}”`).join(' or ')}. Choose a value from
                      the observed list.
                    </p>
                  ) : null}

                  {labelCounts ? (
                    <div className="mapping-summary" role="status">
                      <p className="small" style={{ margin: 0 }}>
                        <strong>
                          {integer(labelCounts.train)} train + {integer(labelCounts.test)} test rows
                        </strong>{' '}
                        with the current mapping.
                      </p>
                      {labelCounts.missing > 0 ? (
                        <p className="small warn-text" style={{ margin: '4px 0 0' }}>
                          {integer(labelCounts.missing)}{' '}
                          {pluralise(labelCounts.missing, 'row')}{' '}
                          {labelCounts.missing === 1 ? 'has' : 'have'} an empty {observed.column}{' '}
                          value. Empty cells are missing, not a third label; those rows are excluded
                          from the split and reported.
                        </p>
                      ) : null}
                      {labelCounts.unmapped > 0 ? (
                        <p className="small warn-text" style={{ margin: '4px 0 0' }}>
                          {integer(labelCounts.unmapped)} {pluralise(labelCounts.unmapped, 'row')}{' '}
                          carry another label (
                          {labelCounts.unmappedValues
                            .slice(0, 5)
                            .map((item) => `“${item.value}”: ${integer(item.count)}`)
                            .join(', ')}
                          {labelCounts.unmappedValues.length > 5 ? ', …' : ''}). Those rows are
                          excluded from the audited split and reported — never folded into train or
                          test.
                        </p>
                      ) : null}
                      {!labelCounts.missing && !labelCounts.unmapped ? (
                        <p className="small muted" style={{ margin: '4px 0 0' }}>
                          Every row carries one of the two mapped labels.
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </>
              ) : (
                <p className="hint" style={{ marginTop: 8 }}>
                  The observed values are not available, so the labels are entered as text. They
                  must match the file exactly, including capitalisation.
                </p>
              )}

              {splitInfo && splitInfo.missing_count > 0 ? (
                <p className="hint" style={{ marginTop: 6 }}>
                  {integer(splitInfo.missing_count)}{' '}
                  {pluralise(splitInfo.missing_count, 'row')}{' '}
                  {splitInfo.missing_count === 1 ? 'has' : 'have'} an empty {roles.split} value and
                  are treated as missing, not as either label.
                </p>
              ) : null}

              {visibleSplitIssues.length ? (
                <div style={{ marginTop: 8 }}>
                  <Callout
                    tone={
                      visibleSplitIssues.some((issue) => issue.severity === 'error')
                        ? 'danger'
                        : 'warn'
                    }
                    title="The train/test mapping needs attention"
                  >
                    <ul className="list-tight">
                      {visibleSplitIssues.map((issue) => (
                        <li key={`${issue.code}-${issue.message}`}>
                          <span className="mono tiny">{issue.code}</span> {issue.message}
                          {issue.hint ? <span className="hint">{issue.hint}</span> : null}
                        </li>
                      ))}
                    </ul>
                  </Callout>
                </div>
              ) : null}
            </div>
          ) : (
            <span className="hint">
              Choose the column that marks train and test. If your file has no such column, answer
              the first question with “No — help me create a split” instead.
            </span>
          )}
        </fieldset>
      ) : null}

      <div className="grid-2">
        <fieldset className="role-question">
          <legend>What should the model predict?</legend>
          <p className="small muted" style={{ marginTop: 0 }}>
            The target column. Examples: <span className="mono">churned</span>,{' '}
            <span className="mono">quality</span>, <span className="mono">price</span>.{' '}
            {ENABLES.target}
          </p>
          <select
            aria-label="Target column"
            value={roles.target ?? NONE}
            onChange={(event) => onChange({ target: event.target.value === NONE ? null : event.target.value })}
          >
            <option value={NONE}>{NOT_SURE}</option>
            {columns.map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
          {suggestionFor('target', { target: suggested.target })}
          <span className="hint">
            The target is never compared as a feature. Choosing “not applicable” skips the
            target-copy check and the target diagnostics; the other checks still run.
          </span>
        </fieldset>

        <fieldset className="role-question">
          <legend>Do several rows describe the same person, device or item?</legend>
          <p className="small muted" style={{ marginTop: 0 }}>
            The entity / group column. Examples: <span className="mono">customer_id</span>,{' '}
            <span className="mono">patient_id</span>, <span className="mono">device</span>.{' '}
            {ENABLES.entity}
          </p>
          <select
            aria-label="Entity column"
            value={roles.entity ?? NONE}
            onChange={(event) => onChange({ entity: event.target.value === NONE ? null : event.target.value })}
          >
            <option value={NONE}>{NOT_SURE}</option>
            {columns.map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
          {suggestionFor('entity', { entity: suggested.entity })}
          <span className="hint">
            Missing entity values are counted separately and never merged into one artificial
            entity. Choosing “not applicable” skips the entity-overlap check.
          </span>
        </fieldset>

        <fieldset className="role-question">
          <legend>Does the file record when each row happened?</legend>
          <p className="small muted" style={{ marginTop: 0 }}>
            The timestamp column. Examples: <span className="mono">order_date</span>,{' '}
            <span className="mono">created_at</span>. {ENABLES.timestamp}
          </p>
          <select
            aria-label="Timestamp column"
            value={roles.timestamp ?? NONE}
            onChange={(event) => onChange({ timestamp: event.target.value === NONE ? null : event.target.value })}
          >
            <option value={NONE}>{NOT_SURE}</option>
            {columns.map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
          {suggestionFor('timestamp', { timestamp: suggested.timestamp })}
          <span className="hint">
            Values must parse as dates at a documented rate. Choosing “not applicable” skips the
            chronology check and the chronological holdout.
          </span>
        </fieldset>
      </div>

      <fieldset className="role-question role-question--features">
        <legend>Which columns should the checks compare? ({roles.features.length} selected)</legend>
        <p className="small muted" style={{ marginTop: 0 }}>
          These are the columns compared between train and test. Feature order is preserved and
          recorded in the report. Identifier columns (row numbers, UUIDs) should stay unselected —
          they identify rows, they do not describe them.
        </p>
        <div className="feature-actions">
          <button type="button" className="btn btn--small" onClick={selectAllVisible}>
            Select all shown
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={clearFeatures}
            disabled={roles.features.length === 0}
          >
            Clear selection
          </button>
        </div>
        <div className="feature-grid">
          {visibleFeatures.map((column) => {
            const checked = roles.features.includes(column)
            return (
              <div key={column} className="checkbox-row">
                <input
                  id={`feature-${column}`}
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => toggleFeature(column, event.target.checked)}
                />
                <label htmlFor={`feature-${column}`}>
                  <span className="mono">{column}</span>
                  <span className="hint">{typeHint(types[column])}</span>
                </label>
              </div>
            )
          })}
        </div>
        <span className="hint">
          Columns held by another role are not offered here — the audit never compares the target,
          split, entity or timestamp column as features.
        </span>
        {!roles.features.length ? (
          <p className="mapping-error" role="alert">
            No feature columns are selected. Choose at least one column for the checks to compare.
          </p>
        ) : null}

        {roles.metadata_excluded.length ? (
          <details className="disclosure" style={{ marginTop: 10 }}>
            <summary>Excluded as metadata ({roles.metadata_excluded.length})</summary>
            <p className="small muted" style={{ marginTop: 0 }}>
              {metadataReason ??
                'These columns look like row identifiers or bookkeeping fields. They are not compared as features, but they stay in the file and appear in the preview.'}
            </p>
            <ul className="list-tight small">
              {roles.metadata_excluded.map((column) => (
                <li key={column}>
                  <span className="mono">{column}</span>{' '}
                  <button
                    type="button"
                    className="btn btn--small btn--ghost"
                    onClick={() => onChange({ features: [...roles.features, column] })}
                  >
                    Compare as a feature
                  </button>
                </li>
              ))}
            </ul>
          </details>
        ) : null}

        {roles.features.length > 1 ? (
          <details className="disclosure">
            <summary>Reorder selected features ({roles.features.length})</summary>
            <div style={{ display: 'grid', gap: 2 }}>
              {roles.features.map((feature, index) => (
                <div key={feature} className="row" style={{ alignItems: 'center', gap: 8 }}>
                  <span className="mono small" style={{ minWidth: 190 }}>
                    {index + 1}. {feature}
                  </span>
                  <button
                    type="button"
                    className="btn btn--small"
                    onClick={() => move(feature, -1)}
                    disabled={index === 0}
                    aria-label={`Move ${feature} up`}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="btn btn--small"
                    onClick={() => move(feature, 1)}
                    disabled={index === roles.features.length - 1}
                    aria-label={`Move ${feature} down`}
                  >
                    ↓
                  </button>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </fieldset>

      {validationPending ? (
        <p className="small muted" style={{ margin: 0 }} role="status">
          Checking these roles with the server…
        </p>
      ) : null}

      {errors.length ? (
        <Callout
          tone="danger"
          title={`${errors.length} blocking configuration ${pluralise(errors.length, 'problem')}`}
        >
          <ul className="list-tight">
            {errors.map((issue) => (
              <li key={`${issue.code}-${issue.column ?? ''}-${issue.message}`}>
                <span className="mono tiny">{issue.code}</span> {issue.message}
                {issue.hint ? <span className="hint">{issue.hint}</span> : null}
              </li>
            ))}
          </ul>
        </Callout>
      ) : null}

      {warnings.length ? (
        <Callout
          tone="warn"
          title={`${warnings.length} ${pluralise(warnings.length, 'warning')} — the audit can still run`}
        >
          <ul className="list-tight">
            {warnings.map((issue) => (
              <li key={`${issue.code}-${issue.column ?? ''}-${issue.message}`}>
                <span className="mono tiny">{issue.code}</span> {issue.message}
                {issue.hint ? <span className="hint">{issue.hint}</span> : null}
              </li>
            ))}
          </ul>
        </Callout>
      ) : null}

      {effective?.ok ? (
        <Callout tone="ok" title="Column assignments do not conflict">
          {effective.resolved
            ? `${effective.resolved.feature_columns.length} ${pluralise(
                effective.resolved.feature_columns.length,
                'feature column',
              )} will be compared; ` +
              `${effective.resolved.metadata_excluded.length} ${pluralise(
                effective.resolved.metadata_excluded.length,
                'column',
              )} ${effective.resolved.metadata_excluded.length === 1 ? 'is' : 'are'} excluded as metadata. `
            : ''}
          This checks only that no column holds two roles. It is not audit readiness — answer the
          split question and confirm the roles above before running.
        </Callout>
      ) : null}
    </div>
  )
}
