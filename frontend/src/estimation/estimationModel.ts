/**
 * estimation UI estimation model helpers.
 *
 * Pure functions: form state → the estimation request body, a stable signature for
 * request/response ordering, labels for the three named estimators, selection
 * of the diagnostics a view should display, and - most importantly - a
 * deterministic staleness comparison between a stored run and the study as it
 * stands now.
 *
 * Nothing here estimates anything. Every number the studio shows comes from the
 * backend payload; this module only describes and compares payloads.
 */

import type {
  EstimationRequestPayload,
  EstimationResult,
  EstimationRunPayload,
  EstimatorName,
} from '../api/types'

export type MissingPolicy = 'complete_case' | 'median_mode'
export type UncertaintyMethod = 'influence_function' | 'bootstrap'
export type CohortPartition = 'train' | 'test'
export type EstimatorChoice = 'compare' | EstimatorName

export const ESTIMATOR_LABELS: Record<EstimatorName, string> = {
  regression_adjustment: 'Regression adjustment',
  ipw: 'Inverse propensity weighting',
  aipw: 'Cross-fitted AIPW',
}

export const ESTIMATOR_SHORT: Record<EstimatorName, string> = {
  regression_adjustment: 'RA',
  ipw: 'IPW',
  aipw: 'AIPW',
}

export const ESTIMATOR_DESCRIPTIONS: Record<EstimatorName, string> = {
  regression_adjustment:
    'G-computation: one outcome model, predicted under treatment and control for every analysed row, then averaged.',
  ipw:
    'Hájek-normalized inverse propensity weights: the treated and control weighted outcome means are differenced.',
  aipw:
    'Augmented IPW with cross-fitted nuisance models: doubly robust in theory, and the only estimator here whose out-of-fold predictions are never in-sample.',
}

export const ESTIMATOR_ORDER: EstimatorName[] = ['regression_adjustment', 'ipw', 'aipw']

export interface EstimationConfig {
  treatmentNode: string
  outcomeNode: string
  adjustmentNodes: string[]
  treatedValue: string
  controlValue: string
  missingPolicy: MissingPolicy
  crossFitSplits: number
  groupColumn: string | null
  uncertaintyMethod: UncertaintyMethod
  uncertaintyLevel: number
  bootstrapReps: number
  seed: string
  truncationEnabled: boolean
  truncationLower: number
  truncationUpper: number
  cohortAssignment: string
  cohortPartition: CohortPartition
}

export function defaultConfig(): EstimationConfig {
  return {
    treatmentNode: '',
    outcomeNode: '',
    adjustmentNodes: [],
    treatedValue: '1',
    controlValue: '0',
    missingPolicy: 'complete_case',
    crossFitSplits: 5,
    groupColumn: null,
    uncertaintyMethod: 'bootstrap',
    uncertaintyLevel: 0.95,
    bootstrapReps: 500,
    seed: '',
    truncationEnabled: false,
    truncationLower: 0.05,
    truncationUpper: 0.95,
    cohortAssignment: '',
    cohortPartition: 'test',
  }
}

/** The request body exactly as the estimation contract expects it (strict schema). */
export function buildRequest(
  config: EstimationConfig,
  graphFingerprint: string | null,
): EstimationRequestPayload {
  const assignment = config.cohortAssignment.trim()
  const seedText = config.seed.trim()
  const parsedSeed = seedText === '' ? null : Number(seedText)
  return {
    estimand: 'ate',
    treatment_node: config.treatmentNode,
    outcome_node: config.outcomeNode,
    adjustment_nodes: [...config.adjustmentNodes].sort(),
    treatment_mapping: { treated: config.treatedValue, control: config.controlValue },
    cohort: {
      split_assignment_id: assignment === '' ? null : assignment,
      partition: assignment === '' ? null : config.cohortPartition,
    },
    missing_data_policy: config.missingPolicy,
    cross_fit: {
      splits: config.crossFitSplits,
      group_column: config.groupColumn,
    },
    uncertainty: {
      method: config.uncertaintyMethod,
      level: config.uncertaintyLevel,
      reps: config.bootstrapReps,
      seed: parsedSeed !== null && Number.isFinite(parsedSeed) ? parsedSeed : null,
    },
    propensity_truncation: config.truncationEnabled
      ? { lower: config.truncationLower, upper: config.truncationUpper }
      : null,
    expected_spec_fingerprint_sha256: graphFingerprint,
  }
}

/**
 * A stable identity for everything a result depends on. Two responses are only
 * interchangeable when their signatures match; a response carrying an older
 * signature is discarded rather than displayed against newer settings.
 */
export function requestSignature(
  request: EstimationRequestPayload | null,
  context: { datasetId: string | null; graphId: string | null; graphFingerprint: string | null },
): string {
  return JSON.stringify({
    datasetId: context.datasetId,
    graphId: context.graphId,
    graphFingerprint: context.graphFingerprint,
    request,
  })
}

export function estimatorLabel(name: string): string {
  return ESTIMATOR_LABELS[name as EstimatorName] ?? name
}

export function estimatorShort(name: string): string {
  return ESTIMATOR_SHORT[name as EstimatorName] ?? name
}

export function resultFor(
  payload: EstimationRunPayload | null,
  estimator: EstimatorName,
): EstimationResult | null {
  return payload?.results.find((result) => result.estimator === estimator) ?? null
}

export function estimatedResults(payload: EstimationRunPayload | null): EstimationResult[] {
  return payload?.results.filter((result) => result.status === 'estimated') ?? []
}

export function failedResults(payload: EstimationRunPayload | null): EstimationResult[] {
  return payload?.results.filter((result) => result.status === 'failed') ?? []
}

