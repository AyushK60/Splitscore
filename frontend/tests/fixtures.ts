/**
 * Small typed fixtures for the component tests.
 *
 * Every value here is written by hand against the API contract in
 * `src/api/types.ts`; nothing is produced by calling the code under test, and no
 * fixture is copied from a live response. The numbers are deliberately trivial
 * (for example 2 shared entities out of 4) so the expectations in the tests can
 * be read directly from the fixture.
 */
import type {
  AuditResponse,
  ChecksResponse,
  ColumnRoles,
  ColumnTypeInfo,
  ColumnValuesResponse,
  CompareResponse,
  DatasetLoadedResponse,
  DatasetSummary,
  DemoListResponse,
  Diagnostics,
  EvaluationSummary,
  Finding,
  HealthResponse,
  NotEvaluatedCheck,
  PreviewResponse,
  ResolvedRoles,
  RoleValidationResult,
  RuleOutcome,
  SplitSummary,
} from '../src/api/types'
import { DEFAULT_AUDIT_CONFIG } from '../src/lib/defaults'

export const COLUMNS = ['customer_id', 'tenure_months', 'monthly_spend', 'churned', 'split'] as const

export function rolesFixture(overrides: Partial<ColumnRoles> = {}): ColumnRoles {
  return {
    features: ['tenure_months', 'monthly_spend'],
    target: 'churned',
    entity: 'customer_id',
    timestamp: null,
    split: 'split',
    split_train_value: 'train',
    split_test_value: 'test',
    metadata_excluded: [],
    ...overrides,
  }
}

export function columnTypesFixture(): Record<string, ColumnTypeInfo> {
  const numeric = (name: string): ColumnTypeInfo => ({
    name,
    numeric_parse_ratio: 1,
    datetime_parse_ratio: 0,
    distinct_values: 20,
    missing_count: 0,
    missing_ratio: 0,
    looks_numeric: true,
    looks_datetime: false,
    looks_identifier: false,
    example_values: ['1', '2', '3'],
  })
  return {
    customer_id: {
      name: 'customer_id',
      numeric_parse_ratio: 0,
      datetime_parse_ratio: 0,
      distinct_values: 4,
      missing_count: 0,
      missing_ratio: 0,
      looks_numeric: false,
      looks_datetime: false,
      looks_identifier: true,
      example_values: ['C-1', 'C-2', 'C-3'],
    },
    tenure_months: numeric('tenure_months'),
    monthly_spend: numeric('monthly_spend'),
    churned: {
      name: 'churned',
      numeric_parse_ratio: 0,
      datetime_parse_ratio: 0,
      distinct_values: 2,
      missing_count: 0,
      missing_ratio: 0,
      looks_numeric: false,
      looks_datetime: false,
      looks_identifier: false,
      example_values: ['no', 'yes', 'no'],
    },
    split: {
      name: 'split',
      numeric_parse_ratio: 0,
      datetime_parse_ratio: 0,
      distinct_values: 2,
      missing_count: 0,
      missing_ratio: 0,
      looks_numeric: false,
      looks_datetime: false,
      looks_identifier: false,
      example_values: ['train', 'test', 'test'],
    },
  }
}

export function datasetSummaryFixture(overrides: Partial<DatasetSummary> = {}): DatasetSummary {
  return {
    dataset_id: 'ds-fixture-a',
    name: 'fixture.csv',
    source: 'demo',
    is_synthetic: true,
    fingerprint_sha256: 'f'.repeat(64),
    row_count: 40,
    column_count: COLUMNS.length,
    columns: [...COLUMNS],
    created_at_utc: '2026-01-01T00:00:00+00:00',
    demo_id: 'fixture_demo',
    warnings: [],
    ...overrides,
  }
}

export function resolvedRolesFixture(): ResolvedRoles {
  return {
    feature_columns: ['tenure_months', 'monthly_spend'],
    target_column: 'churned',
    entity_column: 'customer_id',
    timestamp_column: null,
    split_column: 'split',
    train_value: 'train',
    test_value: 'test',
    metadata_excluded: [],
    unused_columns: [],
  }
}

