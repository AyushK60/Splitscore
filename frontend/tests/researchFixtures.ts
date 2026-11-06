/**
 * S9C research fixtures: hand-written payloads matching the backend contract,
 * with independently specified expectations (never derived from the code
 * under test). Derived from the estimationFixtures study so ResearchView can
 * build its request from a real-shape reproducibility block.
 */

import type {
  RobustnessRunPayload,
  SubgroupRunPayload,
  WhatIfRunPayload,
} from '../src/api/types'
import { DATASET_ID, GRAPH_ID, GRAPH_FINGERPRINT, runPayload } from './estimationFixtures'

export const SUBGROUP_RUN_ID = 'run-s9c-subgroups'
export const ROBUSTNESS_RUN_ID = 'run-s9c-robustness'
export const WHATIF_RUN_ID = 'run-s9c-whatif'

export function subgroupPayload(overrides: Partial<SubgroupRunPayload> = {}): SubgroupRunPayload {
  return {
    graph_id: GRAPH_ID,
    dataset_id: DATASET_ID,
    revision: 1,
    spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    analysis_kind: 'subgroups',
    estimation_version: '1.0.0',
    subgroup_schema_version: '1.0.0',
    estimand: 'ate',
    gate: runPayload().gate,
    analysis: runPayload().analysis,
    subgroup: {
      node_id: 'region',
      column: 'region',
      kind: 'categorical',
      definition: 'Observed levels of the categorical baseline variable',
      numeric_binning: null,
      requested_levels: null,
      bin_edges: null,
      intent: 'exploratory',
      rows_excluded_missing: 0,
    },
    overall: {
      estimator: 'aipw',
      estimate: 1.665,
      standard_error: 0.12,
      ci_lower: 1.43,
      ci_upper: 1.9,
      interval_level: 0.95,
      note: 'The overall ATE on the same cohort.',
    },
    groups: [
      {
        label: 'east',
        rows: 300,
        treated_rows: 88,
        control_rows: 212,
        status: 'estimated',
        estimate: 1.41,
        standard_error: 0.21,
        ci_lower: 1.0,
        ci_upper: 1.82,
        warnings: [],
        propensity_summary: {
          treated_min: 0.12,
          treated_max: 0.83,
          control_min: 0.05,
          control_max: 0.9,
          extreme_rows: 0,
        },
      },
      {
        label: 'north',
        rows: 480,
        treated_rows: 161,
        control_rows: 319,
        status: 'estimated',
        estimate: 1.72,
        standard_error: 0.16,
        ci_lower: 1.41,
        ci_upper: 2.03,
        warnings: [],
        propensity_summary: {
          treated_min: 0.2,
          treated_max: 0.91,
          control_min: 0.11,
          control_max: 0.94,
          extreme_rows: 0,
        },
      },
      {
        label: 'south',
        rows: 420,
        treated_rows: 100,
        control_rows: 320,
        status: 'unavailable',
        estimate: null,
        standard_error: null,
        ci_lower: null,
        ci_upper: null,
        unavailable_reason:
          'This subgroup has 4 treated and 3 control rows; at least 10 rows per arm are required before a subgroup effect is estimated. No estimate was fabricated.',
        warnings: [],
      },
    ],
    contrasts: [
      {
        a: 'north',
        b: 'east',
        difference: 0.31,
        standard_error: 0.264,
        ci_lower: -0.207,
        ci_upper: 0.827,
      },
    ],
    notes: [
      { code: 'pseudo_outcome_provenance', text: 'Pseudo-outcome provenance note.' },
      { code: 'intent', text: 'Exploratory note.' },
      { code: 'multiple_comparisons', text: 'Multiple comparisons note.' },
    ],
    reproducibility: runPayload().reproducibility,
    scope_note: 'Scope note for subgroup effects.',
    run_id: SUBGROUP_RUN_ID,
    created_at_utc: '2026-11-07T00:00:00+00:00',
    ...overrides,
  }
}

