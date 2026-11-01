/**
 * Charts.
 *
 * Deliberately hand-built from CSS bars rather than a charting library: the
 * figures here are simple two-series comparisons, they must survive printing,
 * and they need an accessible text alternative. Every chart is rendered with
 * `role="img"` plus a description, and each is accompanied by the same numbers in
 * a real `<table>` so nothing is conveyed by colour or position alone.
 */

import type { CategoryShare } from '../api/types'
import { percent } from '../lib/format'

export interface BarDatum {
  label: string
  train: number
  test: number
  trainCount: number
  testCount: number
}

export function BarPairChart({
  title,
  description,
  data,
  valueFormatter = percent,
  maxLabels = 10,
}: {
  title: string
  description: string
  data: BarDatum[]
  valueFormatter?: (value: number | null | undefined) => string
  maxLabels?: number
}) {
  const shown = data.slice(0, maxLabels)
  const maximum = Math.max(
    0,
    ...shown.flatMap((datum) => [Math.abs(datum.train), Math.abs(datum.test)]),
  )

  return (
    <figure style={{ margin: 0 }}>
      <figcaption className="small muted" style={{ marginBottom: 6 }}>
        {description}
      </figcaption>
      <div className="legend">
        <span>
          <span className="legend__swatch legend__swatch--train" aria-hidden="true" />
          Train
        </span>
        <span>
          <span className="legend__swatch legend__swatch--test" aria-hidden="true" />
          Test
        </span>
      </div>
      <div
        className="bars"
        role="img"
        aria-label={`${title}. ${description} ${shown
          .map(
            (datum) =>
              `${datum.label}: train ${valueFormatter(datum.train)} (${datum.trainCount}), test ${valueFormatter(datum.test)} (${datum.testCount})`,
          )
          .join('. ')}`}
      >
        {shown.map((datum) => (
          <div key={datum.label}>
            <div className="bar-row">
              <span className="bar-row__label" title={datum.label}>
                train {datum.label}
              </span>
              <span className="bar-track">
                <span
                  className="bar-fill"
                  style={{ width: maximum > 0 ? `${(datum.train / maximum) * 100}%` : '0%' }}
                />
              </span>
              <span className="bar-row__value">{valueFormatter(datum.train)}</span>
            </div>
            <div className="bar-row">
              <span className="bar-row__label" title={datum.label}>
                test {datum.label}
              </span>
              <span className="bar-track">
                <span
                  className="bar-fill bar-fill--test"
                  style={{ width: maximum > 0 ? `${(datum.test / maximum) * 100}%` : '0%' }}
                />
              </span>
              <span className="bar-row__value">{valueFormatter(datum.test)}</span>
            </div>
          </div>
        ))}
      </div>
      {data.length > shown.length ? (
        <p className="tiny muted">
          Showing the {shown.length} most frequent categories; {data.length - shown.length} more are
          included in the table below.
        </p>
      ) : null}
    </figure>
  )
}

export function categoriesToBars(categories: CategoryShare[]): BarDatum[] {
  return categories.map((category) => ({
    label: category.category === '' ? '(empty)' : category.category,
    train: category.train_ratio,
    test: category.test_ratio,
    trainCount: category.train_count,
    testCount: category.test_count,
  }))
}

export function histogramToBars(
  edges: number[],
  trainCounts: number[],
  testCounts: number[],
  trainRows: number,
  testRows: number,
): BarDatum[] {
  const bars: BarDatum[] = []
  for (let index = 0; index < trainCounts.length; index += 1) {
    const low = edges[index]
    const high = edges[index + 1]
    const label = `${low?.toPrecision?.(4) ?? low} – ${high?.toPrecision?.(4) ?? high}`
    bars.push({
      label,
      train: trainRows > 0 ? trainCounts[index] / trainRows : 0,
      test: testRows > 0 ? testCounts[index] / testRows : 0,
      trainCount: trainCounts[index],
      testCount: testCounts[index],
    })
  }
  return bars
}
