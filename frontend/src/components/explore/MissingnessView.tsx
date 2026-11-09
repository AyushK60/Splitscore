import { useEffect, useRef, useState } from 'react'

import { exploreApi } from '../../api/client'
import type { BrushPredicate, MissingnessResponse } from '../../api/types'
import { FigureExport } from './FigureExport'

/**
 * Missing-data exploration.
 *
 * Two layers with two different truth claims, labelled separately:
 *  - the per-column bars and percentages are EXACT aggregates over the whole
 *    dataset (or the active selection, with the whole-dataset numbers kept
 *    alongside for comparison);
 *  - the cell matrix is a bounded rendering aid (systematic grid sample in
 *    file order) whose stride and coverage are stated in its caption.
 * "Missing" follows the V1 convention: an empty cell, and nothing else.
 */

interface Props {
  datasetId: string
  predicates: BrushPredicate[]
  selectionActive: boolean
  groupCandidates: string[]
}

export function MissingnessView({ datasetId, predicates, selectionActive, groupCandidates }: Props) {
  const [data, setData] = useState<MissingnessResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [groupBy, setGroupBy] = useState('')
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    let cancelled = false
    exploreApi
      .missingness(datasetId, {
        group_by: groupBy || null,
        filters: selectionActive ? predicates : [],
      })
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
      })
      .catch((e) => {
        if (cancelled) return
        setData(null)
        setError(e instanceof Error ? e.message : 'Missingness could not be computed.')
      })
    return () => {
      cancelled = true
    }
  }, [datasetId, groupBy, selectionActive, predicates])

  const maxPct = Math.max(
    1,
    ...(data?.per_column.map((c) => c.missing_pct) ?? []),
    ...(data?.population_counts?.map((c) => c.missing_pct) ?? []),
  )

  return (
    <figure className="xfig" data-figure="missingness">
      <figcaption className="xfig__caption">
        <span className="xfig__title">Missingness</span>
        <span className="xfig__sub">
          {data
            ? `${data.population.toLocaleString('en-US')} rows in scope · population ${data.population_total?.toLocaleString('en-US') ?? data.population}`
            : 'computing…'}
        </span>
        <FigureExport
          figureId="missingness"
          title={`Missingness - ${data ? data.columns.length : '?'} columns`}
          settings={data ? `empty-cell policy · ${data.matrix.method} matrix` : ''}
          counts={
            data
              ? `${data.population.toLocaleString('en-US')} rows in scope${
                  data.population_total ? ` of ${data.population_total.toLocaleString('en-US')} total` : ''
                }`
              : ''
          }
          sampling={data?.matrix.description}
          notes={[data?.policy ?? 'Missing means an empty cell.'].concat(
            data?.columns
              .slice(0, 3)
              .map((name) => {
                const entry = data.per_column.find((c) => c.column === name)
                return `${name}: ${entry?.missing_pct.toFixed(1)}% missing (${entry?.missing_count} rows)`
              }) ?? [],
          )}
          getSvg={() => svgRef.current}
        />
      </figcaption>

      <div className="xfig__controls">
        <label className="xfig__control">
          Break down by
          <select className="xselect" value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
            <option value="">(none)</option>
            {groupCandidates.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && (
        <p className="xw__ploterror" role="alert">
          {error}
        </p>
      )}

      {data && (
        <>
          <div className="xmiss__bars">
            {data.per_column.map((entry) => {
              const populationEntry = data.population_counts?.find((c) => c.column === entry.column)
              return (
                <div key={entry.column} className="xmiss__bar">
                  <span className="xmiss__name">{entry.column}</span>
                  <span className="xmiss__track">
                    <span
                      className="xmiss__fill"
                      style={{ width: `${(entry.missing_pct / maxPct) * 100}%` }}
                      title={`${entry.missing_count} missing rows`}
                    />
                  </span>
                  <span className="xmiss__value">
                    {entry.missing_pct.toFixed(1)}% ({entry.missing_count.toLocaleString('en-US')})
                  </span>
                  {populationEntry && populationEntry.column === entry.column && (
                    <span className="xmiss__value xmiss__value--population">
                      all rows: {populationEntry.missing_pct.toFixed(1)}%
                    </span>
                  )}
                </div>
              )
            })}
          </div>

          <div className="xmiss__matrix">
            <span className="xmiss__matrixtitle">{data.matrix.description}</span>
            <svg
              ref={svgRef}
              width={Math.min(720, data.columns.length * 22 + 60)}
              height={Math.min(300, data.matrix.rows.length * 6 + 30)}
              role="img"
              aria-label="Missingness matrix"
            >
              {data.matrix.rows.map((row, r) =>
                row.cells.map((cell, c) =>
                  cell ? (
                    <rect
                      key={`${r}-${c}`}
                      x={c * 22 + 30}
                      y={r * 6}
                      width={20}
                      height={5}
                      fill="var(--rs-copper)"
                      opacity={0.8}
                    >
                      <title>{row.id}</title>
                    </rect>
                  ) : (
                    <rect
                      key={`${r}-${c}`}
                      x={c * 22 + 30}
                      y={r * 6}
                      width={20}
                      height={5}
                      fill="var(--rs-sunken)"
                    />
                  ),
                ),
              )}
              {data.columns.map((column, c) => (
                <text
                  key={column}
                  transform={`rotate(-40 ${c * 22 + 34} ${data.matrix.rows.length * 6 + 14})`}
                  x={c * 22 + 34}
                  y={data.matrix.rows.length * 6 + 14}
                  className="xfig__axislabel"
                >
                  {column}
                </text>
              ))}
            </svg>
            <span className="xmiss__note">
              Each row is one observation (immutable row id on hover); copper marks a missing cell.
              The matrix is a rendering aid - the percentages above are exact for the whole
              population.
            </span>
          </div>

          {data.groups && data.groups.length > 0 && (
            <div className="xdist__groups">
              {data.groups.map((group) => {
                const worst = [...group.per_column].sort((a, b) => b.missing_pct - a.missing_pct)[0]
                return (
                  <div key={group.group} className="xdist__group">
                    <span className="xdist__groupname">
                      {group.group} - {group.rows.toLocaleString('en-US')} rows
                    </span>
                    <span className="xdist__groupstats">
                      {worst
                        ? `highest missingness: ${worst.column} ${worst.missing_pct.toFixed(1)}%`
                        : 'no columns'}
                    </span>
                  </div>
                )
              })}
            </div>
          )}

          <p className="xfig__note">{data.policy}</p>
          {data.filters_note && <p className="xfig__note xfig__note--copper">{data.filters_note}</p>}
        </>
      )}
    </figure>
  )
}
