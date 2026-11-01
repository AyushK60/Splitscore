/**
 * Start (landing).
 *
 * The first screen answers three questions in order — what does this tool do,
 * how do I try it, what can it find — and shows what "shared information"
 * between a training and a testing side actually looks like before asking for
 * anything. The check catalogue, the honesty notes, the limits and the full
 * demo list stay one disclosure away, so a first-time reader is not asked to
 * digest them first.
 */

import { useRef } from 'react'

import { bytes, integer } from '../lib/format'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'
import { Callout } from '../components/ui'

/**
 * Two sides of a split, with two rows appearing on both sides.
 *
 * Purely decorative next to the caption that says the same thing in words; the
 * colours reuse the train/test palette used by the charts so the diagram and
 * the results speak one language.
 */
function OverlapDiagram() {
  const trainRows = [40, 64, 88, 112, 136]
  const shared = new Set([64, 112])
  return (
    <svg
      className="overlap-figure"
      viewBox="0 0 312 178"
      role="img"
      aria-label="Diagram: a training side and a testing side of a split; two rows appear on both sides — the shared information an audit looks for."
    >
      <text className="overlap-figure__label" x="16" y="20">
        TRAIN
      </text>
      <text className="overlap-figure__label" x="208" y="20">
        TEST
      </text>
      {trainRows.map((y) => {
        const isShared = shared.has(y)
        return (
          <g key={y}>
            <rect
              x="16"
              y={y}
              width="104"
              height="16"
              rx="4"
              className={isShared ? 'overlap-figure__row--shared' : 'overlap-figure__row--train'}
            />
            <rect
              x="192"
              y={y}
              width="104"
              height="16"
              rx="4"
              className={isShared ? 'overlap-figure__row--shared' : 'overlap-figure__row--test'}
            />
            {isShared ? (
              <line
                x1="126"
                y1={y + 8}
                x2="186"
                y2={y + 8}
                className="overlap-figure__link"
              />
            ) : null}
          </g>
        )
      })}
    </svg>
  )
}

