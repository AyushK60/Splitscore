import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { exploreApi } from '../api/client'
import type { SeriesResponse } from '../api/types'
import { CorrelationHeatmap } from '../components/explore/CorrelationHeatmap'
import { Distributions } from '../components/explore/Distributions'
import { MissingnessView } from '../components/explore/MissingnessView'
import { ParallelCoordinates } from '../components/explore/ParallelCoordinates'
import { RowEvidence } from '../components/explore/RowEvidence'
import { SimilarityExplorer } from '../components/explore/SimilarityExplorer'
import { ScatterFocus } from '../components/explore/ScatterFocus'
import { ScatterMatrix } from '../components/explore/ScatterMatrix'
import { useExplore } from '../explore/ExploreState'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'

/**
 * The Scientific Visual Explorer.
 *
 * One dataset, one shared selection, several coordinated views. The layout is
 * deliberately a workbench, not a dashboard: research controls in one band, a
 * large plot canvas that gets the space serious analysis needs, and a
 * permanent row-evidence inspector that keeps every mark traceable to
 * immutable row ids. Plot modes are tabs over the same canvas - every mode
 * reads and writes the same selection.
 */

const MAX_AXES = 12
const DEFAULT_AXIS_COUNT = 8
const SERIES_DEBOUNCE_MS = 160

type PlotTab = 'coordinates' | 'correlation' | 'scatter' | 'matrix' | 'distribution' | 'missingness' | 'similarity'

const TABS: Array<{ id: PlotTab; label: string }> = [
  { id: 'coordinates', label: 'Parallel coordinates' },
  { id: 'correlation', label: 'Correlations' },
  { id: 'scatter', label: 'Scatter' },
  { id: 'matrix', label: 'Scatter matrix' },
  { id: 'distribution', label: 'Distributions' },
  { id: 'missingness', label: 'Missingness' },
  { id: 'similarity', label: 'Split similarity' },
]

type Props = { onNavigate: (view: ViewId) => void }

