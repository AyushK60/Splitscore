/**
 * Workspace entry (S5).
 *
 * The workbench has ONE public landing page; this is not a second one. It is
 * the instrument's entry panel: when no dataset is active it offers the three
 * real ways in (upload, bundled synthetic demonstration, resume the session's
 * dataset when one exists), and when a dataset is already loaded it becomes a
 * contextual overview of where the session stands and what to do next.
 */

import { useRef } from 'react'

import { integer } from '../lib/format'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'

interface DemoEntry {
  demo_id: string
  title: string
  subtitle: string
  teaching_point: string
  row_count: number
  column_count: number
  file_present: boolean
}

function fingerprint8(sha: string): string {
  return sha.slice(0, 8)
}

/** Contextual overview: a dataset is already active in this session. */
function SessionOverview({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const { dataset, roles, audit, comparison } = useApp()
  if (!dataset) return null
  const summary = dataset.dataset
  const splitLabel =
    roles.split && roles.split_train_value && roles.split_test_value
      ? `${roles.split}: ${roles.split_train_value} / ${roles.split_test_value}`
      : 'not chosen yet — set it in Data'
  const stages: Array<{
    id: ViewId
    title: string
    state: string
    action: string
  }> = [
    {
      id: 'dataset',
      title: 'Data',
      state: 'File loaded and roles proposed',
      action: 'Verify split source and column roles',
    },
    {
      id: 'audit',
      title: 'Audit results',
      state: audit
        ? `Audit run — ${audit.result.findings.length} finding${audit.result.findings.length === 1 ? '' : 's'}`
        : 'Not audited yet in this session',
      action: audit ? 'Review findings and the risk scorecard' : 'Run the audit from Data',
    },
    {
      id: 'study',
      title: 'Study',
      state: dataset.dataset ? 'Data dictionary and profile available' : '',
      action: 'Record the study card and methodology (optional)',
    },
    {
      id: 'explore',
      title: 'Explore',
      state: `${integer(summary.row_count)} rows ready for the visual explorer`,
      action: 'Inspect distributions and link selections (optional)',
    },
    {
      id: 'comparison',
      title: 'Compare',
      state: comparison ? 'Split comparison available' : 'No comparison run yet',
      action: 'Compare alternative ways of splitting',
    },
  ]

  return (
    <div className="rs we">
      <p className="rs-eyebrow">Workspace — session active</p>
      <h1 className="rs-h1">Where this session stands</h1>
      <p className="rs-lede">
        A dataset is loaded in memory. Everything below reads the same session context; nothing
        here is persisted between browser sessions unless you export it.
      </p>

      <section className="we__context" aria-label="Active dataset">
        <div className="we__contextfile">
          <span className="we__contextname">{summary.name}</span>
          <span className="xw__badge">
            {summary.source === 'demo' ? 'Synthetic demo' : 'Uploaded file'}
          </span>
        </div>
        <dl className="we__facts">
          <div>
            <dt>Shape</dt>
            <dd>
              {integer(summary.row_count)} rows × {summary.column_count} columns
            </dd>
          </div>
          <div>
            <dt>Fingerprint</dt>
            <dd className="mono">{fingerprint8(summary.fingerprint_sha256)}…</dd>
          </div>
          <div>
            <dt>Split</dt>
            <dd>{splitLabel}</dd>
          </div>
          <div>
            <dt>Entity</dt>
            <dd>{roles.entity ?? 'none declared'}</dd>
          </div>
        </dl>
      </section>

      <nav className="we__stages" aria-label="Workspace stages">
        {stages.map((stage) => (
          <button
            key={stage.id}
            type="button"
            className="we__stage"
            onClick={() => onNavigate(stage.id)}
          >
            <span className="we__stagetitle">{stage.title}</span>
            <span className="we__stagestate">{stage.state}</span>
            <span className="we__stageaction">{stage.action} →</span>
          </button>
        ))}
      </nav>
    </div>
  )
}

/** Entry panel: no usable dataset in this session yet. */
export function OverviewView({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const { dataset, demos, health, uploadFile, loadDemo, busyLabel } = useApp()
  const fileInput = useRef<HTMLInputElement>(null)

  if (dataset) {
    return <SessionOverview onNavigate={onNavigate} />
  }

  const demoList: DemoEntry[] = (demos?.demos ?? []).map((demo) => ({
    demo_id: demo.demo_id,
    title: demo.title,
    subtitle: demo.subtitle,
    teaching_point: demo.teaching_point,
    row_count: demo.row_count,
    column_count: demo.column_count,
    file_present: demo.file_present,
  }))
  const uploadLimitMb = health ? (health.limits.max_upload_bytes ?? 0) / (1024 * 1024) : null

  const openDemo = async (demoId: string) => {
    await loadDemo(demoId)
    onNavigate('dataset')
  }

  return (
    <div className="rs we">
      <p className="rs-eyebrow">Workspace entry</p>
      <h1 className="rs-h1">Load a dataset to begin</h1>
      <p className="rs-lede">
        The workbench audits a train/test split for leakage. Everything starts from one dataset —
        bring your own file, or open a bundled synthetic demonstration with its leak built in.
      </p>

      <div className="we__entry">
        <section className="we__panel we__panel--upload" aria-labelledby="we-upload">
          <h2 id="we-upload" className="we__paneltitle">
            1 — Upload a dataset
          </h2>
          <p className="we__paneltext">
            Your own CSV with the rows you want to audit. The file is read into server memory for
            this session only; it is never written to disk and never leaves your machine.
          </p>
          <button
            type="button"
            className="btn btn--primary"
            disabled={busyLabel !== null}
            onClick={() => fileInput.current?.click()}
          >
            Choose a CSV file
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,.txt,.tsv,text/csv"
            className="visually-hidden"
            tabIndex={-1}
            aria-hidden="true"
            onChange={async (event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (file) {
                await uploadFile(file)
                onNavigate('dataset')
              }
            }}
          />
          <ul className="we__honest">
            <li>Formats: .csv, .tsv, .txt (comma- or tab-separated text)</li>
            <li>
              {uploadLimitMb
                ? `Limit: up to ${uploadLimitMb.toFixed(0)} MB per upload`
                : 'Limits are reported by the backend once it responds'}
            </li>
            <li>In-memory session storage · SHA-256 fingerprint for reproducibility</li>
          </ul>
        </section>

        <section className="we__panel" aria-labelledby="we-demos">
          <h2 id="we-demos" className="we__paneltitle">
            2 — Open a synthetic demonstration
          </h2>
          <p className="we__paneltext">
            Six bundled datasets, each generated with a specific leakage problem built in. They are
            teaching data — not real people or events — and each states what it demonstrates.
          </p>
          {!demos ? (
            <p className="we__paneltext">
              The demo list has not loaded yet. If it stays empty, check that the backend is
              running.
            </p>
          ) : (
            <ul className="we__demolist">
              {demoList.map((demo) => (
                <li key={demo.demo_id} className="we__demo">
                  <div className="we__demomain">
                    <span className="we__demotitle">{demo.title}</span>
                    <span className="we__demosub">{demo.subtitle}</span>
                    <span className="we__demopoint">{demo.teaching_point}</span>
                    <span className="we__demometa">
                      Synthetic · {integer(demo.row_count)} rows × {demo.column_count} columns
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn--small btn--primary"
                    disabled={busyLabel !== null || !demo.file_present}
                    onClick={() => void openDemo(demo.demo_id)}
                  >
                    Open
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <p className="we__footnote">
        A loaded dataset opens the Data stage, where the split source and column roles are
        confirmed before anything is audited. Steps that cannot run yet stay disabled rather than
        pretending.
      </p>
    </div>
  )
}