export function OverviewView({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const { checks, demos, health, loadDemo, uploadFile, busyLabel } = useApp()
  const fileInput = useRef<HTMLInputElement>(null)

  const featured = demos?.featured_journey
  const otherDemos = demos?.demos ?? []
  const featuredId = featured?.demo_id
  const featuredDemo = otherDemos.find((demo) => demo.demo_id === featuredId)
  const uploadLimitMb = health ? (health.limits.max_upload_bytes ?? 0) / (1024 * 1024) : null

  // The gallery leads with the featured demo, then any demo whose file is
  // actually present. Everything stays reachable in "Browse other demos".
  const galleryDemos = [...otherDemos]
    .sort((a, b) => {
      if (a.demo_id === featuredId) return -1
      if (b.demo_id === featuredId) return 1
      return Number(b.file_present) - Number(a.file_present)
    })
    .slice(0, 3)

  const openDemo = async (demoId: string) => {
    await loadDemo(demoId)
    onNavigate('dataset')
  }

  return (
    <div className="landing">
      <section className="landing__hero">
        <div className="landing__hero-text">
          <p className="landing__eyebrow">
            <span className="badge badge--info">ML data-leakage checks</span>
          </p>
          <h1>Check whether your training and test data share information</h1>
          <p className="landing__lead">
            SplitScope checks whether your training and test rows share information — duplicated
            records, the same person or device on both sides, time leaks, or a column that copies
            the value you want to predict — that could make model results look better than they are.
          </p>

          <div className="landing__actions">
            <button
              type="button"
              className="btn btn--primary btn--big"
              disabled={busyLabel !== null || !featuredDemo?.file_present}
              onClick={() => void (featuredDemo && openDemo(featuredDemo.demo_id))}
            >
              Try a demo
            </button>
            <button
              type="button"
              className="btn btn--big"
              disabled={busyLabel !== null}
              onClick={() => fileInput.current?.click()}
            >
              Upload CSV
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
          </div>

          <p className="landing__note">
            “Try a demo” opens a small{' '}
            <strong>synthetic</strong> dataset ({featuredDemo ? featuredDemo.title : 'bundled demo'}){' '}
            with sensible settings already filled in. “Upload CSV” uses your own file
            {uploadLimitMb ? ` — CSV, up to ${uploadLimitMb.toFixed(0)} MB` : ''}; it stays in server
            memory and is never written to disk.
          </p>
        </div>

        <figure className="landing__figure">
          <OverlapDiagram />
          <figcaption>
            An audit looks for rows, people and dates that appear on both sides of a split — the
            overlap that makes test results look better than they are.
          </figcaption>
        </figure>
      </section>

      <section className="landing__gallery" aria-labelledby="scenarios">
        <h2 id="scenarios">Start from an example</h2>
        {!demos ? (
          <p className="hint">
            The bundled demo list has not loaded yet. You can still upload your own CSV; if that
            also fails, check that the backend is running.
          </p>
        ) : (
          <div className="scenario-grid">
            {galleryDemos.map((demo) => (
              <article className="scenario-card" key={demo.demo_id}>
                <div className="scenario-card__title">
                  <strong>{demo.title}</strong>
                </div>
                <p className="scenario-card__text">{demo.subtitle}</p>
                <div className="scenario-card__foot">
                  <span className="tiny muted">
                    Synthetic · {integer(demo.row_count)} × {demo.column_count}
                  </span>
                  <button
                    type="button"
                    className="btn btn--small btn--primary"
                    disabled={busyLabel !== null || !demo.file_present}
                    onClick={() => void openDemo(demo.demo_id)}
                  >
                    Open
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="landing__how" aria-labelledby="what-next">
        <h2 id="what-next">How it works</h2>
        <ol className="landing__steps">
          <li>
            <strong>Load a file</strong>
            Upload a CSV or open one of the synthetic demos. Your file stays in server memory.
          </li>
          <li>
            <strong>Answer a few questions</strong>
            Does the file already mark train and test? What does each column mean? Suggestions are
            shown with their reason and never applied silently.
          </li>
          <li>
            <strong>Run the audit</strong>
            Every enabled check runs, with the exact rows behind each finding — and checks that
            could not run are listed separately.
          </li>
          <li>
            <strong>Compare or export</strong>
            Optionally compare other ways of splitting, then export a JSON report or a
            self-contained HTML file.
          </li>
        </ol>
        {featured ? (
          <p className="landing__walkthrough">
            The featured demo walks through: {featured.steps.slice(0, 4).join(' → ')}
          </p>
        ) : null}
      </section>

      <details className="disclosure">
        <summary>Browse other demos</summary>
        <ul className="demo-list">
          {otherDemos.map((demo) => (
            <li key={demo.demo_id}>
              <div className="demo-list__row">
                <div>
                  <div className="demo-list__title">
                    <strong>{demo.title}</strong>
                    <span className="badge badge--neutral">Synthetic</span>
                    <span className="tiny muted">
                      {integer(demo.row_count)} rows × {demo.column_count} columns
                    </span>
                  </div>
                  <p className="small muted" style={{ margin: '2px 0 0' }}>
                    {demo.subtitle}
                  </p>
                  <p className="small" style={{ margin: '2px 0 0' }}>
                    {demo.teaching_point}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn btn--small"
                  disabled={busyLabel !== null || !demo.file_present}
                  onClick={() => void openDemo(demo.demo_id)}
                >
                  Load
                </button>
              </div>
            </li>
          ))}
        </ul>
      </details>

      <details className="disclosure">
        <summary>What SplitScope checks (and what it does not)</summary>
        {!checks ? (
          <p className="small muted">The check list has not loaded from the backend yet.</p>
        ) : (
          <>
            <ul className="list-tight">
              {checks.checks.map((check) => (
                <li key={check.rule_id}>
                  <strong>{check.title}</strong>
                  {check.default_enabled ? null : <span className="hint"> (off by default)</span>}
                  <span className="small"> — {check.summary}</span>
                </li>
              ))}
            </ul>
            <h3>What this app does not do</h3>
            <ul className="list-tight small">
              {checks.what_this_app_does_not_do.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <Callout tone="warn" title="What “no findings” means">
              {checks.no_findings_means}
            </Callout>
          </>
        )}
      </details>

      <details className="disclosure">
        <summary>Limits, privacy and technical details</summary>
        <ul className="list-tight small">
          <li>Uploads stay in server memory and expire; nothing is written to disk.</li>
          <li>Values are treated as data, never as instructions, in every view and export.</li>
          <li>
            A SHA-256 fingerprint identifies your file for reproducibility; it is an identifier,
            not anonymization.
          </li>
          {health ? (
            <li>
              Limits: {bytes(health.limits.max_upload_bytes)} per upload ·{' '}
              {integer(health.limits.max_rows)} rows · {integer(health.limits.max_columns)}{' '}
              columns.
            </li>
          ) : null}
        </ul>
      </details>
    </div>
  )
}
