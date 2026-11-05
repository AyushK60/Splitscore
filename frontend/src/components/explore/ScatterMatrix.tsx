import { useEffect, useMemo, useState } from 'react'

import { exploreApi } from '../../api/client'
import type { ExploreSchema, SeriesResponse } from '../../api/types'
import {
  formatCorrelation,
  groupColors,
  isDiscreteAxis,
  jitterOffset,
  markStrokeWidth,
  pearsonR,
  pointOpacity,
} from '../../explore/scatterMarks'
import { FigureExport } from './FigureExport'

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

const PANEL = 218

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
        <FigureExport
          figureId="scatter-matrix"
          title={`Scatter matrix — ${columns.join(', ')}`}
          settings={`pairwise panels · up to 4 variables`}
          counts={
            series
              ? `${series.drawn_rows.toLocaleString('en-US')} of ${series.filtered_population.toLocaleString('en-US')} rows drawn per panel`
              : ''
          }
          sampling={series?.sampling.description}
          notes={['Panels share the render sample; open a pair full-size for vector exports.']}
          getSvg={() => null}
          vectorExports={false}
        />
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
        <>
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
          {colorColumn && colorLevels.length > 1 && (
            <div className="xpc__legend">
              <span className="xpc__legendtitle">Colour: {colorColumn}</span>
              {colorLevels.map((level, index) => (
                <span key={level} className="xpc__legenditem">
                  <span
                    className="xpc__swatch"
                    style={{ background: groupColors(colorLevels)[index] }}
                  />
                  {level}
                </span>
              ))}
              {selectedIds.size > 0 && (
                <span className="xpc__legenditem xpc__legenditem--selected">
                  <span className="xpc__swatch xpc__swatch--selected" /> selected
                </span>
              )}
            </div>
          )}
          <p className="xfig__note">
            Each panel is the same render sample, not a separately filtered population. The
            correlation shown is Pearson’s r on the drawn rows: a descriptive summary of this
            sample, not a finding or a causal claim. Low-cardinality axes are offset by at most 4px
            so repeated values remain countable; the values and r are unchanged.
          </p>
        </>
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

  const xValues = series.rows
    .map((row) => row.values[x])
    .filter((value): value is number => typeof value === 'number')
  const yValues = series.rows
    .map((row) => row.values[y])
    .filter((value): value is number => typeof value === 'number')
  const discreteX = isDiscreteAxis(xValues)
  const discreteY = isDiscreteAxis(yValues)
  const width = markStrokeWidth(series.drawn_rows)
  const hasSelection = selectedIds.size > 0
  const palette = groupColors(colorLevels)
  const levelColor = (level: string) => {
    const index = colorLevels.indexOf(level)
    return index >= 0 ? palette[index] : '#6e6e6e'
  }

  const groups = new Map<string, string[]>()
  const selected: string[] = []
  for (const row of series.rows) {
    const xv = row.values[x]
    const yv = row.values[y]
    if (typeof xv !== 'number' || typeof yv !== 'number') continue
    const xOffset = discreteX ? jitterOffset(row.id, 'x') : 0
    const yOffset = discreteY ? jitterOffset(row.id, 'y') : 0
    const dot = `M${(px(xv) + xOffset).toFixed(1)} ${(py(yv) + yOffset).toFixed(1)}h.01`
    if (hasSelection && selectedIds.has(row.id)) selected.push(dot)
    else {
      const key = colorColumn ? String(row.values[colorColumn] ?? '(missing)') : 'all'
      const bucket = groups.get(key) ?? []
      bucket.push(dot)
      groups.set(key, bucket)
    }
  }
  const correlation = pearsonR(series.rows, x, y)
  const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toPrecision(3))

  return (
    <div
      className="xmatrix__panel"
      role="button"
      tabIndex={0}
      aria-label={`Scatter of ${x} against ${y}; ${formatCorrelation(correlation)}. Open full size.`}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onOpen()
        }
      }}
    >
      <svg
        width={PANEL}
        height={PANEL}
        role="img"
        aria-label={`Scatter of ${x} against ${y}`}
      >
        <title>
          {x} × {y} — click to open full size
        </title>
        <rect x={38} y={10} width={inner} height={inner} fill="none" stroke="var(--rs-line)" />
        {[...groups.entries()].map(([level, dots]) => (
          <path
            key={`halo-${level}`}
            d={dots.join('')}
            stroke="var(--rs-surface)"
            strokeWidth={width + 2}
            strokeLinecap="round"
            opacity={pointOpacity(series.drawn_rows, hasSelection) * 0.6}
            fill="none"
          />
        ))}
        {[...groups.entries()].map(([level, dots]) => (
          <path
            key={level}
            d={dots.join('')}
            stroke={colorColumn ? levelColor(level) : 'var(--rs-teal)'}
            strokeWidth={hasSelection ? width * 0.82 : width}
            strokeLinecap="round"
            opacity={pointOpacity(series.drawn_rows, hasSelection)}
            fill="none"
          />
        ))}
        {hasSelection && (
          <>
            <path d={selected.join('')} stroke="var(--rs-surface)" strokeWidth={width + 2.8} strokeLinecap="round" fill="none" />
            <path d={selected.join('')} stroke="var(--rs-copper)" strokeWidth={width + 0.4} strokeLinecap="round" fill="none" />
          </>
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
        {Math.min(xScale.valid_count, yScale.valid_count).toLocaleString('en-US')} valid pairs ·{' '}
        <span className="mono" title="Pearson correlation on the drawn render sample; descriptive only">
          {formatCorrelation(correlation)}
        </span>
        {(discreteX || discreteY) ? ' · discrete-axis offset ≤4px' : ''}
      </span>
      {colorColumn && colorLevels.length > 1 && (
        <span className="xmatrix__color">colour marks: {colorColumn}</span>
      )}
    </div>
  )
}
