import type { AuditConfig, ColumnRoles, SplitConfig } from '../api/types'

/**
 * Mirrors `AuditConfig` defaults in `backend/app/audit/types.py`. The backend
 * always re-validates what it receives, so a drift here can only change what the
 * form starts with, never what the engine runs.
 */
export const DEFAULT_AUDIT_CONFIG: AuditConfig = {
  enable_exact_duplicates: true,
  enable_entity_overlap: true,
  enable_chronology: true,
  enable_target_copy: true,
  near_duplicates: {
    enabled: false,
    threshold: 0.05,
    scaling: 'robust',
    min_numeric_ratio: 0.8,
    max_missing_fraction_per_row: 0.5,
    oversize_policy: 'sample',
    max_combined_rows: 500,
    sample_seed: 7,
  },
  strip_whitespace: true,
  normalize_numeric_strings: false,
  missing_tokens: [],
  chronology_intent: 'future_prediction',
  entity_overlap_high_test_share: 0.1,
  chronology_high_train_share: 0.02,
  target_copy_min_coverage: 0.9,
  target_copy_high_coverage: 0.99,
  target_copy_baseline_margin: 0.05,
  target_copy_min_comparable_rows: 10,
  max_examples: 10,
  max_example_rows_per_example: 4,
}

export const EMPTY_ROLES: ColumnRoles = {
  features: [],
  target: null,
  entity: null,
  timestamp: null,
  split: null,
  split_train_value: null,
  split_test_value: null,
  metadata_excluded: [],
}

/** The candidate strategies offered by the comparison view, in display order. */
export function defaultStrategies(testFraction = 0.25, seed = 12345): SplitConfig[] {
  return [
    { kind: 'random', label: 'Random holdout', test_fraction: testFraction, seed },
    { kind: 'stratified', label: 'Stratified holdout', test_fraction: testFraction, seed },
    { kind: 'group', label: 'Group holdout', test_fraction: testFraction, seed },
    { kind: 'chronological', label: 'Chronological holdout', test_fraction: testFraction, seed },
  ]
}
