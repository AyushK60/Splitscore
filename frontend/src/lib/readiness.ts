/**
 * Readiness derivation for the run gate.
 *
 * "Can I run the audit?" has one answer, computed in one place, so no view can
 * offer a run button whose prerequisites are missing. The backend stays the
 * authority — this derivation only reflects what the file and the roles say —
 * and every reason names the action that removes it.
 *
 * Two different questions are reported separately, because conflating them was
 * misleading: a validation response that says "no column holds two roles" does
 * NOT mean the audit is ready. The entry question may still be unanswered, the
 * train/test labels may still be missing, or the user may not yet have vouched
 * for name-based suggestions.
 *
 *   - `columnState` answers: do the column assignments conflict?
 *   - `ready` answers: is the whole audit workflow ready to run?
 *
 * The Results view uses `blockers` (full sentences, no inline editor there);
 * the Data view uses `workflowBlockers`, which summarises column problems
 * instead of repeating the validation text already shown next to the controls.
 */

import type { ColumnRoles, ColumnTypeInfo, RoleValidationResult, SplitConfig } from '../api/types'

export type SplitMode = 'existing' | 'generate'

export type ColumnTypesByName = Record<string, ColumnTypeInfo>

export interface ReadinessInput {
  roles: ColumnRoles
  validation: RoleValidationResult | null
  /** True while the server has not yet seen the current roles. */
  validationPending?: boolean
  /** False until the user vouches for name-based role suggestions. */
  suggestionsConfirmed?: boolean
  splitMode: SplitMode | null
  generate: SplitConfig | null
  columnTypes: ColumnTypesByName
}

export type ColumnState = 'checking' | 'conflicted' | 'consistent'
export type SplitState = 'unanswered' | 'incomplete' | 'ready'

export interface Readiness {
  ready: boolean
  /** Every blocker, in plain language, for views without the inline editor. */
  blockers: string[]
  /**
   * Blockers for the Data view: column problems are reduced to one summary
   * line because the detailed text is already shown next to the controls.
   */
  workflowBlockers: string[]
  /** Things that will happen but are not failures, e.g. rows excluded from the split. */
  cautions: string[]
  /** Short label for the run button, e.g. "Run audit" or "Run audit (generate the split now)". */
  runLabel: string
  /** What the audit will actually split on, for the summary line. */
  splitDescription: string
  /** Whether the column assignments conflict (a narrower question than `ready`). */
  columnState: ColumnState
  /** One sentence describing the column assignments, for the role editor. */
  columnSummary: string
  /** Full validation/role messages about the columns, in plain language. */
  columnBlockers: string[]
  /** Whether the split question is answered well enough to submit. */
  splitState: SplitState
}

const STRATEGY_NAMES: Record<string, string> = {
  random: 'Random holdout',
  stratified: 'Stratified holdout',
  group: 'Group holdout',
  chronological: 'Chronological holdout',
  existing: 'The split already in the file',
}

export function strategyName(kind: string): string {
  return STRATEGY_NAMES[kind] ?? kind
}

export function splitModeLabel(mode: SplitMode | null): string {
  if (mode === 'existing') return 'Use the split already in the file'
  if (mode === 'generate') return 'Create a split when the audit runs'
  return 'Not chosen yet'
}

