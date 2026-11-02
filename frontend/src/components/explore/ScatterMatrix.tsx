import { useEffect, useMemo, useState } from 'react'

import { exploreApi } from '../../api/client'
import type { ExploreSchema, SeriesResponse } from '../../api/types'

/**
 * Scatter-plot matrix for a bounded subset of numeric variables.
 *
 * Panels render the same render sample the backend draws for the focus view,
 * so a point is the same observation everywhere. The subset is capped at four
 * variables (six pairwise panels) with the cap stated in the interface — a
 * 50-variable matrix would be unreadable and heavy. Clicking a panel opens
 * that pair in the focus scatter.
 */

const MAX_MATRIX_COLUMNS = 4

interface Props {
  schema: ExploreSchema
  selectedIds: Set<string>
  colorColumn: string | null
  colorLevels: string[]
  onOpenPair: (x: string, y: string) => void
}

const PANEL = 190

export function ScatterMatrix({ schema, selectedIds, colorColumn, colorLevels, onOpenPair }: Props) {
  const numeric = schema.numeric_columns
  const [columns, setColumns] = useState<string[]>(() => numeric.slice(0, MAX_MATRIX_COLUMNS))
  const [series, setSeries] = useState<SeriesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setColumns((previous) => {
      const kept = previous.filter((c) => numeric.includes(c))
      if (kept.length >= 2) return kept
      return numeric.slice(0, MAX_MATRIX_COLUMNS)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema.dataset.dataset_id])

  useEffect(() => {
    if (columns.length < 2) {
      setSeries(null)
      return
    }
    let cancelled = false
    const request = colorColumn && !columns.includes(colorColumn) ? [...columns, colorColumn] : columns
    exploreApi
      .series(schema.dataset.dataset_id, { columns: request, max_rows: 1500 })
      .then((result) => {
        if (cancelled) return
        setSeries(result)
        setError(null)
      })
      .catch((e) => {
        if (cancelled) return
        setSeries(null)
        setError(e instanceof Error ? e.message : 'Scatter-matrix data could not be loaded.')
      })
    return () => {
      cancelled = true
    }
  }, [schema.dataset.dataset_id, columns, colorColumn])

  const toggle = (column: string) => {
    setColumns((previous) => {
      if (previous.includes(column)) return previous.filter((c) => c !== column)
      if (previous.length >= MAX_MATRIX_COLUMNS) return previous
      return [...previous, column]
    })
  }

  const pairs = useMemo(() => {
    const out: Array<{ x: string; y: string }> = []
    for (let i = 0; i < columns.length; i++) {
      for (let j = i + 1; j < columns.length; j++) {
        out.push({ x: columns[i], y: columns[j] })
      }
    }
    return out
  }, [columns])

  if (numeric.length < 2) {
    return (
      <p className="xw__placeholder">
        A scatter matrix needs at least two numeric columns; this dataset has {numeric.length}.
      </p>
    )
  }

  return (
    <figure className="xfig" data-figure="scatter-matrix">
      <figcaption className="xfig__caption">
        <span className="xfig__title">Scatter matrix</span>
        <span className="xfig__sub">
          {series
            ? `${series.drawn_rows.toLocaleString('en-US')} of ${series.filtered_population.toLocaleString('en-US')} rows drawn per panel${
                series.sampling.stride > 1 ? ` (every ${series.sampling.stride}th row)` : ''
              }`
            : 'loading…'}
          {' · '}click a panel to open the pair full-size
        </span>
      </figcaption>

      <div className="xfig__controls">
        <div className="xw__chips">
          {numeric.map((column) => (
            <button
              key={column}
              type="button"
              className={`xchip${columns.includes(column) ? ' xchip--on' : ''}`}
              aria-pressed={columns.includes(column)}
              disabled={!columns.includes(column) && columns.length >= MAX_MATRIX_COLUMNS}
              onClick={() => toggle(column)}
            >
              {column}
            </button>
          ))}
        </div>
        <span className="xw__controlmeta">up to {MAX_MATRIX_COLUMNS} variables — the cap keeps panels readable</span>
      </div>

      {error && (
        <p className="xw__ploterror" role="alert">
          {error}
        </p>
      )}

      {series && (
        <div className="xmatrix">
          {pairs.map(({ x, y }) => (
            <MatrixPanel
              key={`${x}\u0000${y}`}
              series={series}
              x={x}
              y={y}
              selectedIds={selectedIds}
              colorColumn={colorColumn}
              colorLevels={colorLevels}
              onOpen={() => onOpenPair(x, y)}
            />
          ))}
        </div>
      )}
    </figure>
  )
}

function MatrixPanel({
  series,
  x,
  y,
  selectedIds,
  colorColumn,
  colorLevels,
  onOpen,
}: {
  series: SeriesResponse
  x: string
  y: string
  selectedIds: Set<string>
  colorColumn: string | null
  colorLevels: string[]
  onOpen: () => void
}) {
  const inner = PANEL - 46
  const xScale = series.scale[x]
  const yScale = series.scale[y]
  if (!xScale?.numeric || !yScale?.numeric || xScale.min === null || yScale.min === null) return null
  const xMin = xScale.min
  const xMax = xScale.max ?? xMin
  const yMin = yScale.min
  const yMax = yScale.max ?? yMin
  const px = (value: number) => 38 + ((value - xMin) / (xMax - xMin || 1)) * inner
  const py = (value: number) => 10 + inner - ((value - yMin) / (yMax - yMin || 1)) * inner

  const unselected: string[] = []
  const selected: string[] = []
  for (const row of series.rows) {
    const xv = row.values[x]
    const yv = row.values[y]
    if (typeof xv !== 'number' || typeof yv !== 'number') continue
    const dot = `M${px(xv).toFixed(1)} ${py(yv).toFixed(1)}h.01`
    if (selectedIds.size > 0 && selectedIds.has(row.id)) selected.push(dot)
    else unselected.push(dot)
  }
  const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toPrecision(3))

  return (
    <div className="xmatrix__panel">
      <svg
        width={PANEL}
        height={PANEL - 16}
        role="img"
        aria-label={`Scatter of ${x} against ${y}`}
        style={{ cursor: 'pointer' }}
        onClick={onOpen}
      >
        <title>
          {x} × {y} — click to open full size
        </title>
        <rect x={38} y={10} width={inner} height={inner} fill="none" stroke="var(--rs-line)" />
        <path d={unselected.join('')} stroke="var(--rs-teal)" strokeWidth={1.6} strokeLinecap="round" opacity={0.5} fill="none" />
        {selectedIds.size > 0 && (
          <path d={selected.join('')} stroke="var(--rs-copper)" strokeWidth={2.6} strokeLinecap="round" fill="none" />
        )}
        <text x={38 + inner / 2} y={PANEL - 14} textAnchor="middle" className="xfig__axislabel">
          {x}
        </text>
        <text
          transform={`rotate(-90 10 ${10 + inner / 2})`}
          x={10}
          y={10 + inner / 2}
          textAnchor="middle"
          className="xfig__axislabel"
        >
          {y}
        </text>
        <text x={38} y={10 + inner + 10} className="xpc__tick">{fmt(xMin)}</text>
        <text x={38 + inner} y={10 + inner + 10} textAnchor="end" className="xpc__tick">{fmt(xMax)}</text>
      </svg>
      <span className="xmatrix__pairs">
        {Math.min(xScale.valid_count, yScale.valid_count).toLocaleString('en-US')} valid pairs
      </span>
      {colorColumn && colorLevels.length > 1 && (
        <span className="xmatrix__color">coloured by {colorColumn}</span>
      )}
    </div>
  )
}
