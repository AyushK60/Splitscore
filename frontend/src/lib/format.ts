import type { CheckStatus, Severity } from '../api/types'

export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

export function fraction(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

export function integer(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('en-US')
}

export function number(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return String(Number(value.toFixed(digits)))
}

export function bytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`
  return `${(value / (1024 * 1024)).toFixed(2)} MiB`
}

export function timestamp(iso: string | null | undefined): string {
  if (!iso) return '—'
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return `${parsed.toISOString().replace('T', ' ').slice(0, 19)} UTC`
}

export function humanDuration(milliseconds: number | null | undefined): string {
  if (milliseconds === null || milliseconds === undefined) return '—'
  if (milliseconds < 1000) return `${milliseconds.toFixed(1)} ms`
  return `${(milliseconds / 1000).toFixed(2)} s`
}

const SEVERITY_LABEL: Record<Severity, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
  info: 'Info',
}

export const SEVERITY_ORDER: Severity[] = ['high', 'medium', 'low', 'info']

export function severityLabel(severity: Severity): string {
  return SEVERITY_LABEL[severity]
}

const STATUS_LABEL: Record<CheckStatus, string> = {
  disabled: 'Disabled',
  not_evaluated: 'Not evaluated: role not selected',
  unsupported: 'Unsupported for this data',
  insufficient_data: 'Insufficient data',
  error: 'Check failed',
}

export function statusLabel(status: CheckStatus): string {
  return STATUS_LABEL[status]
}

export const STATUS_EXPLANATION: Record<CheckStatus, string> = {
  disabled: 'You turned this check off for this audit. It produced no result.',
  not_evaluated: 'A column role this check needs was not selected, so it did not run.',
  unsupported: 'The check is out of scope for this dataset or feature set in this version.',
  insufficient_data: 'A documented minimum (row count or coverage) was not met, so the check did not run.',
  error:
    'The check raised an error. The other checks still ran. This is not a passing result; please report it.',
}

/** Maps a rule id to the view section it belongs to, for filter grouping. */
export function ruleGroupLabel(category: string): string {
  switch (category) {
    case 'duplicate':
      return 'Duplicates'
    case 'group':
      return 'Groups / entities'
    case 'temporal':
      return 'Chronology'
    case 'target':
      return 'Target'
    case 'similarity':
      return 'Similarity'
    default:
      return category
  }
}

export function pluralise(count: number, singular: string, plural?: string): string {
  return count === 1 ? singular : (plural ?? `${singular}s`)
}

export function truncate(value: string, limit = 90): string {
  if (value.length <= limit) return value
  return `${value.slice(0, limit - 1)}…`
}

export function joinOrDash(values: string[], separator = ', '): string {
  return values.length ? values.join(separator) : '—'
}