export function readiness(input: ReadinessInput): Readiness {
  const {
    roles,
    validation,
    validationPending,
    suggestionsConfirmed = true,
    splitMode,
    generate,
    columnTypes,
  } = input
  const columnBlockers: string[] = []
  const workflowBlockers: string[] = []
  const cautions: string[] = []

  // ---- column assignments (narrow question) --------------------------------
  const special = new Set(
    [roles.target, roles.entity, roles.timestamp, roles.split].filter(Boolean) as string[],
  )
  const clashing = roles.features.filter((name) => special.has(name))
  if (clashing.length) {
    columnBlockers.push(
      `${clashing.join(', ')} ${clashing.length === 1 ? 'is' : 'are'} both a feature and another role. Remove the feature choice or the special role.`,
    )
  }
  if (!roles.features.length) {
    columnBlockers.push('No feature columns are selected, so there is nothing to compare.')
  }

  let columnState: ColumnState = 'checking'
  const serverUnconfirmed = validationPending || !validation
  if (serverUnconfirmed) {
    // Not an error in the columns — the server simply has not answered yet.
  } else if (!validation.ok) {
    const errors = validation.issues.filter((issue) => issue.severity === 'error')
    for (const issue of errors) {
      columnBlockers.push(issue.hint ? `${issue.message} ${issue.hint}` : issue.message)
    }
    columnState = 'conflicted'
  } else {
    columnState = columnBlockers.length ? 'conflicted' : 'consistent'
  }
  if (!serverUnconfirmed && columnBlockers.length) columnState = 'conflicted'

  let columnSummary: string
  if (columnState === 'checking') {
    columnSummary = 'The server is still checking these column assignments.'
  } else if (columnState === 'conflicted') {
    columnSummary = `${columnBlockers.length} ${columnBlockers.length === 1 ? 'column problem needs' : 'column problems need'} attention before the audit can run.`
  } else {
    const resolved = validation?.resolved
    if (resolved) {
      const features = resolved.feature_columns.length
      const metadata = resolved.metadata_excluded.length
      columnSummary =
        `${features} ${features === 1 ? 'feature column will' : 'feature columns will'} be compared` +
        (metadata
          ? `; ${metadata} ${metadata === 1 ? 'column is' : 'columns are'} excluded as metadata.`
          : '.') +
        ' No column holds two roles.'
    } else {
      columnSummary = 'These column assignments do not conflict.'
    }
  }

  // ---- workflow prerequisites (the whole run) ------------------------------
  let columnSummaryLine: string | null = null
  if (columnBlockers.length) {
    columnSummaryLine = `Resolve the ${columnBlockers.length} blocking column ${columnBlockers.length === 1 ? 'problem' : 'problems'} shown next to the questions above.`
    workflowBlockers.push(columnSummaryLine)
  }
  if (serverUnconfirmed) {
    workflowBlockers.push('The server has not confirmed the current column roles yet.')
  }
  if (!suggestionsConfirmed) {
    workflowBlockers.push(
      'Confirm the suggested column roles — accept them or adjust them — before running the audit.',
    )
  }

  let splitDescription: string
  let splitState: SplitState
  if (splitMode === null) {
    splitState = 'unanswered'
    workflowBlockers.push(
      'Answer the first question: does the file already say which rows are training and testing?',
    )
    splitDescription = 'not chosen yet'
  } else if (splitMode === 'existing') {
    if (!roles.split) {
      splitState = 'incomplete'
      workflowBlockers.push(
        'No split column is selected. Pick the column that marks train and test, or switch to generating a split.',
      )
    } else if (!roles.split_train_value || !roles.split_test_value) {
      splitState = 'incomplete'
      workflowBlockers.push(
        `Map the values of ${roles.split} to train and test — both labels are required.`,
      )
    } else if (roles.split_train_value === roles.split_test_value) {
      splitState = 'incomplete'
      workflowBlockers.push(
        `Choose different values for train and test — both currently say “${roles.split_train_value}”.`,
      )
    } else {
      splitState = 'ready'
      const info = columnTypes[roles.split]
      // Empty cells carry neither label. The backend excludes those rows from
      // the split and reports them, so this is a caution, not a blocker.
      if (info && info.missing_count > 0) {
        cautions.push(
          `${info.missing_count.toLocaleString()} ${info.missing_count === 1 ? 'row has' : 'rows have'} an empty ${roles.split} value; those rows are excluded from the split and reported by the audit.`,
        )
      }
    }
    splitDescription = roles.split
      ? `${roles.split} = ${roles.split_train_value ?? '?'} (train) / ${roles.split_test_value ?? '?'} (test)`
      : 'the split column in the file'
  } else {
    splitState = 'ready'
    if (!generate) {
      splitState = 'incomplete'
      workflowBlockers.push('Choose how to split the rows — no strategy is selected yet.')
    } else if (generate.kind === 'stratified' && !roles.target) {
      splitState = 'incomplete'
      workflowBlockers.push('A stratified holdout needs a target column to stratify by.')
    } else if (generate.kind === 'group' && !roles.entity) {
      splitState = 'incomplete'
      workflowBlockers.push('A group holdout needs an entity/group column.')
    } else if (generate.kind === 'chronological' && !roles.timestamp) {
      splitState = 'incomplete'
      workflowBlockers.push('A chronological holdout needs a timestamp column.')
    }
    splitDescription = generate
      ? `${strategyName(generate.kind)} generated now (${Math.round(generate.test_fraction * 100)}% test, seed ${generate.seed})`
      : 'a split generated now'
  }

  // Full messages for views without an inline editor: column details first,
  // then workflow reasons. The Data view uses `workflowBlockers` alone, where
  // the column detail is already next to the controls.
  const blockers = [
    ...columnBlockers,
    ...workflowBlockers.filter((blocker) => blocker !== columnSummaryLine),
  ]

  return {
    ready: blockers.length === 0,
    blockers,
    workflowBlockers,
    cautions,
    runLabel: splitMode === 'generate' ? 'Run audit (generate the split now)' : 'Run audit',
    splitDescription,
    columnState,
    columnSummary,
    columnBlockers,
    splitState,
  }
}
