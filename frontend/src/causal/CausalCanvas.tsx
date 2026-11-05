/**
 * The causal graph canvas.
 *
 * React Flow is configured as a *derived* view over the draft: nodes and edges
 * are computed from the draft spec, and every interaction is reported back to
 * the reducer. Nothing is stored in React Flow that the draft does not also
 * hold, so a reload or an undo can never desync the canvas from the science.
 *
 * Selection is owned by the application, not by React Flow: RF's internal
 * selection state fires empty-selection events whenever its store updates,
 * which would clear a 'graph' selection and can loop against a controlled
 * draft. Clicks are routed through onNodeClick/onEdgeClick/onPaneClick and the
 * selected classes are driven purely by the draft's `selected` state. RF's own
 * selection and delete machinery is therefore disabled; deletion is handled by
 * the view's keyboard handler with the same confirmation rules as the
 * inspector.
 */

import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  MarkerType,
  type Connection,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
  useReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useEffect, useMemo } from 'react'

import type { CausalIssue, CausalNodeKind } from '../api/types'
import type { CausalDraft, Selection } from './CausalLabState'
import { issueIndex, toFlowEdges, toFlowNodes, type CausalEdgeData, type VariableNodeData } from './adapter'

const KIND_CHIP: Record<CausalNodeKind, string> = {
  treatment: 'treatment',
  outcome: 'outcome',
  covariate: 'covariate',
  mediator: 'mediator?',
  effect_modifier: 'modifier?',
  unobserved: 'unobserved',
}

/** Flow view-model types: the v12 generics take the full node/edge type. */
type VariableFlowNode = Node<VariableNodeData, 'variable'>
type CausalFlowEdge = Edge<CausalEdgeData, 'causal'>

function VariableNode({ data, id }: NodeProps<VariableFlowNode>) {
  const chip = KIND_CHIP[data.kind]
  return (
    <div
      className={[
        'cnode',
        data.isSelected ? 'cnode--selected' : '',
        data.isTreatment ? 'cnode--treatment' : '',
        data.isOutcome ? 'cnode--outcome' : '',
        data.hasIssue ? 'cnode--issue' : '',
        data.observed ? '' : 'cnode--unobserved',
      ].join(' ')}
      data-node-id={id}
    >
      <span className="cnode__bar" aria-hidden="true" />
      <div className="cnode__body">
        <p className="cnode__label">{data.label}</p>
        <p className="cnode__meta">
          {data.isTreatment ? <span className="cnode__tag cnode__tag--treatment">treatment</span> : null}
          {data.isOutcome ? <span className="cnode__tag cnode__tag--outcome">outcome</span> : null}
          {data.column ? (
            <span className="cnode__column">{data.column}</span>
          ) : (
            <span className="cnode__column cnode__column--none">no column</span>
          )}
          {!data.observed ? <span className="cnode__tag">hypothetical</span> : null}
          <span className="cnode__kind">{chip}</span>
        </p>
      </div>
      {/* Connection handles: incoming edges attach left, outgoing right. */}
      <Handle type="target" position={Position.Left} className="cnode__handle" isConnectable />
      <Handle type="source" position={Position.Right} className="cnode__handle" isConnectable />
    </div>
  )
}

function CausalEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  markerEnd,
}: EdgeProps<CausalFlowEdge>) {
  const edgePath = useMemo(() => {
    // A gentle vertical bow keeps multiple edges between neighbouring nodes
    // legible without overlapping their labels.
    const mx = (sourceX + targetX) / 2
    const my = (sourceY + targetY) / 2
    return `M ${sourceX} ${sourceY} Q ${mx} ${my - 14} ${targetX} ${targetY}`
  }, [sourceX, sourceY, targetX, targetY])

  const selected = data?.isSelected ?? false
  return (
    <g className={selected ? 'cedge--selected' : data?.hasIssue ? 'cedge--issue' : undefined}>
      {/* Invisible wide path: the click target. React Flow's onEdgeClick
          handles the event on the wrapping <g>. */}
      <path
        className="cedge-interaction"
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={22}
        data-edge-id={id}
      />
      <path
        className={selected ? 'cedge cedge--selected' : 'cedge'}
        d={edgePath}
        fill="none"
        markerEnd={markerEnd}
        pointerEvents="none"
      />
    </g>
  )
}

const NODE_TYPES = { variable: VariableNode }
const EDGE_TYPES = { causal: CausalEdge }
const ARROW = { type: MarkerType.ArrowClosed, width: 16, height: 16 } as const

export interface CausalCanvasProps {
  draft: CausalDraft
  issues: CausalIssue[]
  selected: Selection
  onConnect: (connection: Connection) => void
  onMoveNode: (nodeId: string, x: number, y: number) => void
  onSelect: (selection: Selection) => void
  /** Registers the provider's fit-view so the toolbar can trigger it. */
  registerFitView: (fit: (() => void) | null) => void
  emptyState?: React.ReactNode
}

function CanvasInner(props: CausalCanvasProps) {
  const { byNode, edgeIndexes } = useMemo(() => issueIndex(props.issues), [props.issues])
  const nodes = useMemo(
    () =>
      toFlowNodes(
        props.draft,
        byNode,
        props.selected?.kind === 'node' ? props.selected.id : null,
      ),
    [props.draft, props.selected, byNode],
  )
  const edges = useMemo(
    () =>
      toFlowEdges(
        props.draft,
        edgeIndexes,
        props.selected?.kind === 'edge' ? props.selected.id : null,
      ),
    [props.draft, props.selected, edgeIndexes],
  )
  const nodeCount = props.draft.nodes.length

  const { fitView } = useReactFlow()
  const { registerFitView } = props
  useEffect(() => {
    registerFitView(fitView)
    return () => registerFitView(null)
  }, [fitView, registerFitView])

  // The `fitView` prop only runs at mount. Refit after the node population
  // settles so nothing sits outside the viewport. The fit is debounced because
  // a fit issued in the same tick the node was added runs before React Flow
  // has measured the node's dimensions — it would fit the *previous* graph and
  // strand the newest node off-canvas.
  useEffect(() => {
    if (nodeCount === 0) return
    const timer = window.setTimeout(() => fitView({ padding: 0.28, minZoom: 0.55 }), 120)
    return () => window.clearTimeout(timer)
  }, [nodeCount, fitView])

  return (
    <div className="clab__canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges.map((edge) => ({ ...edge, markerEnd: ARROW }))}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onConnect={props.onConnect}
        onNodeDragStop={(_, node) => props.onMoveNode(node.id, node.position.x, node.position.y)}
        onNodeClick={(_, node) => props.onSelect({ kind: 'node', id: node.id })}
        onEdgeClick={(_, edge) => props.onSelect({ kind: 'edge', id: edge.id })}
        onPaneClick={() => props.onSelect(null)}
        elementsSelectable={false}
        deleteKeyCode={null}
        minZoom={0.2}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
        className="clab__flow"
        fitView
        fitViewOptions={{ padding: 0.28, minZoom: 0.55 }}
      >
        <Background variant={BackgroundVariant.Dots} gap={26} size={1.4} color="var(--line-strong)" />
        <Controls showInteractive={false} position="bottom-right" className="clab__controls" />
        {nodeCount > 10 ? (
          <MiniMap pannable zoomable className="clab__minimap" nodeStrokeWidth={2} />
        ) : null}
      </ReactFlow>
      {nodeCount === 0 && props.emptyState ? props.emptyState : null}
    </div>
  )
}

export function CausalCanvas(props: CausalCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  )
}
