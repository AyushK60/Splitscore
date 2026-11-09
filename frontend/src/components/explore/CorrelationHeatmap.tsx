import { useEffect, useMemo, useRef, useState } from 'react'

import { exploreApi } from '../../api/client'
import type { CorrelationResponse, ExploreSchema } from '../../api/types'
import { FigureExport } from './FigureExport'

/**
 * Correlation heatmap (Pearson / Spearman).
 *
 * Every cell is one pairwise coefficient computed server-side over the full
 * population, with its own valid-pair count. Cells whose coefficient is
 * undefined (constant column, too few complete pairs) render as hatched
 * "undefined" - never as zero. The caption states the missingness policy and
 * the standing caveat: association, not causation.
 */

const MAX_CORR_COLUMNS = 10

interface Props {
  schema: ExploreSchema
  onRequestScatter: (x: string, y: string) => void
}

function coefficientColor(r: number | null): string {
  if (r === null) return 'url(#xcorr-undefined)'
  const t = Math.min(1, Math.abs(r))
  if (r > 0) {
    // paper → copper
    return `color-mix(in srgb, var(--rs-copper) ${Math.round(12 + 78 * t)}%, var(--rs-surface))`
  }
  // paper → deep teal
  return `color-mix(in srgb, var(--rs-teal) ${Math.round(12 + 78 * t)}%, var(--rs-surface))`
}

