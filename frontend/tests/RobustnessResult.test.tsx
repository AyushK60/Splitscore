/**
 * S9C-B Robustness view: distribution figure, original reference, honest
 * failure list, sensitivity grid shading.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RobustnessResult } from '../src/research/RobustnessView'
import { robustnessPayload, sensitivityPayload } from './researchFixtures'

describe('RobustnessResult (subsampling)', () => {
  it('shows the original estimate as the reference', () => {
    render(<RobustnessResult payload={robustnessPayload()} />)
    expect(screen.getByTestId('robustness-original').textContent).toContain('1.580')
  })

  it('renders the repetition histogram and its summary row', () => {
    render(<RobustnessResult payload={robustnessPayload()} />)
    expect(screen.getByTestId('robustness-histogram')).toBeTruthy()
    expect(screen.getByTestId('robustness-original-line')).toBeTruthy()
    expect(screen.getByTestId('robustness-mean').textContent).toContain('1.564')
  })

  it('lists failed repetitions with their reasons, never averaged away', () => {
    render(<RobustnessResult payload={robustnessPayload()} />)
    const failures = screen.getByTestId('robustness-failures')
    expect(within(failures).getByText(/Repetition 7/)).toBeTruthy()
    expect(within(failures).getByText(/total weight zero/)).toBeTruthy()
  })

  it('carries the experiment caveat beside the figure', () => {
    render(<RobustnessResult payload={robustnessPayload()} />)
    expect(screen.getByText(/stability is not absence of bias/)).toBeTruthy()
  })
})

describe('RobustnessResult (sensitivity grid)', () => {
  it('renders the full 5×5 grid with numeric cells', () => {
    render(<RobustnessResult payload={sensitivityPayload()} />)
    expect(screen.getByTestId('sensitivity-cell-0-0').textContent).toBe('1.58')
    expect(screen.getByTestId('sensitivity-cell-4-4').textContent).toBe('1.20')
    expect(screen.getByTestId('sensitivity-grid')).toBeTruthy()
  })

  it('labels the analysis as a hypothetical scenario, not a bound', () => {
    render(<RobustnessResult payload={sensitivityPayload()} />)
    expect(screen.getByText(/not a bound/)).toBeTruthy()
  })

  it('shades movement away from the original without inventing statistics', () => {
    render(<RobustnessResult payload={sensitivityPayload()} />)
    expect(screen.getByText(/descriptive shading of the scenario table, not a statistic/)).toBeTruthy()
  })
})
