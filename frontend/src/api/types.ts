/**
 * TypeScript mirrors of the backend response contracts.
 *
 * These are hand-maintained. `docs/openapi.json` (regenerated with
 * `python scripts/export_openapi.py`) is the authoritative contract, and
 * `npm run typecheck` catches a mismatch in any field the UI reads.
 * Only fields the UI uses are declared; the API returns more.
 */

export type Severity = 'high' | 'medium' | 'low' | 'info'

export type CheckStatus =
  | 'disabled'
  | 'not_evaluated'
  | 'unsupported'
  | 'insufficient_data'
  | 'error'

export interface Count {
  label: string
  affected: number
  denominator: number
  unit: 'rows' | 'groups' | 'signatures' | 'columns' | 'pairs' | 'values'
  scope: string
  note: string | null
}

export interface EvidenceExample {
  label: string
  row_ids: string[]
  details: Record<string, string>
}

export interface Finding {
  rule_id: string
  title: string
  severity: Severity
  severity_rationale: string
  description: string
  evidence_summary: string
  counts: Count[]
  examples: EvidenceExample[]
  example_total: number
  examples_truncated: boolean
  recommended_action: string
  limitations: string[]
  assumptions: string[]
}

export interface NotEvaluatedCheck {
  rule_id: string
  title: string
  status: CheckStatus
  reason: string
  details: Record<string, string>
}

export interface RuleMetric {
  key: string
  label: string
  value: number | string
  unit: string | null
}

export interface RuleOutcome {
  rule_id: string
  title: string
  status: 'evaluated' | CheckStatus
  duration_ms: number
  findings: Finding[]
  metrics: RuleMetric[]
  not_evaluated: NotEvaluatedCheck | null
}

export interface ColumnTypeInfo {
  name: string
  numeric_parse_ratio: number
  datetime_parse_ratio: number
  distinct_values: number
  missing_count: number
  missing_ratio: number
  looks_numeric: boolean
  looks_datetime: boolean
  looks_identifier: boolean
  example_values: string[]
}

export interface DatasetSummary {
  dataset_id: string
  name: string
  source: 'upload' | 'demo'
  is_synthetic: boolean
  fingerprint_sha256: string
  row_count: number
  column_count: number
  columns: string[]
  created_at_utc: string
  demo_id: string | null
  warnings: string[]
}

export interface ColumnRoles {
  features: string[]
  target: string | null
  entity: string | null
  timestamp: string | null
  split: string | null
  split_train_value: string | null
  split_test_value: string | null
  metadata_excluded: string[]
}

export interface ResolvedRoles {
  feature_columns: string[]
  target_column: string | null
  entity_column: string | null
  timestamp_column: string | null
  split_column: string | null
  train_value: string | null
  test_value: string | null
  metadata_excluded: string[]
  unused_columns: string[]
}

export interface RoleIssue {
  code: string
  message: string
  severity: 'error' | 'warning'
  column: string | null
  hint: string | null
}

export interface RoleValidationResult {
  roles: ColumnRoles
  ok: boolean
  issues: RoleIssue[]
  resolved: ResolvedRoles | null
}

export interface NearDuplicateSettings {
  enabled: boolean
  threshold: number
  scaling: 'robust' | 'none'
  min_numeric_ratio: number
  max_missing_fraction_per_row: number
  oversize_policy: 'sample' | 'skip'
  max_combined_rows: number
  sample_seed: number
}

export interface AuditConfig {
  enable_exact_duplicates: boolean
  enable_entity_overlap: boolean
  enable_chronology: boolean
  enable_target_copy: boolean
  near_duplicates: NearDuplicateSettings
  strip_whitespace: boolean
  normalize_numeric_strings: boolean
  missing_tokens: string[]
  chronology_intent: 'future_prediction' | 'not_applicable'
  entity_overlap_high_test_share: number
  chronology_high_train_share: number
  target_copy_min_coverage: number
  target_copy_high_coverage: number
  target_copy_baseline_margin: number
  target_copy_min_comparable_rows: number
  max_examples: number
  max_example_rows_per_example: number
}

export interface SplitSummary {
  strategy_id: string
  label: string
  kind: 'existing' | 'random' | 'stratified' | 'group' | 'chronological'
  requested_test_fraction: number | null
  achieved_test_fraction: number
  train_rows: number
  test_rows: number
  seed: number | null
  split_column: string | null
  train_value: string | null
  test_value: string | null
  proportion_note: string | null
  notes: string[]
  assignment_id: string | null
}

export interface SplitCounts {
  train_rows: number
  test_rows: number
  total_rows: number
}

export interface ColumnMissingness {
  column: string
  train_missing: number
  train_missing_ratio: number
  test_missing: number
  test_missing_ratio: number
  missing_ratio_gap: number
}

export interface CategoryShare {
  category: string
  train_count: number
  train_ratio: number
  test_count: number
  test_ratio: number
  ratio_gap: number
  is_other_bucket: boolean
}

export interface DistributionSummary {
  column: string
  kind: 'categorical' | 'continuous' | 'not_available'
  categories: CategoryShare[]
  train_missing: number
  test_missing: number
  max_abs_ratio_gap: number | null
  train_stats: Record<string, number>
  test_stats: Record<string, number>
  histogram_edges: number[]
  train_histogram: number[]
  test_histogram: number[]
  note: string | null
}