export function validationFixture(overrides: Partial<RoleValidationResult> = {}): RoleValidationResult {
  return {
    roles: rolesFixture(),
    ok: true,
    issues: [],
    resolved: resolvedRolesFixture(),
    ...overrides,
  }
}

export function loadedFixture(overrides: Partial<DatasetLoadedResponse> = {}): DatasetLoadedResponse {
  return {
    dataset: datasetSummaryFixture(),
    column_types: columnTypesFixture(),
    suggested_roles: rolesFixture(),
    suggested_roles_confidence: 'recommended',
    role_suggestions: { feature_count: 2 },
    validation: validationFixture(),
    dataset_limits: { max_rows: 10_000, max_columns: 100 },
    demo: null,
    recommended_audit_config: DEFAULT_AUDIT_CONFIG,
    recommended_split: null,
    ...overrides,
  }
}

export function findingFixture(overrides: Partial<Finding> = {}): Finding {
  return {
    rule_id: 'SS-ENT-001',
    title: 'Entity overlap between train and test splits',
    severity: 'high',
    severity_rationale: 'Fixture rationale: many test rows belong to a training entity.',
    description: 'Fixture description of the observed overlap.',
    evidence_summary: '2 entity value(s) are shared between the splits, covering 3 test row(s).',
    counts: [
      {
        label: 'Shared entity values',
        affected: 2,
        denominator: 4,
        unit: 'values',
        scope: 'full split',
        note: null,
      },
    ],
    examples: [
      {
        label: 'C-1',
        row_ids: ['row-000001', 'row-000002'],
        details: { side: 'both splits' },
      },
    ],
    example_total: 2,
    examples_truncated: false,
    recommended_action: 'Use a group holdout on the entity column.',
    limitations: ['Fixture limitation: the entity column must be trustworthy.'],
    assumptions: ['Fixture assumption: each row belongs to exactly one entity.'],
    ...overrides,
  }
}

export function notEvaluatedFixture(
  ruleId = 'SS-CHR-001',
  overrides: Partial<NotEvaluatedCheck> = {},
): NotEvaluatedCheck {
  return {
    rule_id: ruleId,
    title: 'Training records extend beyond the earliest test timestamp',
    status: 'not_evaluated',
    reason: 'No timestamp column was selected.',
    details: { timestamp_column: 'not selected' },
    ...overrides,
  }
}

export function evaluationFixture(overrides: Partial<EvaluationSummary> = {}): EvaluationSummary {
  return {
    evaluated_rule_ids: ['SS-ENT-001'],
    not_evaluated: [notEvaluatedFixture()],
    findings_total: 1,
    findings_by_severity: { high: 1, medium: 0, low: 0, info: 0 },
    headline: '1 high finding across 1 evaluated check',
    ...overrides,
  }
}

export function ruleOutcomeFixture(
  overrides: Partial<RuleOutcome> = {},
): RuleOutcome {
  return {
    rule_id: 'SS-ENT-001',
    title: 'Entity overlap between train and test splits',
    status: 'evaluated',
    duration_ms: 3.2,
    findings: [findingFixture()],
    metrics: [{ key: 'shared_groups', label: 'Shared entity groups', value: 2, unit: null }],
    not_evaluated: null,
    ...overrides,
  }
}

export function diagnosticsFixture(overrides: Partial<Diagnostics> = {}): Diagnostics {
  return {
    counts: { train_rows: 30, test_rows: 10, total_rows: 40 },
    missingness: [],
    missingness_note: 'No missing values were observed in the fixture.',
    target: null,
    disclaimer: 'Diagnostics are descriptive, not findings.',
    ...overrides,
  }
}