export function robustnessPayload(
  overrides: Partial<RobustnessRunPayload> = {},
): RobustnessRunPayload {
  const estimates = [1.52, 1.61, 1.44, 1.7, 1.58, 1.49, 1.66, 1.55, 1.62, 1.47]
  return {
    graph_id: GRAPH_ID,
    dataset_id: DATASET_ID,
    revision: 1,
    spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    analysis_kind: 'robustness',
    estimation_version: '1.0.0',
    robustness_schema_version: '1.0.0',
    estimand: 'ate',
    gate: runPayload().gate,
    analysis: runPayload().analysis,
    original: {
      estimator: 'ipw',
      estimate: 1.58,
      failure: null,
      note: 'The same estimator fitted once on the full analysis cohort.',
    },
    result: {
      experiment: 'subsampling',
      parameters: { estimator: 'ipw', reps: 10, fraction: 0.5, subsample_rows: 65, cohort_rows: 130 },
      distribution: {
        mean: 1.564,
        standard_deviation: 0.0877,
        min: 1.44,
        max: 1.7,
        q05: 1.442,
        q50: 1.565,
        q95: 1.694,
      },
      estimates,
      failures: [{ rep: 7, reason: 'A treatment arm received total weight zero; the Hájek estimator is undefined.' }],
      warnings: ['Subsampling caveat: stability is not absence of bias.'],
      method_note: 'Each repetition draws a subsample at the recorded fraction.',
    },
    reproducibility: runPayload().reproducibility,
    scope_note: 'Scope note for robustness experiments.',
    run_id: ROBUSTNESS_RUN_ID,
    created_at_utc: '2026-11-07T00:00:00+00:00',
    ...overrides,
  }
}

export function sensitivityPayload(
  overrides: Partial<RobustnessRunPayload> = {},
): RobustnessRunPayload {
  const grid = [
    [1.58, 1.55, 1.51, 1.47, 1.42],
    [1.56, 1.52, 1.48, 1.43, 1.38],
    [1.54, 1.49, 1.44, 1.39, 1.33],
    [1.52, 1.46, 1.4, 1.34, 1.27],
    [1.5, 1.43, 1.36, 1.28, 1.2],
  ]
  const base = robustnessPayload()
  return {
    ...base,
    original: { ...base.original, estimator: 'regression_adjustment' },
    result: {
      ...base.result,
      experiment: 'unmeasured_confounder_simulation',
      parameters: {
        estimator: 'regression_adjustment',
        prevalence: 0.3,
        gamma_values: [0, 0.25, 0.5, 0.75, 1],
        kappa_values: [0, 0.1, 0.2, 0.3, 0.4],
        outcome_sd: 2.1,
      },
      grid,
      estimates: [],
      distribution: null,
      failures: [],
      warnings: ['The simulated confounder is a hypothetical scenario, not a bound.'],
      method_note: 'For each (γ, κ) cell a binary confounder is simulated and adjusted for.',
    },
    ...overrides,
  }
}

export function whatIfPayload(overrides: Partial<WhatIfRunPayload> = {}): WhatIfRunPayload {
  return {
    graph_id: GRAPH_ID,
    dataset_id: DATASET_ID,
    revision: 1,
    spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    analysis_kind: 'what_if',
    estimation_version: '1.0.0',
    what_if_schema_version: '1.0.0',
    estimand: 'ate',
    gate: runPayload().gate,
    analysis: runPayload().analysis,
    model_specification: {
      kind: 'regression_adjustment_outcome_model',
      outcome_task: 'linear',
      units: 'outcome_units',
      uncertainty: 'None is reported; a scenario prediction is a conditional model expectation.',
      covariates: ['age', 'baseline_score', 'region'],
    },
    profile_scenario: {
      profile: { age: 55, baseline_score: 50.2, region: 'south' },
      disclosures: [
        { field: 'age', source: 'explicit', value: 55 },
        { field: 'baseline_score', source: 'cohort_median', value: 50.2 },
        { field: 'region', source: 'explicit', value: 'south' },
      ],
      treated_prediction: 12.4,
      control_prediction: 10.9,
      contrast: 1.5,
    },
    cohort_scenario: {
      treated_mean: 12.31,
      control_mean: 10.72,
      contrast: 1.59,
      note: 'The same model averaged over the whole analysis cohort.',
    },
    warnings: ['Model-based conditional predictions — not observed outcomes.'],
    reproducibility: runPayload().reproducibility,
    scope_note: 'Scope note for what-if scenarios.',
    run_id: WHATIF_RUN_ID,
    created_at_utc: '2026-11-07T00:00:00+00:00',
    ...overrides,
  }
}
