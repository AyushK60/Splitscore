import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { exploreApi } from '../../api/client'
import type { BrushPredicate, ExploreSchema, SeriesResponse } from '../../api/types'
import { FigureExport } from './FigureExport'

/**
 * Single scatter plot with a box brush.
 *
 * Dragging a rectangle creates two range predicates (one per axis) in the
 * shared selection engine — the same predicates a parallel-coordinates brush
 * produces, so a scatter selection highlights in every other view. Points are
 * the backend's render sample; the pair's valid count is exact.
 */

const PAD = { top: 16, right: 18, bottom: 44, left: 62 }

interface Props {
  schema: ExploreSchema
  x: string
  y: string
  onAxisChange: (axis: 'x' | 'y', column: string) => void
  onPredicates: (predicates: BrushPredicate[]) => void
  predicates: BrushPredicate[]
  selectedIds: Set<string>
  colorColumn: string | null
  colorLevels: string[]
}

function groupColors(levels: string[]): string[] {
  const palette = ['var(--rs-teal)', '#5b6d9e', '#7d9b4e', '#9e5b8a', '#4e8a9e', '#9e7d4e', '#8a5a00', '#6e6e6e']
  return levels.map((_, i) => palette[i % palette.length])
}

export function ScatterFocus({
  schema,
  x,
  y,
  onAxisChange,
  onPredicates,
  predicates,
  selectedIds,
  colorColumn,
  colorLevels,
}: Props) {
  const [series, setSeries] = useState<SeriesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [size, setSize] = useState({ width: 720, height: 460 })
  const [drag, setDrag] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null)
  const dragRef = useRef<{ x0: number; y0: number; x1: number; y1: number } | null>(null)
  // The plot div renders only once data exists, so the ref arrives after
  // mount; state (not a plain ref) re-runs the observer effect when it does.
  const [plotEl, setPlotEl] = useState<HTMLDivElement | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    if (!plotEl) return
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect
      // On phones the panel itself is narrower than the old 420px floor; the
      // plot container scrolls horizontally instead of overflowing the page.
      const floor = Math.min(420, window.innerWidth - 40)
      setSize({ width: Math.max(floor, rect.width), height: Math.max(340, rect.height) })
    })
    observer.observe(plotEl)
    return () => observer.disconnect()
  }, [plotEl])

  useEffect(() => {
    if (!x || !y || x === y) {
      setSeries(null)
      return
    }
    let cancelled = false
    const columns = colorColumn && colorColumn !== x && colorColumn !== y ? [x, y, colorColumn] : [x, y]
    exploreApi
      .series(schema.dataset.dataset_id, { columns, max_rows: 2000 })
      .then((result) => {
        if (cancelled) return
        setSeries(result)
        setError(null)
      })
      .catch((e) => {
        if (cancelled) return
        setSeries(null)
        setError(e instanceof Error ? e.message : 'Scatter data could not be loaded.')
      })
    return () => {
      cancelled = true
    }
  }, [schema.dataset.dataset_id, x, y, colorColumn])

  const innerWidth = size.width - PAD.left - PAD.right
  const innerHeight = size.height - PAD.top - PAD.bottom

  const xScale = series?.scale[x]
  const yScale = series?.scale[y]
  const xMin = xScale?.min ?? 0
  const xMax = xScale?.max ?? 1
  const yMin = yScale?.min ?? 0
  const yMax = yScale?.max ?? 1

  const px = useCallback(
    (value: number) => PAD.left + ((value - xMin) / (xMax - xMin || 1)) * innerWidth,
    [xMin, xMax, innerWidth],
  )
  const py = useCallback(
    (value: number) => PAD.top + innerHeight - ((value - yMin) / (yMax - yMin || 1)) * innerHeight,
    [yMin, yMax, innerHeight],
  )
  const vx = (x: number) => xMin + ((x - PAD.left) / innerWidth) * (xMax - xMin)
  const vy = (y: number) => yMin + (1 - (y - PAD.top) / innerHeight) * (yMax - yMin)

  const levelList = useMemo(() => (colorColumn ? colorLevels : ['all']), [colorColumn, colorLevels])
  const levelColors = useMemo(() => groupColors(levelList), [levelList])

  const buckets = useMemo(() => {
    const map = new Map<string, string[]>() // path "M x y h…" dots
    const selected: string[] = []
    if (!series) return { map, selected }
    for (const row of series.rows) {
      const xv = row.values[x]
      const yv = row.values[y]
      if (typeof xv !== 'number' || typeof yv !== 'number') continue
      const dot = `M${px(xv).toFixed(1)} ${py(yv).toFixed(1)}h.01`
      if (selectedIds.size > 0 && selectedIds.has(row.id)) selected.push(dot)
      else {
        const key = colorColumn ? String(row.values[colorColumn] ?? '(missing)') : 'all'
        const bucket = map.get(key) ?? []
        bucket.push(dot)
        map.set(key, bucket)
      }
    }
    return { map, selected }
  }, [series, x, y, px, py, selectedIds, colorColumn])

  const commitBrush = () => {
    const finished = dragRef.current
    dragRef.current = null
    setDrag(null)
    if (!finished) return
    const xLo = vx(Math.min(finished.x0, finished.x1))
    const xHi = vx(Math.max(finished.x0, finished.x1))
    const yLo = vy(Math.max(finished.y0, finished.y1))
    const yHi = vy(Math.min(finished.y0, finished.y1))
    if (Math.abs(finished.x1 - finished.x0) < 4 && Math.abs(finished.y1 - finished.y0) < 4) return
    // A scatter brush replaces any previous range on these two axes and keeps
    // brushes on other axes (union-within-column still applies per axis).
    const others = predicates.filter((p) => p.kind === 'range' && p.column !== x && p.column !== y)
    onPredicates([...others, { column: x, kind: 'range', min: xLo, max: xHi }, { column: y, kind: 'range', min: yLo, max: yHi }])
  }

  if (!x || !y) {
    return <p className="xw__placeholder">Choose two numeric variables to draw a scatter plot.</p>
  }

  const pairValid = Math.min(xScale?.valid_count ?? 0, yScale?.valid_count ?? 0)
  const fmt = (v: number) => (Number.isInteger(v) ? v.toLocaleString('en-US') : v.toPrecision(3))

  return (
    <figure className="xfig" data-figure="scatter">
      <figcaption className="xfig__caption">
        <span className="xfig__title">
          Scatter — {x} (x) × {y} (y)
        </span>
        <span className="xfig__sub">
          {series
            ? `${series.drawn_rows.toLocaleString('en-US')} of ${series.filtered_population.toLocaleString('en-US')} rows drawn${
                series.sampling.stride > 1 ? ` (every ${series.sampling.stride}th row)` : ''
              } · up to ${pairValid.toLocaleString('en-US')} valid pairs`
            : 'loading…'}
        </span>
        <FigureExport
          figureId="scatter"
          title={`Scatter — ${x} (x) × ${y} (y)`}
          settings={`${series ? `render sample of ${series.filtered_population.toLocaleString('en-US')} rows` : ''}${
            colorColumn ? ` · coloured by ${colorColumn}` : ''
          }`}
          counts={
            series
              ? `${series.drawn_rows.toLocaleString('en-US')} drawn · up to ${pairValid.toLocaleString('en-US')} valid pairs${
                  selectedIds.size > 0 ? ` · ${selectedIds.size.toLocaleString('en-US')} selected` : ''
                }`
              : ''
          }
          sampling={series?.sampling.description}
          notes={['Point positions are genuine values; missing or unparsable cells are not drawn.']}
          getSvg={() => svgRef.current}
        />
      </figcaption>

      <div className="xfig__controls">
        <label className="xfig__control">
          x
          <select className="xselect" value={x} onChange={(e) => onAxisChange('x', e.target.value)}>
            {schema.numeric_columns.map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
        </label>
        <label className="xfig__control">
          y
          <select className="xselect" value={y} onChange={(e) => onAxisChange('y', e.target.value)}>
            {schema.numeric_columns.map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
        </label>
        {predicates.some((p) => p.kind === 'range') && (
          <button type="button" className="xbtn xbtn--tiny" onClick={() => onPredicates([])}>
            Reset scatter brushes
          </button>
        )}
      </div>

      {error && (
        <p className="xw__ploterror" role="alert">
          {error}
        </p>
      )}

      {series && xScale && yScale && (
        <div ref={setPlotEl} className="xfig__plot">
          <svg
            ref={svgRef}
            width={size.width}
            height={size.height}
            role="img"
            aria-label={`Scatter plot of ${x} against ${y}`}
            style={{ touchAction: 'none' }}
          >
            <rect
              x={PAD.left}
              y={PAD.top}
              width={innerWidth}
              height={innerHeight}
              fill="none"
              stroke="var(--rs-line)"
            />
            {[0.25, 0.5, 0.75].map((t) => (
              <g key={t}>
                <line
                  x1={PAD.left + innerWidth * t}
                  y1={PAD.top}
                  x2={PAD.left + innerWidth * t}
                  y2={PAD.top + innerHeight}
                  stroke="var(--rs-line)"
                  strokeDasharray="2 4"
                />
                <line
                  x1={PAD.left}
                  y1={PAD.top + innerHeight * t}
                  x2={PAD.left + innerWidth}
                  y2={PAD.top + innerHeight * t}
                  stroke="var(--rs-line)"
                  strokeDasharray="2 4"
                />
              </g>
            ))}
            {/* unselected points: one path per colour group */}
            {[...buckets.map.entries()].map(([level, dots], i) => (
              <path
                key={level}
                d={dots.join('')}
                stroke={colorColumn ? levelColors[i % levelColors.length] : 'var(--rs-teal)'}
                strokeWidth={selectedIds.size > 0 ? 1 : 2}
                strokeLinecap="round"
                opacity={selectedIds.size > 0 ? 0.25 : 0.55}
                fill="none"
              />
            ))}
            {/* selected points */}
            {selectedIds.size > 0 && (
              <path d={buckets.selected.join('')} stroke="var(--rs-copper)" strokeWidth={3} strokeLinecap="round" fill="none" />
            )}
            {/* live brush rect */}
            {drag && (
              <rect
                x={Math.min(drag.x0, drag.x1)}
                y={Math.min(drag.y0, drag.y1)}
                width={Math.abs(drag.x1 - drag.x0)}
                height={Math.abs(drag.y1 - drag.y0)}
                className="xpc__brush xpc__brush--live"
              />
            )}
            {/* axis labels */}
            <text x={PAD.left + innerWidth / 2} y={size.height - 8} textAnchor="middle" className="xfig__axistitle">
              {x}
            </text>
            <text
              transform={`rotate(-90 14 ${PAD.top + innerHeight / 2})`}
              x={14}
              y={PAD.top + innerHeight / 2}
              textAnchor="middle"
              className="xfig__axistitle"
            >
              {y}
            </text>
            <text x={PAD.left} y={PAD.top + innerHeight + 16} className="xpc__tick">
              {fmt(xMin)}
            </text>
            <text x={PAD.left + innerWidth} y={PAD.top + innerHeight + 16} textAnchor="end" className="xpc__tick">
              {fmt(xMax)}
            </text>
            <text x={PAD.left - 8} y={PAD.top + 10} textAnchor="end" className="xpc__tick">
              {fmt(yMax)}
            </text>
            <text x={PAD.left - 8} y={PAD.top + innerHeight} textAnchor="end" className="xpc__tick">
              {fmt(yMin)}
            </text>
          </svg>
          {/* brush capture layer sits above the svg */}
          <div
            className="xfig__brushlayer"
            onPointerDown={(e) => {
              const rect = e.currentTarget.getBoundingClientRect()
              const point = { x: e.clientX - rect.left, y: e.clientY - rect.top }
              dragRef.current = { x0: point.x, y0: point.y, x1: point.x, y1: point.y }
              setDrag({ x0: point.x, y0: point.y, x1: point.x, y1: point.y })
              e.currentTarget.setPointerCapture(e.pointerId)
            }}
            onPointerMove={(e) => {
              const rect = e.currentTarget.getBoundingClientRect()
              const point = { x: e.clientX - rect.left, y: e.clientY - rect.top }
              if (dragRef.current) dragRef.current = { ...dragRef.current, x1: point.x, y1: point.y }
              setDrag((previous) => (previous ? { ...previous, x1: point.x, y1: point.y } : previous))
            }}
            onPointerUp={(e) => {
              e.currentTarget.releasePointerCapture(e.pointerId)
              commitBrush()
            }}
          />
        </div>
      )}

      {colorColumn && (
        <div className="xpc__legend">
          <span className="xpc__legendtitle">Colour: {colorColumn}</span>
          {levelList.map((level, i) => (
            <span key={level} className="xpc__legenditem">
              <span className="xpc__swatch" style={{ background: levelColors[i % levelColors.length] }} />
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
        Drag a rectangle to select observations — the selection joins the same shared pool as the
        parallel-coordinates brushes and the row-evidence inspector.
      </p>
    </figure>
  )
}
