/**
 * HeroScene — the single dominant scientific illustration on the landing page.
 *
 * Composition (one scene, not a collage of charts): a conceptual variable
 * network at the top, two record columns separated by a split boundary, and a
 * detected cross-split duplicate that links a training row to a testing row.
 *
 * Everything drawn here is illustrative and labelled as synthetic/conceptual:
 * it is decorative storytelling about what the auditor looks for, never a
 * computed result. The animation communicates one real flow — a scan pass that
 * finds information shared across the boundary.
 *
 * Motion: entrance reveals run once; the scan pass and the pair pulse loop
 * quietly; both pause when the figure scrolls off screen, and every animation
 * collapses to a clean static composition under `prefers-reduced-motion`.
 */
import { useEffect, useRef, useState } from 'react'

const ROWS = 9
const ROW_TOP = 226
const ROW_H = 16
const ROW_STEP = 24
const TRAIN_X = 64
const TEST_X = 384
const COL_W = 212

const HIGHLIGHT = { train: 3, test: 5 }

/** Deterministic per-row fill so the ledger reads as data, not as a pattern block. */
function rowOpacity(index: number): number {
  return index % 3 === 1 ? 0.09 : index % 3 === 2 ? 0.05 : 0.07
}

function rows(x: number, side: 'train' | 'test') {
  const items = []
  for (let i = 0; i < ROWS; i += 1) {
    const y = ROW_TOP + i * ROW_STEP
    const shared = i === HIGHLIGHT[side]
    items.push(
      <g key={`${side}-${i}`}>
        <rect
          x={x}
          y={y}
          width={COL_W}
          height={ROW_H}
          rx={3}
          className={shared ? 'hs-row hs-row--hit' : 'hs-row'}
          fillOpacity={shared ? undefined : rowOpacity(i)}
        />
        {[1, 2, 3].map((cell) => (
          <line
            key={cell}
            x1={x + (COL_W / 4) * cell}
            y1={y + 3}
            x2={x + (COL_W / 4) * cell}
            y2={y + ROW_H - 3}
            className="hs-cell-line"
          />
        ))}
      </g>,
    )
  }
  return items
}

const NODES = [
  { x: 96, y: 112, label: 'f_tenure', target: false },
  { x: 222, y: 84, label: 'f_plan', target: false },
  { x: 334, y: 140, label: 'f_region', target: false },
  { x: 446, y: 90, label: 'f_tickets', target: false },
  { x: 556, y: 134, label: 'target', target: true },
]

const NODE_EDGES: Array<[number, number]> = [
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 4],
  [1, 3],
]

/** Variables reaching down into the records they describe. */
const DROP_LINKS = [
  { from: 0, to: 170 },
  { from: 2, to: 250 },
  { from: 2, to: 412 },
  { from: 4, to: 500 },
]

