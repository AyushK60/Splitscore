/**
 * Left rail: graph workspace controls.
 *
 * Dataset identity, the graph selector (server list), creation, and the
 * variable palette (search dataset columns, add observed or hypothetical
 * variables). Collapsible; becomes a drawer on small screens.
 */

import { useMemo, useState } from 'react'

import type { CausalGraphSummary } from '../api/types'
import type { CausalDraft } from './CausalLabState'

export interface VariableRailProps {
  datasetName: string
  datasetColumns: string[]
  addedColumns: Set<string>
  draft: CausalDraft
  graphs: CausalGraphSummary[]
  currentGraphId: string | null
  collapsed: boolean
  onToggleCollapsed: () => void
  onSelectGraph: (graphId: string) => void
  onNewGraph: () => void
  onDeleteGraph: () => void
  onAddColumn: (column: string) => void
  onAddHypothetical: () => void
}

export function VariableRail(props: VariableRailProps) {
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const matches = needle
      ? props.datasetColumns.filter((column) => column.toLowerCase().includes(needle))
      : props.datasetColumns
    return matches.slice(0, 40)
  }, [props.datasetColumns, query])

  if (props.collapsed) {
    return (
      <aside className="clab__rail clab__rail--collapsed" aria-label="Graph workspace controls">
        <button
          type="button"
          className="clab__rail-toggle"
          onClick={props.onToggleCollapsed}
          aria-label="Expand the graph workspace panel"
          title="Expand panel"
        >
          <span aria-hidden="true">»</span>
          <span className="visually-hidden">Expand the graph workspace panel</span>
        </button>
      </aside>
    )
  }

  return (
    <aside className="clab__rail" aria-label="Graph workspace controls">
      <div className="clab-rail__head">
        <div>
          <p className="clab-rail__eyebrow">Dataset</p>
          <p className="clab-rail__dataset" title={props.datasetName}>{props.datasetName}</p>
          <p className="clab-rail__meta">{props.datasetColumns.length} columns</p>
        </div>
        <button
          type="button"
          className="clab__rail-toggle"
          onClick={props.onToggleCollapsed}
          aria-label="Collapse the graph workspace panel"
          title="Collapse panel"
        >
          <span aria-hidden="true">«</span>
          <span className="visually-hidden">Collapse the graph workspace panel</span>
        </button>
      </div>

      <section className="clab-rail__section">
        <p className="clab-rail__eyebrow">Graphs for this dataset</p>
        {props.graphs.length === 0 ? (
          <p className="clab-note clab-note--quiet">No saved graphs yet.</p>
        ) : (
          <ul className="clab-graph-list">
            {props.graphs.map((graph) => (
              <li key={graph.graph_id}>
                <button
                  type="button"
                  className={[
                    'clab-graph-item',
                    graph.graph_id === props.currentGraphId ? 'clab-graph-item--active' : '',
                  ].join(' ')}
                  onClick={() => props.onSelectGraph(graph.graph_id)}
                  aria-current={graph.graph_id === props.currentGraphId ? 'true' : undefined}
                >
                  <span className="clab-graph-item__name">{graph.name}</span>
                  <span className="clab-graph-item__meta">
                    {graph.node_count} var{graph.node_count === 1 ? '' : 's'} ·{' '}
                    {graph.edge_count} edge{graph.edge_count === 1 ? '' : 's'} ·{' '}
                    <span className={graph.error_count ? 'clab-flag-error' : 'clab-flag-ok'}>
                      {graph.error_count ? `${graph.error_count} error${graph.error_count === 1 ? '' : 's'}` : 'valid'}
                    </span>
                    {graph.warning_count ? `, ${graph.warning_count} warning${graph.warning_count === 1 ? '' : 's'}` : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="clab-actions">
          <button type="button" className="btn btn--small" onClick={props.onNewGraph}>
            New graph
          </button>
          {props.currentGraphId ? (
            <button type="button" className="btn btn--small" onClick={props.onDeleteGraph}>
              Delete current
            </button>
          ) : null}
        </div>
      </section>

      <section className="clab-rail__section">
        <p className="clab-rail__eyebrow">Add observed variable</p>
        <input
          type="search"
          className="clab-search"
          placeholder="Search dataset columns…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search dataset columns"
        />
        <ul className="clab-column-list" aria-label="Dataset columns">
          {filtered.map((column) => {
            const added = props.addedColumns.has(column)
            return (
              <li key={column}>
                <button
                  type="button"
                  className="clab-column-item"
                  disabled={added}
                  onClick={() => props.onAddColumn(column)}
                  aria-label={`Add ${column}`}
                  title={added ? `${column} is already in the graph` : `Add ${column}`}
                >
                  <span className="clab-column-item__name">{column}</span>
                  <span className="clab-column-item__action">{added ? 'in graph' : '+ add'}</span>
                </button>
              </li>
            )
          })}
          {filtered.length === 0 ? (
            <li><p className="clab-note clab-note--quiet">No matching columns.</p></li>
          ) : null}
        </ul>
      </section>

      <section className="clab-rail__section">
        <p className="clab-rail__eyebrow">Hypothetical variable</p>
        <p className="clab-note clab-note--quiet">
          A variable you believe matters but that has no measured column - for example a suspected
          unmeasured confounder.
        </p>
        <button type="button" className="btn btn--small" onClick={props.onAddHypothetical}>
          Add hypothetical variable
        </button>
      </section>

      <p className="clab-rail__footnote">{props.draft.nodes.length} of 60 variables · {props.draft.edges.length} of 240 edges</p>
    </aside>
  )
}
