/**
 * View B — Covariate Balance.
 *
 * Pins the Love-plot mapping: unadjusted and (only where weights exist)
 * weighted SMDs, the 0.1 heuristic guide, undefined values shown as undefined,
 * and the explicit "no weights applied" disclosure for regression adjustment.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { BalanceView } from '../src/estimation/BalanceView'
import { estimatedResult } from './estimationFixtures'

function renderBalance(result = estimatedResult('ipw')) {
  return render(<BalanceView result={result} provenance={['Run run-s9b-fixture']} staleNote={null} />)
}

describe('BalanceView', () => {
  it('plots one row per covariate comparison with both coinages of SMD', () => {
    renderBalance()
    expect(screen.getAllByTestId('love-row')).toHaveLength(5)
    // Weighted estimator: unweighted circles and weighted diamonds.
    expect(screen.getAllByTestId('love-unweighted')).toHaveLength(5)
    expect(screen.getAllByTestId('love-weighted')).toHaveLength(4)

    const table = screen.getByTestId('balance-table')
    expect(within(table).getByText('0.330')).toBeInTheDocument()
    expect(within(table).getByText('-0.020')).toBeInTheDocument()
    expect(within(table).getByText('region · south')).toBeInTheDocument()
    expect(within(table).getAllByText('category level')).toHaveLength(3)
  })

  it('sorts by imbalance by default so the worst covariate comes first', () => {
    renderBalance()
    const rows = screen.getAllByTestId('love-row')
    // region · south has |0.41| unweighted, the largest magnitude.
    expect(rows[0].getAttribute('aria-label')).toContain('region · south')
    fireEvent.change(screen.getByLabelText('Sort covariates'), { target: { value: 'order' } })
    expect(screen.getAllByTestId('love-row')[0].getAttribute('aria-label')).toContain('age')
  })

  it('never invents post-weighting values for regression adjustment', () => {
    renderBalance(estimatedResult('regression_adjustment'))
    expect(screen.getAllByTestId('love-unweighted')).toHaveLength(5)
    expect(screen.queryAllByTestId('love-weighted')).toHaveLength(0)
    expect(screen.getByTestId('balance-not-weighted').textContent).toContain(
      'No post-weighting values are shown',
    )
    const table = screen.getByTestId('balance-table')
    expect(within(table).getAllByText('not applicable')).toHaveLength(5)
  })

  it('shows an undefined SMD transparently instead of plotting zero', () => {
    renderBalance()
    // region · north has a null weighted SMD in the fixture.
    expect(screen.getByTestId('balance-undefined-note').textContent).toContain('1 comparison')
    const table = screen.getByTestId('balance-table')
    expect(within(table).getByText('undefined')).toBeInTheDocument()
  })

  it('labels the 0.1 guide as a heuristic and keeps the scientific caveat', () => {
    renderBalance()
    expect(screen.getByText('0.1 heuristic guide')).toBeInTheDocument()
    expect(screen.getByText('+0.1')).toBeInTheDocument()
    expect(screen.getByText('−0.1')).toBeInTheDocument()
    expect(screen.getByText(/does not establish that unmeasured confounding is absent/)).toBeInTheDocument()
  })

  it('discloses diagnostic imputation when the backend reports it', () => {
    const result = estimatedResult('ipw')
    render(
      <BalanceView
        result={{
          ...result,
          diagnostics: {
            ...result.diagnostics!,
            balance: {
              ...result.diagnostics!.balance,
              diagnostic_imputation:
                'Balance diagnostics are computed on median/mode-imputed covariate values.',
            },
          },
        }}
        provenance={[]}
        staleNote="Stale: the adjustment set changed."
      />,
    )
    expect(screen.getByTestId('balance-imputation-note').textContent).toContain(
      'median/mode-imputed',
    )
    expect(screen.getByText(/Stale: the adjustment set changed/)).toBeInTheDocument()
  })

  it('shows keyboard-focus details for a covariate', () => {
    renderBalance()
    const row = screen.getAllByTestId('love-row')[0]
    fireEvent.focus(row)
    expect(document.querySelector('.esttable-block__note')?.textContent).toContain('weighted')
  })
})
