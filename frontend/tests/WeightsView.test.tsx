/**
 * View D — Weights & Reliability.
 *
 * Pins raw vs Kish effective sample size, retained fractions, the truncation
 * disclosure and the not-applicable state for an estimator that applies no
 * weights.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { WeightsView } from '../src/estimation/WeightsView'
import { estimatedResult } from './estimationFixtures'

describe('WeightsView', () => {
  it('plots raw rows beside the effective sample size per arm', () => {
    render(<WeightsView result={estimatedResult('ipw')} provenance={['Run run-s9b-fixture']} />)
    const treated = screen.getByTestId('ess-arm-treated')
    expect(treated.textContent).toContain('45')
    expect(treated.textContent).toContain('37.5')
    expect(treated.textContent).toContain('83% of rows retained')
    const control = screen.getByTestId('ess-arm-control')
    expect(control.textContent).toContain('75')
    expect(control.textContent).toContain('60.0')
    expect(control.textContent).toContain('80% of rows retained')
  })

  it('reports weight summaries and effective sizes in the diagnostic table', () => {
    render(<WeightsView result={estimatedResult('ipw')} provenance={[]} />)
    const table = screen.getByTestId('weights-table')
    expect(within(table).getByText('6.250')).toBeInTheDocument()
    expect(within(table).getByText('1.40 / 3.20 / 5.10')).toBeInTheDocument()
    expect(within(table).getByText(/untruncated/)).toBeInTheDocument()
    expect(within(table).getByText('A few rows carrying large weights shrink the effective sample.')).toBeInTheDocument()
  })

  it('discloses explicit truncation and keeps the bias/variance reading', () => {
    const result = estimatedResult('ipw')
    const overlap = result.diagnostics!.overlap!
    render(
      <WeightsView
        result={{
          ...result,
          truncation: { lower: 0.05, upper: 0.95 },
          diagnostics: {
            ...result.diagnostics!,
            overlap: { ...overlap, truncation: { lower: 0.05, upper: 0.95 } },
          },
        }}
        provenance={[]}
      />,
    )
    expect(screen.getByTestId('weights-truncation-note').textContent).toContain(
      'Truncation disclosure',
    )
    expect(screen.getByText(/trades bias for variance control/)).toBeInTheDocument()
  })

  it('shows unstable-weight warnings without calling them a software error', () => {
    const result = estimatedResult('ipw')
    const overlap = result.diagnostics!.overlap!
    render(
      <WeightsView
        result={{
          ...result,
          diagnostics: {
            ...result.diagnostics!,
            overlap: {
              ...overlap,
              warnings: ['The treated arm’s effective sample size (12.0) is below a quarter of its row count (45).'],
            },
          },
        }}
        provenance={[]}
      />,
    )
    expect(screen.getByTestId('weights-warnings').textContent).toContain('below a quarter')
    expect(screen.getByText(/it does not invalidate the estimate by itself/)).toBeInTheDocument()
  })

  it('is explicitly not applicable for regression adjustment', () => {
    render(<WeightsView result={estimatedResult('regression_adjustment')} provenance={[]} />)
    expect(screen.getByTestId('weights-unavailable').textContent).toContain(
      'Regression adjustment does not weight observations',
    )
  })
})
