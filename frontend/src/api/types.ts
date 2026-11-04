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

/** S5: user-declared prediction-time availability of one feature column. */
export type AvailabilityLevel =
  | 'before_prediction'
  | 'at_prediction'
  | 'after_prediction'
  | 'unknown'

export interface PreprocessingStep {
  name: string
  kind: string
  columns: string[]
  fit_context: 'train_only' | 'full_dataset' | 'unknown' | 'not_recorded'
}

export interface PreprocessingDeclaration {
  steps: PreprocessingStep[]
  note: string | null
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
  /** S5 declarations: never inferred, never fabricated by the UI. */
  feature_availability: Record<string, AvailabilityLevel>
  derived_feature_dependencies: Record<string, string[]>
  temporal_horizon_days: number | null
  temporal_horizon_note: string | null
  preprocessing: PreprocessingDeclaration | null
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
  risk_scorecard: RiskScorecard | null
}

/** F06 — category-based risk scorecard derived from one audit's outcomes. */
export type ScorecardStatus =
  | 'finding_present'
  | 'evaluated_no_finding'
  | 'error'
  | 'not_applicable'
  | 'not_checked'

export interface ScorecardRule {
  rule_id: string
  title: string
  status: 'evaluated' | 'disabled' | 'not_evaluated' | 'unsupported' | 'insufficient_data' | 'error'
  finding_count: number
  max_severity: Finding['severity'] | null
  not_evaluated_reason: string | null
}

export interface ScorecardCategory {
  key: string
  label: string
  status: ScorecardStatus
  finding_count: number
  max_severity: Finding['severity'] | null
  affected_rows: number | null
  rules: ScorecardRule[]
}