export function HeroScene() {
  const figureRef = useRef<HTMLElement>(null)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    const node = figureRef.current
    if (!node || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => setPaused(!entries.some((entry) => entry.isIntersecting)),
      { threshold: 0.05 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const trainHitY = ROW_TOP + HIGHLIGHT.train * ROW_STEP + ROW_H /2
  const testHitY = ROW_TOP + HIGHLIGHT.test * ROW_STEP + ROW_H / 2
  const arc = `M${TRAIN_X + COL_W},${trainHitY} C${TRAIN_X + COL_W + 44},${trainHitY} ${
    TEST_X - 44
  },${testHitY} ${TEST_X},${testHitY}`

  return (
    <figure className={`lp-hero__figure${paused ? ' is-paused' : ''}`} ref={figureRef}>
      <svg
        className="hs-scene"
        viewBox="0 0 660 504"
        role="img"
        aria-labelledby="hs-title hs-desc"
        preserveAspectRatio="xMidYMid meet"
      >
        <title id="hs-title">
          Conceptual audit field: variables, training and testing records, and one detected
          cross-split duplicate
        </title>
        <desc id="hs-desc">
          A synthetic illustration. Five variable nodes connect down into two columns of records
          separated by a split boundary, labelled train and test. A highlighted training row and a
          highlighted testing row are joined by an arc across the boundary, annotated as an
          identical feature vector found on both sides. The scene is illustrative synthetic data,
          not a computed analysis result.
        </desc>

        <defs>
          <radialGradient id="hs-vignette" cx="46%" cy="30%" r="82%">
            <stop offset="0%" stopColor="#0d2637" />
            <stop offset="100%" stopColor="#07121f" />
          </radialGradient>
          <pattern id="hs-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M24 0H0v24" fill="none" stroke="#7fd3e8" strokeOpacity="0.06" strokeWidth="1" />
          </pattern>
          <linearGradient id="hs-scan" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#49c6dc" stopOpacity="0" />
            <stop offset="45%" stopColor="#49c6dc" stopOpacity="0.28" />
            <stop offset="55%" stopColor="#49c6dc" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#49c6dc" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="hs-scan-v" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#49c6dc" stopOpacity="0" />
            <stop offset="50%" stopColor="#49c6dc" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#49c6dc" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Frame + microgrid */}
        <rect x="0.5" y="0.5" width="659" height="503" rx="14" fill="url(#hs-vignette)" />
        <rect x="0.5" y="0.5" width="659" height="503" rx="14" fill="url(#hs-grid)" />
        <rect
          x="0.5"
          y="0.5"
          width="659"
          height="503"
          rx="14"
          fill="none"
          stroke="#7fd3e8"
          strokeOpacity="0.22"
        />

        {/* Scene header */}
        <g className="hs-in" style={{ animationDelay: '60ms' }}>
          <text className="hs-header" x="24" y="36">
            SPLITSCOPE · AUDIT FIELD
          </text>
          <g>
            <rect x="474" y="20" width="162" height="22" rx="11" className="hs-pill" />
            <text className="hs-pill-text" x="555" y="35" textAnchor="middle">
              SYNTHETIC · CONCEPTUAL
            </text>
          </g>
        </g>

        {/* Conceptual variable network */}
        <g className="hs-in" style={{ animationDelay: '180ms' }}>
          {NODE_EDGES.map(([a, b]) => (
            <line
              key={`${a}-${b}`}
              x1={NODES[a].x}
              y1={NODES[a].y}
              x2={NODES[b].x}
              y2={NODES[b].y}
              className="hs-edge"
            />
          ))}
          {DROP_LINKS.map(({ from, to }) => (
            <line
              key={to}
              x1={NODES[from].x}
              y1={NODES[from].y + 14}
              x2={to}
              y2={206}
              className="hs-drop"
            />
          ))}
          {NODES.map((node) => (
            <g key={node.label} className={node.target ? 'hs-node hs-node--target' : 'hs-node'}>
              <circle cx={node.x} cy={node.y} r="14" className="hs-node__ring" />
              <circle cx={node.x} cy={node.y} r="4.5" className="hs-node__core" />
              <text className="hs-node__label" x={node.x} y={node.y + 30} textAnchor="middle">
                {node.label}
              </text>
            </g>
          ))}
        </g>

        {/* Split boundary */}
        <g className="hs-in" style={{ animationDelay: '300ms' }}>
          <line x1="330" y1="196" x2="330" y2="442" className="hs-boundary" />
          <text className="hs-micro hs-boundary-label" x="330" y="212" textAnchor="middle">
            SPLIT BOUNDARY
          </text>
        </g>

        {/* Record columns */}
        <g className="hs-in" style={{ animationDelay: '360ms' }}>
          <rect x={TRAIN_X} y="202" width="9" height="9" rx="2" className="hs-swatch hs-swatch--train" />
          <text className="hs-col-label" x={TRAIN_X + 16} y="211">
            TRAIN · 192 rows
          </text>
          <rect x={TEST_X} y="202" width="9" height="9" rx="2" className="hs-swatch hs-swatch--test" />
          <text className="hs-col-label" x={TEST_X + 16} y="211">
            TEST · 48 rows
          </text>
          {rows(TRAIN_X, 'train')}
          {rows(TEST_X, 'test')}
        </g>

        {/* Scan pass — the audit reading both sides of the boundary */}
        <rect className="hs-scan-band" x="48" y="212" width="564" height="34" fill="url(#hs-scan)" />
        <rect className="hs-scan-line" x="48" y="212" width="564" height="2" fill="url(#hs-scan-v)" />

        {/* The detected pair */}
        <g className="hs-in" style={{ animationDelay: '520ms' }}>
          <rect
            x={TRAIN_X - 5}
            y={ROW_TOP + HIGHLIGHT.train * ROW_STEP - 5}
            width={COL_W + 10}
            height={ROW_H + 10}
            rx="6"
            className="hs-pair-halo"
          />
          <rect
            x={TEST_X - 5}
            y={ROW_TOP + HIGHLIGHT.test * ROW_STEP - 5}
            width={COL_W + 10}
            height={ROW_H + 10}
            rx="6"
            className="hs-pair-halo"
          />
          <path d={arc} className="hs-arc" />
          <path d={arc} className="hs-arc-pulse" />
          <circle cx={TRAIN_X + COL_W} cy={trainHitY} r="3.2" className="hs-arc-node" />
          <circle cx={TEST_X} cy={testHitY} r="3.2" className="hs-arc-node" />
        </g>

        {/* Detection annotation */}
        <g className="hs-in" style={{ animationDelay: '640ms' }}>
          <rect x="40" y="452" width="580" height="42" rx="9" className="hs-tag" />
          <path d="M56 465.5l6 6.5-6 6.5-6-6.5z" className="hs-tag__mark" />
          <text className="hs-tag__text" x="74" y="474">
            SS-DUP-001 · identical feature vector on both sides of the split
          </text>
          <text className="hs-micro hs-tag__note" x="74" y="488">
            row-000187 ↔ row-000243 · illustrative synthetic example, not a computed result
          </text>
        </g>
      </svg>

      <figcaption className="lp-hero__caption">
        <span className="lp-hero__caption-label">Conceptual illustration</span>
        Variables feed records on both sides of a split. The audit reads each side and links the
        rows that share information across the boundary — here one synthetic pair. Nothing in this
        scene is a computed analysis result.
      </figcaption>
    </figure>
  )
}