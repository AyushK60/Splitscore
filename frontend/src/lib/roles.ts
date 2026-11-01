/**
 * Role-patch normalisation.
 *
 * A role patch is a user's intent ("make quality the target"). The rules below
 * turn that intent into a consistent role set, because a single column cannot
 * hold two roles and the backend rejects that with role_overlap /
 * column_multi_role issues:
 *
 * - assigning a special role (target/entity/timestamp/split) removes the column
 *   from the feature list, keeping every other feature and its order;
 * - a special role can only hold one column: picking a new one releases the old
 *   column back to "no special role" (it stays excluded from features only if
 *   the user had it there, which it no longer is);
 * - the split role owns its train/test labels; changing the split column clears
 *   the labels so a stale mapping can never be submitted;
 * - clearing a special role does not silently re-add the column to features —
 *   that stays an explicit user choice, and the returned `releaseNote` tells the
 *   UI what to explain.
 *
 * The function is pure so both the state layer and the tests exercise exactly
 * the same behaviour.
 */

import type { ColumnRoles } from '../api/types'

export interface RolePatchResult {
  roles: ColumnRoles
  /** Human-readable explanations of every automatic adjustment, in order. */
  notes: string[]
}

const SPECIAL_KEYS = ['target', 'entity', 'timestamp', 'split'] as const
type SpecialKey = (typeof SPECIAL_KEYS)[number]

function withoutFeature(features: string[], column: string): string[] {
  return features.filter((name) => name !== column)
}

/**
 * Applies a partial role patch, resolving special-role conflicts.
 *
 * `columnExists` lets the caller drop values that are not columns of the
 * current dataset (a patch can outlive the dataset it was written for).
 */
export function normaliseRolePatch(
  roles: ColumnRoles,
  patch: Partial<ColumnRoles>,
  columnExists: (name: string) => boolean = () => true,
): RolePatchResult {
  const notes: string[] = []
  const next: ColumnRoles = {
    ...roles,
    features: [...roles.features],
    metadata_excluded: [...roles.metadata_excluded],
  }

  // 1. Drop values that are not columns of this dataset (stale patches).
  for (const key of SPECIAL_KEYS) {
    const value = next[key]
    if (value !== null && !columnExists(value)) {
      next[key] = null
      notes.push(`Cleared ${key} role: ${value} is not a column of this dataset.`)
    }
  }
  next.features = next.features.filter(columnExists)
  next.metadata_excluded = next.metadata_excluded.filter(columnExists)

  // 2. Apply the raw patch first; conflicts are resolved afterwards.
  for (const [key, value] of Object.entries(patch) as [keyof ColumnRoles, ColumnRoles[keyof ColumnRoles] | undefined][]) {
    if (value === undefined) continue
    if (key === 'features') {
      next.features = [...(value as string[])].filter(columnExists)
    } else if (key === 'metadata_excluded') {
      next.metadata_excluded = [...(value as string[])]
    } else if (key === 'split_train_value' || key === 'split_test_value') {
      next[key] = (value as string | null) === '' ? null : (value as string | null)
    } else {
      next[key] = value as string | null
    }
  }

  // 2b. A patch can outlive the dataset it was written for, so the same
  //     existence filter applies to what the patch just set.
  for (const key of SPECIAL_KEYS) {
    const value = next[key]
    if (value !== null && !columnExists(value)) {
      next[key] = null
      if (key === 'split') {
        next.split_train_value = null
        next.split_test_value = null
      }
      notes.push(`Cleared ${key} role: ${value} is not a column of this dataset.`)
    }
  }

  // 3. A special role may name only one column. Whichever special key now names
  //    the same column as another is resolved deterministically: the key the
  //    patch just set keeps the column (the user's latest intent wins), and
  //    otherwise the later special role does.
  const patched = new Set(
    (Object.entries(patch) as [keyof ColumnRoles, unknown][])
      .filter(([key, value]) => value !== undefined && (SPECIAL_KEYS as readonly string[]).includes(key))
      .map(([key]) => key as SpecialKey),
  )
  const held = new Map<string, SpecialKey>()
  for (const key of SPECIAL_KEYS) {
    const column = next[key]
    if (column === null) continue
    const previous = held.get(column)
    if (previous === undefined) {
      held.set(column, key)
      continue
    }
    const keep = patched.has(key) ? key : patched.has(previous) ? previous : key
    const release = keep === key ? previous : key
    next[release] = null
    if (release === 'split') {
      next.split_train_value = null
      next.split_test_value = null
      notes.push(
        `The split role moved from ${column} to the ${keep} role, so the train/test labels for it were cleared.`,
      )
    } else {
      notes.push(`Removed the ${release} role from ${column}: one column can hold only one role.`)
    }
    held.set(column, keep)
  }

  // 4. A column holding a special role is not also a feature.
  const specialColumns = new Set(SPECIAL_KEYS.map((key) => next[key]).filter(Boolean) as string[])
  const pruned = next.features.filter((name) => !specialColumns.has(name))
  if (pruned.length !== next.features.length) {
    const removed = next.features.filter((name) => specialColumns.has(name))
    next.features = pruned
    for (const column of removed) {
      notes.push(
        `Removed ${column} from the feature columns because it now has a special role; the other ${pruned.length} features are unchanged.`,
      )
    }
  }

  // 5. The split labels belong to the split column: reset them when the column
  //    changed so a mapping for the old column can never be submitted.
  if (next.split !== roles.split) {
    next.split_train_value = null
    next.split_test_value = null
  }

  // 6. A feature is never also excluded metadata.
  next.metadata_excluded = next.metadata_excluded.filter((name) => !next.features.includes(name))

  return { roles: next, notes }
}

/** Roles as they should be submitted: no column both special and featured. */
export function consistentRoles(roles: ColumnRoles): ColumnRoles {
  const special = new Set(
    [roles.target, roles.entity, roles.timestamp, roles.split].filter(Boolean) as string[],
  )
  return { ...roles, features: roles.features.filter((name) => !special.has(name)) }
}

export const __testing = { withoutFeature }
