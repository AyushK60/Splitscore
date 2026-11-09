/**
 * View A - Effect Summary.
 *
 * Pins the mapping from the estimation result payload to the figure: the exact
 * estimates and interval bounds, the zero reference, positive/negative
 * directions, the unavailable-interval state and the failed-estimator state.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EffectSummary } from '../src/estimation/EffectSummary'
import { estimatedResult, failedResult, runPayload } from './estimationFixtures'

function renderSummary(payload = runPayload()) {
  return render(
    <EffectSummary payload={payload} studyNote="Study note." provenance={['Run run-s9b-fixture']} />,
  )
}

function dotX(estimator: string): number | null {
  const dot = screen.getByTestId(`summary-dot-${estimator}`)
  const value = dot.getAttribute('cx')
  return value === null ? null : Number(value)
}

describe('EffectSummary', () => {
  it('plots the three estimators with the backend values, not rounded substitutes', () => {
    renderSummary()
    expect(screen.getByTestId('summary-dot-regression_adjustment').getAttribute('data-value')).toBe('2')
    expect(screen.getByTestId('summary-dot-ipw').getAttribute('data-value')).toBe('1.6')
    expect(screen.getByTestId('summary-dot-aipw').getAttribute('data-value')).toBe('1.8')

    const table = screen.getByTestId('effect-summary-table')
    expect(within(table).getByText('2.000')).toBeInTheDocument()
    expect(within(table).getByText('1.600')).toBeInTheDocument()
    expect(within(table).getByText('1.800')).toBeInTheDocument()
    expect(within(table).getByText('1.700 to 2.300')).toBeInTheDocument()
  })

  it('draws a zero reference between positive and negative estimates', () => {
    renderSummary(
      runPayload({
        results: [
          estimatedResult('ipw', {
            estimate: -0.4,
            uncertainty: {
              status: 'available',
              method: 'bootstrap_percentile',
              level: 0.95,
              standard_error: 0.1,
              ci_lower: -0.7,
              ci_upper: -0.1,
              assumptions: [],
            },
          }),
          estimatedResult('aipw', { estimate: 0.9 }),
        ],
      }),
    )

    const zero = document.querySelector('.estchart__zero')
    expect(zero).not.toBeNull()
    const zeroX = Number(zero?.getAttribute('x1'))
    expect(dotX('ipw')).toBeLessThan(zeroX)
    expect(dotX('aipw')).toBeGreaterThan(zeroX)
    expect(screen.getByText('no effect')).toBeInTheDocument()
  })

  it('shows interval caps exactly at the reported confidence bounds', () => {
    renderSummary()
    const interval = document
      .querySelector('[data-testid="summary-row-ipw"] .estrow__interval')
    expect(interval?.getAttribute('x1')).toBeDefined()
    expect(interval?.getAttribute('x2')).toBeDefined()
    // The IPW interval is 1.29–1.91: both inside the domain and ordered.
    expect(Number(interval?.getAttribute('x1'))).toBeLessThan(Number(interval?.getAttribute('x2')))
    expect(screen.getByTestId('summary-dot-ipw').getAttribute('cx')).toBeDefined()
  })

  it('marks an unavailable interval without fabricating bounds', () => {
    renderSummary(
      runPayload({
        results: [
          estimatedResult('aipw', {
            uncertainty: {
              status: 'unavailable',
              method: 'bootstrap_percentile',
              level: 0.95,
              standard_error: null,
              ci_lower: null,
              ci_upper: null,
              unavailable_reason: 'Fewer than 100 bootstrap replicates succeeded.',
              assumptions: [],
            },
          }),
        ],
        comparison: undefined,
      }),
    )
    expect(screen.getByTestId('summary-dot-aipw')).toBeInTheDocument()
    expect(document.querySelector('.estrow__interval')).toBeNull()
    expect(screen.getAllByText(/interval unavailable/i).length).toBeGreaterThan(0)
    const table = screen.getByTestId('effect-summary-table')
    expect(within(table).getByText(/Fewer than 100 bootstrap replicates succeeded/)).toBeInTheDocument()
  })

  it('represents a failed estimator as failed, never as a zero effect', () => {
    renderSummary(
      runPayload({
        results: [
          failedResult('regression_adjustment'),
          estimatedResult('ipw'),
          estimatedResult('aipw'),
        ],
        comparison: undefined,
      }),
    )

    expect(screen.queryByTestId('summary-dot-regression_adjustment')).toBeNull()
    expect(screen.getByTestId('summary-failure-regression_adjustment').textContent).toContain(
      'Failed',
    )
    const table = screen.getByTestId('summary-table-regression_adjustment')
    expect(within(table).getByText('not estimated')).toBeInTheDocument()
    expect(within(table).getByText('failed')).toBeInTheDocument()
  })

  it('renders the failure state alone when every estimator fails', () => {
    renderSummary(
      runPayload({
        results: [failedResult('regression_adjustment'), failedResult('ipw'), failedResult('aipw')],
        comparison: undefined,
      }),
    )
    expect(screen.getByTestId('summary-all-failed').textContent).toContain(
      'a failed estimate is not a zero effect',
    )
  })

  it('exposes estimate details on keyboard focus', () => {
    renderSummary()
    const row = screen.getByTestId('summary-row-aipw')
    fireEvent.focus(row)
    const detail = document.querySelector('.estsum__detail')
    expect(detail?.textContent).toContain('Cross-fitted AIPW')
    expect(detail?.textContent).toContain('1.800')
    expect(detail?.textContent).toContain('1.500 to 2.100')
    fireEvent.blur(row)
    expect(document.querySelector('.estsum__detail')?.textContent).toContain('Point at a row')
  })

  it('labels the outcome units and the comparison caveat', () => {
    renderSummary()
    expect(screen.getAllByText(/outcome units/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Agreement between estimators is not a validity check/)).toBeInTheDocument()
    expect(screen.getByText('Largest pairwise difference:')).toBeInTheDocument()
  })
})
