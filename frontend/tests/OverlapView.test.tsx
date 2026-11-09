/**
 * View C - Overlap & Propensity.
 *
 * Pins the histogram mapping (per-arm counts and within-arm shares), the
 * quantile strip, truncation disclosure, warnings and the regression-adjustment
 * "not applicable" state. No per-group distribution is inferred.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { OverlapView } from '../src/estimation/OverlapView'
import { estimatedResult } from './estimationFixtures'

describe('OverlapView', () => {
  it('draws one bin per fixed histogram bin from the backend payload', () => {
    render(<OverlapView result={estimatedResult('ipw')} provenance={['Run run-s9b-fixture']} />)
    expect(screen.getAllByTestId('overlap-bin')).toHaveLength(20)
    expect(screen.getByText('treated')).toBeInTheDocument()
    expect(screen.getByText('control')).toBeInTheDocument()
    // The overlap window is the intersection of the reported 1st–99th percentiles.
    expect(screen.getByText('0.120 – 0.580')).toBeInTheDocument()
    expect(screen.getByText(/median 0.33/)).toBeInTheDocument()
  })

  it('reports both arms counts and within-arm shares in the table', () => {
    render(<OverlapView result={estimatedResult('ipw')} provenance={[]} />)
    const table = screen.getByTestId('overlap-table')
    // Bin 1 (0.05–0.10) has 4 treated and 9 control rows in the fixture.
    const rows = within(table).getAllByRole('row')
    const firstDataRow = rows.find((row) => row.textContent?.includes('0.05 – 0.10'))!
    expect(firstDataRow.textContent).toContain('4')
    expect(firstDataRow.textContent).toContain('8.9%')
    expect(firstDataRow.textContent).toContain('9')
    expect(firstDataRow.textContent).toContain('12.0%')
  })

  it('discloses truncation exactly as the backend reports it', () => {
    const result = estimatedResult('ipw')
    const overlap = result.diagnostics!.overlap!
    render(
      <OverlapView
        result={{
          ...result,
          diagnostics: {
            ...result.diagnostics!,
            overlap: {
              ...overlap,
              truncation: { lower: 0.05, upper: 0.95 },
              warnings: ['Propensity truncation was applied as explicitly requested.'],
            },
          },
        }}
        provenance={[]}
      />,
    )
    expect(screen.getByTestId('overlap-truncation-note').textContent).toContain('[0.05, 0.95]')
    expect(screen.getByTestId('overlap-warnings').textContent).toContain('truncation was applied')
  })

  it('says that no warning is not a positivity test', () => {
    render(<OverlapView result={estimatedResult('ipw')} provenance={[]} />)
    expect(screen.getByTestId('overlap-no-warnings').textContent).toContain(
      'not a positivity test',
    )
    expect(document.body.textContent).toContain(
      'These are empirical overlap diagnostics for the fitted propensity distribution in this dataset.',
    )
    expect(screen.getAllByText(/fitted propensity/).length).toBeGreaterThan(0)
  })

  it('is explicitly not applicable when the result has no propensity model', () => {
    render(<OverlapView result={estimatedResult('regression_adjustment')} provenance={[]} />)
    expect(screen.getByTestId('overlap-unavailable').textContent).toContain(
      'Propensity scores are only fitted by the IPW and AIPW estimators',
    )
  })

  it('exposes bin details on keyboard focus', () => {
    render(<OverlapView result={estimatedResult('ipw')} provenance={[]} />)
    const bin = screen.getAllByTestId('overlap-bin')[1]
    fireEvent.focus(bin)
    expect(document.querySelector('.estsum__detail')?.textContent).toContain('treated 4')
    expect(document.querySelector('.estsum__detail')?.textContent).toContain('control 9')
  })
})
