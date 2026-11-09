/**
 * estimation UI model helpers: request construction, signatures and staleness rules.
 *
 * These are pure functions, so they are tested directly; the heavy rendering
 * behaviour lives in the component tests beside this file.
 */
import { describe, expect, it } from 'vitest'

import {
  buildRequest,
  defaultConfig,
  diagnosticResult,
  overlapResult,
  requestSignature,
  stalenessReasons,
  type EstimationConfig,
} from '../src/estimation/estimationModel'
import { niceTicks, formatNumber, unitsLabel } from '../src/estimation/format'
import {
  DATASET_FINGERPRINT,
  GRAPH_FINGERPRINT,
  estimatedResult,
  failedResult,
  runPayload,
} from './estimationFixtures'

function config(overrides: Partial<EstimationConfig> = {}): EstimationConfig {
  return {
    ...defaultConfig(),
    treatmentNode: 'treatment',
    outcomeNode: 'outcome',
    adjustmentNodes: ['region', 'age'],
    ...overrides,
  }
}

describe('buildRequest', () => {
  it('maps every field to the strict estimation request shape', () => {
    const request = buildRequest(
      config({
        treatedValue: 'yes',
        controlValue: 'no',
        missingPolicy: 'median_mode',
        uncertaintyMethod: 'influence_function',
        bootstrapReps: 250,
        seed: '42',
        truncationEnabled: true,
        truncationLower: 0.1,
        truncationUpper: 0.9,
        crossFitSplits: 3,
        groupColumn: 'unit_id',
      }),
      GRAPH_FINGERPRINT,
    )

    expect(request).toEqual({
      estimand: 'ate',
      treatment_node: 'treatment',
      outcome_node: 'outcome',
      adjustment_nodes: ['age', 'region'],
      treatment_mapping: { treated: 'yes', control: 'no' },
      cohort: { split_assignment_id: null, partition: null },
      missing_data_policy: 'median_mode',
      cross_fit: { splits: 3, group_column: 'unit_id' },
      uncertainty: { method: 'influence_function', level: 0.95, reps: 250, seed: 42 },
      propensity_truncation: { lower: 0.1, upper: 0.9 },
      expected_spec_fingerprint_sha256: GRAPH_FINGERPRINT,
    })
  })

  it('sends an explicit null cohort and no truncation unless requested', () => {
    const request = buildRequest(config(), GRAPH_FINGERPRINT)
    expect(request.cohort).toEqual({ split_assignment_id: null, partition: null })
    expect(request.propensity_truncation).toBeNull()
    expect(request.uncertainty.seed).toBeNull()
  })

  it('names a partition only when an assignment id is supplied', () => {
    const withoutAssignment = buildRequest(config({ cohortPartition: 'train' }), GRAPH_FINGERPRINT)
    expect(withoutAssignment.cohort).toEqual({ split_assignment_id: null, partition: null })

    const withAssignment = buildRequest(
      config({ cohortAssignment: 'assign-1', cohortPartition: 'train' }),
      GRAPH_FINGERPRINT,
    )
    expect(withAssignment.cohort).toEqual({ split_assignment_id: 'assign-1', partition: 'train' })
  })
})

describe('requestSignature', () => {
  it('changes when the request, graph or dataset changes and not otherwise', () => {
    const context = { datasetId: 'ds-1', graphId: 'g-1', graphFingerprint: GRAPH_FINGERPRINT }
    const base = requestSignature(buildRequest(config(), GRAPH_FINGERPRINT), context)
    expect(requestSignature(buildRequest(config(), GRAPH_FINGERPRINT), context)).toBe(base)
    expect(
      requestSignature(buildRequest(config({ bootstrapReps: 300 }), GRAPH_FINGERPRINT), context),
    ).not.toBe(base)
    expect(requestSignature(buildRequest(config(), GRAPH_FINGERPRINT), { ...context, graphFingerprint: 'c'.repeat(64) })).not.toBe(base)
    expect(requestSignature(buildRequest(config(), GRAPH_FINGERPRINT), { ...context, datasetId: 'ds-2' })).not.toBe(base)
  })
})