export interface Diagnostics {
  counts: SplitCounts
  missingness: ColumnMissingness[]
  missingness_note: string
  target: DistributionSummary | null
  disclaimer: string
}

export interface EvaluationSummary {
  evaluated_rule_ids: string[]
  not_evaluated: NotEvaluatedCheck[]
  findings_total: number
  findings_by_severity: Record<string, number>
  headline: string
}

export interface AuditResult {
  schema_version: string
  app_version: string
  generated_at_utc: string
  duration_ms: number
  audit_config: AuditConfig
  roles: ColumnRoles
  resolved_roles: ResolvedRoles
  dataset: DatasetSummary
  split: SplitSummary
  evaluation: EvaluationSummary
  findings: Finding[]
  rule_outcomes: RuleOutcome[]
  diagnostics: Diagnostics
  audit_limits: Record<string, unknown>
  limitations: string[]
  assumptions: string[]
}

export interface ComparisonRow {
  strategy_id: string
  label: string
  kind: string
  supported: boolean
  unsupported_reason: string | null
  requested_test_fraction: number | null
  achieved_test_fraction: number | null
  train_rows: number
  test_rows: number
  proportion_note: string | null
  exact_duplicate_test_rows: number | null
  exact_duplicate_test_share: number | null
  entity_shared_groups: number | null
  entity_overlap_test_share: number | null
  chronology_status: string | null
  target_summary: string | null
  target_max_abs_ratio_gap: number | null
  finding_counts: Record<string, number>
  not_evaluated: NotEvaluatedCheck[]
  notes: string[]
}

export interface ComparisonResult {
  schema_version: string
  app_version: string
  generated_at_utc: string
  duration_ms: number
  dataset: DatasetSummary
  roles: ColumnRoles
  resolved_roles: ResolvedRoles
  audit_config: AuditConfig
  strategies: unknown[]
  rows: ComparisonRow[]
  per_strategy_findings: Record<string, Finding[]>
  selection_note: string
  limitations: string[]
}

export interface SplitConfig {
  kind: 'existing' | 'random' | 'stratified' | 'group' | 'chronological'
  label: string
  test_fraction: number
  seed: number
  strategy_id?: string | null
}

export interface CheckCatalogueEntry {
  rule_id: string
  title: string
  category: string
  default_enabled: boolean
  requires: string[]
  summary: string
  detects: string[]
  does_not_detect: string[]
}

export interface ChecksResponse {
  checks: CheckCatalogueEntry[]
  what_this_app_does_not_do: string[]
  no_findings_means: string
}

export interface DemoPayload {
  demo_id: string
  title: string
  subtitle: string
  filename: string
  synthetic: boolean
  is_control: boolean
  seed: number
  row_count: number
  column_count: number
  columns: string[]
  sha256: string
  teaching_point: string
  generation_method: string
  expected_findings: Array<{ rule_id: string; severity: string; why: string }>
  recommended_audit: Record<string, unknown>
  recommended_split: SplitConfig | null
  planted_cases: Array<Record<string, unknown>>
  summary_metrics: Record<string, unknown>
  notes: string[]
  file_present: boolean
}

export interface DemoListResponse {
  demos: DemoPayload[]
  featured_journey: { demo_id: string; title: string; steps: string[] }
}

export interface DatasetLoadedResponse {
  dataset: DatasetSummary
  column_types: Record<string, ColumnTypeInfo>
  suggested_roles: ColumnRoles
  suggested_roles_confidence: string
  role_suggestions: {
    reasons?: Record<string, string>
    metadata_columns?: string[]
    metadata_reason?: string
    feature_count?: number
    features_not_suggested?: string[]
    roles_detected?: number
    note?: string
  }
  validation: RoleValidationResult
  dataset_limits: Record<string, number>
  demo: DemoPayload | null
  recommended_audit_config: AuditConfig | null
  recommended_split: SplitConfig | null
}

export interface PreviewResponse {
  dataset_id: string
  columns: string[]
  row_ids: string[]
  rows: string[][]
  offset: number
  limit: number
  total_rows: number
  truncated_columns: boolean
  note: string
}

export interface HealthResponse {
  status: 'ok'
  app_name: string
  app_version: string
  audit_schema_version: string
  server_time_utc: string
  limits: Record<string, number>
  store: {
    datasets: number
    runs: number
    assignments: number
    total_bytes: number
    evictions: number
    expirations: number
    limits: Record<string, number>
  }
  storage_note: string
}

export interface AuditResponse {
  run_id: string
  result: AuditResult
  export_hint: string
  /** Present when the audit used a split generated now rather than one read from the file. */
  assignment: AssignmentHandle | null
}

export interface AssignmentHandle {
  strategy_id: string
  assignment_id: string
  label: string
  kind: string
  train_rows: number
  test_rows: number
  download_path: string
}

export interface ColumnValueCount {
  value: string
  count: number
}

export interface ColumnValuesResponse {
  dataset_id: string
  column: string
  total_rows: number
  distinct_count: number
  missing_count: number
  values: ColumnValueCount[]
  truncated: boolean
  note: string
}

export interface CompareResponse {
  run_id: string
  result: ComparisonResult
  assignments: AssignmentHandle[]
  sanitization_note: string
  selection_note: string
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}
