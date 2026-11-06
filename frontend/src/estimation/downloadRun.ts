/**
 * Download one estimation run exactly as the backend returned it.
 *
 * This is the reproducibility artifact: every estimate, diagnostic, warning,
 * fingerprint, seed and software version in one JSON file. Nothing is added or
 * recomputed here.
 */

import type { EstimationRunPayload } from '../api/types'

export function estimationExport(payload: EstimationRunPayload): void {
  const envelope = {
    export_kind: 'splitscope_causal_estimation_run',
    exported_at_utc: new Date().toISOString(),
    note: 'This file is the backend estimation payload verbatim plus the export envelope. It carries no uploaded data rows.',
    run: payload,
  }
  const blob = new Blob([JSON.stringify(envelope, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `splitscope_estimation_${payload.run_id}.json`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