export function CorrelationHeatmap({ schema, onRequestScatter }: Props) {
  const numeric = schema.numeric_columns
  const [columns, setColumns] = useState<string[]>(() => numeric.slice(0, 8))
  const [method, setMethod] = useState<'pearson' | 'spearman'>('pearson')
  const [data, setData] = useState<CorrelationResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [focused, setFocused] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    setColumns((previous) => {
      const kept = previous.filter((c) => numeric.includes(c))
      if (kept.length >= 2) return kept
      return numeric.slice(0, 8)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema.dataset.dataset_id])

  useEffect(() => {
    if (columns.length < 2) {
      setData(null)
      return
    }
    let cancelled = false
    exploreApi
      .correlation(schema.dataset.dataset_id, columns, method)
      .then((result) => {
        if (cancelled) return
        setData(result)
        setError(null)
      })
      .catch((e) => {
        if (cancelled) return
        setData(null)
        setError(e instanceof Error ? e.message : 'Correlations could not be computed.')
      })
    return () => {
      cancelled = true
    }
  }, [schema.dataset.dataset_id, columns, method])

  const cellMap = useMemo(() => {
    const map = new Map<string, CorrelationResponse['cells'][number]>()
    for (const cell of data?.cells ?? []) {
      map.set(`${cell.x}\u0000${cell.y}`, cell)
      map.set(`${cell.y}\u0000${cell.x}`, cell)
    }
    return map
  }, [data])

  const toggle = (column: string) => {
    setColumns((previous) => {
      if (previous.includes(column)) return previous.filter((c) => c !== column)
      if (previous.length >= MAX_CORR_COLUMNS) return previous
      return [...previous, column]
    })
  }

  const focusedCell = useMemo(() => {
    if (!focused || !data) return null
    return cellMap.get(focused) ?? null
  }, [focused, data, cellMap])

  if (numeric.length < 2) {
    return (
      <p className="xw__placeholder">
        Correlation needs at least two numeric columns; this dataset has {numeric.length}.
      </p>
    )
  }

  const size = 34
  const pad = 110
  const width = pad + columns.length * size + 20
  const height = pad - 40 + columns.length * size + 30

  return (
    <figure className="xfig" data-figure="correlation">
      <figcaption className="xfig__caption">
        <span className="xfig__title">Correlation matrix - {method}</span>
        <span className="xfig__sub">
          {data
            ? `${data.population.toLocaleString('en-US')} rows · pairwise complete observations · ${data.min_pairs} pair minimum`
            : 'computing…'}
        </span>
        <FigureExport
          figureId={`correlation-${method}`}
          title={`Correlation matrix (${method}) - ${columns.join(', ')}`}
          settings={`${method} · ${columns.length} variables · pairwise complete`}
          counts={data ? `${data.population.toLocaleString('en-US')} rows · ${data.cells.length} pairs` : ''}
          notes={[
            'Correlation describes association, not causation.',
            `Each cell keeps its own valid-pair count; coefficients need at least ${data?.min_pairs ?? 3} complete pairs.`,
          ]}
          getSvg={() => svgRef.current}
        />
      </figcaption>

      <div className="xfig__controls">
        <div className="xfig__toggle" role="group" aria-label="Correlation method">
          <button
            type="button"
            className="xbtn xbtn--tiny"
            aria-pressed={method === 'pearson'}
            onClick={() => setMethod('pearson')}
          >
            Pearson
          </button>
          <button
            type="button"
            className="xbtn xbtn--tiny"
            aria-pressed={method === 'spearman'}
            onClick={() => setMethod('spearman')}
          >
            Spearman
          </button>
        </div>
        <div className="xw__chips">
          {numeric.map((column) => (
            <button
              key={column}
              type="button"
              className={`xchip${columns.includes(column) ? ' xchip--on' : ''}`}
              aria-pressed={columns.includes(column)}
              disabled={!columns.includes(column) && columns.length >= MAX_CORR_COLUMNS}
              onClick={() => toggle(column)}
            >
              {column}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="xw__ploterror" role="alert">
          {error}
        </p>
      )}

      {data && columns.length >= 2 && (
        <div className="xfig__scroll">
          <svg ref={svgRef} width={width} height={height} role="img" aria-label={`${method} correlation matrix`}>
            <defs>
              <pattern id="xcorr-undefined" width="6" height="6" patternUnits="userSpaceOnUse">
                <rect width="6" height="6" fill="var(--rs-sunken)" />
                <path d="M0 6 L6 0" stroke="var(--rs-line-strong)" strokeWidth="1" />
              </pattern>
            </defs>
            {columns.map((column, i) => (
              <g key={`label-${column}`}>
                <text
                  x={pad - 8}
                  y={i * size + size / 2 + 26}
                  textAnchor="end"
                  className="xfig__axislabel"
                >
                  {column}
                </text>
                <text
                  x={i * size + size / 2 + pad}
                  y={18}
                  textAnchor="start"
                  transform={`rotate(-40 ${i * size + size / 2 + pad} 18)`}
                  className="xfig__axislabel"
                >
                  {column}
                </text>
              </g>
            ))}
            {columns.map((x, i) =>
              columns.map((y, j) => {
                if (j < i) return null
                const cell = cellMap.get(`${x}\u0000${y}`)
                const key = `${x}\u0000${y}`
                const px = pad + j * size
                const py = i * size + 26
                const isDiagonal = i === j
                return (
                  <g
                    key={key}
                    className="xfig__cell"
                    onPointerEnter={() => setFocused(key)}
                    onClick={() => !isDiagonal && onRequestScatter(x, y)}
                    style={{ cursor: isDiagonal ? 'default' : 'pointer' }}
                  >
                    <title>
                      {isDiagonal
                        ? x
                        : cell?.coefficient === null
                          ? `${x} × ${y}: undefined (${cell?.warning ?? 'no valid pairs'})`
                          : `${x} × ${y}: r = ${cell?.coefficient?.toFixed(3)} on ${cell?.n_valid} pairs`}
                    </title>
                    <rect
                      x={px}
                      y={py}
                      width={size - 2}
                      height={size - 2}
                      rx={2}
                      fill={isDiagonal ? 'var(--rs-sunken)' : coefficientColor(cell?.coefficient ?? null)}
                      stroke="var(--rs-line)"
                    />
                    {!isDiagonal && cell?.coefficient !== null && (
                      <text
                        x={px + (size - 2) / 2}
                        y={py + (size - 2) / 2 + 3.5}
                        textAnchor="middle"
                        className="xfig__cellvalue"
                      >
                        {cell?.coefficient?.toFixed(2)}
                      </text>
                    )}
                  </g>
                )
              }),
            )}
          </svg>
          <div className="xfig__legend">
            <span>-1</span>
            <span className="xfig__ramp xfig__ramp--teal" />
            <span>0</span>
            <span className="xfig__ramp xfig__ramp--copper" />
            <span>+1</span>
            <span className="xfig__legenditem">
              <span className="xfig__undefswatch" /> undefined (constant / too few pairs)
            </span>
          </div>
        </div>
      )}

      <div className="xfig__detail" aria-live="polite">
        {focusedCell ? (
          focusedCell.coefficient === null ? (
            <p>
              <strong>{focusedCell.x} × {focusedCell.y}</strong> - undefined on{' '}
              {focusedCell.n_valid} complete pairs
              {focusedCell.warning === 'constant_x' || focusedCell.warning === 'constant_y'
                ? ' (a variable is constant, so the coefficient does not exist)'
                : focusedCell.warning === 'insufficient_pairs'
                  ? ` (fewer than ${data?.min_pairs} complete pairs)`
                  : ''}
              . Undefined is shown as undefined, never as zero.
            </p>
          ) : (
            <p>
              <strong>
                {focusedCell.x} × {focusedCell.y}
              </strong>{' '}
              - {focusedCell.method} r = {focusedCell.coefficient.toFixed(3)} on{' '}
              {focusedCell.n_valid.toLocaleString('en-US')} complete pairs (policy:{' '}
              {focusedCell.missing_policy.replace(/_/g, ' ')}). Click the cell to open the scatter.
            </p>
          )
        ) : (
          <p className="muted tiny">Hover a cell for its coefficient and valid-pair count.</p>
        )}
        <p className="xfig__note">
          Correlation describes association within this dataset. It is not evidence of a causal
          relationship, and a low correlation is not evidence that a split is safe.
        </p>
      </div>
    </figure>
  )
}
