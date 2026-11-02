/**
 * HeroField — the landing page's audit field.
 *
 * The scene is not a card placed beside the headline: it is the ground the
 * whole hero sits on. Two registers of records (train / test) run edge to edge,
 * separated by a single vertical boundary rule. Columns feed the records from
 * above, one filament leaves a training row, climbs across the boundary and
 * lands on the testing row that shares its information, and a slow scan pass
 * reads the field from left to right.
 *
 * Everything drawn is illustrative and labelled as such in the hero copy: it
 * tells the story of what the auditor looks for, it is never a computed result.
 * Motion pauses when the hero leaves the viewport and collapses to a still
 * composition under `prefers-reduced-motion`.
 */
import { useEffect, useRef, useState } from 'react'

const BOUNDARY = 900
const ROW_TOP = 196
const ROW_STEP = 15
const ROW_COUNT = 42

/** Deterministic noise: the field must read as records, not as a pattern block. */
function wave(seed: number) {
  const v = Math.sin(seed * 78.233 + 12.9898) * 43758.5453
  return v - Math.floor(v)
}

type Row = {
  y: number
  trainW: number
  testW: number
  strong: boolean
  cells: boolean
}

const ROWS: Row[] = Array.from({ length: ROW_COUNT }, (_, i) => ({
  y: ROW_TOP + i * ROW_STEP,
  trainW: 260 + wave(i) * 590,
  testW: 110 + wave(i + 31) * 330,
  strong: i % 6 === 2,
  cells: wave(i + 71) > 0.62,
}))

const TICKS = Array.from({ length: 15 }, (_, i) => 132 + i * 50)

const LEAK = { train: 21, test: 9 }
const rowCentre = (row: number) => ROW_TOP + row * ROW_STEP + ROW_STEP / 2

const trainY = rowCentre(LEAK.train)
const testY = rowCentre(LEAK.test)

const LEAK_PATH =
  `M700 ${trainY} C820 ${trainY} 820 ${testY} 1000 ${testY} ` +
  `C1090 ${testY} 1160 ${testY - 8} 1240 ${testY}`

const COLUMNS = [
  { x: 196, label: 'customer_id', row: 24 },
  { x: 336, label: 'signup_ts', row: 14 },
  { x: 476, label: 'plan_tier', row: 30 },
  { x: 616, label: 'region', row: 18 },
  { x: 756, label: 'spend_30d', row: 34 },
  { x: 1046, label: 'target', row: LEAK.test, target: true },
]