export function ExploreView(_props: Props) {
  const { dataset, roles } = useApp()
  const { schema, schemaError, colorColumn, setColorColumn, selection, applyPredicates, clearSelection } =
    useExplore()

  const [axes, setAxes] = useState<string[]>([])
  const [series, setSeries] = useState<SeriesResponse | null>(null)
  const [seriesError, setSeriesError] = useState<string | null>(null)
  const [focusMode, setFocusMode] = useState(false)
  const [tab, setTab] = useState<PlotTab>('coordinates')
  const [scatterX, setScatterX] = useState('')
  const [scatterY, setScatterY] = useState('')
  const seriesSeq = useRef(0)

  const numericColumns = schema?.numeric_columns ?? []

  // Sensible default axes: up to DEFAULT_AXIS_COUNT numeric columns, first load.
  useEffect(() => {
    if (!schema) return
    setAxes((previous) => {
      if (previous.length > 0) {
        const kept = previous.filter((c) => numericColumns.includes(c))
        return kept.length > 0 ? kept : numericColumns.slice(0, DEFAULT_AXIS_COUNT)
      }
      return numericColumns.slice(0, DEFAULT_AXIS_COUNT)
    })
    setScatterX((previous) => (numericColumns.includes(previous) ? previous : numericColumns[0] ?? ''))
    setScatterY((previous) => (numericColumns.includes(previous) ? previous : numericColumns[1] ?? ''))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema?.dataset.dataset_id])

  const openPair = useCallback((x: string, y: string) => {
    setScatterX(x)
    setScatterY(y)
    setTab('scatter')
  }, [])

  const predicates = selection.predicates

  // Point-level data for the drawn sample. Re-fetched when the axes, the
  // colour grouping or the active predicates change; the backend samples the
  // filtered population so brushing reshapes what is drawn, not just what is
  // highlighted.
  useEffect(() => {
    if (!schema || axes.length === 0) {
      setSeries(null)
      return
    }
    const datasetId = schema.dataset.dataset_id
    const seq = ++seriesSeq.current
    const timer = setTimeout(() => {
      const columns = colorColumn && !axes.includes(colorColumn) ? [...axes, colorColumn] : axes
      exploreApi
        .series(datasetId, {
          columns,
          max_rows: 1200,
          filters: predicates.filter((p) => p.kind === 'range' || p.kind === 'values'),
        })
        .then((result) => {
          if (seq !== seriesSeq.current) return
          setSeries(result)
          setSeriesError(null)
        })
        .catch((error) => {
          if (seq !== seriesSeq.current) return
          setSeries(null)
          setSeriesError(error instanceof Error ? error.message : 'The plot data could not be loaded.')
        })
    }, SERIES_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [schema, axes, colorColumn, predicates])

  const colorLevels = useMemo(() => {
    if (!schema || !colorColumn) return []
    const column = schema.columns.find((c) => c.name === colorColumn)
    return (column?.text?.top_levels ?? []).map((l) => l.value).slice(0, 8)
  }, [schema, colorColumn])

  const toggleAxis = useCallback((column: string) => {
    setAxes((previous) =>
      previous.includes(column)
        ? previous.filter((c) => c !== column)
        : previous.length >= MAX_AXES
          ? previous
          : [...previous, column],
    )
  }, [])

  if (!dataset) {
    return (
      <div className="rs xw">
        <p className="rs-eyebrow">Visual explorer</p>
        <h1 className="rs-h1">Nothing loaded yet</h1>
        <p className="xw__empty">
          The explorer charts the dataset currently in memory. Load one of the bundled synthetic
          demonstrations or upload a CSV on the Start page, then return here.
        </p>
        <p>
          <button type="button" className="btn btn--primary" onClick={() => _props.onNavigate('overview')}>
            Go to Start
          </button>
        </p>
      </div>
    )
  }

  const shortFingerprint = dataset.dataset.fingerprint_sha256.slice(0, 12)

  return (
    <div className="rs xw">
      <header className="xw__header">
        <div>
          <p className="rs-eyebrow">Visual explorer</p>
          <h1 className="rs-h1">Explore the loaded dataset</h1>
        </div>
        <div className="xw__identity" aria-label="Dataset identity">
          <span className="xw__identityname">{dataset.dataset.name}</span>
          <span className="xw__identitymeta">
            {dataset.dataset.row_count.toLocaleString('en-US')} rows × {dataset.dataset.column_count} columns
          </span>
          <span className="xw__identitymeta" title={dataset.dataset.fingerprint_sha256}>
            sha256:{shortFingerprint}…
          </span>
          <span className={`xw__badge${dataset.dataset.source === 'demo' ? ' xw__badge--demo' : ''}`}>
            {dataset.dataset.source === 'demo' ? 'bundled synthetic demo' : 'uploaded file'}
          </span>
        </div>
      </header>

      {schemaError && (
        <div className="callout callout--danger" role="alert">
          <p className="callout__title">Explorer could not read this dataset</p>
          <p style={{ margin: 0 }}>{schemaError}</p>
        </div>
      )}

      <section className="xw__controls" aria-label="Research controls">
        <div className="xw__controlgroup xw__controlgroup--axes">
          <div className="xw__controlhead">
            <span className="xw__controllabel">Axes - numeric variables</span>
            <span className="xw__controlmeta">
              {axes.length} of {numericColumns.length} selected · max {MAX_AXES}
            </span>
          </div>
          <div className="xw__chips">
            {numericColumns.map((column) => (
              <button
                key={column}
                type="button"
                className={`xchip${axes.includes(column) ? ' xchip--on' : ''}`}
                aria-pressed={axes.includes(column)}
                disabled={!axes.includes(column) && axes.length >= MAX_AXES}
                onClick={() => toggleAxis(column)}
              >
                {column}
              </button>
            ))}
            {numericColumns.length === 0 && (
              <span className="tiny muted">No numeric columns in this dataset.</span>
            )}
          </div>
        </div>

        <div className="xw__controlgroup">
          <span className="xw__controllabel">Colour grouping</span>
          <select
            className="xselect"
            value={colorColumn ?? ''}
            onChange={(event) => setColorColumn(event.target.value || null)}
            aria-label="Colour grouping variable"
          >
            <option value="">(none - all rows one colour)</option>
            {(schema?.color_candidates ?? []).map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
          <span className="xw__controlmeta">low-cardinality columns only, so legends stay readable</span>
        </div>

        <div className="xw__controlgroup">
          <span className="xw__controllabel">Active population</span>
          <p className="xw__popcount">
            {selection.status === 'ready' ? (
              <>
                <strong>{selection.totalSelected.toLocaleString('en-US')}</strong> selected of{' '}
                {schema?.row_count.toLocaleString('en-US') ?? '—'}
              </>
            ) : (
              <>{schema?.row_count.toLocaleString('en-US') ?? '—'} rows (no filters)</>
            )}
          </p>
          {roles.split && (
            <span className="xw__controlmeta">
              split column {roles.split}
              {roles.split_train_value && roles.split_test_value
                ? ` (${roles.split_train_value} / ${roles.split_test_value})`
                : ''}
            </span>
          )}
          <button
            type="button"
            className="xbtn"
            disabled={selection.predicates.length === 0}
            onClick={clearSelection}
          >
            Clear selection
          </button>
        </div>

        <div className="xw__controlgroup">
          <span className="xw__controllabel">Canvas</span>
          <button type="button" className="xbtn" aria-pressed={focusMode} onClick={() => setFocusMode((f) => !f)}>
            {focusMode ? 'Show row evidence' : 'Focus the plot'}
          </button>
          <span className="xw__controlmeta">
            {focusMode
              ? 'the plot uses the full width; the inspector is collapsed'
              : 'inspector visible beside the plot'}
          </span>
        </div>
      </section>

      {seriesError && (
        <p className="xw__ploterror" role="alert">
          {seriesError}
        </p>
      )}

      <nav className="xw__tabs" aria-label="Plot modes">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            className={`xtab${tab === entry.id ? ' xtab--on' : ''}`}
            aria-current={tab === entry.id ? 'true' : undefined}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </nav>

      <div className={`xw__body${focusMode ? ' xw__body--focus' : ''}`}>
        <div className="xw__canvas">
          {tab === 'coordinates' && (
            <>
              {series ? (
                <ParallelCoordinates
                  series={series}
                  colorColumn={colorColumn}
                  colorLevels={colorLevels}
                  selectedIds={selection.status === 'ready' ? selection.ids : new Set()}
                  predicates={predicates}
                  onPredicates={applyPredicates}
                  onHoverRow={() => {}}
                  resizeKey={focusMode ? 'focus' : 'split'}
                />
              ) : (
                <div className="xw__placeholder">
                  {axes.length === 0
                    ? 'Choose at least one numeric variable to draw the parallel-coordinates canvas.'
                    : 'Preparing the plot from the loaded dataset…'}
                </div>
              )}
            </>
          )}
          {tab === 'correlation' && schema && (
            <CorrelationHeatmap schema={schema} onRequestScatter={openPair} />
          )}
          {tab === 'scatter' && schema && (
            <ScatterFocus
              schema={schema}
              x={scatterX}
              y={scatterY}
              onAxisChange={(axis, column) =>
                axis === 'x' ? setScatterX(column) : setScatterY(column)
              }
              onPredicates={applyPredicates}
              predicates={predicates}
              selectedIds={selection.status === 'ready' ? selection.ids : new Set()}
              colorColumn={colorColumn}
              colorLevels={colorLevels}
            />
          )}
          {tab === 'matrix' && schema && (
            <ScatterMatrix
              schema={schema}
              selectedIds={selection.status === 'ready' ? selection.ids : new Set()}
              colorColumn={colorColumn}
              colorLevels={colorLevels}
              onOpenPair={openPair}
            />
          )}
          {tab === 'distribution' && schema && (
            <Distributions
              schema={schema}
              predicates={predicates}
              selectionActive={selection.status === 'ready' && selection.predicates.length > 0}
            />
          )}
          {tab === 'missingness' && schema && (
            <MissingnessView
              datasetId={schema.dataset.dataset_id}
              predicates={predicates}
              selectionActive={selection.status === 'ready' && selection.predicates.length > 0}
              groupCandidates={schema.color_candidates}
            />
          )}
          {tab === 'similarity' && schema && <SimilarityExplorer schema={schema} />}
        </div>
        {!focusMode && (
          <aside className="xw__inspector">
            <RowEvidence />
          </aside>
        )}
      </div>
    </div>
  )
}
