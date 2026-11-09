import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { BrushPredicate, SeriesResponse } from '../../api/types'
import { FigureExport } from './FigureExport'

/** A committed axis brush over real data units. */
type BrushRangePredicate = Extract<BrushPredicate, { kind: 'range' }>

/**
 * Parallel coordinates - the Visual Explorer's flagship instrument.
 *
 * Scientific rules this rendering obeys:
 *  - Only genuinely numeric columns become axes; the header names the column
 *    and the axis range in data units (min–max of the *filtered population*,
 *    not of the drawn sample).
 *  - Lines are the render sample the backend chose (systematic grid). The
 *    caption states how many of how many rows are drawn - sampled density is
 *    never passed off as the whole dataset.
 *  - A missing or unparsable cell breaks the polyline at that axis instead of
 *    dropping the row or inventing a position.
 *  - A constant column collapses to a mid-rail with an explicit "constant"
 *    note instead of a fake spread.
 *  - Brushing a range creates a predicate over real data units; predicates on
 *    the same axis union, across axes intersect (documented in the backend).
 *  - Selected observations are drawn individually in copper; everything else
 *    is dimmed group paths (one path per colour group, so the element count
 *    stays small at thousands of lines).
 */

interface Props {
  series: SeriesResponse
  /** Column driving line colour, with its observed levels. */
  colorColumn: string | null
  colorLevels: string[]
  /** Immutable ids of the active selection (from the shared engine). */
  selectedIds: Set<string>
  predicates: BrushPredicate[]
  onPredicates: (predicates: BrushPredicate[]) => void
  onHoverRow: (id: string | null) => void
  /** Bumped to force axis geometry to re-measure (focus mode toggles). */
  resizeKey?: string
}

interface AxisLayout {
  column: string
  x: number
  min: number
  max: number
  constant: boolean
  brokenRows: number
}

const PAD = { top: 48, right: 110, bottom: 46, left: 70 }

function fmt(value: number): string {
  if (Number.isInteger(value)) return value.toLocaleString('en-US')
  if (Math.abs(value) >= 1000) return value.toLocaleString('en-US', { maximumFractionDigits: 0 })
  if (Math.abs(value) >= 10) return value.toFixed(1)
  return value.toPrecision(3)
}

function colorsFor(levels: string[]): string[] {
  // Group hues deliberately exclude copper: copper marks the user's own
  // selection everywhere in the explorer, so a colour group must never be
  // mistaken for a selected cohort.
  const palette = [
    '#7e1f2c',
    '#e0a21b',
    '#2f2b27',
    '#c4577a',
    '#a89a88',
    '#8c5a3c',
    '#e8c36a',
    '#d98ca3',
  ]
  return levels.map((_, i) => palette[i % palette.length])
}

