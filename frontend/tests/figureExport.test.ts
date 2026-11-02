/**
 * Figure export provenance: predicate descriptions follow the documented
 * combination rule (union within a column, intersect across columns), the
 * manifest carries dataset identity and a no-raw-rows privacy note, and
 * filenames are safe and traceable.
 */
import { describe, expect, it } from 'vitest'

import {
  describePredicates,
  exportFilename,
  figureManifest,
  captionLines,
  type FigureContext,
} from '../src/explore/figureExport'
import type { ExploreSchema, SelectionState } from '../src/api/types'

function schemaFixture(): ExploreSchema {
  return {
    dataset: {
      dataset_id: 'ds-1',
      name: 'panel.csv',
      source: 'demo',
      is_synthetic: true,
      fingerprint_sha256: 'a'.repeat(64),
      row_count: 240,
      column_count: 8,
      demo_id: null,
    },
    row_id_scheme: 'row-000001…',
    row_count: 240,
    columns: [],
    numeric_columns: ['a', 'b'],
    color_candidates: [],
    suggested_color_column: null,
    split: null,
  }
}

function contextFixture(selection: Partial<SelectionState> = {}): FigureContext {
  return {
    schema: schemaFixture(),
    selection: {
      predicates: [],
      totalSelected: 0,
      ids: new Set(),
      idsTruncated: false,
      status: 'idle',
      error: null,
      ...selection,
    },
    appVersion: '1.0.0',
    generatedAtUtc: '2026-11-03T00:00:00Z',
  }
}

describe('predicate descriptions', () => {
  it('unions ranges on the same column and intersects across columns', () => {
    const text = describePredicates([
      { column: 'a', kind: 'range', min: 0, max: 5 },
      { column: 'a', kind: 'range', min: 8, max: 9 },
      { column: 'b', kind: 'range', min: 1, max: 2 },
    ])
    expect(text).toContain('a ∈ [0, 5] OR a ∈ [8, 9]')
    expect(text).toContain('AND')
    expect(text).toContain('b ∈ [1, 2]')
  })

  it('describes value predicates with their levels', () => {
    const text = describePredicates([{ column: 'g', kind: 'values', values: ['x', 'y', 'z'] }])
    expect(text).toBe('g ∈ {x, y, z}')
  })
})

describe('figure manifest', () => {
  it('carries dataset identity, selection counts and the privacy note', () => {
    const context = contextFixture({
      predicates: [{ column: 'a', kind: 'range', min: 1, max: 4 }],
      totalSelected: 80,
    })
    const manifest = figureManifest(
      {
        figureId: 'parallel-coordinates',
        title: 'Parallel coordinates — a, b',
        settings: '2 numeric axes',
        counts: '80 of 240 rows drawn',
        sampling: 'All rows are drawn.',
      },
      context,
    )
    expect(manifest.figure_id).toBe('parallel-coordinates')
    expect((manifest.dataset as Record<string, unknown>).sha256).toBe('a'.repeat(64))
    expect(manifest.active_selection).toMatchObject({ total_selected: 80, population: 240 })
    expect((manifest.privacy as Record<string, unknown>).raw_rows_embedded).toBe(false)
    expect((manifest.caption as string[]).join(' ')).toContain('80 of 240')
  })

  it('states when no selection is active', () => {
    const lines = captionLines(
      { figureId: 'x', title: 'T', settings: 's', counts: 'c' },
      contextFixture(),
    )
    expect(lines.join(' ')).toContain('Active selection: none')
  })
})

describe('export filenames', () => {
  it('are prefixed, dataset-scoped and timestamped without colons', () => {
    const name = exportFilename('scatter', 'repeated_entity.csv', 'svg')
    expect(name).toMatch(/^splitscope_scatter_repeated_entity_\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.svg$/)
  })
})
