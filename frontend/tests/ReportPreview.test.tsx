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

describe('dossier preview — S10-B causal sections', () => {
  const causalSections: Record<string, DossierSection> = {
    causal_graph: section('causal_graph', 'Causal graph specification', {
      graph_id: 'cgraph-1',
      graph_revision: 3,
      graph_spec_fingerprint_sha256: 'b'.repeat(64),
      name: 'Retention DAG',
      description: null,
      analysis: { treatment: 'tenure', outcome: 'churn' },
      nodes: [{ node_id: 'age', label: 'Age', column: 'age', observed: true, kind: 'covariate', description: null }],
      edges: [{ source: 'age', target: 'churn', rationale: '<confounder &x>', reference: null }],
      assumptions: [{ rationale: 'No unmeasured confounding assumed.' }],
      caveat: 'An edge is an assumption, not empirical proof.',
    }),
    causal_estimation: section('causal_estimation', 'Causal effect estimation', {
      runs: [
        {
          run_id: 'run-est-1',
          created_at_utc: '2026-11-07T00:00:00+00:00',
          estimand: 'ate',
          cohort: { rows_final: 1200, treated_rows: 600, control_rows: 600, missing_data_policy: 'complete_case' },
          estimators: [
            {
              estimator: 'aipw',
              status: 'estimated',
              estimate: 1.234,
              units: 'outcome_units',
              interval: { ci_lower: 0.9, ci_upper: 1.6, interval_level: 0.95 },
              warnings: ['A warning from the estimator.'],
            },
            { estimator: 'ipw', status: 'failed', failure: { reason: 'degenerate arm' } },
          ],
          scope_note: 'Estimates are conditional on assumptions.',
        },
      ],
      total: 1,
      interpretation_note: 'Estimates are ATEs on one cohort.',
    }),
    subgroups: section('subgroups', 'Subgroup and heterogeneity', {
      run_id: 'run-sub-1',
      subgroup: { column: 'region', definition: 'Observed levels', intent: 'exploratory' },
      overall: { estimate: 1.5, ci_lower: 1.1, ci_upper: 1.9 },
      groups: [
        { label: 'east', rows: 300, treated_rows: 60, control_rows: 240, estimate: 1.4, ci_lower: 0.8, ci_upper: 2.0, status: 'estimated', warnings: [] },
        { label: 'tiny', rows: 12, treated_rows: 2, control_rows: 10, estimate: null, ci_lower: null, ci_upper: null, status: 'unavailable', warnings: [] },
      ],
      contrasts: [{ a: 'east', b: 'tiny', difference: 1.4, ci_lower: -0.5, ci_upper: 3.3 }],
      notes: [{ code: 'multiple_comparisons', text: 'Several subgroup estimates are inspected at once.' }],
      scope_note: 'Exploratory evidence about this sample.',
    }),
    robustness: section('robustness', 'Robustness and sensitivity', {
      run_id: 'run-rob-1',
      original: { estimate: 1.5 },
      experiment: 'unmeasured_confounder_simulation',
      parameters: { estimator: 'regression_adjustment', prevalence: 0.3 },
      distribution: null,
      repetition_count: null,
      full_series_included: false,
      failures: [],
      warnings: ['This is a hypothetical scenario analysis, not a bound.'],
      method_note: 'The grid shows the scenario.',
      scope_note: 'None of them proves the causal assumptions.',
    }),
    what_if: section('what_if', 'Model-based what-if scenarios', {
      run_id: 'run-wif-1',
      model_specification: { kind: 'regression_adjustment_outcome_model', units: 'outcome_units' },
      profile_scenario: {
        treated_prediction: 14.9,
        control_prediction: 13.2,
        contrast: 1.7,
        disclosures: [{ field: 'age', source: 'explicit', value: 55 }],
      },
      cohort_scenario: { contrast: 1.7 },
      warnings: ['It is not an observed outcome, not an individual counterfactual, and not an interval-bearing estimate.'],
      scope_note: 'Conditional model expectation.',
    }),
    methodology: section('methodology', 'Methodology', {
      methodology_version: '1.0.0',
      presentation: 'concise',
      paragraphs: [
        { title: 'Data source and sample', text: "The analysis used 'panel.csv'." },
        { title: 'Causal identification and estimation', text: 'Not evaluated — no qualifying analysis run was included in this dossier.' },
      ],
      sources: {},
      scope_note: 'Missing inputs are marked explicitly.',
    }),
  }

  function causalDossier(): DossierReport {
    const base = dossier()
    return {
      ...base,
      schema_version: '1.1.0',
      sections: causalSections,
      included_sections: Object.keys(causalSections),
    }
  }

  it('renders the causal graph section with its assumption caveat', () => {
    render(<ReportPreview report={causalDossier()} />)
    expect(screen.getByRole('heading', { name: 'Causal graph specification' })).toBeInTheDocument()
    expect(screen.getByText('An edge is an assumption, not empirical proof.')).toBeInTheDocument()
    expect(screen.getByText('<confounder &x>')).toBeInTheDocument()
  })

  it('renders estimation rows exactly as stored, including the failed estimator', () => {
    render(<ReportPreview report={causalDossier()} />)
    expect(screen.getByText('1.234')).toBeInTheDocument()
    expect(screen.getByText('0.900 to 1.600 (level 0.95)')).toBeInTheDocument()
    expect(screen.getByText('failed')).toBeInTheDocument()
    expect(screen.getByText('degenerate arm')).toBeInTheDocument()
  })

  it('renders subgroup unavailable rows as unavailable, never zero', () => {
    render(<ReportPreview report={causalDossier()} />)
    expect(screen.getByText('unavailable')).toBeInTheDocument()
    expect(screen.getByText('Several subgroup estimates are inspected at once.')).toBeInTheDocument()
  })

  it('keeps the sensitivity caveat and the what-if counterfactual boundary', () => {
    render(<ReportPreview report={causalDossier()} />)
    expect(screen.getByText('This is a hypothetical scenario analysis, not a bound.')).toBeInTheDocument()
    expect(
      screen.getByText('It is not an observed outcome, not an individual counterfactual, and not an interval-bearing estimate.'),
    ).toBeInTheDocument()
  })

  it('renders methodology paragraphs including the not-evaluated state', () => {
    render(<ReportPreview report={causalDossier()} />)
    expect(screen.getByRole('heading', { name: 'Methodology' })).toBeInTheDocument()
    expect(screen.getByText("The analysis used 'panel.csv'.")).toBeInTheDocument()
    expect(screen.getByText('Not evaluated — no qualifying analysis run was included in this dossier.')).toBeInTheDocument()
  })
})
