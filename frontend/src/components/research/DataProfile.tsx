import { useState } from 'react'

import type { ProfileColumn, ProfileResponse } from '../../api/types'

/**
 * Computed dataset profile.
 *
 * Only measured values appear here. Outliers are labelled candidates, type
 * detection states its reason, and the missing-value convention is spelled out
 * so a reader cannot mistake a convention for a fact about the world.
 */

type Props = {
  profile: ProfileResponse
  onOpenDictionary: () => void
}

function formatNumber(value: number): string {
  if (Number.isInteger(value)) return value.toLocaleString()
  return value.toLocaleString(undefined, { maximumFractionDigits: 3 })
}

function summaryFor(column: ProfileColumn): string {
  if (column.numeric) {
    return `${formatNumber(column.numeric.min)} – ${formatNumber(column.numeric.max)} · median ${formatNumber(column.numeric.median)}`
  }
  if (column.datetime) {
    return `${column.datetime.min_utc.slice(0, 10)} → ${column.datetime.max_utc.slice(0, 10)}`
  }
  if (column.distinct_count <= 12) {
    return column.examples.join(' · ') || '—'
  }
  return 'free text'
}

export function DataProfile({ profile, onOpenDictionary }: Props) {
  const [open, setOpen] = useState<string | null>(null)
  const selected = profile.columns.find((column) => column.column === open)
  const dataset = profile.dataset

  return (
    <div className="rs-card">
      <div className="rs-card__top">
        <div>
          <p className="rs-eyebrow">Data profile</p>
          <h2 className="rs-h2">What the file actually contains</h2>
          <p className="rs-lede">
            Every figure is computed from the loaded dataset. Opening this view does not change the
            data or any audit result.
          </p>
        </div>
        <button type="button" className="rs-btn" onClick={onOpenDictionary}>
          Edit the dictionary
        </button>
      </div>

      <div className="rs-stats">
        <div className="rs-stat">
          <p className="rs-stat__value">{dataset.row_count.toLocaleString()}</p>
          <p className="rs-stat__label">rows</p>
        </div>
        <div className="rs-stat">
          <p className="rs-stat__value">{dataset.column_count}</p>
          <p className="rs-stat__label">columns</p>
        </div>
        <div className="rs-stat">
          <p className="rs-stat__value">{dataset.numeric_columns}</p>
          <p className="rs-stat__label">numeric</p>
        </div>
        <div className="rs-stat">
          <p className="rs-stat__value">{dataset.datetime_columns}</p>
          <p className="rs-stat__label">datetime</p>
        </div>
        <div className="rs-stat">
          <p className="rs-stat__value">{dataset.duplicate_rows}</p>
          <p className="rs-stat__label">repeated rows</p>
        </div>
      </div>

      {dataset.duplicate_rows > 0 ? (
        <p className="rs-note">
          Repeated rows: {dataset.duplicate_row_groups} group(s). First examples:{' '}
          {dataset.duplicate_example_row_ids.join(', ')}. Repetition inside one file is a fact about
          the file - not by itself evidence about a split.
        </p>
      ) : null}

      <div className="rs-table-wrap">
        <table className="rs-table">
          <caption className="rs-caption">Detected types are advisory; confirm one in the dictionary.</caption>
          <thead>
            <tr>
              <th scope="col">Column</th>
              <th scope="col">Type</th>
              <th scope="col">Missing</th>
              <th scope="col">Distinct</th>
              <th scope="col">Range / values</th>
              <th scope="col">Flags</th>
            </tr>
          </thead>
          <tbody>
            {profile.columns.map((column) => (
              <tr
                key={column.column}
                className={open === column.column ? 'is-selected' : undefined}
              >
                <th scope="row">
                  <button
                    type="button"
                    className="rs-rowlink"
                    onClick={() => setOpen(open === column.column ? null : column.column)}
                    aria-expanded={open === column.column}
                  >
                    {column.column}
                  </button>
                </th>
                <td>
                  <span className="rs-type">{column.detected_type}</span>
                </td>
                <td className="rs-num">
                  {column.missing_count} ({Math.round(column.missing_ratio * 100)}%)
                </td>
                <td className="rs-num">{column.distinct_count}</td>
                <td className="rs-mono">{summaryFor(column)}</td>
                <td>
                  <div className="rs-chips">
                    {column.flags.length ? (
                      column.flags.map((flag) => (
                        <span className="rs-flag" key={flag}>
                          {flag.replace(/_/g, ' ')}
                        </span>
                      ))
                    ) : (
                      <span className="rs-dim">—</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected ? (
        <section className="rs-inspector" aria-label={`Details for ${selected.column}`}>
          <h3 className="rs-h3">{selected.column}</h3>
          <p className="rs-hint">{selected.detected_type_reason}</p>
          <dl className="rs-dl">
            <div>
              <dt>Detected type</dt>
              <dd>{selected.detected_type}</dd>
            </div>
            <div>
              <dt>Missing</dt>
              <dd>
                {selected.missing_count} of {dataset.row_count} ({Math.round(selected.missing_ratio * 100)}%)
              </dd>
            </div>
            <div>
              <dt>Distinct</dt>
              <dd>{selected.distinct_count}</dd>
            </div>
            <div>
              <dt>Examples</dt>
              <dd>{selected.examples.length ? selected.examples.join(' · ') : 'none'}</dd>
            </div>
            {selected.numeric ? (
              <>
                <div>
                  <dt>Mean / median</dt>
                  <dd>
                    {formatNumber(selected.numeric.mean)} / {formatNumber(selected.numeric.median)}
                  </dd>
                </div>
                <div>
                  <dt>Std. deviation</dt>
                  <dd>{formatNumber(selected.numeric.std)}</dd>
                </div>
                <div>
                  <dt>Quartiles</dt>
                  <dd>
                    {formatNumber(selected.numeric.q1)} · {formatNumber(selected.numeric.q3)}
                  </dd>
                </div>
                <div>
                  <dt>Outlier candidates</dt>
                  <dd>
                    {selected.numeric.outlier_candidates} under {selected.numeric.outlier_rule} -
                    candidates, not errors
                  </dd>
                </div>
              </>
            ) : null}
            {selected.datetime ? (
              <>
                <div>
                  <dt>Parsed</dt>
                  <dd>
                    {selected.datetime.parsed} values · {selected.datetime.unparsed} unparsed
                  </dd>
                </div>
                <div>
                  <dt>Span</dt>
                  <dd>
                    {selected.datetime.min_utc} → {selected.datetime.max_utc} (
                    {formatNumber(selected.datetime.span_days)} days)
                  </dd>
                </div>
              </>
            ) : null}
          </dl>
        </section>
      ) : null}

      {profile.warnings.length ? (
        <ul className="rs-issues">
          {profile.warnings.map((warning) => (
            <li className="rs-issue rs-issue--warning" key={warning}>
              <strong>note</strong> {warning}
            </li>
          ))}
        </ul>
      ) : null}

      <details className="rs-details">
        <summary>Conventions used by these numbers</summary>
        <ul>
          {profile.conventions.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </details>
    </div>
  )
}