/**
 * The result whose diagnostics a view should show.
 *
 * Weighting diagnostics only exist where a propensity model was fitted, so a
 * weighted result is preferred; regression adjustment is the fallback and its
 * views say plainly that no weights were applied.
 */
export function diagnosticResult(
  payload: EstimationRunPayload | null,
  prefer: 'weighted' | 'any' = 'weighted',
): EstimationResult | null {
  const estimated = estimatedResults(payload)
  if (prefer === 'weighted') {
    const weighted = estimated.find((result) => result.diagnostics?.balance.weighted)
    if (weighted) return weighted
  }
  return estimated.find((result) => result.diagnostics?.balance) ?? null
}

export function overlapResult(payload: EstimationRunPayload | null): EstimationResult | null {
  return (
    estimatedResults(payload).find((result) => result.diagnostics?.overlap != null) ?? null
  )
}

export type StalenessReason = { code: string; label: string }

function sameSet(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false
  const a = [...left].sort()
  const b = [...right].sort()
  return a.every((value, index) => value === b[index])
}

/**
 * Deterministic comparison of a stored run against the current study.
 *
 * A layout-only graph edit never reaches this check: the graph fingerprint is
 * scientific content only, so moving a node cannot stale a result. Every
 * meaning-changing difference is named individually, because "stale" without a
 * reason is not actionable.
 */
export function stalenessReasons(
  payload: EstimationRunPayload,
  context: {
    datasetFingerprint: string | null
    graphId: string | null
    graphFingerprint: string | null
    config: EstimationConfig
  },
): StalenessReason[] {
  const reasons: StalenessReason[] = []
  const repro = payload.reproducibility
  const { config } = context

  if (payload.stale) {
    reasons.push({
      code: 'server_stale',
      label: payload.staleness_reason ?? 'The server reports this result as stale.',
    })
  }
  if (
    context.datasetFingerprint &&
    repro.dataset_fingerprint_sha256 !== context.datasetFingerprint
  ) {
    reasons.push({
      code: 'dataset_changed',
      label: 'The dataset in memory is not the dataset this result was computed on.',
    })
  }
  if (context.graphId && repro.graph_id !== context.graphId) {
    reasons.push({
      code: 'graph_switched',
      label: 'A different causal graph is selected now.',
    })
  }
  if (
    context.graphFingerprint &&
    repro.graph_spec_fingerprint_sha256 !== context.graphFingerprint
  ) {
    reasons.push({
      code: 'graph_changed',
      label:
        'The graph’s scientific content changed (edges, scope or observed status) since this result was computed.',
    })
  }
  if (repro.treatment_node !== config.treatmentNode) {
    reasons.push({ code: 'treatment_changed', label: 'The selected treatment changed.' })
  }
  if (repro.outcome_node !== config.outcomeNode) {
    reasons.push({ code: 'outcome_changed', label: 'The selected outcome changed.' })
  }
  if (!sameSet(repro.adjustment_nodes, config.adjustmentNodes)) {
    reasons.push({
      code: 'adjustment_changed',
      label: 'The adjustment set differs from the one this result used.',
    })
  }
  if (
    repro.treatment_mapping.treated !== config.treatedValue ||
    repro.treatment_mapping.control !== config.controlValue
  ) {
    reasons.push({
      code: 'mapping_changed',
      label: 'The treatment/control value mapping changed.',
    })
  }
  const assignment = config.cohortAssignment.trim()
  const cohortSame =
    (repro.cohort.split_assignment_id ?? '') === assignment &&
    (assignment === ''
      ? true
      : (repro.cohort.partition ?? '') === config.cohortPartition)
  if (!cohortSame) {
    reasons.push({ code: 'cohort_changed', label: 'The analysis cohort changed.' })
  }
  if (repro.missing_data_policy !== config.missingPolicy) {
    reasons.push({ code: 'missing_policy_changed', label: 'The missing-data policy changed.' })
  }
  if (
    repro.cross_fitting.splits !== config.crossFitSplits ||
    (repro.cross_fitting.group_column ?? null) !== (config.groupColumn ?? null)
  ) {
    reasons.push({ code: 'crossfit_changed', label: 'The cross-fitting design changed.' })
  }
  if (repro.uncertainty.method !== config.uncertaintyMethod) {
    reasons.push({ code: 'uncertainty_method_changed', label: 'The uncertainty method changed.' })
  }
  if (Math.abs(repro.uncertainty.level - config.uncertaintyLevel) > 1e-9) {
    reasons.push({ code: 'uncertainty_level_changed', label: 'The interval level changed.' })
  }
  if (
    config.uncertaintyMethod === 'bootstrap' &&
    repro.uncertainty.reps !== config.bootstrapReps
  ) {
    reasons.push({ code: 'reps_changed', label: 'The number of bootstrap replicates changed.' })
  }
  // An empty seed means "let the server draw one", so only a *specified* seed
  // that differs from the one this run resolved to makes the result stale.
  const specifiedSeed = config.seed.trim()
  if (specifiedSeed !== '' && Number(specifiedSeed) !== repro.uncertainty.resolved_seed) {
    reasons.push({ code: 'seed_changed', label: 'The reproducibility seed changed.' })
  }
  const truncationSame =
    (repro.propensity_truncation === null) === !config.truncationEnabled &&
    (!config.truncationEnabled ||
      (repro.propensity_truncation?.lower === config.truncationLower &&
        repro.propensity_truncation?.upper === config.truncationUpper))
  if (!truncationSame) {
    reasons.push({ code: 'truncation_changed', label: 'The propensity truncation changed.' })
  }
  return reasons
}
