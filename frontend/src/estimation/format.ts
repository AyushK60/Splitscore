/**
 * Presentation formatting for the estimation studio.
 *
 * All values arrive from the backend at full precision; these helpers only
 * choose how many digits to *display*. They never recompute, rescale or
 * substitute a number, and an absent value renders as an explicit dash or an
 * "unavailable" phrase rather than a zero.
 */

export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function formatCompact(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return value.toLocaleString('en-US', { maximumFractionDigits: digits })
}

export function formatInteger(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return Math.round(value).toLocaleString('en-US')
}

export function unitsLabel(units: string | null | undefined, outcomeTask?: 'linear' | 'logistic'): string {
  if (units === 'probability_difference') return 'probability difference'
  if (units === 'outcome_units') return 'outcome units'
  if (outcomeTask === 'logistic') return 'probability difference'
  return 'outcome units'
}

export function estimateWithUnits(
  value: number | null | undefined,
  units: string | null | undefined,
  digits = 3,
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'Unavailable'
  const unit = units === 'probability_difference' ? 'probability points' : unitsLabel(units)
  return `${formatNumber(value, digits)} ${unit}`
}

/** A clean, human tick sequence covering the domain. */
export function niceTicks(min: number, max: number, target = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return [min]
  const span = max - min
  const rawStep = span / Math.max(1, target)
  const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)))
  const candidates = [1, 2, 2.5, 5, 10].map((factor) => factor * magnitude)
  // Choose the conventional step closest to the ideal spacing rather than the
  // next one up: rounding up too aggressively collapses a plot to three ticks.
  const step = candidates.reduce((best, candidate) =>
    Math.abs(Math.log(candidate / rawStep)) < Math.abs(Math.log(best / rawStep)) ? candidate : best,
  )
  const start = Math.ceil(min / step) * step
  const ticks: number[] = []
  for (let value = start; value <= max + step * 1e-9; value += step) {
    ticks.push(Number(value.toFixed(10)))
  }
  return ticks
}

export function tickLabel(value: number, step: number): string {
  if (Math.abs(value) < step * 1e-9) return '0'
  if (Math.abs(value) >= 100) return value.toFixed(0)
  if (Math.abs(value) >= 1) return value.toFixed(2).replace(/\.?0+$/, '')
  const decimals = Math.min(4, Math.max(1, Math.ceil(-Math.log10(step))))
  return value.toFixed(decimals).replace(/0+$/, '').replace(/\.$/, '')
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function formatAgo(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`
  return `${(seconds / 3600).toFixed(1)} h ago`
}

export function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function toCsv(header: string[], rows: Array<Array<unknown>>): string {
  return [header, ...rows].map((row) => row.map(csvCell).join(',')).join('\n')
}
