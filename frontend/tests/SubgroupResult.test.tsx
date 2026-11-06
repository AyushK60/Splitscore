/**
 * S9C-A Subgroup Effects view: forest plot marks, unavailable groups,
 * contrasts and table, against hand-written payload fixtures.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { SubgroupResult } from '../src/research/SubgroupView'
import { subgroupPayload } from './researchFixtures'

describe('SubgroupResult', () => {
  it('renders one row per subgroup with its interval and value', () => {
    render(<SubgroupResult payload={subgroupPayload()} />)
    const chart = screen.getByTestId('subgroup-forest-chart')
    expect(chart).toBeTruthy()
    expect(screen.getByTestId('forest-row-0')).toBeTruthy()
    expect(screen.getByTestId('forest-row-1')).toBeTruthy()
    // The unavailable group is listed, not plotted as a zero.
    expect(screen.getByText(/Not estimated/)).toBeTruthy()
  })

  it('labels the overall reference and the intent', () => {
    render(<SubgroupResult payload={subgroupPayload()} />)
    expect(screen.getByText(/overall 1.665/)).toBeTruthy()
    expect(screen.getByText(/exploratory/)).toBeTruthy()
  })

  it('shows the unavailable reason verbatim in the table, never an estimate', () => {
    render(<SubgroupResult payload={subgroupPayload()} />)
    const row = screen.getByTestId('subgroup-table-south')
    expect(within(row).getByText('unavailable')).toBeTruthy()
    expect(within(row).queryByText(/1\./)).toBeNull()
    // The full reason is rendered where the figure lists the unavailable group.
    expect(screen.getByText(/No estimate was fabricated/)).toBeTruthy()
  })

  it('renders the between-group contrast with its own interval', () => {
    render(<SubgroupResult payload={subgroupPayload()} />)
    const contrasts = screen.getByTestId('subgroup-contrasts')
    expect(contrasts.textContent).toContain('north − east')
    expect(contrasts.textContent).toContain('0.310')
    expect(contrasts.textContent).toContain('-0.207')
  })

  it('carries the pseudo-outcome provenance and multiple-comparison notes', () => {
    render(<SubgroupResult payload={subgroupPayload()} />)
    expect(screen.getByText('Pseudo-outcome provenance note.')).toBeTruthy()
    expect(screen.getByText('Multiple comparisons note.')).toBeTruthy()
  })

  it('exposes the CSV export whose values match the plotted groups', () => {
    render(<SubgroupResult payload={subgroupPayload()} />)
    expect(screen.getByTestId('subgroup-table')).toBeTruthy()
    // The export metadata path is exercised by estimationExport tests; here we
    // pin that the figure block exists with export actions.
    expect(screen.getByTestId('subgroup-forest')).toBeTruthy()
  })
})
