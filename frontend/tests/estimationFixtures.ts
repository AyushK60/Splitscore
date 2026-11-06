/**
 * Hand-written S9B estimation fixtures.
 *
 * These mirror the real S9A payload shape (captured from the running backend,
 * see docs/S9B_API_INTEGRATION.md) but every number is chosen by hand so the
 * assertions can be read directly from the fixture: RA 2.0, IPW 1.6, AIPW 1.8,
 * with intervals that straddle zero only where the test says so.
 */
import type {
  CausalGraphPayload,
  CausalIdentificationResponse,
  EstimationBalanceCovariate,
  EstimationRunPayload,
  EstimationValidateResponse,
  EstimationResult,
} from '../src/api/types'

export const DATASET_ID = 'ds-s9b-fixture'
export const GRAPH_ID = 'cgraph-s9b-fixture'
export const GRAPH_FINGERPRINT = 'b'.repeat(64)
export const DATASET_FINGERPRINT = 'a'.repeat(64)

function histogram(
  treatedCounts: number[],
  controlCounts: number[],
): {
  bin_edges: number[]
  bin_count: number
  treated_counts: number[]
  control_counts: number[]
  treated_share: number[]
  control_share: number[]
  definition: string
} {
  const treatedTotal = treatedCounts.reduce((sum, value) => sum + value, 0)
  const controlTotal = controlCounts.reduce((sum, value) => sum + value, 0)
  return {
    bin_edges: Array.from({ length: 21 }, (_, index) => index * 0.05),
    bin_count: 20,
    treated_counts: treatedCounts,
    control_counts: controlCounts,
    treated_share: treatedCounts.map((value) =>
      treatedTotal === 0 ? 0 : Number((value / treatedTotal).toFixed(8)),
    ),
    control_share: controlCounts.map((value) =>
      controlTotal === 0 ? 0 : Number((value / controlTotal).toFixed(8)),
    ),
    definition:
      'Counts of fitted propensity scores in 20 fixed bins of width 0.05 over [0, 1]; shares are relative frequencies within each arm.',
  }
}