export function splitSummaryFixture(overrides: Partial<SplitSummary> = {}): SplitSummary {
  return {
    strategy_id: 'existing',
    label: 'Existing split column',
    kind: 'existing',
    requested_test_fraction: null,
    achieved_test_fraction: 0.25,
    train_rows: 30,
    test_rows: 10,
    seed: null,
    split_column: 'split',
    train_value: 'train',
    test_value: 'test',
    proportion_note: null,
    notes: [],
    assignment_id: null,
    ...overrides,
  }
}

export function auditResponseFixture(overrides: Partial<AuditResponse> = {}): AuditResponse {
  const finding = findingFixture()
  return {
    run_id: 'run-fixture-1',
    export_hint: 'Download this run from the export view.',
    assignment: null,
    result: {
      schema_version: '1.0.0',
      app_version: '1.0.0-test',
      generated_at_utc: '2026-01-01T00:00:00+00:00',
      duration_ms: 12.5,
      audit_config: structuredClone(DEFAULT_AUDIT_CONFIG),
      roles: rolesFixture(),
      resolved_roles: resolvedRolesFixture(),
      dataset: datasetSummaryFixture(),
      split: splitSummaryFixture(),
      evaluation: evaluationFixture(),
      findings: [finding],
      rule_outcomes: [
        ruleOutcomeFixture(),
        ruleOutcomeFixture({
          rule_id: 'SS-CHR-001',
          title: 'Training records extend beyond the earliest test timestamp',
          status: 'not_evaluated',
          findings: [],
          metrics: [],
          not_evaluated: notEvaluatedFixture(),
        }),
      ],
      diagnostics: diagnosticsFixture(),
      audit_limits: { max_examples: 10 },
      limitations: ['Fixture limitation of the audit.'],
      assumptions: ['Fixture assumption of the audit.'],
      risk_scorecard: {
        categories: [
          {
            key: 'entity',
            label: 'Entity',
            status: 'finding_present',
            finding_count: 1,
            max_severity: 'high',
            affected_rows: 3,
            rules: [
              {
                rule_id: 'SS-ENT-001',
                title: 'Entity overlap between train and test splits',
                status: 'evaluated',
                finding_count: 1,
                max_severity: 'high',
                not_evaluated_reason: null,
              },
            ],
          },
          {
            key: 'pipeline',
            label: 'Pipeline',
            status: 'not_checked',
            finding_count: 0,
            max_severity: null,
            affected_rows: null,
            rules: [
              {
                rule_id: 'SS-PPF-001',
                title: 'Preprocessing fit boundary (declared)',
                status: 'not_evaluated',
                finding_count: 0,
                max_severity: null,
                not_evaluated_reason: 'No preprocessing declaration was provided.',
              },
            ],
          },
        ],
        note: 'Fixture scorecard note.',
      },
    },
    ...overrides,
  }
}

export function comparisonResponseFixture(overrides: Partial<CompareResponse> = {}): CompareResponse {
  return {
    run_id: 'compare-fixture-1',
    sanitization_note: 'Fixture sanitization note.',
    selection_note: 'Fixture selection note.',
    assignments: [],
    result: {
      schema_version: '1.0.0',
      app_version: '1.0.0-test',
      generated_at_utc: '2026-01-01T00:00:00+00:00',
      duration_ms: 8,
      dataset: datasetSummaryFixture(),
      roles: rolesFixture(),
      resolved_roles: resolvedRolesFixture(),
      audit_config: structuredClone(DEFAULT_AUDIT_CONFIG),
      strategies: [],
      plans: [],
      rows: [
        {
          strategy_id: 'group',
          label: 'Group holdout',
          kind: 'group',
          supported: true,
          unsupported_reason: null,
          requested_test_fraction: 0.25,
          achieved_test_fraction: 0.25,
          train_rows: 30,
          test_rows: 10,
          proportion_note: null,
          exact_duplicate_test_rows: null,
          exact_duplicate_test_share: null,
          entity_shared_groups: null,
          entity_overlap_test_share: null,
          chronology_status: null,
          target_summary: null,
          target_max_abs_ratio_gap: null,
          finding_counts: {},
          not_evaluated: [],
          notes: [],
        },
      ],
      per_strategy_findings: { group: [] },
      selection_note: 'Fixture selection note.',
      limitations: ['Fixture comparison limitation.'],
    },
    ...overrides,
  }
}