export interface RiskScorecard {
  categories: ScorecardCategory[]
  note: string
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
  plans: PlanComparison[]
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

export interface SimilarityPair {
  train_row_id: string
  test_row_id: string
  distance: number
  top_diffs: Array<{ column: string; scaled_diff: string; train_value: string; test_value: string }>
  train_values: Record<string, string>
  test_values: Record<string, string>
}

export interface SimilarityResponse {
  pairs: SimilarityPair[]
  pairs_total_available: number
  pairs_truncated: boolean
  method: string
  scaling: Record<string, string>
  split: Record<string, string>
  populations: Record<string, number>
  nearest_neighbour_summary: Record<string, number>
  nn_histogram: number[]
  nn_histogram_edges: number[]
  sampling: string
  limitations: string[]
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

export interface PlanConfig {
  kind: 'repeated_stratified_cv' | 'group_cv' | 'rolling_origin'
  label: string
  n_folds: number
  repeats: number
  gap: number
  plan_id?: string | null
}

export interface PlanFoldFacts {
  fold_index: number
  repeat: number
  train_rows: number
  test_rows: number
  exact_duplicate_test_rows: number | null
  entity_shared_groups: number | null
  entity_overlap_test_share: number | null
  chronology_status: string | null
  findings_by_rule: Record<string, number>
  findings_total: number
  duration_ms: number
}

export interface PlanComparison {
  plan_id: string
  kind: string
  label: string
  n_folds: number
  repeats: number
  gap: number
  seed: number | null
  supported: boolean
  unsupported_reason: string | null
  notes: string[]
  folds: PlanFoldFacts[]
  aggregate: {
    folds_audited?: number
    folds_with_findings?: number
    max_findings_in_one_fold?: number
    findings_by_rule_total?: Record<string, number>
    folds_with_chronology_violation?: number
    mean_entity_overlap_test_share?: number | null
    max_entity_overlap_test_share?: number | null
    mean_test_fraction?: number | null
  }
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


// --------------------------------------------------------------------------
// S3 research workspace
// --------------------------------------------------------------------------

export type ResearchRole =
  | 'entity'
  | 'timestamp'
  | 'split'
  | 'target'
  | 'predictor'
  | 'treatment'
  | 'confounder'
  | 'mediator'
  | 'effect_modifier'
  | 'instrument'
  | 'sensitive'
  | 'future_only'
  | 'excluded'

export interface StudyField {
  name: string
  label: string
  section: string
  required: boolean
  help: string
  kind: 'text' | 'longtext' | 'select'
  value: string | string[] | null
  declared: boolean
  provenance: 'user_declared' | 'missing'
}

export interface StudyCompletion {
  required: number
  declared: number
  ratio: number
  missing: string[]
  note: string
}

export interface StudyIssue {
  code: string
  severity: 'error' | 'warning' | 'info'
  field?: string
  column?: string | null
  message: string
  hint?: string | null
}

export interface StudyResponse {
  study_id: string
  dataset_id: string
  dataset_name: string
  schema_version: string
  revision: number
  created_at_utc: string
  updated_at_utc: string
  card: Record<string, unknown>
  completion: StudyCompletion
  fields: StudyField[]
  issues: StudyIssue[]
  provenance: {
    declared: string[]
    missing: string[]
    computed: string[]
    inferred: string[]
    note: string
  }
  roles: {
    assignments: Record<string, ResearchRole[]>
    derived_roles: ColumnRoles
    ok: boolean
    issues: StudyIssue[]
    errors: number
    warnings: number
    note: string
  }
  split_values: { train: string | null; test: string | null }
  column_declarations: Record<string, Record<string, string | null>>
  select_options: Record<string, Array<{ value: string; label: string }>>
  storage_note: string
  app: { name: string; version: string }
  roles_seeded_from?: string | null
}

export interface ProfileNumeric {
  count: number
  min: number
  max: number
  mean: number
  median: number
  std: number
  q1: number
  q3: number
  outlier_candidates: number
  outlier_rule: string
}

export interface ProfileDatetime {
  parsed: number
  unparsed: number
  parse_ratio: number
  min_utc: string
  max_utc: string
  span_days: number
}

export interface ProfileColumn {
  column: string
  detected_type: string
  detected_type_reason: string
  declared_type: string | null
  description: string | null
  unit: string | null
  measurement_scale: string | null
  roles: ResearchRole[]
  missing_count: number
  missing_ratio: number
  distinct_count: number
  distinct_ratio: number
  examples: string[]
  numeric_parse_ratio: number
  datetime_parse_ratio: number
  unparsed_numeric_cells: number
  numeric: ProfileNumeric | null
  datetime: ProfileDatetime | null
  flags: string[]
}

export interface ProfileResponse {
  dataset: {
    dataset_id: string
    dataset_name?: string
    name: string
    row_count: number
    column_count: number
    fingerprint_sha256: string
    is_synthetic: boolean
    duplicate_rows: number
    duplicate_row_groups: number
    duplicate_example_row_ids: string[]
    numeric_columns: number
    datetime_columns: number
  }
  columns: ProfileColumn[]
  summary: {
    constant_columns: string[]
    all_missing_columns: string[]
    identifier_like_columns: string[]
    mixed_type_columns: string[]
    columns_with_outlier_candidates: string[]
  }
  warnings: string[]
  conventions: string[]
  notes: string[]
}

export interface DictionaryResponse {
  dataset_id: string
  dataset_name: string
  columns: ProfileColumn[]
  assignments: Record<string, ResearchRole[]>
  summary: ProfileResponse['summary']
  conventions: string[]
  note: string
}

export interface RoleMapResponse {
  ok: boolean
  errors: number
  warnings: number
  issues: StudyIssue[]
  derived_roles: ColumnRoles
  assignments: Record<string, ResearchRole[]>
  study: StudyResponse
}

export interface ManifestCheck {
  name: string
  ok: boolean
  expected: string | null
  actual: string | null
  message: string
}

export interface ManifestValidation {
  status: 'match' | 'dataset_mismatch' | 'schema_mismatch' | 'unsupported_version' | 'malformed'
  ok: boolean
  message: string
  checks: ManifestCheck[]
  study?: Record<string, unknown> | null
  applied?: boolean
  study_state?: StudyResponse
}

export interface ManifestResponse {
  manifest_schema_version: string
  study_schema_version: string
  created_at_utc: string
  application: { name: string; version: string }
  study: Record<string, unknown>
  dataset: {
    name: string
    source: string
    is_synthetic: boolean
    sha256: string
    rows: number
    columns: number
    encoding: string
    row_id_scheme: string
    schema_fingerprint: string
  }
  roles: {
    assignments: Record<string, ResearchRole[]>
    derived_column_roles: ColumnRoles
    role_validation: { ok: boolean; errors: number; warnings: number }
  }
  analysis: Record<string, unknown>
  exclusions: Record<string, unknown>
  warnings: string[]
  integrity: { raw_data_embedded: boolean; cell_values_embedded: boolean }
}

// --------------------------------------------------------------------------
// S4 Scientific Visual Explorer
// --------------------------------------------------------------------------

export interface ExploreDatasetIdentity {
  dataset_id: string
  name: string
  source: 'demo' | 'upload'
  is_synthetic: boolean
  fingerprint_sha256: string
  row_count: number
  column_count: number
  demo_id: string | null
}

export interface ExploreNumericSummary {
  missing_count: number
  unparsed_count: number
  valid_count: number
  min?: number
  max?: number
  mean?: number
  median?: number
  all_integer?: boolean
}

export interface ExploreTextSummary {
  missing_count: number
  distinct: number
  top_levels: Array<{ value: string; count: number }>
}

export interface ExploreColumn {
  name: string
  detected_type: 'numeric' | 'integer' | 'categorical' | 'boolean' | 'datetime' | 'identifier' | 'text' | 'empty'
  roles: string[]
  numeric?: ExploreNumericSummary
  text?: ExploreTextSummary
}

export interface ExploreSchema {
  dataset: ExploreDatasetIdentity
  row_id_scheme: string
  row_count: number
  columns: ExploreColumn[]
  numeric_columns: string[]
  color_candidates: string[]
  suggested_color_column: string | null
  split: { column: string; train_value: string | null; test_value: string | null } | null
}

export interface ExploreScale {
  numeric: boolean
  min: number | null
  max: number | null
  valid_count: number
  missing_count: number
  unparsed_count: number
}

export interface SeriesRow {
  id: string
  index: number
  values: Record<string, number | string | null>
}

export interface SeriesResponse {
  dataset_id: string
  columns: string[]
  population: number
  filtered_population: number
  filters_active: boolean
  drawn_rows: number
  sampling: { method: string; stride: number; description: string }
  scale: Record<string, ExploreScale>
  rows: SeriesRow[]
}

export type BrushPredicate =
  | { column: string; kind: 'range'; min: number; max: number }
  | { column: string; kind: 'values'; values: string[] }

export interface SelectionResponse {
  dataset_id: string
  population: number
  total_selected: number
  ids_truncated: boolean
  row_ids: string[]
  predicates: Array<Record<string, unknown>>
}

export interface CorrelationCell {
  x: string
  y: string
  method: string
  coefficient: number | null
  n_valid: number
  missing_policy: string
  warning: string | null
}

export interface CorrelationResponse {
  method: string
  columns: string[]
  cells: CorrelationCell[]
  min_pairs: number
  warnings: string[]
  population: number
  note: string
}

export interface BoxStatsDto {
  n: number
  q1: number
  median: number
  q3: number
  whisker_low: number
  whisker_high: number
  iqr: number
  outlier_count: number
  outlier_examples: number[]
  definition: string
}

export interface DistributionGroup {
  group: string
  rows: number
  bins?: number[]
  counts?: number[]
  valid_count?: number
  missing_count?: number
  unparsed_count?: number
  box?: BoxStatsDto | null
  levels?: Array<{ value: string; count: number }>
  other_count?: number
  distinct?: number
}

export interface DistributionResponse {
  column: string
  kind: 'numeric' | 'categorical'
  bins?: number[]
  counts?: number[]
  valid_count?: number
  missing_count?: number
  unparsed_count?: number
  population: number
  box?: BoxStatsDto | null
  levels?: Array<{ value: string; count: number }>
  other_count?: number
  distinct?: number
  group_by: string | null
  groups?: DistributionGroup[]
  selection?: SelectionOverlay
  filters_note?: string
}

export interface MissingnessColumn {
  column: string
  missing_count: number
  missing_pct: number
}

export interface MissingnessResponse {
  columns: string[]
  per_column: MissingnessColumn[]
  population: number
  matrix: {
    rows: Array<{ id: string; cells: number[] }>
    row_count_drawn: number
    stride: number
    method: string
    description: string
  }
  policy: string
  group_by: string | null
  groups?: Array<{ group: string; rows: number; per_column: MissingnessColumn[] }>
  population_counts?: MissingnessColumn[]
  population_total?: number
  filters_note?: string
}

export interface RowsResponse {
  dataset_id: string
  columns: string[]
  rows: Array<{ id: string; index: number; values: Record<string, string> }>
  unknown_ids: string[]
  population: number
}

export interface SelectionOverlay {
  counts?: number[]
  valid_count?: number
  missing_count?: number
  unparsed_count?: number
  population: number
  box?: BoxStatsDto | null
}

// --------------------------------------------------------------------------
// S6 Model Lab — statistical workbench (F09)
// --------------------------------------------------------------------------

export type StatisticsTask = 'ols' | 'logistic'

export interface StatisticsRequest {
  task: StatisticsTask
  outcome: string
  predictors: string[]
  missing_policy: 'complete_case' | 'fail'
  intercept: boolean
  positive_level: string | null
  categorical_references: Record<string, string>
  alpha: number
}

export interface StatisticalCoefficient {
  term: string
  kind: 'intercept' | 'coefficient'
  estimate: number
  std_error: number
  ci_low: number
  ci_high: number
  statistic: number | null
  p_value: number | null
  odds_ratio?: number
  odds_ratio_ci_low?: number
  odds_ratio_ci_high?: number
}

export interface ModelWarning {
  code: string
  severity: 'low' | 'medium' | 'high'
  message: string
}

export interface StatisticalModelResult {
  run_id: string
  created_at_utc: string
  kind: 'statistical_model'
  task: StatisticsTask
  specification: {
    task: StatisticsTask
    task_label: string
    outcome: string
    predictors: string[]
    intercept: boolean
    missing_policy: 'complete_case' | 'fail'
    alpha: number
    positive_level: string | null
    formula: string
    coding: Array<{
      column: string
      kind: 'continuous' | 'categorical'
      reference: string | null
      levels: string[] | null
      missing_count: number
      unparsable_count: number
    }>
    outcome_coding: {
      kind: 'continuous' | 'binary'
      positive_level: string | null
      negative_level?: string | null
      levels: string[] | null
      positive_count?: number
      negative_count?: number
      missing_count: number
      unparsable_count: number
    }
    notes: string[]
  }
  dataset: {
    dataset_id: string
    name: string
    sha256: string
    row_count: number
    column_count: number
  }
  population: {
    rows_total: number
    analyzed: number
    excluded: number
    excluded_missing_by_column: Record<string, number>
    policy: 'complete_case' | 'fail'
    complete_case_note: string
  }
  coefficients: StatisticalCoefficient[]
  fit: {
    n: number
    method: string
    df_model?: number
    df_resid?: number
    r_squared?: number
    adjusted_r_squared?: number
    f_statistic?: number | null
    f_p_value?: number | null
    sigma?: number | null
    log_likelihood?: number
    null_log_likelihood?: number
    likelihood_ratio?: number
    likelihood_ratio_p_value?: number | null
    mcfadden_pseudo_r_squared?: number
    aic?: number
    bic?: number
    converged?: boolean
  }
  diagnostics: {
    vif: Array<{ term: string; vif: number | null; note?: string }>
    condition_number: number
    sample: {
      method: string
      stride: number
      drawn_rows: number
      analyzed_rows: number
      description: string
      rows: Array<{
        row_id: string
        observed: number
        fitted: number
        residual?: number
        probability?: number
      }>
    }
    residual_summary?: Record<string, number | null>
    fitted_summary?: Record<string, number | null>
    probability_summary?: Record<string, number | null>
  }
  warnings: ModelWarning[]
  versions: Record<string, string>
}

export interface ModelRunListResponse {
  dataset_id: string
  runs: Array<{
    run_id: string
    kind: string
    dataset_id: string
    label: string
    created_seconds_ago: number
  }>
  note: string
}

// --------------------------------------------------------------------------
// S6 Model Lab — predictive evaluation (F10)
// --------------------------------------------------------------------------

export type PredictionTask = 'classification' | 'regression'
export type GeneratedSplitStrategy = 'random' | 'stratified' | 'group' | 'chronological'

export interface PredictionRequest {
  task: PredictionTask
  outcome: string
  predictors: string[]
  positive_level: string | null
  split_source: 'existing' | 'generated'
  split_strategy: GeneratedSplitStrategy
  test_fraction: number
  seed: number
  validation_fraction: number
  models: string[]
  subgroup_column: string | null
  subgroup_bins: number[]
}

export interface PredictionCandidate {
  family: string
  label: string
  status: 'fitted' | 'failed'
  selection_metric?: string
  selection_score?: number
  validation?: Record<string, number>
  parameters?: Record<string, unknown>
  error?: string
}

export interface PredictionPerClass {
  label: string
  support: number
  predicted: number
  precision: number | null
  recall: number | null
  f1: number | null
  accuracy: number | null
}

export interface PredictionPrCurve {
  precision: number[]
  recall: number[]
  average_precision: number | null
  positive_count: number | null
  negative_count: number | null
  prevalence: number | null
  n_points: number
  method: string
}

export interface PredictionCalibrationEntry {
  bin_low: number
  bin_high: number
  count: number
  mean_predicted: number | null
  observed_rate: number | null
  observed_rate_low?: number | null
  observed_rate_high?: number | null
}

export interface PredictionCalibrationSummary {
  n: number
  bins: number
  prevalence: number | null
  brier_score: number | null
  expected_calibration_error: number
  max_calibration_error: number
  rows_in_bins: number
  method: string
  note: string
}

export interface PredictionQq {
  applicable: boolean
  reason?: string
  partition?: string
  n: number
  plotted_points?: number
  theoretical?: number[]
  sample?: number[]
  reference_intercept?: number
  reference_slope?: number
  method?: string
  note?: string
}

export interface PredictionInfluencePoint {
  row_id: string
  fitted: number
  residual: number
  leverage: number
  standardized_residual: number
  cooks_distance: number
}

export interface PredictionInfluenceCoefficient {
  term: string
  estimate: number
  std_error: number | null
  ci_low: number | null
  ci_high: number | null
  statistic: number | null
  p_value: number | null
}

export interface PredictionInfluence {
  applicable: boolean
  reason?: string
  partition?: string
  model?: string
  n?: number
  parameters?: number
  residual_df?: number
  rank?: number
  condition_number?: number | null
  thresholds?: Record<string, number>
  counts?: Record<string, number>
  max_leverage?: number
  max_cooks?: number
  coefficients?: PredictionInfluenceCoefficient[]
  points?: PredictionInfluencePoint[]
  top_influence?: PredictionInfluencePoint[]
  method?: string
  note?: string
}

export interface PredictionImportanceRow {
  feature: string
  importance_mean: number
  importance_sd: number | null
}

export interface PredictionImportance {
  applicable: boolean
  reason?: string
  partition?: string
  n?: number
  repeats?: number
  metric?: string
  baseline_score?: number
  rows?: PredictionImportanceRow[]
  method?: string
  note?: string
}

export interface PredictionSubgroupRow {
  group: string
  n: number
  metric_denominator?: number
  share: number
  metric_name?: string
  metric: number | null
  ci_low?: number | null
  ci_high?: number | null
  ci_level?: number
  ci_method?: string | null
  outcome_mean?: number
  outcome_measure?: string
  positive_count?: number | null
  negative_count?: number | null
  correct?: number | null
  warning: string | null
}

export interface PredictionSubgroup {
  column: string
  partition: 'test'
  test_rows: number
  grouped_rows: number
  outside_bins: number
  minimum_recommended_rows: number
  interval_level?: number
  outcome_measure?: string
  comparison_note?: string
  rows: PredictionSubgroupRow[]
  note: string
}

export interface PredictionMetrics {
  n: number
  accuracy?: number
  balanced_accuracy?: number | null
  roc_auc?: number | null
  pr_auc?: number | null
  average_precision?: number | null
  pr_auc_definition?: string
  prevalence?: number | null
  positive_count?: number | null
  negative_count?: number | null
  classes?: string[]
  confusion_matrix?: number[][]
  per_class?: PredictionPerClass[]
  pr_curve?: PredictionPrCurve | null
  mae?: number
  rmse?: number
  r2?: number | null
  residual_summary?: Record<string, number | null>
  undefined: Array<{ metric: string; reason: string }>
}

export interface PredictionResult {
  run_id: string
  created_at_utc: string
  kind: 'prediction_model'
  task: PredictionTask
  specification: {
    task: PredictionTask
    outcome: string
    predictors: string[]
    positive_level: string | null
    subgroup_column: string | null
    subgroup_bins: number[]
    seed: number
    validation_fraction: number
    selection_rule: string
    test_evaluations: number
    notes: string[]
  }
  dataset: {
    dataset_id: string
    name: string
    sha256: string
    row_count: number
    column_count: number
  }
  split: {
    source: 'existing' | 'generated'
    strategy: string
    seed: number | null
    summary: Record<string, unknown>
    partitions: { fit: number; validation: number; test: number }
    partition_row_ids_sha256: Record<string, string>
    test_row_ids_sha256: string
  }
  outcome: {
    kind: 'classification' | 'regression'
    labels?: string[]
    positive_level?: string | null
    positive_class?: string
    positive_index?: number
    class_counts?: Record<string, number>
    mean?: number
    std?: number
    missing_count?: number
  }
  design: {
    numeric: string[]
    categorical: string[]
    missing_by_column: Record<string, number>
    categorical_levels: Record<string, string[]>
    preprocessing: {
      numeric: string
      categorical: string
      fit_partition: string
      learned_on_rows: number
      learned: {
        numeric_medians: Record<string, number>
        categorical_modes: Record<string, string | null>
      }
    }
  }
  candidates: PredictionCandidate[]
  selected: {
    family: string
    label: string
    validation: { metric: string; score: number; accuracy?: number; mae?: number }
    parameters: Record<string, unknown>
    refit_rows: number
  }
  evaluation: {
    partition: 'test'
    n: number
    metrics: PredictionMetrics
    diagnostics: {
      partition?: string
      confusion_matrix?: number[][]
      per_class?: PredictionPerClass[]
      roc_curve?: {
        fpr: number[]
        tpr: number[]
        thresholds: number[]
        auc: number
      } | null
      pr_curve?: PredictionPrCurve | null
      calibration?: PredictionCalibrationEntry[] | null
      calibration_summary?: PredictionCalibrationSummary | null
      qq?: PredictionQq | null
      influence?: PredictionInfluence | null
      permutation_importance?: PredictionImportance | null
      errors?: Array<{
        row_id: string
        observed: string
        predicted: string
        probability_positive: number | null
      }>
      error_count?: number
      sample?: {
        method: string
        stride: number
        drawn_rows: number
        test_rows: number
        description: string
        rows: Array<{
          row_id: string
          observed: number
          predicted: number
          residual: number
        }>
      }
      residual_summary?: Record<string, number | null>
      undefined: Array<{ metric: string; reason: string }>
    }
    predictions: {
      rows: Array<{
        row_id: string
        observed: string | number
        predicted: string | number
        probability_positive?: number | null
      }>
      test_rows: number
      truncated: boolean
      cap: number
    }
  }
  subgroups: PredictionSubgroup | null
  warnings: ModelWarning[]
  versions: Record<string, string>
}