const EMPTY_TREATED = [0, 4, 13, 16, 8, 2, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
const EMPTY_CONTROL = [0, 9, 20, 22, 14, 6, 2, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

export const BALANCE_COVARIATES: EstimationBalanceCovariate[] = [
  { column: 'age', kind: 'numeric', level: null, smd_unweighted: 0.3296804, smd_weighted: -0.0204 },
  {
    column: 'baseline_score',
    kind: 'numeric',
    level: null,
    smd_unweighted: 0.2688686,
    smd_weighted: 0.0142,
  },
  { column: 'region', kind: 'categorical', level: 'east', smd_unweighted: -0.2598798, smd_weighted: 0.0091 },
  { column: 'region', kind: 'categorical', level: 'north', smd_unweighted: -0.1887579, smd_weighted: null },
  { column: 'region', kind: 'categorical', level: 'south', smd_unweighted: 0.4103154, smd_weighted: 0.0261 },
]

function overlapFixture(overrides: Record<string, unknown> = {}) {
  return {
    propensity_summary: {
      min: 0.0754,
      max: 0.6786,
      quantiles_overall: { '0.01': 0.1, '0.05': 0.13, '0.25': 0.2, '0.5': 0.27, '0.75': 0.37, '0.95': 0.52, '0.99': 0.6 },
      quantiles_treated: { '0.01': 0.12, '0.05': 0.15, '0.25': 0.25, '0.5': 0.33, '0.75': 0.43, '0.95': 0.56, '0.99': 0.62 },
      quantiles_control: { '0.01': 0.09, '0.05': 0.13, '0.25': 0.18, '0.5': 0.25, '0.75': 0.34, '0.95': 0.48, '0.99': 0.58 },
    },
    propensity_histogram: histogram(EMPTY_TREATED, EMPTY_CONTROL),
    extremes: {
      'below_0.01': 0,
      'above_0.99': 0,
      count_definition: 'fitted propensity strictly outside [0.01, 0.99]',
    },
    effective_sample_sizes: {
      treated_rows_unweighted: 45,
      control_rows_unweighted: 75,
      treated_ess_weighted: 37.5,
      control_ess_weighted: 60,
    },
    weight_summary: {
      max_individual_weight: 6.25,
      quantiles_total_weight: { '0.5': 1.4, '0.95': 3.2, '0.99': 5.1 },
    },
    warnings: [] as string[],
    scope_note:
      'These are empirical overlap diagnostics for the fitted propensity distribution in this dataset.',
    truncation: null as { lower: number; upper: number } | null,
    ...overrides,
  }
}

export function estimatedResult(
  estimator: 'regression_adjustment' | 'ipw' | 'aipw',
  overrides: Partial<EstimationResult> = {},
): EstimationResult {
  const weightless = estimator === 'regression_adjustment'
  return {
    estimator,
    status: 'estimated',
    estimate: estimator === 'ipw' ? 1.6 : estimator === 'aipw' ? 1.8 : 2,
    mu1: 4,
    mu0: 2,
    treated_mean: 4.2,
    control_mean: 2.3,
    units: 'outcome_units',
    sample_size: 120,
    model_specification: weightless
      ? { outcome_model: 'linear_least_squares', treatment_as_feature: true }
      : { propensity_model: 'logistic_l2_C1.0', weighting: 'hajek_normalized' },
    fold_row_counts: estimator === 'aipw' ? [24, 24, 24, 24, 24] : null,
    truncation: null,
    uncertainty: {
      status: 'available',
      method: 'bootstrap_percentile',
      level: 0.95,
      standard_error: 0.13,
      ci_lower: estimator === 'ipw' ? 1.29 : estimator === 'aipw' ? 1.5 : 1.7,
      ci_upper: estimator === 'ipw' ? 1.91 : estimator === 'aipw' ? 2.1 : 2.3,
      bootstrap: {
        reps_requested: 500,
        reps_succeeded: 500,
        reps_failed: 0,
        seed: 987654321,
        interval_type: 'percentile',
        refit_nuisance_models: true,
        sample_failure_messages: [],
      },
      assumptions: ['The interval assumes independent observations.'],
    },
    diagnostics: {
      balance: {
        covariates: BALANCE_COVARIATES.map((covariate) =>
          weightless ? { ...covariate, smd_weighted: null } : covariate,
        ),
        weighted: !weightless,
        interpretation_note:
          'Standardized mean differences are descriptive summaries of covariate balance in this sample.',
      },
      overlap: weightless ? null : overlapFixture(),
    },
    warnings: [],
    ...overrides,
  }
}

export function failedResult(
  estimator: 'regression_adjustment' | 'ipw' | 'aipw',
  reason = 'The propensity model could not be fitted on this cohort.',
): EstimationResult {
  return {
    estimator,
    status: 'failed',
    failure: { reason, details: { library_error: 'ValueError' } },
  }
}

export function runPayload(overrides: Partial<EstimationRunPayload> = {}): EstimationRunPayload {
  return {
    graph_id: GRAPH_ID,
    dataset_id: DATASET_ID,
    revision: 1,
    spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    estimation_version: '1.0.0',
    estimation_schema_version: '1.0.0',
    estimand: 'ate',
    gate: {
      gate: 'passed',
      adjustment_set_verification: {
        treatment: 'treatment',
        outcome: 'outcome',
        adjustment_set: ['age', 'baseline_score', 'region'],
        valid: true,
        violations: [],
        open_backdoor_paths: [],
        path_listing_bounded: false,
        interpretation: 'Every backdoor path is blocked by this set under the assumed DAG.',
        interpretation_note: 'Backdoor admissibility is a property of the assumed graph.',
      },
      treatment_node: 'treatment',
      outcome_node: 'outcome',
      adjustment_nodes: ['age', 'baseline_score', 'region'],
      caveat:
        'The adjustment set was verified against the drawn graph only. Exchangeability, consistency, positivity and correct model specification remain assumptions.',
    },
    analysis: {
      rows_in_dataset: 130,
      rows_in_analysis_cohort_frame: 130,
      rows_final: 120,
      treated_rows: 45,
      control_rows: 75,
      exclusions: [
        {
          reason: 'missing_outcome_value',
          detail: 'Rows without a parsable outcome were excluded.',
          count: 10,
          sample_row_ids: ['row-000001'],
        },
      ],
      covariates: [
        { column: 'age', kind: 'numeric', levels: null, missing_in_cohort: 0 },
        {
          column: 'baseline_score',
          kind: 'numeric',
          levels: null,
          missing_in_cohort: 0,
        },
        {
          column: 'region',
          kind: 'categorical',
          levels: ['east', 'north', 'south'],
          missing_in_cohort: 0,
        },
      ],
      outcome_task: 'linear',
      outcome_coding: { kind: 'continuous', interpretation: "The estimate is in the outcome's own units." },
      missing_data_policy: 'complete_case',
      treatment_column: 'treatment',
      outcome_column: 'outcome',
      adjustment_columns: ['age', 'baseline_score', 'region'],
      outcome_units_note: 'The outcome was treated as continuous; estimates are in the outcome units.',
    },
    results: [estimatedResult('regression_adjustment'), estimatedResult('ipw'), estimatedResult('aipw')],
    comparison: {
      shared_analysis:
        'All results below were computed on the same prepared cohort, treatment mapping, adjustment set and estimand; they differ only in the estimator.',
      estimates: { regression_adjustment: 2, ipw: 1.6, aipw: 1.8 },
      max_pairwise_difference: 0.4,
      interpretation:
        'Material disagreement between estimators that share a cohort and adjustment set is a model-specification or instability signal. It is reported, not resolved.',
    },
    defaults_applied: [
      {
        field: 'cohort.split_assignment_id',
        value: null,
        meaning: 'No train/test partition named: the cohort is every dataset row that survives data preparation.',
      },
    ],
    reproducibility: {
      dataset_id: DATASET_ID,
      dataset_fingerprint_sha256: DATASET_FINGERPRINT,
      graph_id: GRAPH_ID,
      graph_revision: 1,
      graph_spec_fingerprint_sha256: GRAPH_FINGERPRINT,
      estimation_version: '1.0.0',
      estimation_schema_version: '1.0.0',
      estimators: ['regression_adjustment', 'ipw', 'aipw'],
      treatment_node: 'treatment',
      outcome_node: 'outcome',
      adjustment_nodes: ['age', 'baseline_score', 'region'],
      treatment_mapping: { treated: '1', control: '0' },
      cohort: { split_assignment_id: null, partition: null },
      missing_data_policy: 'complete_case',
      cross_fitting: { splits: 5, group_column: null },
      uncertainty: { method: 'bootstrap', level: 0.95, reps: 500, seed: null, resolved_seed: 987654321 },
      propensity_truncation: null,
      software_versions: { python: '3.11.9', scikit_learn: '1.9.1' },
      limits: {
        max_rows: 10000,
        min_rows_total: 20,
        min_rows_per_arm: 10,
        max_covariates: 30,
        max_categorical_levels: 12,
        max_encoded_features: 300,
        max_bootstrap_reps: 2000,
        min_bootstrap_reps: 100,
        min_crossfit_splits: 2,
        max_crossfit_splits: 10,
      },
    },
    scope_note:
      'The estimate is an average treatment effect computed from this dataset under the assumed graph and the named adjustment set.',
    run_id: 'run-s9b-fixture',
    created_at_utc: '2026-11-06T09:00:00+00:00',
    ...overrides,
  }
}

export function validatePayload(
  overrides: Partial<EstimationValidateResponse> = {},
): EstimationValidateResponse {
  const run = runPayload()
  return {
    graph_id: GRAPH_ID,
    dataset_id: DATASET_ID,
    revision: 1,
    spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    schema_version: '1.0.0',
    estimation_version: '1.0.0',
    estimation_schema_version: '1.0.0',
    readiness: 'ready',
    gate: run.gate,
    cohort_preview: {
      rows_in_dataset: 130,
      rows_in_analysis_cohort_frame: 130,
      rows_final: 120,
      treated_rows: 45,
      control_rows: 75,
      exclusions: [],
      covariates: run.analysis.covariates,
      outcome_task: 'linear',
      outcome_coding: run.analysis.outcome_coding,
      missing_data_policy: 'complete_case',
    },
    limits: run.reproducibility.limits,
    note: 'Nothing was estimated and nothing was stored.',
    ...overrides,
  }
}

export function graphPayload(overrides: Partial<CausalGraphPayload> = {}): CausalGraphPayload {
  const node = (nodeId: string, kind: string) => ({
    node_id: nodeId,
    label: nodeId,
    column: nodeId,
    observed: true,
    kind: kind as 'covariate',
    description: null,
    layout: null,
    resolved_column_type: 'float',
    derived_structure: {
      parents: [] as string[],
      children: [] as string[],
      ancestors: [] as string[],
      descendants: [] as string[],
      is_collider: false,
      on_directed_treatment_outcome_path: false,
    },
  })
  return {
    graph_id: GRAPH_ID,
    dataset_id: DATASET_ID,
    dataset_name: 'causal_effect.csv',
    dataset_fingerprint_sha256: DATASET_FINGERPRINT,
    schema_version: '1.0.0',
    revision: 1,
    created_at_utc: '2026-11-06T08:00:00+00:00',
    updated_at_utc: '2026-11-06T08:00:00+00:00',
    spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    name: 'Confounding demonstration',
    description: null,
    nodes: [
      node('age', 'covariate'),
      node('baseline_score', 'covariate'),
      node('region', 'covariate'),
      node('treatment', 'treatment'),
      node('outcome', 'outcome'),
    ],
    edges: [
      { source: 'age', target: 'treatment', rationale: null, reference: null },
      { source: 'age', target: 'outcome', rationale: null, reference: null },
      { source: 'treatment', target: 'outcome', rationale: null, reference: null },
    ],
    analysis: { treatment: 'treatment', outcome: 'outcome' },
    assumptions: [],
    validation: {
      ok: true,
      error_count: 0,
      warning_count: 0,
      errors: [],
      warnings: [],
      derived: {
        node_count: 5,
        edge_count: 3,
        is_dag: true,
        has_directed_treatment_outcome_path: true,
        path_enumeration_bounded: false,
        treatment: 'treatment',
        outcome: 'outcome',
        nodes: {},
        note: 'Derived structure of the saved graph.',
      },
    },
    validation_scope_note: 'Form only.',
    storage_note: 'Bounded in-memory store.',
    app: { name: 'SplitScope', version: '1.0.0' },
    ...overrides,
  }
}

export function identificationPayload(
  overrides: Partial<CausalIdentificationResponse> = {},
): CausalIdentificationResponse {
  return {
    graph_id: GRAPH_ID,
    dataset_id: DATASET_ID,
    revision: 1,
    spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    schema_version: '1.0.0',
    identification_version: '1.0.0',
    status: 'backdoor_adjustment_available',
    treatment: 'treatment',
    outcome: 'outcome',
    explanations: [],
    caveats: [],
    search: {
      graph_id: GRAPH_ID,
      dataset_id: DATASET_ID,
      revision: 1,
      spec_fingerprint_sha256: GRAPH_FINGERPRINT,
      schema_version: '1.0.0',
      treatment: 'treatment',
      outcome: 'outcome',
      search_status: 'complete',
      sets: [
        {
          set: ['age', 'baseline_score', 'region'],
          verification: 'verified',
          inclusion_minimal: true,
        },
      ],
      forbidden_variables: ['treatment', 'outcome'],
      eligible_candidates: ['age', 'baseline_score', 'region'],
      candidates_considered: 3,
      bounds: { max_set_size: 3, max_candidates: 10 },
      interpretation_note: 'Backdoor admissibility is a property of the assumed graph.',
    },
    interpretation_note: 'Identification describes the assumed graph only.',
    ...overrides,
  }
}