describe('stalenessReasons', () => {
  const payload = runPayload()
  const context = {
    datasetFingerprint: DATASET_FINGERPRINT,
    graphId: 'cgraph-s9b-fixture',
    graphFingerprint: GRAPH_FINGERPRINT,
    config: config({
      bootstrapReps: 500,
      seed: '',
      uncertaintyLevel: 0.95,
      adjustmentNodes: ['age', 'baseline_score', 'region'],
    }),
  }

  it('reports nothing when the result matches the current study', () => {
    expect(stalenessReasons(payload, context)).toEqual([])
  })

  it('reports a layout-only graph edit as not stale (fingerprint unchanged)', () => {
    // A layout drag never reaches this function with a new fingerprint: the
    // scientific fingerprint is what is compared.
    expect(stalenessReasons(payload, { ...context, graphFingerprint: GRAPH_FINGERPRINT })).toEqual([])
  })

  it('names a dataset change, a graph change and a different graph', () => {
    const reasons = stalenessReasons(payload, {
      ...context,
      datasetFingerprint: 'd'.repeat(64),
      graphFingerprint: 'e'.repeat(64),
      graphId: 'other-graph',
    }).map((reason) => reason.code)
    expect(reasons.slice(0, 3)).toEqual(['dataset_changed', 'graph_switched', 'graph_changed'])
  })

  it('names each configuration change separately', () => {
    const reasons = stalenessReasons(payload, {
      ...context,
      config: config({
        bootstrapReps: 250,
        seed: '7',
        adjustmentNodes: ['age'],
        treatedValue: 'yes',
        missingPolicy: 'median_mode',
        crossFitSplits: 3,
        cohortAssignment: 'assign-9',
      }),
    }).map((reason) => reason.code)

    expect(reasons).toEqual(
      expect.arrayContaining([
        'adjustment_changed',
        'mapping_changed',
        'cohort_changed',
        'missing_policy_changed',
        'crossfit_changed',
        'reps_changed',
        'seed_changed',
      ]),
    )
  })

  it('trusts the server stale flag and carries its reason', () => {
    const reasons = stalenessReasons(
      { ...payload, stale: true, staleness_reason: 'The graph changed on the server.' },
      context,
    )
    expect(reasons[0]).toEqual({ code: 'server_stale', label: 'The graph changed on the server.' })
  })
})

describe('diagnostics selection', () => {
  it('prefers a weighted result and falls back to regression adjustment', () => {
    const payload = runPayload()
    expect(diagnosticResult(payload)?.estimator).toBe('ipw')
    expect(overlapResult(payload)?.estimator).toBe('ipw')

    const unweighted = runPayload({ results: [estimatedResult('regression_adjustment')] })
    expect(diagnosticResult(unweighted)?.estimator).toBe('regression_adjustment')
    expect(overlapResult(unweighted)).toBeNull()
  })

  it('never treats a failed estimator as a source of diagnostics', () => {
    const payload = runPayload({
      results: [failedResult('ipw'), estimatedResult('aipw')],
    })
    expect(diagnosticResult(payload)?.estimator).toBe('aipw')
  })
})

describe('presentation helpers', () => {
  it('formats numbers without inventing a zero for missing values', () => {
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber(1.2)).toBe('1.200')
    expect(formatNumber(-0.5, 2)).toBe('-0.50')
  })

  it('labels outcome units honestly', () => {
    expect(unitsLabel('outcome_units')).toBe('outcome units')
    expect(unitsLabel('probability_difference')).toBe('probability difference')
  })

  it('produces ticks that cover the domain', () => {
    const ticks = niceTicks(-0.5, 2.2, 5)
    expect(ticks.length).toBeGreaterThan(3)
    expect(Math.min(...ticks)).toBeGreaterThanOrEqual(-0.5)
    expect(Math.max(...ticks)).toBeLessThanOrEqual(2.2)
  })
})
