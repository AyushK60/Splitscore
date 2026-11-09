/**
 * Scatter render rules: deterministic jitter, discrete-axis detection, sampled
 * correlation and visibility tiers. These are display rules only; the tests
 * pin the honesty boundary - jitter never changes the underlying value and
 * correlation ignores non-numeric or non-finite cells.
 */
import { describe, expect, it } from 'vitest'

import {
  SCATTER_PALETTE,
  formatCorrelation,
  groupColors,
  isDiscreteAxis,
  jitterOffset,
  markStrokeWidth,
  pearsonR,
  pointOpacity,
} from '../src/explore/scatterMarks'

describe('discrete-axis detection', () => {
  it('flags a low-cardinality numeric axis with enough rows to overplot', () => {
    expect(isDiscreteAxis([1, 2, 3, 4, 5, 6, 1, 2, 3])).toBe(true)
  })

  it('does not flag a continuous axis or a tiny sample', () => {
    const continuous = Array.from({ length: 40 }, (_, index) => index * 1.37)
    expect(isDiscreteAxis(continuous)).toBe(false)
    expect(isDiscreteAxis([1, 1, 1, 1, 1, 1, 1])).toBe(false)
  })
})

describe('jitter offsets', () => {
  it('is deterministic per row and axis', () => {
    expect(jitterOffset('row-000001', 'x')).toBe(jitterOffset('row-000001', 'x'))
    expect(jitterOffset('row-000001', 'x')).not.toBe(jitterOffset('row-000001', 'y'))
  })

  it('stays inside the disclosed pixel bound and differs across rows', () => {
    const offsets = ['row-000001', 'row-000002', 'row-000003', 'row-000004'].map((id) =>
      jitterOffset(id, 'y'),
    )
    for (const offset of offsets) {
      expect(Math.abs(offset)).toBeLessThanOrEqual(4.2)
    }
    expect(new Set(offsets).size).toBeGreaterThan(1)
  })
})

describe('pearson correlation', () => {
  const rows = [
    { values: { x: 1, y: 2 } },
    { values: { x: 2, y: 4 } },
    { values: { x: 3, y: 6 } },
    { values: { x: 4, y: 8 } },
    { values: { x: 5, y: null } },
    { values: { x: 6, y: 'n/a' } },
  ]

  it('uses only finite numeric pairs', () => {
    expect(pearsonR(rows, 'x', 'y')).toBeCloseTo(1, 12)
  })

  it('returns null when fewer than three pairs or variance is zero', () => {
    expect(pearsonR(rows.slice(0, 2), 'x', 'y')).toBeNull()
    expect(
      pearsonR(
        [
          { values: { x: 1, y: 1 } },
          { values: { x: 1, y: 2 } },
          { values: { x: 1, y: 3 } },
        ],
        'x',
        'y',
      ),
    ).toBeNull()
  })

  it('formats a signed coefficient and the unavailable state', () => {
    expect(formatCorrelation(0.834)).toBe('r +0.83')
    expect(formatCorrelation(-0.124)).toBe('r −0.12')
    expect(formatCorrelation(null)).toBe('r -')
  })
})

describe('mark visibility tiers', () => {
  it('widens strokes and raises opacity as the drawn sample shrinks', () => {
    expect(markStrokeWidth(200)).toBeGreaterThan(markStrokeWidth(800))
    expect(markStrokeWidth(800)).toBeGreaterThan(markStrokeWidth(2000))
    expect(pointOpacity(200, false)).toBeGreaterThan(pointOpacity(800, false))
    expect(pointOpacity(800, false)).toBeGreaterThan(pointOpacity(2000, false))
    expect(pointOpacity(200, true)).toBeLessThan(pointOpacity(2000, false))
  })

  it('cycles a bounded palette without inventing extra group colours', () => {
    expect(groupColors(['a', 'b', 'c'])).toEqual(SCATTER_PALETTE.slice(0, 3))
    const many = groupColors(Array.from({ length: 11 }, (_, index) => `g${index}`))
    expect(many).toHaveLength(11)
    expect(many[8]).toBe(SCATTER_PALETTE[0])
  })
})
