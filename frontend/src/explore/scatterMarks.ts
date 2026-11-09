/**
 * Shared scatter-mark rules for the explorer.
 *
 * Dense samples need a wider stroke and a light halo to stay legible on warm
 * paper. Low-cardinality axes (for example `month_index` with six values) would
 * otherwise collapse into perfectly vertical stacks; those axes receive a
 * deterministic sub-5px display offset. The offset is disclosed in the figure
 * caption, never applied to the underlying values, brush predicates or
 * correlation estimates.
 */

export const SCATTER_PALETTE = [
  '#7e1f2c',
  '#e0a21b',
  '#2f2b27',
  '#c4577a',
  '#a89a88',
  '#8c5a3c',
  '#e8c36a',
  '#d98ca3',
] as const

export function groupColors(levels: string[]): string[] {
  return levels.map((_, index) => SCATTER_PALETTE[index % SCATTER_PALETTE.length])
}

export function markStrokeWidth(drawnRows: number): number {
  if (drawnRows > 1200) return 2.15
  if (drawnRows > 500) return 2.55
  return 3.1
}

/** True when an axis has few enough distinct values that marks will overplot. */
export function isDiscreteAxis(values: number[]): boolean {
  if (values.length < 8) return false
  return new Set(values).size <= 12
}

/**
 * A stable offset derived from the row id and axis. It is deterministic across
 * renders, so a point never dances when selection or colour grouping changes.
 */
export function jitterOffset(rowId: string, axis: 'x' | 'y', maxPixels = 4.2): number {
  let hash = axis === 'x' ? 2166136261 : 2246822519
  for (let index = 0; index < rowId.length; index += 1) {
    hash ^= rowId.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  // Map unsigned 32-bit to [-1, 1] with a small irrational step to avoid bands.
  const unit = ((hash >>> 0) / 0xffffffff) * 2 - 1
  return unit * maxPixels
}

export function pearsonR(
  rows: Array<{ values: Record<string, number | string | null> }>,
  x: string,
  y: string,
): number | null {
  let n = 0
  let sumX = 0
  let sumY = 0
  let sumXX = 0
  let sumYY = 0
  let sumXY = 0
  for (const row of rows) {
    const xv = row.values[x]
    const yv = row.values[y]
    if (typeof xv !== 'number' || typeof yv !== 'number') continue
    if (!Number.isFinite(xv) || !Number.isFinite(yv)) continue
    n += 1
    sumX += xv
    sumY += yv
    sumXX += xv * xv
    sumYY += yv * yv
    sumXY += xv * yv
  }
  if (n < 3) return null
  const numerator = n * sumXY - sumX * sumY
  const denominator = Math.sqrt((n * sumXX - sumX * sumX) * (n * sumYY - sumY * sumY))
  if (!Number.isFinite(denominator) || denominator === 0) return null
  return Math.max(-1, Math.min(1, numerator / denominator))
}

export function formatCorrelation(value: number | null): string {
  if (value === null) return 'r —'
  return `r ${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(2)}`
}

export function pointOpacity(drawnRows: number, hasSelection: boolean): number {
  if (hasSelection) return 0.2
  if (drawnRows > 1200) return 0.7
  if (drawnRows > 500) return 0.78
  return 0.86
}
