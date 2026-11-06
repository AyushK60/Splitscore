/**
 * S9C-C What-If view: two-arm prediction bars, contrast, disclosed profile,
 * and the model-based (not observed) framing.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { WhatIfResult } from '../src/research/WhatIfView'
import { whatIfPayload } from './researchFixtures'

describe('WhatIfResult', () => {
  it('renders treated and control prediction bars and the contrast', () => {
    render(<WhatIfResult payload={whatIfPayload()} />)
    expect(screen.getByTestId('whatif-treated-bar')).toBeTruthy()
    expect(screen.getByTestId('whatif-control-bar')).toBeTruthy()
    expect(screen.getByTestId('whatif-contrast').textContent).toContain('1.500')
  })

  it('labels the predictions as model-based, never observed counterfactuals', () => {
    render(<WhatIfResult payload={whatIfPayload()} />)
    expect(screen.getAllByText(/model-based\s+conditional predictions/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/not observed outcomes/).length).toBeGreaterThan(0)
  })

  it('shows the cohort-standardised contrast beside the profile scenario', () => {
    render(<WhatIfResult payload={whatIfPayload()} />)
    expect(screen.getByText(/Cohort-standardised contrast/)).toBeTruthy()
    expect(screen.getByText(/1.590/)).toBeTruthy()
  })

  it('lists the profile with explicit and default sources', () => {
    render(<WhatIfResult payload={whatIfPayload()} />)
    const table = screen.getByTestId('whatif-profile')
    expect(within(table).getByText('55')).toBeTruthy()
    expect(within(table).getByText('cohort median (default)')).toBeTruthy()
    expect(within(table).getAllByText('set explicitly').length).toBe(2)
  })

  it('reports that no interval is attached to a scenario', () => {
    render(<WhatIfResult payload={whatIfPayload()} />)
    expect(
      screen.getByText(/None is reported; a scenario prediction is a conditional model expectation/),
    ).toBeTruthy()
  })
})
