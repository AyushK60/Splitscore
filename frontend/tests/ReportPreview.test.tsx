/**
 * Dossier renderer contract: the preview renders the server payload rather than
 * recomposing numbers in the browser. The tests pin the visible honesty states:
 * real counts and denominators, an unavailable section that keeps its reason,
 * no raw-data promise, escaped study text, and a TOC limited to included
 * sections.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ReportPreview } from '../src/components/report/ReportPreview'
import type {
  DossierReport,
  DossierReproducibility,
  DossierSection,
  DossierSummary,
  SplitSummary,
} from '../src/api/types'

const split: SplitSummary = {
  strategy_id: 'existing',
  label: 'Existing split column',
  kind: 'existing',
  requested_test_fraction: null,
  achieved_test_fraction: 0.2542,
  train_rows: 179,
  test_rows: 61,
  seed: null,
  split_column: 'split',
  train_value: 'train',
  test_value: 'test',
  proportion_note: null,
  notes: [],
  assignment_id: null,
}

const summary: DossierSummary = {
  study_title: '<script>alert("study")</script>',
  objective: 'Estimate whether the declared split separates entities.',
  design: 'Retrospective split audit.',
  dataset_name: 'panel.csv',
  synthetic: true,
  split,
  audit_headline:
    '1 finding(s) across 6 evaluated check(s): 1 high. 5 check(s) did not run and are listed separately.',
  findings_total: 1,
  findings_by_severity: { high: 1 },
  evaluated_rule_count: 6,
  not_evaluated_count: 5,
  key_findings: [
    { rule_id: 'SS-ENT-001', title: 'Entity overlap between train and test', severity: 'high' },
  ],
  analyses: [
    { key: 'audit', label: 'Leakage audit', run_id: 'run-audit', status: 'included' },
    { key: 'comparison', label: 'Split comparison', run_id: null, status: 'not_run' },
  ],
  model_count: 0,
  comparison_available: false,
  cautions: [
    'The split comparison was not run. Absence of a comparison is not evidence of equivalence.',
  ],
  note: 'This summary synthesises only the sections and runs named in the request.',
}

const reproducibility: DossierReproducibility = {
  report_schema_version: '1.0.0',
  app: { name: 'SplitScope', version: '1.0.0' },
  generated_at_utc: '2026-11-04T10:00:00+00:00',
  dataset_id: 'ds-test',
  dataset_name: 'panel.csv',
  dataset_sha256: 'a'.repeat(64),
  row_count: 240,
  column_count: 8,
  audit_run_id: 'run-audit',
  comparison_run_id: null,
  model_run_ids: [],
  model_environments: [],
  deterministic_note: 'Deterministic for the listed run IDs and dataset fingerprint.',
  storage_note: 'Runs live in the server session store; this dossier is a portable snapshot.',
}

function section(
  id: string,
  title: string,
  data: DossierSection['data'],
  overrides: Partial<DossierSection> = {},
): DossierSection {
  return {
    id,
    title,
    description: `${title} description from the server catalogue.`,
    included: true,
    available: true,
    reason: null,
    data,
    ...overrides,
  }
}

function dossier(): DossierReport {
  const sections: Record<string, DossierSection> = {
    summary: section('summary', 'Executive summary', summary),
    audit: section('audit', 'Leakage audit', null, {
      available: false,
      reason: 'No audit run was included in this request.',
    }),
    reproducibility: section('reproducibility', 'Reproducibility', reproducibility),
  }
  return {
    report_kind: 'dossier',
    schema_version: '1.0.0',
    generated_at_utc: '2026-11-04T10:00:00+00:00',
    app: { name: 'SplitScope', version: '1.0.0' },
    title: 'Evidence dossier — panel.csv',
    dataset: {
      dataset_id: 'ds-test',
      name: 'panel.csv',
      is_synthetic: true,
      source: 'demo',
      sha256: 'a'.repeat(64),
      row_count: 240,
      column_count: 8,
    },
    request: {
      sections: ['summary', 'audit', 'reproducibility'],
      audit_run_id: 'run-audit',
      comparison_run_id: null,
      model_run_ids: [],
    },
    summary,
    sections,
    included_sections: ['summary', 'audit', 'reproducibility'],
    integrity: {
      raw_data_embedded: false,
      row_predictions_embedded: false,
      bounded_evidence_embedded: true,
      note: 'The full uploaded dataset and row-level test predictions are not embedded.',
    },
    reproducibility,
    section_catalogue: [
      { id: 'summary', title: 'Executive summary', description: '' },
      { id: 'audit', title: 'Leakage audit', description: '' },
      { id: 'reproducibility', title: 'Reproducibility', description: '' },
    ],
  }
}

describe('dossier preview', () => {
  it('renders server counts, split denominators and the audit headline', () => {
    render(<ReportPreview report={dossier()} />)
    expect(screen.getByRole('heading', { level: 1, name: 'panel.csv' })).toBeInTheDocument()
    expect(screen.getByText('179 train / 61 test rows · 25.4% test')).toBeInTheDocument()
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
    expect(screen.getByText('6')).toBeInTheDocument()
    expect(screen.getAllByText('5').length).toBeGreaterThan(0)
    expect(screen.getByText(/1 finding\(s\) across 6 evaluated check\(s\)/)).toBeInTheDocument()
    expect(screen.getByText('SS-ENT-001')).toBeInTheDocument()
  })

  it('keeps an unavailable requested section with its server reason', () => {
    render(<ReportPreview report={dossier()} />)
    expect(screen.getByText('Not available in this dossier.')).toBeInTheDocument()
    expect(screen.getByText('No audit run was included in this request.')).toBeInTheDocument()
  })

  it('escapes study text rather than injecting markup', () => {
    const { container } = render(<ReportPreview report={dossier()} />)
    expect(container.querySelector('script')).toBeNull()
    expect(screen.getByText('<script>alert("study")</script>')).toBeInTheDocument()
  })

  it('builds the contents list only from included sections', () => {
    render(<ReportPreview report={dossier()} />)
    const toc = screen.getByRole('navigation', { name: 'Dossier sections' })
    expect(toc.querySelectorAll('a')).toHaveLength(3)
    expect(toc).toHaveTextContent('Executive summary')
    expect(toc).toHaveTextContent('Leakage audit')
    expect(toc).not.toHaveTextContent('Model Lab')
  })

  it('states the export integrity limits and the no-causation boundary', () => {
    render(<ReportPreview report={dossier()} />)
    expect(screen.getByText(/full uploaded dataset and row-level test predictions/)).toBeInTheDocument()
    expect(screen.getByText(/never a guarantee that data is safe/)).toBeInTheDocument()
    expect(screen.queryByText(/causal effect/i)).not.toBeInTheDocument()
  })
})
