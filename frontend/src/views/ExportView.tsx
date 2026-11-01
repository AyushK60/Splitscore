/**
 * Report export.
 *
 * Exports are produced by the backend from the stored run, so what you download is
 * exactly what you reviewed. This view states what each artifact contains, what it
 * deliberately leaves out, and how the CSV assignment handles spreadsheet formula
 * injection.
 */

import { useEffect } from 'react'

import { Callout, Card, EmptyState, Table } from '../components/ui'
import { bytes, integer, pluralise } from '../lib/format'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'

export function ExportView({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const { audit, comparison, health, busyLabel, download, refreshHealth } = useApp()

  // The "Runtime state" counters change as the session progresses; re-fetch on
  // every visit so this page never shows the startup snapshot.
  useEffect(() => {
    void refreshHealth()
  }, [refreshHealth])

  const hasAudit = Boolean(audit)
  const hasComparison = Boolean(comparison)

  return (
    <div className="stack">
      <Card title="Report contents">
        <p className="small muted" style={{ marginTop: 0 }}>
          Every report carries the app version, the audit schema version, a UTC generation timestamp,
          the input file’s SHA-256 fingerprint, the dataset dimensions, the column roles, the audit
          settings and thresholds, the split strategy with its achieved sizes and seed, the evaluated
          / skipped / unsupported checks, the findings with a bounded evidence sample, and the stated
          limitations.
        </p>
        <Callout tone="info" title="What is deliberately not in the report">
          The full uploaded dataset is never embedded by default. Only the bounded example rows
          attached to findings appear. A SHA-256 fingerprint is a reproducibility identifier — it
          proves which bytes were audited, and it does not anonymise them.
        </Callout>
        <Callout tone="info" title="Determinism">
          For the same input, roles and settings, the algorithm outputs are deterministic. Only the
          generation timestamp and the runtime run identifier differ between two runs.
        </Callout>
      </Card>

      <Card title="Audit run">
        {!hasAudit ? (
          <EmptyState
            title="No audit run in this session"
            action={
              <button type="button" className="btn btn--primary" onClick={() => onNavigate('dataset')}>
                Go run an audit
              </button>
            }
          >
            A report always describes one stored run. Run the audit first.
          </EmptyState>
        ) : (
          <>
            <div className="kv">
              <dt>Run id</dt>
              <dd className="mono">{audit?.run_id}</dd>
              <dt>Split audited</dt>
              <dd>{audit?.result.split.label}</dd>
              <dt>Seed</dt>
              <dd className="mono">
                {audit?.result.split.seed !== null && audit?.result.split.seed !== undefined
                  ? audit.result.split.seed
                  : '— (not a generated split)'}
              </dd>
              <dt>Findings</dt>
              <dd>{integer(audit?.result.evaluation.findings_total ?? 0)}</dd>
              <dt>Generated</dt>
              <dd>{audit?.result.generated_at_utc}</dd>
              <dt>Input fingerprint</dt>
              <dd className="mono tiny break">{audit?.result.dataset.fingerprint_sha256}</dd>
            </div>
            {audit?.assignment ? (
              <p className="small">
                <button
                  type="button"
                  className="btn btn--small"
                  disabled={busyLabel !== null}
                  onClick={() => void download(audit.assignment?.download_path ?? '')}
                >
                  Download split assignment CSV
                </button>{' '}
                <span className="muted">
                  {audit.assignment.label} — every row's side as the audit used it, keyed by the
                  internal row id.
                </span>
              </p>
            ) : null}
            <p>
              <button
                type="button"
                className="btn btn--primary"
                disabled={busyLabel !== null}
                onClick={() =>
                  void download('/api/reports/json', { run_id: audit?.run_id })
                }
              >
                Download JSON report
              </button>{' '}
              <button
                type="button"
                className="btn"
                disabled={busyLabel !== null}
                onClick={() =>
                  void download('/api/reports/html', { run_id: audit?.run_id })
                }
              >
                Download self-contained HTML report
              </button>
            </p>
            <p className="small muted" style={{ marginBottom: 0 }}>
              The HTML report is one file with inline styles: open it in a browser and print it to PDF
              if you need a portable copy. All user-supplied text is HTML-escaped when the report is
              built.
            </p>
          </>
        )}
      </Card>

      <Card title="Split comparison run">
        {!hasComparison ? (
          <EmptyState
            title="No comparison run in this session"
            action={
              <button type="button" className="btn btn--primary" onClick={() => onNavigate('comparison')}>
                Go compare splits
              </button>
            }
          >
            Comparison reports describe one stored comparison run.
          </EmptyState>
        ) : (
          <>
            <div className="kv">
              <dt>Run id</dt>
              <dd className="mono">{comparison?.run_id}</dd>
              <dt>Candidates</dt>
              <dd>{comparison?.result.rows.length}</dd>
              <dt>Generated</dt>
              <dd>{comparison?.result.generated_at_utc}</dd>
            </div>
            <p>
              <button
                type="button"
                className="btn btn--primary"
                disabled={busyLabel !== null}
                onClick={() => void download('/api/reports/json', { run_id: comparison?.run_id })}
              >
                Download comparison JSON
              </button>{' '}
              <button
                type="button"
                className="btn"
                disabled={busyLabel !== null}
                onClick={() => void download('/api/reports/html', { run_id: comparison?.run_id })}
              >
                Download comparison HTML
              </button>
            </p>

            {comparison?.assignments.length ? (
              <>
                <h3>Split assignments</h3>
                <Callout tone="warn" title="Export sanitization">
                  {comparison.sanitization_note}
                </Callout>
                <Table
                  caption="One CSV per candidate split, keyed by the stable internal row id."
                  head={
                    <tr>
                      <th scope="col">Strategy</th>
                      <th scope="col" className="num">
                        Train rows
                      </th>
                      <th scope="col" className="num">
                        Test rows
                      </th>
                      <th scope="col">Download</th>
                    </tr>
                  }
                >
                  {comparison.assignments.map((handle) => (
                    <tr key={handle.assignment_id}>
                      <th scope="row">
                        {handle.label}
                        <span className="hint mono">{handle.kind}</span>
                      </th>
                      <td className="num">{integer(handle.train_rows)}</td>
                      <td className="num">{integer(handle.test_rows)}</td>
                      <td>
                        <button
                          type="button"
                          className="btn btn--small"
                          disabled={busyLabel !== null}
                          onClick={() => void download(handle.download_path)}
                        >
                          Download CSV
                        </button>
                      </td>
                    </tr>
                  ))}
                </Table>
              </>
            ) : null}
          </>
        )}
      </Card>

      <Card title="Runtime state and limits">
        {health ? (
          <div className="kv">
            <dt>This process holds</dt>
            <dd>
              {integer(health.store.datasets)} {pluralise(health.store.datasets, 'dataset')},{' '}
              {integer(health.store.runs)} {pluralise(health.store.runs, 'run')},{' '}
              {integer(health.store.assignments)}{' '}
              {pluralise(health.store.assignments, 'split assignment')}
            </dd>
            <dt>Memory used by the store</dt>
            <dd>
              {bytes(health.store.total_bytes)} of {bytes(health.store.limits.max_total_bytes ?? 0)}
            </dd>
            <dt>Evictions / expirations so far</dt>
            <dd>
              {integer(health.store.evictions)} / {integer(health.store.expirations)}
            </dd>
            <dt>Store TTL</dt>
            <dd>
              {health.store.limits.ttl_seconds ?? '—'} seconds. {health.storage_note}
            </dd>
            <dt>Upload limits</dt>
            <dd>
              {bytes(health.limits.max_upload_bytes)} per file · {integer(health.limits.max_rows)}{' '}
              rows · {integer(health.limits.max_columns)} columns
            </dd>
            <dt>Near-duplicate bound</dt>
            <dd>
              at most {integer(health.limits.near_duplicate_max_combined_rows)} combined rows enter the
              distance computation; at most{' '}
              {integer(health.limits.near_duplicate_max_reported_pairs)} pairs are retained as
              evidence
            </dd>
          </div>
        ) : (
          <EmptyState title="The health endpoint has not answered yet" />
        )}
        <p className="small muted" style={{ marginBottom: 0 }}>
          Refreshing the browser tab does not keep a run: the store lives in the server process, and a
          run is addressed by the id shown above until it expires or the process restarts.
        </p>
      </Card>
    </div>
  )
}
