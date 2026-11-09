import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { ApiError, exploreApi } from '../api/client'
import type { BrushPredicate, ExploreSchema } from '../api/types'
import { useApp } from '../state/AppState'

/**
 * The Visual Explorer's shared state: the variable schema of the current
 * dataset and the ONE authoritative selection engine.
 *
 * Selection is a list of brush predicates evaluated by the backend against
 * the whole dataset, returning exact counts and immutable row ids. Charts
 * never keep private filters: brushing anywhere calls `applyPredicates`, and
 * every view reads the same `selection`. That guarantees the PC brush, the
 * scatter highlight, the distribution overlay and the row inspector can never
 * disagree about which observations are active.
 *
 * The engine distinguishes (mirroring the backend payload):
 *  - `population` - every row of the dataset;
 *  - `predicates` - the active brushes (a filter definition, not an id list);
 *  - `selection.totalSelected` - the exact number of rows passing them;
 *  - `selection.ids` - those rows' immutable ids (capped for highlighting).
 */

export interface SelectionState {
  predicates: BrushPredicate[]
  totalSelected: number
  ids: Set<string>
  idsTruncated: boolean
  status: 'idle' | 'computing' | 'ready' | 'error'
  error: string | null
}

export const EMPTY_SELECTION: SelectionState = {
  predicates: [],
  totalSelected: 0,
  ids: new Set(),
  idsTruncated: false,
  status: 'idle',
  error: null,
}

/** Pause after the last brush movement before asking the server to resolve ids. */
const SELECTION_DEBOUNCE_MS = 220

interface ExploreContextValue {
  schema: ExploreSchema | null
  schemaError: string | null
  colorColumn: string | null
  setColorColumn: (column: string | null) => void
  selection: SelectionState
  applyPredicates: (predicates: BrushPredicate[]) => void
  clearSelection: () => void
  highlightedId: string | null
  setHighlightedId: (id: string | null) => void
}

const ExploreContext = createContext<ExploreContextValue | null>(null)

export function ExploreProvider({ children }: { children: ReactNode }) {
  const { dataset } = useApp()
  const datasetId = dataset?.dataset.dataset_id ?? null

  const [schema, setSchema] = useState<ExploreSchema | null>(null)
  const [schemaError, setSchemaError] = useState<string | null>(null)
  const [colorColumn, setColorColumn] = useState<string | null>(null)
  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)

  const selectionSeq = useRef(0)
  const selectionTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingPredicates = useRef<BrushPredicate[]>([])

  // A new dataset invalidates everything the explorer holds: schema, colour
  // choice and above all the selection - a brush computed for one dataset must
  // never highlight rows of another.
  useEffect(() => {
    selectionSeq.current += 1
    if (selectionTimer.current) clearTimeout(selectionTimer.current)
    setSchema(null)
    setSchemaError(null)
    setColorColumn(null)
    setSelection(EMPTY_SELECTION)
    setHighlightedId(null)
    if (!datasetId) return
    let cancelled = false
    exploreApi
      .schema(datasetId)
      .then((next) => {
        if (cancelled) return
        setSchema(next)
        setColorColumn(next.suggested_color_column)
      })
      .catch((error) => {
        if (cancelled) return
        setSchemaError(
          error instanceof ApiError ? error.message : 'The explorer schema could not be loaded.',
        )
      })
    return () => {
      cancelled = true
    }
  }, [datasetId])

  const cancelledOrStale = useCallback(
    (seq: number) => seq !== selectionSeq.current,
    // selectionSeq is a ref, so the check is stable for the provider's life.
    [],
  )

  const runSelection = useCallback(
    (predicates: BrushPredicate[]) => {
      if (!datasetId) return
      const seq = ++selectionSeq.current
      setSelection((previous) => ({
        ...previous,
        predicates,
        status: 'computing',
        error: null,
      }))
      exploreApi
        .selection(datasetId, predicates)
        .then((result) => {
          if (cancelledOrStale(seq)) return
          setSelection({
            predicates,
            totalSelected: result.total_selected,
            ids: new Set(result.row_ids),
            idsTruncated: result.ids_truncated,
            status: 'ready',
            error: null,
          })
        })
        .catch((error) => {
          if (cancelledOrStale(seq)) return
          setSelection((previous) => ({
            ...previous,
            status: 'error',
            error:
              error instanceof ApiError
                ? error.message
                : 'The selection could not be resolved against the dataset.',
          }))
        })
    },
    [datasetId, cancelledOrStale],
  )

  const applyPredicates = useCallback(
    (predicates: BrushPredicate[]) => {
      pendingPredicates.current = predicates
      if (selectionTimer.current) clearTimeout(selectionTimer.current)
      if (predicates.length === 0) {
        selectionSeq.current += 1
        setSelection(EMPTY_SELECTION)
        return
      }
      selectionTimer.current = setTimeout(() => {
        runSelection(pendingPredicates.current)
      }, SELECTION_DEBOUNCE_MS)
    },
    [runSelection],
  )

  const clearSelection = useCallback(() => {
    if (selectionTimer.current) clearTimeout(selectionTimer.current)
    selectionSeq.current += 1
    setSelection(EMPTY_SELECTION)
  }, [])

  useEffect(
    () => () => {
      if (selectionTimer.current) clearTimeout(selectionTimer.current)
    },
    [],
  )

  const value = useMemo<ExploreContextValue>(
    () => ({
      schema,
      schemaError,
      colorColumn,
      setColorColumn,
      selection,
      applyPredicates,
      clearSelection,
      highlightedId,
      setHighlightedId,
    }),
    [schema, schemaError, colorColumn, selection, applyPredicates, clearSelection, highlightedId],
  )

  return <ExploreContext.Provider value={value}>{children}</ExploreContext.Provider>
}

export function useExplore(): ExploreContextValue {
  const context = useContext(ExploreContext)
  if (context === null) {
    throw new Error('useExplore must be used inside <ExploreProvider>')
  }
  return context
}