export const ParallelCoordinates = memo(function ParallelCoordinates({
  series,
  colorColumn,
  colorLevels,
  selectedIds,
  predicates,
  onPredicates,
  onHoverRow,
  resizeKey,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const [size, setSize] = useState({ width: 900, height: 460 })
  const [order, setOrder] = useState<string[]>(series.columns)
  const [drag, setDrag] = useState<{ axis: string; y0: number; y1: number } | null>(null)
  const [hoveredAxis, setHoveredAxis] = useState<string | null>(null)
  // Progressive disclosure: the chart stays compact until a beginner asks for
  // the reading guide. The guide explains the encoding, never an inference.
  const [helpOpen, setHelpOpen] = useState(false)

  // Re-derive the axis order when the requested columns change (dataset or
  // control change), while keeping any reordering the user already applied.
  useEffect(() => {
    setOrder((previous) => {
      const kept = previous.filter((c) => series.columns.includes(c))
      const added = series.columns.filter((c) => !kept.includes(c))
      return [...kept, ...added]
    })
  }, [series.columns])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    // The observed element must contain ONLY the svg: observing a wrapper
    // that also holds other bars makes the svg height chase the wrapper
    // height (which includes those bars) and grow every frame.
    const observer = new ResizeObserver((entries) => {
      const rect = entries[0].contentRect
      // The 560px floor assumes a desktop panel; on a phone the plot container
      // scrolls horizontally rather than overflowing the page.
      const floor = Math.min(560, window.innerWidth - 32)
      setSize({ width: Math.max(floor, rect.width), height: Math.max(360, rect.height) })
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [resizeKey])

  const innerWidth = size.width - PAD.left - PAD.right
  const innerHeight = size.height - PAD.top - PAD.bottom

  const axes: AxisLayout[] = useMemo(() => {
    // Only genuinely numeric columns become axes. A colour variable (e.g. a
    // boolean) may travel in `series.columns` for grouping, but it is not a
    // measurement and must not render as a rail.
    const columns = order.filter((c) => series.scale[c]?.numeric)
    const step = columns.length > 1 ? innerWidth / (columns.length - 1) : 0
    return columns.map((column, i) => {
      const scale = series.scale[column]
      const min = scale.min ?? 0
      const max = scale.max ?? 1
      const constant = scale.min === null || scale.max === null || max - min <= 0
      return {
        column,
        x: PAD.left + (columns.length > 1 ? i * step : innerWidth / 2),
        min,
        max,
        constant,
        brokenRows: series.population - scale.valid_count,
      }
    })
  }, [order, series, innerWidth])

  const yFor = useCallback(
    (axis: AxisLayout, value: number): number | null => {
      if (axis.constant) return PAD.top + innerHeight / 2
      if (!Number.isFinite(value)) return null
      const t = (value - axis.min) / (axis.max - axis.min)
      if (t < -0.0001 || t > 1.0001) return null
      return PAD.top + innerHeight - t * innerHeight
    },
    [innerHeight],
  )

  // One path per colour group for unselected lines (few DOM elements), one
  // path per selected row (highlight must be per-line to read clearly).
  const groups = useMemo(() => {
    const map = new Map<string, string[]>()
    const selected: string[] = []
    for (const row of series.rows) {
      const key = colorColumn ? String(row.values[colorColumn] ?? '(missing)') : 'all'
      if (selectedIds.size > 0 && selectedIds.has(row.id)) {
        selected.push(buildPath(row, order, axes, yFor))
      } else {
        const bucket = map.get(key) ?? []
        bucket.push(buildPath(row, order, axes, yFor))
        map.set(key, bucket)
      }
    }
    return { unselected: map, selected }
  }, [series, order, axes, yFor, selectedIds, colorColumn])

  const levelList = useMemo(
    () => (colorColumn ? colorLevels : ['all']),
    [colorColumn, colorLevels],
  )
  const levelColors = useMemo(() => colorsFor(levelList), [levelList])

  // ---- brushing ------------------------------------------------------------ //
  const axisByColumn = useMemo(() => new Map(axes.map((a) => [a.column, a])), [axes])

  const rangeForDrag = useCallback(
    (axis: AxisLayout, y0: number, y1: number): BrushRangePredicate | null => {
      if (axis.constant) return null
      const toValue = (y: number) => {
        const t = 1 - (y - PAD.top) / innerHeight
        return axis.min + t * (axis.max - axis.min)
      }
      const lo = toValue(Math.max(y0, y1))
      const hi = toValue(Math.min(y0, y1))
      if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null
      return { column: axis.column, kind: 'range', min: lo, max: hi }
    },
    [innerHeight],
  )

  // The committed drag lives in a ref: the commit on pointer-up must read the
  // final drag without depending on a state updater (updaters must stay pure),
  // and the mirrored state only drives the live brush rectangle.
  const dragRef = useRef<{ axis: string; y0: number; y1: number } | null>(null)

  // Brush geometry lives in SVG coordinates. offsetY is relative to the event
  // target (the 14px-wide hit rect, which starts at PAD.top), so measuring
  // against the SVG's own bounding box is the only target-independent reading.
  const svgY = useCallback((event: React.PointerEvent): number => {
    const svg = svgRef.current
    if (!svg) return event.nativeEvent.offsetY
    return event.clientY - svg.getBoundingClientRect().top
  }, [])

  const onPointerDown = useCallback((event: React.PointerEvent, axis: AxisLayout) => {
    if (axis.constant) return
    const target = event.currentTarget as SVGElement
    target.setPointerCapture(event.pointerId)
    const y = svgY(event)
    dragRef.current = { axis: axis.column, y0: y, y1: y }
    setDrag({ axis: axis.column, y0: y, y1: y })
  }, [svgY])

  const onPointerMove = useCallback((event: React.PointerEvent) => {
    const y = svgY(event)
    if (dragRef.current) dragRef.current.y1 = y
    setDrag((previous) => (previous ? { ...previous, y1: y } : previous))
  }, [svgY])

  const onPointerUp = useCallback(
    (event: React.PointerEvent) => {
      const target = event.currentTarget as SVGElement
      target.releasePointerCapture?.(event.pointerId)
      const finished = dragRef.current
      dragRef.current = null
      setDrag(null)
      if (!finished) return
      const axis = axisByColumn.get(finished.axis)
      if (!axis) return
      const predicate = rangeForDrag(axis, finished.y0, finished.y1)
      if (!predicate) return
      // Union with existing brushes on this axis; leave other axes untouched.
      const sameAxis = predicates.filter((p) => p.column === axis.column && p.kind === 'range')
      const others = predicates.filter((p) => !(p.column === axis.column && p.kind === 'range'))
      const only = sameAxis.length === 1 ? sameAxis[0] : undefined
      const isTrivial =
        only !== undefined &&
        only.kind === 'range' &&
        Math.abs(only.min - predicate.min) < 1e-12 &&
        Math.abs(only.max - predicate.max) < 1e-12
      if (!isTrivial) {
        onPredicates([...others, ...sameAxis, predicate])
      } else {
        // Dragging exactly over an existing brush removes it - a deliberate
        // second gesture over the same range reads as "clear this brush".
        onPredicates(others)
      }
    },
    [axisByColumn, rangeForDrag, predicates, onPredicates],
  )

  // ---- axis reordering (accessible controls under the canvas) -------------- //
  const moveAxis = useCallback(
    (column: string, direction: -1 | 1) => {
      setOrder((previous) => {
        const index = previous.indexOf(column)
        const target = index + direction
        if (index < 0 || target < 0 || target >= previous.length) return previous
        const next = [...previous]
        next[index] = next[target]
        next[target] = column
        return next
      })
    },
    [],
  )

  const activeBrushes = predicates.filter((p) => p.kind === 'range') as Array<{
    column: string
    kind: 'range'
    min: number
    max: number
  }>

  const axisStep = axes.length > 1 ? innerWidth / (axes.length - 1) : innerWidth

  if (axes.length === 0) {
    return (
      <div ref={containerRef} className="xpc xpc--empty">
        <p className="xpc__note">
          No numeric columns are selected. Parallel coordinates needs at least one numeric
          variable - categorical columns are available as colour groupings, not as axes.
        </p>
      </div>
    )
  }

  const drawnSelected = selectedIds.size > 0 ? groups.selected.length : 0

  return (
    <figure className="xpc" data-testid="parallel-coordinates">
      <div className="xpc__head">
        <figcaption className="xpc__title">
          Parallel coordinates
          <span className="xpc__subtitle">
            {series.drawn_rows.toLocaleString('en-US')} of{' '}
            {series.filtered_population.toLocaleString('en-US')} rows drawn
            {series.sampling.stride > 1
              ? ` (every ${series.sampling.stride}th row in file order)`
              : ' (all rows)'}
            {series.filters_active ? ' - filters active' : ''}
          </span>
        </figcaption>
        <div className="xpc__actions">
          <span className="xpc__count" aria-live="polite">
            {selectedIds.size > 0
              ? `${selectedIds.size.toLocaleString('en-US')} selected`
              : 'no rows selected'}
          </span>
          <button
            type="button"
            id="xpc-help-toggle"
            className="xbtn xbtn--ghost"
            aria-expanded={helpOpen}
            aria-controls="xpc-help"
            onClick={() => setHelpOpen((open) => !open)}
          >
            {helpOpen ? 'Hide reading guide' : 'How to read this chart'}
          </button>
          {activeBrushes.length > 0 && (
            <button type="button" className="xbtn xbtn--ghost" onClick={() => onPredicates([])}>
              Reset brushes ({activeBrushes.length})
            </button>
          )}
          <FigureExport
            figureId="parallel-coordinates"
            title={`Parallel coordinates - ${axes.map((a) => a.column).join(', ')}`}
            settings={`${axes.length} numeric axes${colorColumn ? ` · coloured by ${colorColumn}` : ''}`}
            counts={`${series.drawn_rows.toLocaleString('en-US')} of ${series.filtered_population.toLocaleString('en-US')} rows drawn${
              selectedIds.size > 0 ? ` · ${selectedIds.size.toLocaleString('en-US')} selected` : ''
            }`}
            sampling={series.sampling.description}
            notes={[
              'Axis ranges cover the full dataset population; drawn lines follow the active filters.',
              'Density of drawn lines represents the render sample, not the full dataset.',
            ]}
            getSvg={() => svgRef.current}
          />
        </div>
      </div>
      <p className="xpc__readhint">
        Each line is one observation · each vertical rail is a numeric variable · drag on a rail to
        brush a value range.
      </p>
      {helpOpen && (
        <section className="xpc__help" id="xpc-help" aria-label="How to read parallel coordinates">
          <div className="xpc__helpgrid">
            <div>
              <h3>One line = one observation</h3>
              <p>
                Each connected line follows a single row of the dataset across every selected
                variable. A line that jumps between rails is one observation whose values differ
                between those variables.
              </p>
            </div>
            <div>
              <h3>One rail = one variable</h3>
              <p>
                The top and bottom of each rail are that variable's observed minimum and maximum in
                the active population. Values are plotted at their real position, in the column's
                own units; a constant column collapses to a mid-rail and says so.
              </p>
            </div>
            <div>
              <h3>Crossing lines</h3>
              <p>
                Crossing means the ordering of values differs between two neighbouring variables.
                It does <strong>not</strong> by itself prove correlation, causation or data leakage;
                read crossings as a prompt to inspect the variables, not as a finding.
              </p>
            </div>
            <div>
              <h3>Brushing a range</h3>
              <p>
                Drag vertically on a rail to select values between two positions. The selection
                count updates immediately, selected rows turn copper and appear in{' '}
                <strong>Row evidence</strong>, and the same rows highlight in Scatter, the scatter
                matrix and distributions. Drag again over the same range to remove that brush.
              </p>
            </div>
          </div>
          <svg
            className="xpc__example"
            viewBox="0 0 320 96"
            role="img"
            aria-label="Annotated example: two rails, low and high values, with two lines crossing between them"
          >
            <line x1="70" y1="12" x2="70" y2="76" stroke="var(--rs-line-strong)" />
            <line x1="250" y1="12" x2="250" y2="76" stroke="var(--rs-line-strong)" />
            <text x="70" y="8" textAnchor="middle" className="xpc__tick">variable A</text>
            <text x="250" y="8" textAnchor="middle" className="xpc__tick">variable B</text>
            <text x="62" y="16" textAnchor="end" className="xpc__tick">high</text>
            <text x="62" y="80" textAnchor="end" className="xpc__tick">low</text>
            <path d="M70 22 L250 68" stroke="var(--rs-teal)" strokeWidth="1.6" fill="none" />
            <path d="M70 68 L250 22" stroke="var(--rs-copper)" strokeWidth="1.6" fill="none" />
            <text x="160" y="92" textAnchor="middle" className="xpc__tick">
              two rows crossing: opposite value order
            </text>
          </svg>
          <p className="xpc__examplecaption">
            The teal and copper lines are two observations. They cross because the row that is high
            on A is low on B. This chart is exploratory: it displays values you selected, and it does
            not estimate effects or detect leakage.
          </p>
          <p className="xpc__helpnote">
            Drawn density is the render sample stated above, not the whole dataset. Axis ranges cover
            the active (filtered) population. Use the reorder controls below the canvas to compare
            adjacent variables, and “Reset brushes” to return to the full population.
          </p>
        </section>
      )}
      <div className="xpc__canvas">
        <div ref={containerRef} className="xpc__plot">
        <svg
          ref={svgRef}
          width={size.width}
          height={size.height}
          role="img"
          aria-label={`Parallel coordinates of ${axes.length} numeric variables, ${series.drawn_rows} rows drawn of ${series.filtered_population}`}
        >
          {/* frame rails */}
          <line x1={PAD.left} y1={PAD.top} x2={size.width - PAD.right} y2={PAD.top} className="xpc__rail" />
          <line x1={PAD.left} y1={PAD.top + innerHeight} x2={size.width - PAD.right} y2={PAD.top + innerHeight} className="xpc__rail" />

          {/* unselected lines: one path per colour group */}
          {[...groups.unselected.entries()].map(([level, paths], i) => (
            <path
              key={`g-${level}`}
              d={paths.join('')}
              className="xpc__line"
              style={{
                stroke: colorColumn ? levelColors[i % levelColors.length] : 'var(--rs-teal)',
                opacity: selectedIds.size > 0 ? 0.09 : colorColumn ? 0.34 : 0.28,
                fill: 'none',
              }}
            />
          ))}

          {/* selected lines: individual paths */}
          {groups.selected.map((d, i) => (
            <path key={`s-${i}`} d={d} className="xpc__line xpc__line--selected" fill="none" />
          ))}

          {/* axes */}
          {axes.map((axis) => {
            const brushes = activeBrushes.filter((b) => b.column === axis.column)
            const dragRange =
              drag && drag.axis === axis.column && !axis.constant
                ? rangeForDrag(axis, drag.y0, drag.y1)
                : null
            return (
              <g key={axis.column} className={`xpc__axis${hoveredAxis === axis.column ? ' xpc__axis--hot' : ''}`}>
                <line
                  x1={axis.x}
                  y1={PAD.top}
                  x2={axis.x}
                  y2={PAD.top + innerHeight}
                  className="xpc__axisline"
                />
                {/* brush hit area */}
                {!axis.constant && (
                  <rect
                    x={axis.x - 7}
                    y={PAD.top}
                    width={14}
                    height={innerHeight}
                    fill="transparent"
                    style={{ cursor: 'ns-resize', touchAction: 'none' }}
                    aria-label={`Brush a value range on ${axis.column}`}
                    onPointerDown={(e) => onPointerDown(e, axis)}
                    onPointerMove={onPointerMove}
                    onPointerUp={onPointerUp}
                    onPointerLeave={() => onHoverRow(null)}
                  />
                )}
                {/* committed brushes */}
                {brushes.map((b, i) => {
                  const yLo = yFor(axis, b.min)
                  const yHi = yFor(axis, b.max)
                  if (yLo === null || yHi === null) return null
                  return (
                    <rect
                      key={`b-${i}`}
                      x={axis.x - 6}
                      y={Math.min(yLo, yHi)}
                      width={12}
                      height={Math.max(2, Math.abs(yHi - yLo))}
                      className="xpc__brush"
                    />
                  )
                })}
                {/* live drag */}
                {dragRange && dragRange.kind === 'range' && (
                  (() => {
                    const yLo = yFor(axis, dragRange.min)
                    const yHi = yFor(axis, dragRange.max)
                    if (yLo === null || yHi === null) return null
                    return (
                      <rect
                        x={axis.x - 6}
                        y={Math.min(yLo, yHi)}
                        width={12}
                        height={Math.max(2, Math.abs(yHi - yLo))}
                        className="xpc__brush xpc__brush--live"
                      />
                    )
                  })()
                )}
                {/* header */}
                <g
                  transform={`translate(${axis.x}, ${PAD.top - 30})`}
                  className="xpc__header"
                  onPointerEnter={() => setHoveredAxis(axis.column)}
                  onPointerLeave={() => setHoveredAxis(null)}
                >
                  {/* Truncate to the space between neighbouring rails; the
                      reorder bar below the canvas always shows full names. */}
                  <title>{axis.column}</title>
                  <text textAnchor="middle" className="xpc__axisname">
                    {truncateName(axis.column, axisStep)}
                  </text>
                  <text textAnchor="middle" y={12} className="xpc__axisrange">
                    {axis.constant
                      ? 'constant / no spread'
                      : `${fmt(axis.min)} – ${fmt(axis.max)}`}
                  </text>
                  {axis.constant && (
                    <text textAnchor="middle" y={PAD.top + innerHeight / 2 - 8} className="xpc__axisnote">
                      every value identical or unparsable
                    </text>
                  )}
                </g>
                {/* tick labels: min / mid / max */}
                {!axis.constant && (
                  <>
                    <text x={axis.x - 10} y={PAD.top + 4} textAnchor="end" className="xpc__tick">
                      {fmt(axis.max)}
                    </text>
                    <text
                      x={axis.x - 10}
                      y={PAD.top + innerHeight / 2}
                      textAnchor="end"
                      className="xpc__tick"
                    >
                      {fmt((axis.min + axis.max) / 2)}
                    </text>
                    <text x={axis.x - 10} y={PAD.top + innerHeight} textAnchor="end" className="xpc__tick">
                      {fmt(axis.min)}
                    </text>
                  </>
                )}
              </g>
            )
          })}
        </svg>
        </div>

        {/* accessible axis reorder controls */}
        <div className="xpc__reorderbar" aria-label="Reorder axes">
          {axes.map((axis, i) => (
            <span key={axis.column} className="xpc__reorderitem">
              <span className="xpc__reordername">{axis.column}</span>
              <button
                type="button"
                className="xbtn xbtn--tiny"
                disabled={i === 0}
                onClick={() => moveAxis(axis.column, -1)}
                aria-label={`Move ${axis.column} left`}
              >
                ◀
              </button>
              <button
                type="button"
                className="xbtn xbtn--tiny"
                disabled={i === axes.length - 1}
                onClick={() => moveAxis(axis.column, 1)}
                aria-label={`Move ${axis.column} right`}
              >
                ▶
              </button>
            </span>
          ))}
          <span className="xpc__reorderhint">
            Drag on an axis to brush a range. Click exactly over an existing brush to remove it.
          </span>
        </div>
      </div>

      {/* legend */}
      <div className="xpc__legend" aria-hidden={colorColumn === null}>
        {colorColumn ? (
          <>
            <span className="xpc__legendtitle">Colour: {colorColumn}</span>
            {levelList.map((level, i) => (
              <span key={level} className="xpc__legenditem">
                <span
                  className="xpc__swatch"
                  style={{ background: levelColors[i % levelColors.length] }}
                />
                {level}
              </span>
            ))}
          </>
        ) : (
          <span className="xpc__legendtitle">All rows - choose a colour variable to group</span>
        )}
        {selectedIds.size > 0 && (
          <span className="xpc__legenditem xpc__legenditem--selected">
            <span className="xpc__swatch xpc__swatch--selected" />
            selected ({drawnSelected} drawn / {selectedIds.size} total)
          </span>
        )}
      </div>
      {selectedIds.size === 0 && (
        <p className="xpc__emptyhint">
          Nothing is selected yet. Drag vertically on any rail to brush a value range - selected rows
          turn copper, appear in Row evidence, and stay highlighted in the other linked plots.
        </p>
      )}
    </figure>
  )
})

function truncateName(name: string, step: number): string {
  // ~6.1px per character at the 11px mono axis font.
  const maxChars = Math.max(4, Math.floor(step / 6.1) - 1)
  return name.length <= maxChars ? name : `${name.slice(0, maxChars)}…`
}

function buildPath(
  row: SeriesResponse['rows'][number],
  order: string[],
  axes: AxisLayout[],
  yFor: (axis: AxisLayout, value: number) => number | null,
): string {
  const positions: Array<[number, number] | null> = []
  for (const axis of axes) {
    const value = row.values[axis.column]
    positions.push(
      typeof value === 'number' ? (yFor(axis, value) === null ? null : [axis.x, yFor(axis, value)!]) : null,
    )
  }
  let d = ''
  let pen = false
  for (let i = 0; i < positions.length; i++) {
    const point = positions[i]
    if (point === null) {
      pen = false
      continue
    }
    d += `${pen ? 'L' : 'M'}${point[0].toFixed(1)} ${point[1].toFixed(1)}`
    pen = true
  }
  return d
}
