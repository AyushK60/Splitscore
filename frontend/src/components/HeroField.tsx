import { useEffect, useState } from 'react'

import type { HeroPhase } from '../lib/useHeroSequence'

/**
 * The Information Boundary Observatory.
 *
 * A full-bleed instrument plate rather than a chart beside the copy. Two
 * registers of record plates sit on either side of a vertical split rule; a
 * scanner crosses them, one plate on each side resolves to the same customer,
 * and the pair is then isolated as evidence.
 *
 * Every value is a fixed illustrative fixture, stated in the readout that
 * accompanies it. The component draws; it never computes.
 */

const PLATE_W = 100
const PLATE_H = 64
const TRAIN_X = [520, 640, 760]
const TEST_X = [930, 1040, 1150, 1260]
const ROW_Y = [200, 300]
const BOUNDARY = 900

const PAIR_TRAIN = { x: 640, y: 300 }
const PAIR_TEST = { x: 1260, y: 200 }

type Plate = {
  key: string
  x: number
  y: number
  pair: boolean
  ticks: number[]
  index: number
}

function tickWidths(seed: number): number[] {
  return [
    18 + ((seed * 7) % 12),
    12 + ((seed * 5) % 16),
    22 + ((seed * 3) % 10),
    10 + ((seed * 11) % 14),
  ]
}

function buildPlates(): Plate[] {
  const plates: Plate[] = []
  let index = 0
  for (const [side, columns] of [
    ['train', TRAIN_X],
    ['test', TEST_X],
  ] as const) {
    columns.forEach((x, column) => {
      ROW_Y.forEach((y, row) => {
        const pair =
          (side === 'train' && x === PAIR_TRAIN.x && y === PAIR_TRAIN.y) ||
          (side === 'test' && x === PAIR_TEST.x && y === PAIR_TEST.y)
        plates.push({
          key: `${side}-${column}-${row}`,
          x,
          y,
          pair,
          ticks: tickWidths(index + column * 3 + row),
          index,
        })
        index += 1
      })
    })
  }
  return plates
}

const PLATES = buildPlates()

/** Leaves the right edge of the training plate and lands on the left edge of
 *  the testing plate, crossing the rule at roughly y = 320. */
const ARC = `M${PAIR_TRAIN.x + PLATE_W} ${PAIR_TRAIN.y + 32} C 760 ${PAIR_TRAIN.y + 32} 980 ${
  PAIR_TEST.y + 32
} ${PAIR_TEST.x} ${PAIR_TEST.y + 32}`

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 700px)').matches,
  )

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(max-width: 700px)')
    const onChange = () => setNarrow(query.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])

  return narrow
}

type HeroFieldProps = {
  phase: HeroPhase
  paused: boolean
  cycle: number
}

export function HeroField({ phase, paused, cycle }: HeroFieldProps) {
  const narrow = useNarrow()

  return (
    <svg
      key={cycle}
      className="hs-scene obs-scene"
      viewBox={narrow ? '480 140 900 560' : '480 140 900 560'}
      preserveAspectRatio="xMidYMid meet"
      data-phase={phase}
      data-paused={paused ? 'true' : 'false'}
      aria-hidden="true"
      focusable="false"
    >
      {/* floor rules give the scene a horizon without a fake perspective grid */}
      <g className="obs-floor">
        {[120, 300, 480, 660, 840].map((y) => (
          <line key={y} x1="0" y1={y} x2="1440" y2={y} />
        ))}
      </g>

      {/* the split boundary */}
      <g className="obs-rule">
        <line className="obs-rule__line" x1={BOUNDARY} y1="140" x2={BOUNDARY} y2="700" />
        {Array.from({ length: 23 }, (_, i) => (
          <line
            key={i}
            className="obs-rule__tick"
            x1={BOUNDARY - 7}
            y1={170 + i * 23}
            x2={BOUNDARY + 7}
            y2={170 + i * 23}
          />
        ))}
        <text className="obs-rule__label" transform={`translate(${BOUNDARY + 22} 560) rotate(-90)`}>
          SPLIT BOUNDARY
        </text>
      </g>

      {/* register legends */}
      <g className="obs-legend">
        <text x={TRAIN_X[0]} y="172" className="obs-legend__title">
          TRAIN REGISTER
        </text>
        <text x={TRAIN_X[0]} y="186" className="obs-legend__sub">
          illustrative records
        </text>
        <text x={TEST_X[3] + PLATE_W} y="172" textAnchor="end" className="obs-legend__title">
          TEST REGISTER
        </text>
        <text x={TEST_X[3] + PLATE_W} y="186" textAnchor="end" className="obs-legend__sub">
          illustrative records
        </text>
      </g>

      {/* record plates */}
      <g className="obs-plates">
        {PLATES.map((plate) => (
          <g
            key={plate.key}
            className={`obs-card${plate.pair ? ' obs-card--pair' : ''}`}
            transform={`translate(${plate.x} ${plate.y})`}
            style={{ ['--i' as string]: plate.index }}
          >
            <g className="obs-card__lift">
              <rect className="obs-card__shadow" x="6" y="7" width={PLATE_W} height={PLATE_H} rx="2" />
              <rect className="obs-card__body" width={PLATE_W} height={PLATE_H} rx="2" />
              <line className="obs-card__edge" x1="2" y1="0.5" x2={PLATE_W - 2} y2="0.5" />
              {plate.ticks.map((width, tick) => (
                <rect
                  key={tick}
                  className={`obs-card__tick${
                    plate.pair && tick === 2 ? ' obs-card__tick--match' : ''
                  }`}
                  x={12}
                  y={16 + tick * 11}
                  width={width}
                  height="4"
                  rx="2"
                />
              ))}
              <rect
                className="obs-card__foot"
                x="12"
                y={PLATE_H - 11}
                width="30"
                height="3"
                rx="1.5"
              />
            </g>
          </g>
        ))}
      </g>

      {/* scanner: crosses the training register and stops at the rule */}
      <g className="hs-scan-band">
        <rect className="obs-scan__fill" x="470" y="140" width="120" height="560" />
        <line className="obs-scan__edge" x1="590" y1="140" x2="590" y2="700" />
      </g>

      {/* aperture at the rule */}
      <g className="obs-aperture">
        <circle cx={BOUNDARY} cy="320" r="58" />
        <circle cx={BOUNDARY} cy="320" r="34" />
        <circle cx={BOUNDARY} cy="320" r="4" className="obs-aperture__core" />
      </g>

      {/* the leak */}
      <g className="obs-arc">
        <path className="obs-arc__glow" d={ARC} pathLength={1} />
        <path className="obs-arc__line" d={ARC} pathLength={1} />
        <circle className="obs-arc__spark" cx="900" cy="320" r="4" />
      </g>

      {/* the finding, labelled in the scene rather than in a floating tooltip */}
      <g className="obs-finding">
        <line className="obs-finding__leader" x1="700" y1="430" x2="740" y2="364" />
        <rect x="690" y="430" width="310" height="44" rx="2" />
        <text x="702" y="448" className="obs-finding__id">
          SS-DUP-001 · shared customer_id
        </text>
        <text x="702" y="462" className="obs-finding__note">
          row-000412 (train) ↔ row-000887 (test)
        </text>
      </g>
    </svg>
  )
}
