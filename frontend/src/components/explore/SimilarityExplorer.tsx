import { useCallback, useEffect, useState } from 'react'

import { exploreApi } from '../../api/client'
import type { ExploreSchema, SimilarityPair, SimilarityResponse } from '../../api/types'
import { useExplore } from '../../explore/ExploreState'
import { integer } from '../../lib/format'

/**
 * F07 — Train/Test Similarity Explorer.
 *
 * The backend computes the K nearest cross-split pairs under the same
 * documented method as SS-NEAR-001 (normalised Chebyshev after pooled median
 * imputation and robust scaling). This panel never invents pairs: it renders
 * the computed list, a nearest-neighbour distance histogram over the test
 * population, and — for the selected pair — a Pair Inspector that resolves the
 * two immutable row ids to the file's own values via the rows endpoint.
 *
 * Selecting a pair highlights its train and test rows in every linked chart
 * (through the shared hover highlight), and the inspector states plainly that
 * similarity is not leakage.
 */

export function SimilarityExplorer({ schema }: { schema: ExploreSchema }) {
  const { highlightedId, setHighlightedId } = useExplore()
  const [result, setResult] = useState<SimilarityResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<SimilarityPair | null>(null)
  const [detail, setDetail] = useState<Record<string, string> | null>(null)

  const datasetId = schema.dataset.dataset_id

  const load = useCallback(
    async (maxPairs: number) => {
      setLoading(true)
      setError(null)
      try {
        const response = await exploreApi.similarity(datasetId, { max_pairs: maxPairs })
        setResult(response)
      } catch (caught) {
        setResult(null)
        setError(caught instanceof Error ? caught.message : 'The similarity request failed.')
      } finally {
        setLoading(false)
      }
    },
    [datasetId],
  )

  useEffect(() => {
    void load(25)
  }, [load])

  // Pair inspector: resolve both rows through the same endpoint the row
  // evidence uses, so what the inspector shows is the file's own text.
  useEffect(() => {
    if (!selected) {
      setDetail(null)
      return
    }
    let cancelled = false
    exploreApi
      .rows(datasetId, [selected.train_row_id, selected.test_row_id])
      .then((response) => {
        if (cancelled) return
        const byId = new Map(response.rows.map((row) => [row.id, row.values]))
        const trainValues = byId.get(selected.train_row_id)
        const testValues = byId.get(selected.test_row_id)
        if (!trainValues || !testValues) {
          setDetail(null)
          return
        }
        const columns = response.columns
        const rows: Record<string, string> = {}
        for (const column of columns) {
          const trainValue = trainValues[column] ?? '(absent)'
          const testValue = testValues[column] ?? '(absent)'
          const marker =
            trainValue === testValue
              ? '='
              : trainValue === '(missing)' || testValue === '(missing)'
                ? '∅'
                : '≠'
          rows[column] = `${marker}  ${trainValue}  |  ${testValue}`
        }
        setDetail(rows)
      })
      .catch(() => {
        if (!cancelled) setDetail(null)
      })
    return () => {
      cancelled = true
    }
  }, [datasetId, selected])

  const histogramMax = Math.max(1, ...(result?.nn_histogram ?? [1]))

  return (
    <figure className="xfig" data-figure="similarity">
      <figcaption className="xfig__caption">
        <span className="xfig__title">Train/test similarity explorer</span>
        <span className="xfig__sub">
          {result
            ? `${result.pairs.length} of ${result.pairs_total_available.toLocaleString('en-US')} cross-split pairs shown · nearest first`
            : 'computing…'}
        </span>
        <span className="xfig__sub">{result?.method}</span>
      </figcaption>

      <div className="xfig__controls">
        {[10, 25, 50].map((count) => (
          <button
            key={count}
            type="button"
            className="xbtn"
            aria-pressed={loading ? false : (result?.pairs.length ?? 0) === count}
            disabled={loading}
            onClick={() => void load(count)}
          >
            {count} pairs
          </button>
        ))}
      </div>

      {error ? (
        <p className="xw__ploterror" role="alert">
          {error}
        </p>
      ) : null}

      {result ? (
        <>
          <div className="xsim__summary">
            <div className="xsim__histogram" role="img"
              aria-label={`Nearest-neighbour distance histogram over ${result.nearest_neighbour_summary.test_rows_analysed} test rows`}>
              {result.nn_histogram.map((count, index) => (
                <div
                  key={index}
                  className="xsim__bin"
                  style={{ height: `${(count / histogramMax) * 100}%` }}
                  title={`${
                    result.nn_histogram_edges[index]?.toFixed(3)
                  }–${result.nn_histogram_edges[index + 1]?.toFixed(3)}: ${count} test row(s)`}
                />
              ))}
            </div>
            <dl className="xsim__facts">
              <div>
                <dt>Test rows analysed</dt>
                <dd>{integer(result.nearest_neighbour_summary.test_rows_analysed ?? 0)}</dd>
              </div>
              <div>
                <dt>Nearest distance (median)</dt>
                <dd>{result.nearest_neighbour_summary.nn_median}</dd>
              </div>
              <div>
                <dt>Scaling</dt>
                <dd>{result.scaling.method}</dd>
              </div>
              <div>
                <dt>Rows dropped (missing)</dt>
                <dd>{integer(result.populations.rows_dropped_missing ?? 0)}</dd>
              </div>
            </dl>
          </div>
          <p className="xfig__note">{result.sampling}</p>

          <div className="xsim__pairs">
            {result.pairs.map((pair) => (
              <button
                key={`${pair.train_row_id}-${pair.test_row_id}`}
                type="button"
                className={`xsim__pair${selected === pair ? ' xsim__pair--on' : ''}`}
                onMouseEnter={() => setHighlightedId(pair.train_row_id)}
                onMouseLeave={() => setHighlightedId(null)}
                onClick={() => setSelected(selected === pair ? null : pair)}
              >
                <span className="xsim__distance mono">{pair.distance.toFixed(4)}</span>
                <span className="xsim__ids mono">
                  {pair.train_row_id} ↔ {pair.test_row_id}
                </span>
                <span className="xsim__top">
                  {pair.top_diffs
                    .slice(0, 3)
                    .map((diff) => `${diff.column} Δ${diff.scaled_diff}`)
                    .join(' · ')}
                </span>
              </button>
            ))}
          </div>
          {result.pairs_truncated ? (
            <p className="xfig__note">
              Showing the {result.pairs.length} nearest of {result.pairs_total_available.toLocaleString('en-US')} computed
              cross-split pairs. Similarity is a screening signal, not leakage — inspect before
              concluding anything.
            </p>
          ) : null}

          {selected ? (
            <div className="xsim__inspector" aria-label="Pair inspector">
              <h4 className="xrow__title">Pair inspector</h4>
              <p className="xfig__note">
                Train row <span className="mono">{selected.train_row_id}</span> and test row{' '}
                <span className="mono">{selected.test_row_id}</span>, resolved to the file's own
                values. Distance {selected.distance.toFixed(4)} in scaled units ({result.scaling.method}).
                {' '}Hovering the pair highlights both rows in the linked charts.
              </p>
              {selected.top_diffs.length ? (
                <>
                  <p className="xrow__notetitle">Top differing numeric columns (scaled units)</p>
                  <ul className="xrow__predicates">
                    {selected.top_diffs.map((diff) => (
                      <li key={diff.column} className="xrow__predicateitem">
                        {diff.column}: train {diff.train_value} vs test {diff.test_value} (Δ
                        {diff.scaled_diff})
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
              {detail ? (
                <div className="xrow__tablewrap">
                  <table className="xrow__table">
                    <thead>
                      <tr>
                        <th scope="col">Column</th>
                        <th scope="col">Train</th>
                        <th scope="col">Test</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(detail).map(([column, line]) => {
                        const [marker, trainValue, testValue] = line.split('|').map((part) => part.trim())
                        return (
                          <tr key={column}>
                            <td>
                              <span className="mono">{marker}</span> {column}
                            </td>
                            <td>{trainValue}</td>
                            <td>{testValue}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="xrow__note">Resolving row values…</p>
              )}
              <p className="xrow__footnote">
                A close pair is a candidate for human inspection — the highlightedId highlight works
                in every chart, and the underlying rows are the same immutable ids the audit cites.
                {highlightedId ? ` Highlighted: ${highlightedId}.` : ''}
              </p>
            </div>
          ) : null}

          <details className="xsim__limits">
            <summary>Method, exclusions and limitations</summary>
            <ul className="list-tight small">
              {result.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
            <p className="small mono">
              {result.scaling.columns_used} column(s) used; imputation: {result.scaling.imputation};{' '}
              {result.scaling.purpose}
            </p>
          </details>
        </>
      ) : null}
    </figure>
  )
}
