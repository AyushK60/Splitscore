import { useEffect, useMemo, useRef, useState } from 'react'

import { exploreApi } from '../../api/client'
import type { BrushPredicate, DistributionResponse, ExploreSchema } from '../../api/types'
import { FigureExport } from './FigureExport'

/**
 * Distribution views: histogram + box plot for numeric columns, frequency
 * bars for categorical ones, with optional group overlays.
 *
 * Denominators are always visible: the caption carries the population, the
 * valid count, and the missing/unparsed exclusions. When a selection is
 * active the backend returns the selected cohort's counts on the SAME bins,
 * drawn beside the population layer (never over it, and never rescaled) so
 * the two can be compared honestly.
 */

interface Props {
  schema: ExploreSchema
  predicates: BrushPredicate[]
  selectionActive: boolean
}

export function Distributions({ schema, predicates, selectionActive }: Props) {
  const allColumns = schema.columns.map((c) => c.name)
  const [column, setColumn] = useState<string>(() => schema.numeric_columns[0] ?? allColumns[0] ?? '')
  const [bins, setBins] = useState(20)
  const [groupBy, setGroupBy] = useState<string>('')
  const [data, setData] = useState<DistributionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const columnType = schema.columns.find((c) => c.name === column)?.detected_type
  const isNumeric = columnType === 'numeric' || columnType === 'integer'
  const columnMeta = schema.columns.find((c) => c.name === column)

  // An integer column with a small range gets one bin per integer: a 20-bin
  // histogram over six whole numbers would render mostly empty rails.
  useEffect(() => {
    const numeric = columnMeta?.numeric
    if (columnType === 'integer' && numeric?.min !== undefined && numeric?.max !== undefined) {
      const span = numeric.max - numeric.min
      if (span >= 0 && span <= 30) {
        setBins(Math.round(span) + 1)
        return
      }
    }
    setBins(20)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [column, columnType, columnMeta?.numeric?.min, columnMeta?.numeric?.max])

  useEffect(() => {
    if (!column) return
    let cancelled = false
    exploreApi
      .distribution(schema.dataset.dataset_id, {
        column,
        bins,
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
        setError(e instanceof Error ? e.message : 'The distribution could not be computed.')
      })
    return () => {
      cancelled = true
    }
  }, [schema.dataset.dataset_id, column, bins, groupBy, selectionActive, predicates])

  const groupOptions = useMemo(
    () => schema.color_candidates.filter((c) => c !== column),
    [schema.color_candidates, column],
  )

  const fmt = (v: number) =>
    Number.isInteger(v) ? v.toLocaleString('en-US') : Math.abs(v) >= 100 ? v.toFixed(1) : v.toPrecision(3)

  return (
    <figure className="xfig" data-figure="distribution">
      <figcaption className="xfig__caption">
        <span className="xfig__title">
          Distribution — {column}
          {isNumeric ? ' (numeric)' : ' (categorical)'}
        </span>
        <span className="xfig__sub">
          {data
            ? `population ${data.population.toLocaleString('en-US')} rows` +
              (isNumeric
                ? ` · ${data.valid_count?.toLocaleString('en-US')} valid · ${data.missing_count} missing · ${data.unparsed_count} unparsable`
                : ` · ${data.missing_count} missing`)
            : 'computing…'}
        </span>
        <FigureExport
          figureId={`distribution-${column}`}
          title={`Distribution — ${column} (${isNumeric ? 'numeric' : 'categorical'})`}
          settings={`${isNumeric ? `${bins} equal-width bins` : 'per-level counts'}${
            data?.group_by ? ` · grouped by ${data.group_by}` : ''
          }`}
          counts={
            data
              ? `population ${data.population.toLocaleString('en-US')} rows${
                  isNumeric ? ` · ${data.valid_count?.toLocaleString('en-US')} valid · ${data.missing_count} missing · ${data.unparsed_count} unparsable` : ` · ${data.missing_count} missing`
                }${data.selection ? ` · selection ${data.selection.population.toLocaleString('en-US')} rows` : ''}`
              : ''
          }
          notes={[
            'Each group uses only its own rows; group sizes are reported.',
            isNumeric
              ? 'Quartiles: linear interpolation; whiskers end at the most extreme values within 1.5×IQR fences.'
              : undefined,
          ].filter((note): note is string => Boolean(note))}
          getSvg={() => svgRef.current}
        />
      </figcaption>

      <div className="xfig__controls">
        <label className="xfig__control">
          Variable
          <select className="xselect" value={column} onChange={(e) => setColumn(e.target.value)}>
            {allColumns.map((name) => (
              <option key={name} value={name}>
                {name}
                {schema.columns.find((c) => c.name === name)?.detected_type
                  ? ` — ${schema.columns.find((c) => c.name === name)?.detected_type}`
                  : ''}
              </option>
            ))}
          </select>
        </label>
        {isNumeric && (
          <label className="xfig__control">
            Bins: {bins}
            <input
              type="range"
              min={5}
              max={60}
              value={bins}
              onChange={(e) => setBins(Number(e.target.value))}
              aria-label="Histogram bin count"
            />
          </label>
        )}
        <label className="xfig__control">
          Group by
          <select className="xselect" value={groupBy} onChange={(e) => setGroupBy(e.target.value)}>
            <option value="">(none)</option>
            {groupOptions.map((name) => (
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

      {data && data.kind === 'numeric' && data.bins && data.counts && (
        <Histogram data={data} fmt={fmt} svgRef={svgRef} />
      )}
      {data && data.kind === 'categorical' && data.levels && (
        <CategoricalChart data={data} svgRef={svgRef} />
      )}

      {data?.groups && data.groups.length > 0 && (
        <div className="xdist__groups">
          {data.groups.map((group) => (
            <div key={group.group} className="xdist__group">
              <span className="xdist__groupname">
                {group.group} — {group.rows.toLocaleString('en-US')} rows
              </span>
              {group.box && (
                <span className="xdist__groupstats">
                  median {fmt(group.box.median)} · IQR {fmt(group.box.q1)}–{fmt(group.box.q3)} ·{' '}
                  {group.box.outlier_count} outliers
                </span>
              )}
              {group.levels && (
                <span className="xdist__groupstats">
                  {group.levels
                    .slice(0, 4)
                    .map((l) => `${l.value}: ${l.count}`)
                    .join(' · ')}
                  {group.other_count ? ` · other: ${group.other_count}` : ''}
                </span>
              )}
            </div>
          ))}
          <p className="xfig__note">
            Each group's statistics use only that group's rows; group sizes are shown so a small
            group is never mistaken for a large one.
          </p>
        </div>
      )}

      {data?.box && (
        <p className="xfig__note">{data.box.definition} Outlier markers count values beyond the fences.</p>
      )}
      {data?.filters_note && <p className="xfig__note xfig__note--copper">{data.filters_note}</p>}
    </figure>
  )
}

function Histogram({
  data,
  fmt,
  svgRef,
}: {
  data: DistributionResponse
  fmt: (v: number) => string
  svgRef: React.RefObject<SVGSVGElement | null>
}) {
  const bins = data.bins ?? []
  const counts = data.counts ?? []
  const sel = data.selection
  const width = 720
  const height = 240
  const pad = { top: 14, right: 12, bottom: 38, left: 46 }
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom
  const maxCount = Math.max(1, ...counts, ...(sel?.counts ?? []))
  const barW = bins.length > 1 ? innerW / (bins.length - 1) : innerW
  const y = (count: number) => pad.top + innerH - (count / maxCount) * innerH

  return (
    <div className="xfig__scroll">
      <svg ref={svgRef} width={width} height={height} role="img" aria-label={`Histogram of ${data.column}`}>
        <line x1={pad.left} y1={pad.top + innerH} x2={pad.left + innerW} y2={pad.top + innerH} stroke="var(--rs-line-strong)" />
        {[0.5, 1].map((t) => (
          <g key={t}>
            <text x={pad.left - 6} y={y(maxCount * t) + 3} textAnchor="end" className="xpc__tick">
              {fmt(Math.round(maxCount * t))}
            </text>
            <line x1={pad.left} y1={y(maxCount * t)} x2={pad.left + innerW} y2={y(maxCount * t)} stroke="var(--rs-line)" strokeDasharray="2 4" />
          </g>
        ))}
        {counts.map((count, i) => (
          <rect
            key={`p-${i}`}
            x={pad.left + i * barW + 1}
            y={y(count)}
            width={Math.max(1, barW - 3)}
            height={pad.top + innerH - y(count)}
            fill="color-mix(in srgb, var(--rs-teal) 26%, var(--rs-surface))"
            stroke="var(--rs-teal)"
          >
            <title>
              [{fmt(bins[i])}, {fmt(bins[i + 1] ?? bins[i])}]: {count} rows
            </title>
          </rect>
        ))}
        {sel &&
          sel.counts.map((count, i) =>
            count > 0 ? (
              <rect
                key={`s-${i}`}
                x={pad.left + i * barW + 1}
                y={y(count)}
                width={Math.max(1, barW / 2)}
                height={pad.top + innerH - y(count)}
                fill="var(--rs-copper)"
                opacity={0.85}
              >
                <title>selected: {count} rows</title>
              </rect>
            ) : null,
          )}
        <text x={pad.left + innerW / 2} y={height - 6} textAnchor="middle" className="xfig__axistitle">
          {data.column}
        </text>
        {bins.length > 1 && (
          <>
            <text x={pad.left} y={height - 22} className="xpc__tick">
              {fmt(bins[0])}
            </text>
            <text x={pad.left + innerW / 2} y={height - 22} textAnchor="middle" className="xpc__tick">
              {fmt((bins[0] + bins[bins.length - 1]) / 2)}
            </text>
            <text x={pad.left + innerW} y={height - 22} textAnchor="end" className="xpc__tick">
              {fmt(bins[bins.length - 1])}
            </text>
          </>
        )}
      </svg>
      <div className="xpc__legend">
        <span className="xpc__legenditem">
          <span className="xpc__swatch" style={{ background: 'color-mix(in srgb, var(--rs-teal) 40%, white)' }} />
          population ({data.population.toLocaleString('en-US')} rows)
        </span>
        {sel && (
          <span className="xpc__legenditem xpc__legenditem--selected">
            <span className="xpc__swatch xpc__swatch--selected" />
            active selection ({sel.population.toLocaleString('en-US')} rows, same bins)
          </span>
        )}
      </div>
    </div>
  )
}

function CategoricalChart({
  data,
  svgRef,
}: {
  data: DistributionResponse
  svgRef: React.RefObject<SVGSVGElement | null>
}) {
  const levels = data.levels ?? []
  const width = 720
  const rowH = 30
  const height = levels.length * rowH + 46
  const padL = 190
  const max = Math.max(1, ...levels.map((l) => l.count))
  return (
    <div className="xfig__scroll">
      <svg ref={svgRef} width={width} height={height} role="img" aria-label={`Frequencies of ${data.column}`}>
        {levels.map((level, i) => (
          <g key={level.value}>
            <text x={padL - 10} y={i * rowH + 19} textAnchor="end" className="xfig__axislabel">
              {level.value}
            </text>
            <rect
              x={padL}
              y={i * rowH + 6}
              width={(level.count / max) * (width - padL - 90)}
              height={rowH - 12}
              fill="color-mix(in srgb, var(--rs-teal) 30%, var(--rs-surface))"
              stroke="var(--rs-teal)"
            >
              <title>
                {level.value}: {level.count} rows
              </title>
            </rect>
            <text
              x={padL + (level.count / max) * (width - padL - 90) + 6}
              y={i * rowH + 19}
              className="xpc__tick"
            >
              {level.count.toLocaleString('en-US')}
            </text>
          </g>
        ))}
        <text x={padL} y={height - 8} className="xfig__axislabel">
          {levels.length} shown
          {data.other_count ? ` · ${data.other_count.toLocaleString('en-US')} rarer rows grouped as “other”` : ''}
          {` · ${data.distinct} distinct values`}
        </text>
      </svg>
    </div>
  )
}
