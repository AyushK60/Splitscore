import { useEffect, useState } from 'react'

import { exploreApi } from '../../api/client'
import type { RowsResponse } from '../../api/types'
import { useExplore } from '../../explore/ExploreState'
import { useApp } from '../../state/AppState'

/**
 * Row Evidence Inspector — the traceability half of every chart.
 *
 * The selection engine resolves brushes to immutable row ids; this panel shows
 * the actual observations behind the current selection: the active predicate,
 * the population arithmetic, and the file's own text values (fetched by id, so
 * what you read is what the CSV says, not a chart's parsed approximation).
 * Hovering a row highlights the same observation in every linked chart.
 */

const PAGE_SIZE = 12

export function RowEvidence() {
  const { schema, selection, highlightedId, setHighlightedId } = useExplore()
  const { audit } = useApp()
  const [page, setPage] = useState(0)
  const [detail, setDetail] = useState<RowsResponse | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const ids = selection.status === 'ready' ? [...selection.ids] : []
  const pageCount = Math.max(1, Math.ceil(ids.length / PAGE_SIZE))

  useEffect(() => {
    setPage(0)
  }, [selection])

  useEffect(() => {
    if (selection.status !== 'ready' || selection.ids.size === 0) {
      setDetail(null)
      setDetailError(null)
      return
    }
    const datasetId = schema?.dataset.dataset_id
    if (!datasetId) return
    const pageIds = ids.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
    let cancelled = false
    exploreApi
      .rows(datasetId, pageIds)
      .then((result) => {
        if (cancelled) return
        setDetail(result)
        setDetailError(null)
      })
      .catch(() => {
        if (cancelled) return
        setDetailError('Row values could not be loaded for this page.')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection, page, schema?.dataset.dataset_id])

  if (!schema) return null

  return (
    <section className="xrow" aria-label="Row evidence inspector">
      <header className="xrow__head">
        <h3 className="xrow__title">Row evidence</h3>
        <span className="xrow__counts">
          {selection.status === 'ready'
            ? `${selection.totalSelected.toLocaleString('en-US')} of ${schema.row_count.toLocaleString('en-US')} rows selected`
            : 'no active selection'}
        </span>
      </header>

      <div className="xrow__predicate">
        {selection.predicates.length === 0 ? (
          <p className="muted tiny" style={{ margin: 0 }}>
            Brush a range on any parallel-coordinates axis to select observations. The dataset
            itself is never changed by a selection.
          </p>
        ) : (
          <ul className="xrow__predicates">
            {selection.predicates.map((predicate, i) => (
              <li key={i} className="xrow__predicateitem">
                {predicate.kind === 'range'
                  ? `${predicate.column} ∈ [${formatNumber(predicate.min)}, ${formatNumber(predicate.max)}]`
                  : `${predicate.column} ∈ {${predicate.values.slice(0, 6).join(', ')}${
                      predicate.values.length > 6 ? ', …' : ''
                    }}`}
              </li>
            ))}
          </ul>
        )}
      </div>

      {selection.idsTruncated && (
        <p className="xrow__note">
          Highlighting covers the first 20,000 selected rows; the count is exact for the whole
          population.
        </p>
      )}
      {selection.status === 'computing' && <p className="xrow__note">Resolving selection…</p>}
      {selection.status === 'error' && (
        <p className="xrow__note xrow__note--bad" role="alert">
          {selection.error}
        </p>
      )}
      {detailError && (
        <p className="xrow__note xrow__note--bad" role="alert">
          {detailError}
        </p>
      )}

      {detail && detail.rows.length > 0 && (
        <>
          <div className="xrow__tablewrap">
            <table className="xrow__table">
              <thead>
                <tr>
                  <th scope="col">Row id</th>
                  {detail.columns.map((column) => (
                    <th scope="col" key={column}>
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {detail.rows.map((row) => (
                  <tr
                    key={row.id}
                    className={row.id === highlightedId ? 'xrow__activetr' : undefined}
                    onMouseEnter={() => setHighlightedId(row.id)}
                    onMouseLeave={() => setHighlightedId(null)}
                  >
                    <td className="xrow__idcell">{row.id}</td>
                    {detail.columns.map((column) => (
                      <td key={column}>{row.values[column] === '' ? '—' : row.values[column]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pageCount > 1 && (
            <nav className="xrow__pager" aria-label="Selected rows pages">
              <button
                type="button"
                className="xbtn xbtn--tiny"
                disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                ← Previous
              </button>
              <span className="tiny muted">
                page {page + 1} / {pageCount}
              </span>
              <button
                type="button"
                className="xbtn xbtn--tiny"
                disabled={page >= pageCount - 1}
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
              >
                Next →
              </button>
            </nav>
          )}
        </>
      )}

      <p className="xrow__footnote">
        {audit ? (
          <>The most recent audit result is available in Results; selections here are analysis
          context, not audit findings.</>
        ) : (
          <>Run the audit from Results to bind leakage findings to this dataset; the explorer
            works independently of it.</>
        )}
        {' '}Values are the file's own text; “—” marks an empty cell.
      </p>
    </section>
  )
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? value.toLocaleString('en-US') : value.toPrecision(4)
}
