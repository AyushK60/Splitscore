/**
 * The Causal Lab (S8B).
 *
 * One dominant graph canvas; a compact, collapsible control rail on the left;
 * a contextual inspector on the right only when something is selected. All
 * scientific authority lives in the S8A backend: the canvas edits a local
 * draft, Save/Validate send it to the real endpoints, and structured
 * validation results are rendered from the server's response — never from a
 * frontend reimplementation.
 *
 * State distinctions that are load-bearing here:
 * - draft (local, never erased by a failed save) vs. saved revision;
 * - the explicit Save button and a dirty indicator replace autosave;
 * - a 422 from the backend keeps the draft and shows its structured errors.
 */

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react'

import { ApiError, causalApi, downloadExport } from '../api/client'
import type {
  CausalAssumptionSpec,
  CausalIssue,
  CausalGraphSummary,
  CausalValidation,
} from '../api/types'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'
import {
  initialLabState,
  isDirty,
  localEdgeProblems,
  slugifyNodeId,
  causalLabReducer,
  type CausalDraft,
  type Selection,
} from './CausalLabState'
import { teachingExample } from './adapter'
import { CausalCanvas } from './CausalCanvas'
import { CausalInspector, selectionToView, type InspectorView } from './CausalInspector'
import { VariableRail } from './VariableRail'

type Props = { onNavigate: (view: ViewId) => void }

/** Rebuilds a CausalValidation from a 422 error envelope's details. */
function validationFromDetails(details: Record<string, unknown>): CausalValidation | null {
  const errors = (details?.['errors'] as CausalIssue[] | undefined) ?? null
  if (!Array.isArray(errors)) return null
  const warnings = (details?.['warnings'] as CausalIssue[] | undefined) ?? []
  const derived = (details?.['derived'] as CausalValidation['derived'] | undefined) ?? null
  return {
    ok: false,
    error_count: errors.length,
    warning_count: Array.isArray(warnings) ? warnings.length : 0,
    errors,
    warnings: Array.isArray(warnings) ? warnings : [],
    derived,
  } as CausalValidation
}

