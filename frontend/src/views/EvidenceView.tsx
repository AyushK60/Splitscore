/**
 * Evidence view.
 *
 * This is where a reader checks the claim rather than trusting the headline: the
 * exact rule, the counts with their denominators, and the concrete row ids the
 * backend attached. When the evidence names rows, they can be fetched from the
 * preview endpoint and shown as they appear in the file.
 *
 * Nothing here is synthesised. If a finding carries no example rows, the view says
 * so instead of inventing a plausible-looking table.
 */

import { useEffect, useState } from 'react'

import { Callout, Card, EmptyState, SeverityBadge, Table } from '../components/ui'
import { integer, percent, pluralise, truncate } from '../lib/format'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'

/** Extracts the numeric part of a `row-000123` style identifier so we can order them. */
function rowIdIndex(rowId: string): number {
  const match = /(\d+)$/.exec(rowId)
  return match ? Number.parseInt(match[1], 10) : Number.POSITIVE_INFINITY
}

export function EvidenceView({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const { audit, comparison, selectedFinding, dataset, preview, loadPreview, busyLabel } = useApp()
  const [showingRows, setShowingRows] = useState(false)

  useEffect(() => {
    setShowingRows(false)
  }, [selectedFinding])

  if (!selectedFinding) {
    const available = audit?.result.findings ?? []
    return (
      <Card title="Finding evidence">
        <EmptyState
          title="No finding selected"
          action={
            <>
              <button type="button" className="btn btn--primary" onClick={() => onNavigate('audit')}>
                Open the audit results
              </button>{' '}
              {comparison ? (
                <button type="button" className="btn" onClick={() => onNavigate('comparison')}>
                  Open the split comparison
                </button>
              ) : null}
            </>
          }
        >
          {available.length
            ? 'Pick any finding from the audit view and choose “Open in evidence view”, or expand a finding and read its evidence inline.'
            : 'Run an audit first; findings carry the evidence, and this view is where you inspect it.'}
        </EmptyState>

        {available.length ? (
          <>
            <h3>Findings available in this session</h3>
            <Table
              head={
                <tr>
                  <th scope="col">Severity</th>
                  <th scope="col">Rule</th>
                  <th scope="col">Finding</th>
                  <th scope="col" className="num">
                    Examples attached
                  </th>
                </tr>
              }
            >
              {available.map((finding) => (
                <tr key={finding.rule_id + finding.title}>
                  <td>
                    <SeverityBadge severity={finding.severity} />
                  </td>
                  <td className="mono tiny">{finding.rule_id}</td>
                  <td>{finding.title}</td>
                  <td className="num">
                    {finding.examples.length}
                    {finding.examples_truncated ? '+' : ''}
                  </td>
                </tr>
              ))}
            </Table>
          </>
        ) : null}
      </Card>
    )
  }

  const { finding, origin, contextLabel } = selectedFinding

  const allRowIds = Array.from(
    new Set(finding.examples.flatMap((example) => example.row_ids)),
  ).sort((left, right) => rowIdIndex(left) - rowIdIndex(right))

  return (
    <div className="stack">
      <Card
        title={finding.title}
        actions={
          <div className="row" style={{ gap: 8, alignItems: 'center' }}>
            <SeverityBadge severity={finding.severity} />
            <button
              type="button"
              className="btn btn--small"
              onClick={() => (origin === 'audit' ? onNavigate('audit') : onNavigate('comparison'))}
            >
              ← Back to {origin === 'audit' ? 'audit results' : 'comparison'}
            </button>
          </div>
        }
      >
        <div className="kv">
          <dt>Rule id</dt>
          <dd className="mono">{finding.rule_id}</dd>
          <dt>Source of this finding</dt>
          <dd>
            {origin === 'audit' ? 'Audit of the existing split' : 'Candidate split in the comparison'}{' '}
            · {contextLabel}
          </dd>
          <dt>Evidence summary</dt>
          <dd>{finding.evidence_summary}</dd>
          <dt>Severity rationale</dt>
          <dd>{finding.severity_rationale}</dd>
        </div>

        <Callout tone="info" title="How to read these numbers">
          Each count names the unit it counts and the denominator it is measured against. Percentages
          are only ever relative to those denominators - never to the dataset as a whole unless the
          scope says so.
        </Callout>

        <h3>Counts</h3>
        <Table
          head={
            <tr>
              <th scope="col">Measure</th>
              <th scope="col" className="num">
                Affected
              </th>
              <th scope="col" className="num">
                Of
              </th>
              <th scope="col" className="num">
                Share
              </th>
              <th scope="col">Unit and scope</th>
            </tr>
          }
        >
          {finding.counts.map((count) => (
            <tr key={count.label}>
              <th scope="row" style={{ fontWeight: 500 }}>
                {count.label}
                {count.note ? <span className="hint">{count.note}</span> : null}
              </th>
              <td className="num">{integer(count.affected)}</td>
              <td className="num">{count.denominator === 0 ? '—' : integer(count.denominator)}</td>
              <td className="num">
                {count.denominator === 0 ? '—' : percent(count.affected / count.denominator)}
              </td>
              <td className="small">
                {count.unit} · {count.scope}
              </td>
            </tr>
          ))}
        </Table>
      </Card>

      <Card title={`Evidence examples (${finding.examples.length} of ${integer(finding.example_total)})`}>
        {finding.examples_truncated ? (
          <Callout tone="warn" title="Truncated on purpose">
            Only the first {finding.examples.length}{' '}
            {pluralise(finding.examples.length, 'example')} {finding.examples.length === 1 ? 'is' : 'are'}
            attached, matching{' '}
            <span className="mono">max_examples = {finding.examples.length}</span> in the audit
            settings. The counts above are dataset-wide; the examples are a bounded illustration, not
            a complete list.
          </Callout>
        ) : null}

        {!finding.examples.length ? (
          <EmptyState title="This finding reports counts only">
            The rule did not attach example rows. That is a property of the check, not missing data -
            the counts above are still authoritative for the scope they name.
          </EmptyState>
        ) : (
          finding.examples.map((example, index) => (
            <div key={`${example.label}-${index}`} className="panel" style={{ marginTop: 10 }}>
              <h4 style={{ marginTop: 0 }}>
                Example {index + 1}: {example.label}
              </h4>
              <p className="rowids">
                <strong>row ids:</strong> {example.row_ids.join(', ')}
              </p>
              {Object.keys(example.details).length ? (
                <dl className="evidence-details">
                  {Object.entries(example.details).map(([key, value]) => (
                    <div key={key} style={{ display: 'contents' }}>
                      <dt>{key}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </div>
          ))
        )}

        {allRowIds.length && dataset ? (
          <>
            <h3>Show these rows as they appear in the file</h3>
            <p className="small muted">
              SplitScope fetches a window of the dataset and highlights the rows this finding cites.
              Values are shown exactly as stored.
            </p>
            <button
              type="button"
              className="btn btn--primary btn--small"
              disabled={busyLabel !== null}
              onClick={async () => {
                setShowingRows(true)
                // Fetch the first window of the dataset; cited rows are highlighted below.
                await loadPreview(0, 50)
              }}
            >
              {showingRows ? 'Reload the first 50 rows' : 'Fetch and highlight cited rows'}
            </button>
            {showingRows && preview ? (
              <>
                <Table
                  caption={`Rows ${preview.offset + 1}–${
                    preview.offset + preview.rows.length
                  } of ${integer(preview.total_rows)}. Cited rows are marked and highlighted.`}
                  head={
                    <tr>
                      <th scope="col">Cites</th>
                      <th scope="col">Row id</th>
                      {preview.columns.map((column) => (
                        <th key={column} scope="col">
                          {column}
                        </th>
                      ))}
                    </tr>
                  }
                >
                  {preview.rows.map((row, rowIndex) => {
                    const rowId = preview.row_ids[rowIndex]
                    const cited = allRowIds.includes(rowId)
                    return (
                      <tr
                        key={rowId}
                        style={cited ? { background: '#fdf8e6', fontWeight: 500 } : undefined}
                      >
                        <td>{cited ? '◆' : ''}</td>
                        <th scope="row" className="mono tiny">
                          {rowId}
                        </th>
                        {row.map((cell, cellIndex) => (
                          <td key={`${rowId}-${preview.columns[cellIndex]}`} className="mono tiny">
                            {cell === '' ? (
                              <span className="muted italic">(empty)</span>
                            ) : (
                              truncate(cell, 40)
                            )}
                          </td>
                        ))}
                      </tr>
                    )
                  })}
                </Table>
                {allRowIds.some((rowId) => rowIdIndex(rowId) >= 50) ? (
                  <p className="tiny muted">
                    Some cited rows fall outside this first window. Their row ids are listed above so
                    you can locate them in the file with the same identifier.
                  </p>
                ) : null}
              </>
            ) : null}
          </>
        ) : null}
      </Card>

      <Card title="Action, assumptions and limitations">
        <h3 style={{ marginTop: 0 }}>Recommended next action</h3>
        <p>{finding.recommended_action}</p>
        {finding.assumptions.length ? (
          <>
            <h3>Assumptions this check made</h3>
            <ul className="list-tight">
              {finding.assumptions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </>
        ) : null}
        {finding.limitations.length ? (
          <>
            <h3>What this finding does not establish</h3>
            <ul className="list-tight">
              {finding.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </>
        ) : null}
      </Card>
    </div>
  )
}
