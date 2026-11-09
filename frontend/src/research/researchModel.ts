/**
 * estimation research model helpers.
 *
 * Pure functions: rebuild the exact estimation estimation request from a stored run's
 * reproducibility block (so subgroup/robustness/what-if analyses are computed
 * on the *same* study as the estimation run they build on), plus shared
 * plotting arithmetic for the forest plot, robustness distributions and the
 * sensitivity grid.
 *
 * Nothing here estimates anything; every number displayed comes from a
 * backend payload.
 */

import type {
  EstimationReproducibility,
  EstimationRequestPayload,
  SubgroupGroup,
} from '../api/types'

/**
 * Rebuild the estimation request a stored run actually used. The
 * reproducibility block echoes every request field, so an advanced analysis
 * can target the identical study - including the graph fingerprint as the
 * staleness guard.
 */
export function requestFromRun(repro: EstimationReproducibility): EstimationRequestPayload {
  return {
    estimand: 'ate',
    treatment_node: repro.treatment_node,
    outcome_node: repro.outcome_node,
    adjustment_nodes: [...repro.adjustment_nodes].sort(),
    treatment_mapping: { ...repro.treatment_mapping },
    cohort: {
      split_assignment_id: repro.cohort.split_assignment_id,
      partition: repro.cohort.partition,
    },
    missing_data_policy: repro.missing_data_policy,
    cross_fit: {
      splits: repro.cross_fitting.splits,
      group_column: repro.cross_fitting.group_column,
    },
    uncertainty: {
      method: repro.uncertainty.method,
      level: repro.uncertainty.level,
      reps: repro.uncertainty.reps,
      seed: repro.uncertainty.resolved_seed,
    },
    propensity_truncation: repro.propensity_truncation
      ? { ...repro.propensity_truncation }
      : null,
    expected_spec_fingerprint_sha256: repro.graph_spec_fingerprint_sha256,
  }
}

// --------------------------------------------------------------------------- //
// Forest plot arithmetic
// --------------------------------------------------------------------------- //

export interface ForestDomain {
  min: number
  max: number
  ticks: number[]
}

export function forestDomain(groups: SubgroupGroup[], overall: number, pad = 0.14): ForestDomain {
  const bounds: number[] = [0, overall]
  for (const group of groups) {
    if (group.status === 'estimated' && typeof group.estimate === 'number') bounds.push(group.estimate)
    if (typeof group.ci_lower === 'number') bounds.push(group.ci_lower)
    if (typeof group.ci_upper === 'number') bounds.push(group.ci_upper)
  }
  let min = Math.min(...bounds)
  let max = Math.max(...bounds)
  if (min === max) {
    min -= 1
    max += 1
  }
  const padding = (max - min) * pad
  return { min: min - padding, max: max + padding, ticks: [] }
}

export function scale(value: number, domain: { min: number; max: number }, left: number, right: number): number {
  return left + ((value - domain.min) / (domain.max - domain.min)) * (right - left)
}

// --------------------------------------------------------------------------- //
// Robustness distribution arithmetic
// --------------------------------------------------------------------------- //

export interface DistributionPlot {
  domain: { min: number; max: number }
  bins: Array<{ from: number; to: number; count: number }>
  binWidth: number
}

const DISTRIBUTION_BINS = 16

/** A fixed-count histogram over the pooled [estimates ∪ original] range. */
export function distributionPlot(estimates: number[], original: number | null): DistributionPlot {
  const values = [...estimates]
  if (original !== null && Number.isFinite(original)) values.push(original)
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    min = 0
    max = 1
  }
  if (min === max) {
    min -= 1
    max += 1
  }
  const binWidth = (max - min) / DISTRIBUTION_BINS
  const bins = Array.from({ length: DISTRIBUTION_BINS }, (_, index) => ({
    from: min + index * binWidth,
    to: min + (index + 1) * binWidth,
    count: 0,
  }))
  for (const value of estimates) {
    const index = Math.min(DISTRIBUTION_BINS - 1, Math.max(0, Math.floor((value - min) / binWidth)))
    bins[index].count += 1
  }
  return { domain: { min, max }, bins, binWidth }
}

/**
 * Sensitivity grid colour scale: the signed distance from the original
 * estimate, as a fraction of the grid's largest absolute distance.
 */
export function sensitivityScale(
  grid: Array<Array<number | null>>,
  original: number,
): { maxDistance: number; cellTone: (value: number) => number } {
  let maxDistance = 0
  for (const row of grid) {
    for (const value of row) {
      if (value === null) continue
      maxDistance = Math.max(maxDistance, Math.abs(value - original))
    }
  }
  if (maxDistance === 0) maxDistance = 1
  return {
    maxDistance,
    cellTone: (value: number) => Math.max(-1, Math.min(1, (value - original) / maxDistance)),
  }
}

export function formatNumber(value: number, digits = 3): string {
  if (!Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}