export function columnValuesFixture(
  overrides: Partial<ColumnValuesResponse> = {},
): ColumnValuesResponse {
  return {
    dataset_id: 'ds-fixture-a',
    column: 'split',
    total_rows: 40,
    distinct_count: 3,
    missing_count: 2,
    values: [
      { value: 'train', count: 24 },
      { value: 'test', count: 14 },
      { value: 'validation', count: 2 },
      { value: '', count: 2 },
    ],
    truncated: false,
    note: 'Two empty cells are reported separately from the observed labels.',
    ...overrides,
  }
}

export function previewFixture(overrides: Partial<PreviewResponse> = {}): PreviewResponse {  return {
    dataset_id: 'ds-fixture-a',
    columns: [...COLUMNS],
    row_ids: ['row-000001', 'row-000002'],
    rows: [
      ['C-1', '10', '99.5', 'no', 'train'],
      ['C-1', '11', '88.5', 'yes', 'test'],
    ],
    offset: 0,
    limit: 2,
    total_rows: 40,
    truncated_columns: false,
    note: 'Fixture preview.',
    ...overrides,
  }
}

export function healthFixture(): HealthResponse {
  return {
    status: 'ok',
    app_name: 'SplitScope',
    app_version: '1.0.0-test',
    audit_schema_version: '1.0.0',
    server_time_utc: '2026-01-01T00:00:00+00:00',
    limits: { max_rows: 10_000 },
    store: {
      datasets: 1,
      runs: 2,
      assignments: 3,
      total_bytes: 4096,
      evictions: 0,
      expirations: 0,
      limits: { max_datasets: 8 },
    },
    storage_note: 'Fixture storage note.',
  }
}

export function checksFixture(): ChecksResponse {
  return {
    checks: [
      {
        rule_id: 'SS-ENT-001',
        title: 'Entity overlap between train and test splits',
        category: 'entity',
        default_enabled: true,
        requires: ['entity'],
        summary: 'Fixture catalogue summary.',
        detects: ['Entities in both splits.'],
        does_not_detect: ['Two spellings of one entity.'],
      },
      {
        rule_id: 'SS-CHR-001',
        title: 'Training records extend beyond the earliest test timestamp',
        category: 'time',
        default_enabled: true,
        requires: ['timestamp'],
        summary: 'Fixture catalogue summary for chronology.',
        detects: ['An unordered split.'],
        does_not_detect: ['Leakage from feature engineering.'],
      },
    ],
    what_this_app_does_not_do: ['It does not detect all data leakage.'],
    no_findings_means: 'Only that the enabled checks found no supported issue.',
  }
}

export function demoPayloadFixture(overrides: Record<string, unknown> = {}) {
  return {
    demo_id: 'fixture_demo',
    title: 'Fixture demo',
    subtitle: 'A tiny synthetic panel',
    filename: 'fixture.csv',
    synthetic: true,
    is_control: false,
    seed: 1,
    row_count: 40,
    column_count: COLUMNS.length,
    columns: [...COLUMNS],
    sha256: 'a'.repeat(64),
    teaching_point: 'Fixture teaching point.',
    generation_method: 'Fixture generation method.',
    expected_findings: [],
    recommended_audit: {},
    recommended_split: null,
    planted_cases: [],
    summary_metrics: {},
    notes: [],
    file_present: true,
    ...overrides,
  }
}

export function demosFixture(): DemoListResponse {
  return {
    demos: [demoPayloadFixture()],
    featured_journey: {
      demo_id: 'fixture_demo',
      title: 'Fixture featured journey',
      steps: ['Load the fixture demo.'],
    },
  }
}
