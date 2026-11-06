/**
 * Shared API error presentation for the estimation studio (S9B) and the
 * causal research stage (S9C). Both surfaces show the backend's own message,
 * its structured fix/violation details, and the typed 410/409 explanations —
 * never a generic "something went wrong" for a refusal the backend named.
 */

import { ApiError } from '../api/client'

export interface ErrorInfo {
  title: string
  message: string
  details: string[]
  status: number
}

export function describeError(error: unknown, fallback: string): ErrorInfo {
  if (error instanceof ApiError) {
    const details: string[] = []
    const raw = error.details ?? {}
    const verification = raw['verification'] as
      | { violations?: Array<{ code?: string; node_id?: string | null; message?: string }> }
      | undefined
    for (const violation of verification?.violations ?? []) {
      details.push(
        `${violation.code ?? 'violation'}${violation.node_id ? ` (${violation.node_id})` : ''}: ${violation.message ?? ''}`,
      )
    }
    const unmatched = raw['unmatched_values_with_counts']
    if (Array.isArray(unmatched)) {
      for (const entry of unmatched) details.push(JSON.stringify(entry))
    }
    for (const key of ['missing_columns', 'fix', 'reason'] as const) {
      const value = raw[key]
      if (typeof value === 'string') details.push(value)
      if (Array.isArray(value)) details.push(value.map(String).join(', '))
    }
    if (error.status === 410) {
      return {
        title: 'The dataset is no longer available',
        message:
          'The backend has expired or evicted this dataset from its bounded in-memory store. Nothing can be estimated against it until it is loaded again.',
        details: ['Load the dataset again from Start, then return to this studio.'],
        status: 410,
      }
    }
    if (error.code === 'infeasible_operation' || error.status === 409) {
      return {
        title: 'The graph changed on the server',
        message: error.message,
        details: [
          'Reload the saved graph and check the readiness probe again. A layout-only edit never causes this; a structural edit does.',
          ...details,
        ],
        status: error.status,
      }
    }
    return { title: fallback, message: error.message, details, status: error.status }
  }
  return {
    title: fallback,
    message: error instanceof Error ? error.message : 'The backend could not be reached.',
    details: [],
    status: 0,
  }
}