export function HeroField() {
  const svgRef = useRef<SVGSVGElement>(null)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    const node = svgRef.current
    if (!node || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => setPaused(!entries.some((entry) => entry.isIntersecting)),
      { threshold: 0 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <svg
      ref={svgRef}
      className={`hs-scene${paused ? ' is-paused' : ''}`}
      viewBox="0 0 1440 900"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <radialGradient id="hs-field" cx="34%" cy="16%" r="94%">
          <stop offset="0%" stopColor="#17281f" />
          <stop offset="50%" stopColor="#0d1712" />
          <stop offset="100%" stopColor="#060c09" />
        </radialGradient>

        <radialGradient id="hs-bloom-copper" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#d9793f" stopOpacity="0.26" />
          <stop offset="100%" stopColor="#d9793f" stopOpacity="0" />
        </radialGradient>

        <radialGradient id="hs-bloom-celadon" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#a7c4b2" stopOpacity="0.14" />
          <stop offset="100%" stopColor="#a7c4b2" stopOpacity="0" />
        </radialGradient>

        <linearGradient id="hs-scan" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#d9793f" stopOpacity="0" />
          <stop offset="72%" stopColor="#e5955c" stopOpacity="0.07" />
          <stop offset="100%" stopColor="#f0b98c" stopOpacity="0.2" />
        </linearGradient>

        <linearGradient id="hs-filament" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#e0803f" stopOpacity="0.45" />
          <stop offset="46%" stopColor="#f6c39c" stopOpacity="1" />
          <stop offset="100%" stopColor="#e0803f" stopOpacity="0.5" />
        </linearGradient>
      </defs>

      {/* Ground and atmosphere */}
      <rect width="1440" height="900" fill="url(#hs-field)" />
      <ellipse cx="1120" cy="330" rx="470" ry="360" fill="url(#hs-bloom-copper)" />
      <ellipse cx="260" cy="720" rx="470" ry="330" fill="url(#hs-bloom-celadon)" />

      {/* Instrument grid */}
      <g className="hs-grid" aria-hidden="true">
        {Array.from({ length: 12 }, (_, i) => (
          <line key={`v${i}`} x1={i * 120 + 60} y1="0" x2={i * 120 + 60} y2="900" />
        ))}
        {Array.from({ length: 8 }, (_, i) => (
          <line key={`h${i}`} x1="0" y1={i * 120 + 60} x2="1440" y2={i * 120 + 60} />
        ))}
      </g>

      {/* The two registers */}
      <g className="hs-records">
        {ROWS.map((row, i) => (
          <g key={i}>
            <rect
              className={row.strong ? 'hs-record hs-record--strong' : 'hs-record'}
              x={60}
              y={row.y}
              width={row.trainW}
              height={5}
              rx={1}
            />
            <rect
              className={row.strong ? 'hs-record hs-record--strong' : 'hs-record'}
              x={BOUNDARY + 30}
              y={row.y}
              width={row.testW}
              height={5}
              rx={1}
            />
            {row.cells ? (
              <>
                <rect
                  className="hs-cell"
                  x={120 + wave(i + 3) * 430}
                  y={row.y - 1}
                  width={34}
                  height={7}
                  rx={1}
                />
                <rect
                  className="hs-cell"
                  x={BOUNDARY + 62 + wave(i + 9) * 250}
                  y={row.y - 1}
                  width={22}
                  height={7}
                  rx={1}
                />
              </>
            ) : null}
          </g>
        ))}
      </g>

      {/* Split boundary */}
      <g className="hs-boundary" aria-hidden="true">
        <line className="hs-boundary__rule" x1={BOUNDARY} y1="104" x2={BOUNDARY} y2="836" />
        <line
          className="hs-boundary__laser"
          x1={BOUNDARY + 7}
          y1="120"
          x2={BOUNDARY + 7}
          y2="820"
        />
        {TICKS.map((y) => (
          <line key={y} className="hs-tick" x1={BOUNDARY - 6} y1={y} x2={BOUNDARY + 6} y2={y} />
        ))}
        <text
          className="hs-boundary__label"
          transform={`translate(${BOUNDARY - 22} 700) rotate(-90)`}
        >
          SPLIT BOUNDARY
        </text>
      </g>

      {/* Columns feeding the records */}
      <g className="hs-columns" aria-hidden="true">
        {COLUMNS.map((column) => {
          const y = rowCentre(column.row)
          return (
            <g key={column.label} className={column.target ? 'hs-column is-target' : 'hs-column'}>
              <path
                className="hs-thread"
                d={`M${column.x} 192 C${column.x + 12} 290, ${column.x - 14} 380, ${column.x} ${y}`}
              />
              <circle className="hs-thread__node" cx={column.x} cy={y} r="3" />
              <text className="hs-column__label" x={column.x} y="182" textAnchor="middle">
                {column.label}
              </text>
            </g>
          )
        })}
      </g>

      {/* The pair the audit links across the boundary */}
      <g className="hs-leak">
        <ellipse
          className="hs-leak__bloom"
          cx="880"
          cy={(trainY + testY) / 2}
          rx="300"
          ry="180"
        />
        <rect className="hs-leak__halo" x="660" y={trainY - 9} width="200" height="18" rx="2" />
        <rect
          className="hs-leak__halo hs-leak__halo--test"
          x={BOUNDARY + 20}
          y={testY - 9}
          width="320"
          height="18"
          rx="2"
        />
        <path className="hs-leak__glow" d={LEAK_PATH} />
        <path className="hs-leak__path" d={LEAK_PATH} />
        <path className="hs-leak__pulse" d={LEAK_PATH} />
        <circle className="hs-leak__node" cx="700" cy={trainY} r="3.6" />
        <circle className="hs-leak__node" cx="1240" cy={testY} r="3.6" />
        <circle className="hs-leak__spark" cx="900" cy="420" r="2.4" />
      </g>

      {/* Detection annotation, clear of the filament */}
      <g className="hs-tag">
        <path className="hs-tag__leader" d="M1052 254 C1040 282, 1024 310, 1012 330" />
        <rect className="hs-tag__box" x="1000" y="196" width="342" height="56" rx="2" />
        <text className="hs-tag__id" x="1016" y="220">
          SS-DUP-001
        </text>
        <text className="hs-tag__note" x="1016" y="238">
          shared feature vector across the split
        </text>
      </g>

      {/* Scan pass */}
      <g className="hs-scan-band" aria-hidden="true">
        <rect x="-280" y="104" width="280" height="740" fill="url(#hs-scan)" />
        <line className="hs-scan-edge" x1="0" y1="104" x2="0" y2="844" />
      </g>
    </svg>
  )
}