export function CausalLabView({ onNavigate }: Props) {
  const { dataset } = useApp()
  const datasetId = dataset?.dataset.dataset_id ?? null
  const [state, dispatch] = useReducer(causalLabReducer, undefined, initialLabState)
  // Latest-state mirror for the global keyboard handler, which must not be
  // re-registered on every keystroke.
  const stateRef = useRef(state)
  stateRef.current = state
  const [graphs, setGraphs] = useState<CausalGraphSummary[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [savedNote, setSavedNote] = useState<string | null>(null)
  const [railCollapsed, setRailCollapsed] = useState(false)
  const [confirmDeleteGraph, setConfirmDeleteGraph] = useState(false)
  const [connectError, setConnectError] = useState<string | null>(null)
  const [validationViewOpen, setValidationViewOpen] = useState(false)
  const fitViewRef = useRef<(() => void) | null>(null)
  const importInputRef = useRef<HTMLInputElement>(null)
  const loadedForDataset = useRef<string | null>(null)

  const dirty = isDirty(state)

  // -- server interactions -------------------------------------------------- //

  const refreshList = useCallback(async () => {
    if (!datasetId) return
    const listing = await causalApi.list(datasetId)
    setGraphs(listing.graphs)
    return listing.graphs
  }, [datasetId])

  useEffect(() => {
    if (!datasetId || loadedForDataset.current === datasetId) return
    loadedForDataset.current = datasetId
    let cancelled = false
    setBusy('Loading causal graphs')
    ;(async () => {
      try {
        const listing = await causalApi.list(datasetId)
        if (cancelled) return
        setGraphs(listing.graphs)
        if (listing.graphs.length > 0) {
          const payload = await causalApi.get(datasetId, listing.graphs[0].graph_id)
          if (cancelled) return
          dispatch({ type: 'load', payload })
        }
      } catch (caught) {
        if (!cancelled) {
          const message =
            caught instanceof ApiError
              ? caught.message
              : 'The causal graph list could not be loaded.'
          dispatch({ type: 'error', title: 'Causal Lab', message })
        }
      } finally {
        if (!cancelled) setBusy(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [datasetId])

  const save = useCallback(async (): Promise<boolean> => {
    if (!datasetId) return false
    setBusy(state.graphId ? 'Saving graph' : 'Creating graph')
    setSavedNote(null)
    try {
      const spec = {
        schema_version: '1.0.0',
        name: state.draft.name.trim() || 'Untitled causal graph',
        description: state.draft.description?.trim() ? state.draft.description.trim() : null,
        dataset_id: datasetId,
        nodes: state.draft.nodes,
        edges: state.draft.edges,
        analysis: state.draft.analysis,
        assumptions: state.draft.assumptions,
      }
      const payload = state.graphId
        ? await causalApi.update(datasetId, state.graphId, spec)
        : await causalApi.create(datasetId, spec)
      dispatch({ type: 'saved', payload })
      setSavedNote(`Saved revision ${payload.revision} · fingerprint ${payload.spec_fingerprint_sha256.slice(0, 12)}…`)
      await refreshList()
      return true
    } catch (caught) {
      if (caught instanceof ApiError) {
        const validation = validationFromDetails(caught.details)
        if (validation) {
          dispatch({ type: 'validation', validation })
          dispatch({
            type: 'validationRejected',
            issues: validation.errors,
            message: 'The backend refused this graph. Your draft is unchanged — fix the errors below.',
          })
          setValidationViewOpen(true)
        } else {
          dispatch({ type: 'error', title: 'Save failed', message: caught.message })
        }
      } else {
        dispatch({ type: 'error', title: 'Save failed', message: 'The backend could not be reached.' })
      }
      return false
    } finally {
      setBusy(null)
    }
  }, [datasetId, state.draft, state.graphId, refreshList])

  const validate = useCallback(async () => {
    if (!datasetId) return
    // The backend is the only validator. A dirty draft is saved first; a
    // rejected save already carries the structured verdict.
    if (dirty) {
      const ok = await save()
      if (!ok) return
    }
    if (!state.graphId) return
    setBusy('Validating graph')
    try {
      const result = await causalApi.validate(datasetId, state.graphId)
      dispatch({ type: 'validation', validation: result.validation })
      setValidationViewOpen(true)
      dispatch({ type: 'select', selection: null })
      setSavedNote(null)
    } catch (caught) {
      if (caught instanceof ApiError) {
        dispatch({ type: 'error', title: 'Validation failed', message: caught.message })
      } else {
        dispatch({ type: 'error', title: 'Validation failed', message: 'The backend could not be reached.' })
      }
    } finally {
      setBusy(null)
    }
  }, [datasetId, dirty, save, state.graphId])

  const selectGraph = useCallback(
    async (graphId: string) => {
      if (!datasetId) return
      if (dirty && !window.confirm('This graph has unsaved changes. Load the selected graph anyway?')) {
        return
      }
      setBusy('Loading graph')
      try {
        const payload = await causalApi.get(datasetId, graphId)
        dispatch({ type: 'load', payload })
        setSavedNote(null)
      } catch (caught) {
        dispatch({
          type: 'error',
          title: 'Could not load graph',
          message: caught instanceof ApiError ? caught.message : 'The backend could not be reached.',
        })
      } finally {
        setBusy(null)
      }
    },
    [datasetId, dirty],
  )

  const newGraph = useCallback(() => {
    if (dirty && !window.confirm('Start a new graph? Unsaved changes to the current draft are discarded.')) {
      return
    }
    dispatch({ type: 'reset', datasetId: datasetId ?? '' })
    setSavedNote(null)
  }, [datasetId, dirty])

  const deleteGraph = useCallback(async () => {
    if (!datasetId || !state.graphId) return
    setBusy('Deleting graph')
    try {
      await causalApi.delete(datasetId, state.graphId)
      await refreshList()
      dispatch({ type: 'reset', datasetId })
      setSavedNote(null)
    } catch (caught) {
      dispatch({
        type: 'error',
        title: 'Delete failed',
        message: caught instanceof ApiError ? caught.message : 'The backend could not be reached.',
      })
    } finally {
      setBusy(null)
      setConfirmDeleteGraph(false)
    }
  }, [datasetId, state.graphId, refreshList])

  const exportGraph = useCallback(() => {
    if (!datasetId || !state.graphId) return
    void downloadExport(causalApi.exportPath(datasetId, state.graphId))
  }, [datasetId, state.graphId])

  const handleImportFile = useCallback(
    async (file: File) => {
      if (!datasetId) return
      setBusy('Importing graph')
      try {
        const text =
          typeof file.text === 'function'
            ? await file.text()
            : await new Promise<string>((resolve, reject) => {
                // jsdom (tests) does not implement Blob.text(); FileReader is
                // the universally available path.
                const reader = new FileReader()
                reader.onload = () => resolve(String(reader.result))
                reader.onerror = () => reject(new Error('The file could not be read.'))
                reader.readAsText(file)
              })
        const parsed: unknown = JSON.parse(text)
        const payload = await causalApi.import(datasetId, parsed as Parameters<typeof causalApi.import>[1])
        dispatch({ type: 'load', payload })
        await refreshList()
        setSavedNote('Imported as a new graph. Review, then save to keep it.')
      } catch (caught) {
        dispatch({
          type: 'error',
          title: 'Import failed',
          message:
            caught instanceof ApiError
              ? caught.message
              : caught instanceof SyntaxError
                ? 'That file is not valid JSON.'
                : caught instanceof Error
                  ? caught.message
                  : 'The file could not be imported.',
        })
      } finally {
        setBusy(null)
      }
    },
    [datasetId, refreshList],
  )

  // -- draft edits ----------------------------------------------------------- //

  const addColumn = useCallback(
    (column: string) => {
      const taken = new Set(state.draft.nodes.map((node) => node.node_id))
      const nodeId = slugifyNodeId(column, taken)
      dispatch({
        type: 'addNode',
        node: {
          node_id: nodeId,
          label: column,
          column,
          observed: true,
          kind: 'covariate',
          description: null,
          layout: null,
        },
      })
      dispatch({ type: 'select', selection: { kind: 'node', id: nodeId } })
    },
    [state.draft.nodes],
  )

  const hypotheticalCount = useRef(0)
  const addHypothetical = useCallback(() => {
    const taken = new Set(state.draft.nodes.map((node) => node.node_id))
    hypotheticalCount.current += 1
    const nodeId = slugifyNodeId(`u_${hypotheticalCount.current}`, taken)
    dispatch({
      type: 'addNode',
      node: {
        node_id: nodeId,
        label: `Hypothetical U${hypotheticalCount.current}`,
        column: null,
        observed: false,
        kind: 'unobserved',
        description: null,
        layout: null,
      },
    })
    dispatch({ type: 'select', selection: { kind: 'node', id: nodeId } })
  }, [state.draft.nodes])

  const connectNodes = useCallback(
    (source: string, target: string) => {
      setConnectError(null)
      const problem = localEdgeProblems(state.draft, source, target)
      if (problem) {
        setConnectError(problem)
        return
      }
      dispatch({ type: 'addEdge', edge: { source, target, rationale: null, reference: null } })
    },
    [state.draft],
  )

  const handleFlowConnect = useCallback(
    (connection: { source: string | null; target: string | null }) => {
      if (!connection.source || !connection.target) return
      connectNodes(connection.source, connection.target)
    },
    [connectNodes],
  )

  const removeEdgeById = useCallback(
    (edgeId: string) => {
      const [source, target] = edgeId.split('->')
      if (source && target) dispatch({ type: 'removeEdge', source, target })
    },
    [],
  )

  const loadExample = useCallback((kind: 'chain' | 'fork' | 'collider') => {
    const example = teachingExample(kind)
    // The example lands in the draft as regular editable content — it is not a
    // second storage system and never bypasses validation.
    dispatch({ type: 'reset', datasetId: datasetId ?? '' })
    for (const node of example.nodes) dispatch({ type: 'addNode', node })
    for (const edge of example.edges) dispatch({ type: 'addEdge', edge })
    dispatch({ type: 'setAnalysis', patch: example.analysis })
    for (const assumption of example.assumptions) dispatch({ type: 'addAssumption', assumption })
    dispatch({
      type: 'setMeta',
      patch: { name: example.name, description: example.description ?? '' },
    })
  }, [datasetId])

  // -- keyboard shortcuts ---------------------------------------------------- //

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing =
        target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        if (typing) return
        event.preventDefault()
        dispatch({ type: event.shiftKey ? 'redo' : 'undo' })
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') {
        if (typing) return
        event.preventDefault()
        dispatch({ type: 'redo' })
      } else if (event.key === 'Escape') {
        if (typing) return
        dispatch({ type: 'select', selection: null })
        setValidationViewOpen(false)
      } else if (event.key === 'Delete' || event.key === 'Backspace') {
        // Canvas keyboard deletion (React Flow's own delete machinery is off).
        // Deletion cascades to connected edges and the analysis scope in the
        // reducer, and is undoable.
        if (typing) return
        const selection = stateRef.current.selected
        if (!selection || selection.kind === 'graph') return
        event.preventDefault()
        if (selection.kind === 'node') dispatch({ type: 'removeNode', nodeId: selection.id })
        else removeEdgeById(selection.id)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [removeEdgeById])

  // -- derived render data ---------------------------------------------------- //

  const issues: CausalIssue[] = state.validation
    ? [...state.validation.errors, ...state.validation.warnings]
    : []
  const structure = state.payload?.validation.derived.nodes ?? null
  const inspectorView: InspectorView | null = validationViewOpen
    ? { kind: 'validation' }
    : selectionToView(state.selected)
  const addedColumns = useMemo(
    () => new Set(state.draft.nodes.map((node) => node.column).filter((column): column is string => Boolean(column))),
    [state.draft.nodes],
  )

  const statusChip = (() => {
    if (!state.validation) {
      return { tone: 'quiet', label: 'Not validated yet' }
    }
    if (state.validation.errors.length > 0) {
      return {
        tone: 'error',
        label: `${state.validation.errors.length} blocking ${state.validation.errors.length === 1 ? 'error' : 'errors'}`,
      }
    }
    return {
      tone: 'ok',
      label: `Structurally valid DAG${state.validation.warning_count ? ` · ${state.validation.warning_count} warning${state.validation.warning_count === 1 ? '' : 's'}` : ''}`,
    }
  })()

  if (!dataset) {
    return (
      <section className="card clab-intro">
        <p className="clab-intro__eyebrow">Causal Lab</p>
        <h1>Draw assumed causal structures</h1>
        <p className="muted">
          The Causal Lab works on a loaded dataset: its variables become the graph's observed
          nodes, and every graph is saved against that dataset on the SplitScope backend.
        </p>
        <p className="muted">Load a dataset first, then return here.</p>
        <div className="clab-actions">
          <button type="button" className="btn" onClick={() => onNavigate('overview')}>
            Go to dataset setup
          </button>
        </div>
      </section>
    )
  }

  const emptyState = (
    <div className="clab-empty" data-testid="causal-empty-state">
      <p className="clab-empty__eyebrow">Synthetic teaching examples</p>
      <h2>Start your assumed structure</h2>
      <ol className="clab-empty__steps">
        <li>Add observed variables from the dataset (left panel).</li>
        <li>Draw assumed relationships between them.</li>
        <li>Choose one treatment and one outcome.</li>
        <li>Document your assumptions.</li>
        <li>Validate the structure with the backend, then save.</li>
      </ol>
      <div className="clab-empty__examples">
        {(['chain', 'fork', 'collider'] as const).map((kind) => (
          <button key={kind} type="button" className="btn btn--small" onClick={() => loadExample(kind)}>
            {kind === 'chain' ? 'Chain example' : kind === 'fork' ? 'Fork example' : 'Collider example'}
          </button>
        ))}
      </div>
      <p className="clab-note">
        The examples are synthetic teaching structures: their edges are assumed relationships for
        instruction, not relationships learned from data.
      </p>
    </div>
  )

  return (
    <section className="clab" aria-label="Causal Lab">
      <div className="clab__toolbar">
        <div className="clab__toolbar-group">
          <button
            type="button"
            className="clab__rail-toggle clab__rail-toggle--toolbar"
            onClick={() => setRailCollapsed((value) => !value)}
            aria-label={railCollapsed ? 'Show the workspace panel' : 'Hide the workspace panel'}
            title="Toggle the workspace panel"
          >
            <span aria-hidden="true">{railCollapsed ? '»' : '«'}</span>
          </button>
          <button
            type="button"
            className="btn btn--small clab-save"
            onClick={() => void save()}
            disabled={Boolean(busy) || (!dirty && Boolean(state.graphId))}
          >
            {dirty ? 'Save changes' : 'Saved'}
            {dirty ? <span className="clab-dirty-dot" aria-hidden="true" /> : null}
            <span className="visually-hidden">{dirty ? ' — unsaved changes' : ' — no unsaved changes'}</span>
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => void validate()}
            disabled={Boolean(busy) || (!dirty && !state.graphId)}
            title="Runs the backend validation engine. Unsaved changes are saved first — the backend is the only validator."
          >
            Validate
          </button>
          <span className={`clab-status clab-status--${statusChip.tone}`}>
            <button
              type="button"
              onClick={() => {
                setValidationViewOpen(true)
                dispatch({ type: 'select', selection: null })
              }}
            >
              {statusChip.label}
            </button>
          </span>
          <span className="clab-revision" aria-live="polite">
            {busy ?? (savedNote ?? (state.graphId ? `revision ${state.revision}` : 'unsaved draft'))}
          </span>
        </div>
        <div className="clab__toolbar-group">
          <button
            type="button"
            className="btn btn--small"
            onClick={() => dispatch({ type: 'undo' })}
            disabled={state.past.length === 0 || Boolean(busy)}
            title="Undo (Ctrl+Z)"
          >
            Undo
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => dispatch({ type: 'redo' })}
            disabled={state.future.length === 0 || Boolean(busy)}
            title="Redo (Ctrl+Shift+Z)"
          >
            Redo
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => fitViewRef.current?.()}
            title="Fit the graph to the canvas"
          >
            Fit view
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={exportGraph}
            disabled={!state.graphId}
            title="Download the versioned JSON export (structure and assumptions only, never dataset rows)"
          >
            Export
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => importInputRef.current?.click()}
            disabled={Boolean(busy)}
            title="Import an export file as a new graph for this dataset"
          >
            Import
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => {
              setValidationViewOpen(false)
              dispatch({ type: 'select', selection: { kind: 'graph' } })
            }}
            title="Edit the graph name, analysis scope and assumption registry"
          >
            Graph settings
          </button>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => {
              setValidationViewOpen(false)
              dispatch({ type: 'select', selection: null })
            }}
            title="Clear selection and close panels (Esc)"
          >
            Clear selection
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void handleImportFile(file)
              event.target.value = ''
            }}
            aria-hidden="true"
            tabIndex={-1}
          />
        </div>
      </div>

      {state.lastError ? (
        <div className="clab-alert" role="alert">
          <strong>{state.lastError.title}:</strong> {state.lastError.message}
          <button type="button" className="btn btn--small" onClick={() => dispatch({ type: 'clearError' })}>
            Dismiss
          </button>
        </div>
      ) : null}

      <div className={`clab__workzone${railCollapsed ? ' clab__workzone--rail-hidden' : ''}`}>
        <VariableRail
          datasetName={dataset.dataset.name}
          datasetColumns={dataset.dataset.columns}
          addedColumns={addedColumns}
          draft={state.draft}
          graphs={graphs}
          currentGraphId={state.graphId}
          collapsed={railCollapsed}
          onToggleCollapsed={() => setRailCollapsed((value) => !value)}
          onSelectGraph={(graphId) => void selectGraph(graphId)}
          onNewGraph={newGraph}
          onDeleteGraph={() => {
            if (!confirmDeleteGraph) {
              setConfirmDeleteGraph(true)
              window.setTimeout(() => setConfirmDeleteGraph(false), 6000)
              return
            }
            void deleteGraph()
          }}
          onAddColumn={addColumn}
          onAddHypothetical={addHypothetical}
        />

        <div className="clab__stage">
          <CausalCanvas
            draft={state.draft}
            /* Only blocking errors mark the canvas; warnings are listed in the
               validation panel — an amber on-canvas paint would overstate
               them. */
            issues={state.validation?.errors ?? []}
            selected={state.selected}
            onConnect={handleFlowConnect}
            onMoveNode={(nodeId, x, y) => dispatch({ type: 'moveNode', nodeId, x, y })}
            onSelect={(selection: Selection) => {
              setValidationViewOpen(false)
              dispatch({ type: 'select', selection })
            }}
            registerFitView={(fit) => {
              fitViewRef.current = fit
            }}
            emptyState={emptyState}
          />
        </div>

        {inspectorView ? (
          <CausalInspector
            view={inspectorView}
            draft={state.draft}
            issues={issues}
            payloadRevision={state.graphId ? state.revision : null}
            structure={structure}
            onPatchNode={(nodeId, patch) => dispatch({ type: 'updateNode', nodeId, patch: patch as never })}
            onPatchEdge={(source, target, patch) => dispatch({ type: 'updateEdge', source, target, patch: patch as never })}
            onPatchMeta={(patch) => dispatch({ type: 'setMeta', patch })}
            onSetAnalysis={(patch) => dispatch({ type: 'setAnalysis', patch })}
            onConnectNodes={connectNodes}
            onRemoveNode={(nodeId) => dispatch({ type: 'removeNode', nodeId })}
            onRemoveEdge={(source, target) => dispatch({ type: 'removeEdge', source, target })}
            onAddAssumption={(category) => {
              const index = state.draft.assumptions.length + 1
              dispatch({
                type: 'addAssumption',
                assumption: {
                  assumption_id: `asmp-note-${index}-${Math.random().toString(36).slice(2, 8)}`,
                  category: category as CausalAssumptionSpec['category'],
                  status: 'not_assessed',
                  source: 'user',
                  rationale: null,
                },
              })
            }}
            onPatchAssumption={(id, patch) => dispatch({ type: 'updateAssumption', assumptionId: id, patch: patch as never })}
            onRemoveAssumption={(id) => dispatch({ type: 'removeAssumption', assumptionId: id })}
            onSelect={(selection) => {
              setValidationViewOpen(false)
              dispatch({ type: 'select', selection })
            }}
            localError={connectError}
          />
        ) : null}
      </div>

      <p className="clab-scope-note">
        A structurally valid DAG is not a scientifically justified causal model: validation checks
        form, not truth. No causal effect is estimated anywhere in this workspace.
      </p>
    </section>
  )
}

export type { CausalDraft }
