/**
 * Parallel Coordinates rendering behaviour with a fixed mock series.
 *
 * Assertions are on what the chart claims: real column names as axes, the
 * sampling honesty caption, selection highlighting, constant-axis labelling
 * and the brush reset control. Geometry is not pixel-tested; the numerical
 * correctness of the underlying values is covered by the backend's
 * scipy-oracle tests.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ParallelCoordinates } from '../src/components/explore/ParallelCoordinates'
import type { SeriesResponse } from '../src/api/types'
import { EMPTY_SELECTION } from '../src/explore/ExploreState'
import type * as exploreStateModule from '../src/explore/ExploreState'

// The export menu reads the explorer and app contexts; the chart under test
// gets fixed fixtures so these tests stay about rendering behaviour.
vi.mock('../src/explore/ExploreState', async (importOriginal) => {
  const actual = await importOriginal<typeof exploreStateModule>()
  return {
    ...actual,
    useExplore: () => ({
      schema: null,
      schemaError: null,
      colorColumn: null,
      setColorColumn: vi.fn(),
      selection: EMPTY_SELECTION,
      applyPredicates: vi.fn(),
      clearSelection: vi.fn(),
      highlightedId: null,
      setHighlightedId: vi.fn(),
    }),
  }
})
vi.mock('../src/state/AppState', () => ({
  useApp: () => ({ health: { app_version: 'test' } }),
}))

// jsdom has no ResizeObserver; the chart measures its container through one.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub)

function seriesFixture(): SeriesResponse {
  return {
    dataset_id: 'ds-test',
    columns: ['a', 'b', 'flat', 'g'],
    population: 6,
    filtered_population: 6,
    filters_active: false,
    drawn_rows: 6,
    sampling: { method: 'systematic_grid', stride: 1, description: 'All rows are drawn.' },
    scale: {
      a: { numeric: true, min: 0, max: 10, valid_count: 6, missing_count: 0, unparsed_count: 0 },
      b: { numeric: true, min: 0, max: 100, valid_count: 6, missing_count: 0, unparsed_count: 0 },
      flat: { numeric: true, min: 5, max: 5, valid_count: 6, missing_count: 0, unparsed_count: 0 },
      g: { numeric: false, min: null, max: null, valid_count: 0, missing_count: 0, unparsed_count: 0 },
    },
    rows: [
      { id: 'row-000001', index: 0, values: { a: 1, b: 10, flat: 5, g: 'x' } },
      { id: 'row-000002', index: 1, values: { a: 5, b: 50, flat: 5, g: 'y' } },
      { id: 'row-000003', index: 2, values: { a: 9, b: 90, flat: 5, g: 'x' } },
      { id: 'row-000004', index: 3, values: { a: 2, b: 20, flat: 5, g: 'y' } },
      { id: 'row-000005', index: 4, values: { a: 7, b: 70, flat: 5, g: 'x' } },
      { id: 'row-000006', index: 5, values: { a: 4, b: null, flat: 5, g: 'y' } },
    ],
  }
}

function renderChart(overrides: Partial<Parameters<typeof ParallelCoordinates>[0]> = {}) {
  const onPredicates = vi.fn()
  const props = {
    series: seriesFixture(),
    colorColumn: 'g',
    colorLevels: ['x', 'y'],
    selectedIds: new Set<string>(),
    predicates: [],
    onPredicates,
    onHoverRow: vi.fn(),
    ...overrides,
  }
  render(<ParallelCoordinates {...props} />)
  return props
}

describe('parallel coordinates', () => {
  it('renders only numeric columns as axes and names them', () => {
    renderChart()
    const svg = screen.getByRole('img', { name: /Parallel coordinates/ })
    // a, b and the constant 'flat' are numeric; the colour variable 'g' is not.
    expect(svg.querySelectorAll('.xpc__axisname').length).toBe(3)
    expect(svg.textContent).toContain('a')
    expect(svg.textContent).toContain('b')
    expect(svg.textContent).toContain('flat')
    expect(svg.textContent).not.toContain('g (')
  })

  it('states the sampling honestly in the caption', () => {
    renderChart()
    expect(screen.getByText(/6 of 6 rows drawn/)).toBeInTheDocument()
    expect(screen.getByText(/all rows\)/i)).toBeInTheDocument()
  })

  it('marks a constant column instead of faking a spread', () => {
    const series = seriesFixture()
    series.columns = ['a', 'flat']
    series.rows = series.rows.map((row) => ({ ...row, values: { a: row.values.a, flat: 5 } }))
    renderChart({ series })
    expect(screen.getAllByText(/constant \/ no spread/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/every value identical or unparsable/).length).toBeGreaterThan(0)
  })

  it('highlights the selection in copper and counts it in the legend', () => {
    renderChart({ selectedIds: new Set(['row-000001', 'row-000003']) })
    expect(screen.getByText(/selected \(2 drawn \/ 2 total\)/)).toBeInTheDocument()
    expect(document.querySelectorAll('.xpc__line--selected').length).toBe(2)
  })

  it('offers a reset control only when brushes are active', () => {
    const { predicates } = renderChart()
    expect(screen.queryByRole('button', { name: /Reset brushes/ })).toBeNull()
    const chart = screen.getByRole('img', { name: /Parallel coordinates/ }).closest('figure')
    expect(chart).not.toBeNull()
    void predicates
  })

  it('exposes accessible axis reorder buttons', () => {
    renderChart()
    const left = screen.getByRole('button', { name: 'Move a left' })
    expect(left).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move a right' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Move a right' }))
    // After the move, 'a' can move left again and 'b' takes the first slot.
    expect(screen.getByRole('button', { name: 'Move a left' })).toBeEnabled()
  })

  it('renders an explanatory placeholder without numeric axes', () => {
    const series = seriesFixture()
    series.columns = ['g']
    renderChart({ series })
    expect(screen.getByText(/No numeric columns are selected/)).toBeInTheDocument()
  })
})
