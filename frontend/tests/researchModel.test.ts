/**
 * estimation research model layer: pure arithmetic and request reconstruction.
 * Expectations are hand-computed, never derived from the implementation.
 */
import { describe, expect, it } from 'vitest'

import { runPayload } from './estimationFixtures'
import {
  distributionPlot,
  forestDomain,
  requestFromRun,
  scale,
  sensitivityScale,
} from '../src/research/researchModel'
import { subgroupPayload } from './researchFixtures'

describe('requestFromRun', () => {
  it('rebuilds the exact request a stored run used, including the fingerprint guard', () => {
    const run = runPayload()
    const request = requestFromRun(run.reproducibility)
    expect(request.treatment_node).toBe(run.reproducibility.treatment_node)
    expect(request.outcome_node).toBe(run.reproducibility.outcome_node)
    expect(request.adjustment_nodes).toEqual([...run.reproducibility.adjustment_nodes].sort())
    expect(request.treatment_mapping).toEqual(run.reproducibility.treatment_mapping)
    expect(request.missing_data_policy).toBe(run.reproducibility.missing_data_policy)
    expect(request.cross_fit).toEqual({
      splits: run.reproducibility.cross_fitting.splits,
      group_column: run.reproducibility.cross_fitting.group_column,
    })
    expect(request.uncertainty.seed).toBe(run.reproducibility.uncertainty.resolved_seed)
    expect(request.expected_spec_fingerprint_sha256).toBe(
      run.reproducibility.graph_spec_fingerprint_sha256,
    )
  })
})

describe('forestDomain', () => {
  it('spans zero, the overall estimate and every interval bound', () => {
    const payload = subgroupPayload()
    const domain = forestDomain(payload.groups, payload.overall.estimate)
    expect(domain.min).toBeLessThanOrEqual(0)
    expect(domain.min).toBeLessThan(1.0) // lowest interval bound
    expect(domain.max).toBeGreaterThan(2.03) // highest interval bound
  })

  it('never collapses to a zero-width domain', () => {
    const domain = forestDomain([], 1.5)
    expect(domain.max - domain.min).toBeGreaterThan(0)
  })
})

describe('scale', () => {
  it('maps the domain onto the pixel range linearly', () => {
    expect(scale(0, { min: 0, max: 10 }, 100, 200)).toBe(100)
    expect(scale(10, { min: 0, max: 10 }, 100, 200)).toBe(200)
    expect(scale(5, { min: 0, max: 10 }, 100, 200)).toBe(150)
  })
})

describe('distributionPlot', () => {
  it('bins the estimates into 16 bins and includes the original in the domain', () => {
    const estimates = Array.from({ length: 32 }, (_, index) => (index % 2 === 0 ? index / 2 : -index / 2))
    const plot = distributionPlot(estimates, 10)
    expect(plot.bins).toHaveLength(16)
    const span = plot.domain.max - plot.domain.min
    expect(plot.domain.max).toBeGreaterThanOrEqual(10 - span / 16)
    expect(plot.domain.min).toBeLessThanOrEqual(-15.5 + span / 16)
    const total = plot.bins.reduce((sum, bin) => sum + bin.count, 0)
    expect(total).toBe(estimates.length)
  })

  it('degenerates safely on a single repeated value', () => {
    const plot = distributionPlot([1.5, 1.5, 1.5], 1.5)
    expect(plot.domain.max).toBeGreaterThan(plot.domain.min)
    expect(plot.bins.every((bin) => bin.count >= 0)).toBe(true)
  })
})

describe('sensitivityScale', () => {
  it('normalises distances by the largest absolute movement', () => {
    const grid = [
      [1.5, 1.4],
      [1.2, null],
    ]
    const { maxDistance, cellTone } = sensitivityScale(grid, 1.5)
    expect(maxDistance).toBeCloseTo(0.3, 10)
    expect(cellTone(1.5)).toBe(0)
    // Signed tone: below the original is negative; the CSS shades by |tone|.
    expect(cellTone(1.35)).toBeCloseTo(-0.5, 10)
    expect(cellTone(1.2)).toBeCloseTo(-1, 10)
    expect(cellTone(1.8)).toBeCloseTo(1, 10)
  })

  it('is safe when every cell equals the original', () => {
    const { maxDistance, cellTone } = sensitivityScale([[1.5]], 1.5)
    expect(maxDistance).toBe(1)
    expect(cellTone(1.5)).toBe(0)
  })
})
