/**
 * Predictive diagnostic components with fixed fixtures.
 *
 * These tests assert the claims the UI makes: the partition, interval and
 * method labels, empty/unsupported states, and that plotted points come from the
 * supplied arrays. Numerical correctness is covered by the backend oracles.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  ImportanceSection,
  InfluenceSection,
  PrPlot,
  QqPlot,
  ReliabilityPlot,
  SubgroupTable,
} from '../src/components/PredictiveDiagnostics'

describe('predictive diagnostic components', () => {
  it('plots the precision-recall curve with AP, prevalence and counts', () => {
    const { container } = render(
      <PrPlot
        curve={{
          precision: [1, 0.8, 0.5],
          recall: [0, 0.5, 1],
          average_precision: 0.71,
          positive_count: 24,
          negative_count: 36,
          prevalence: 0.4,
          n_points: 3,
          method: 'test fixture',
        }}
      />,
    )

    expect(screen.getByRole('img', { name: /precision-recall/i })).toBeInTheDocument()
    expect(container.querySelector('polyline')).not.toBeNull()
    expect(screen.getByText('AP 0.7100')).toBeInTheDocument()
    expect(screen.getByText('prevalence 40.0%')).toBeInTheDocument()
  })

  it('plots only non-empty calibration bins and states the empty case', () => {
    const { container, rerender } = render(
      <ReliabilityPlot
        entries={[
          {
            bin_low: 0,
            bin_high: 0.1,
            count: 5,
            mean_predicted: 0.05,
            observed_rate: 0,
            observed_rate_low: 0,
            observed_rate_high: 0.45,
          },
          {
            bin_low: 0.4,
            bin_high: 0.5,
            count: 8,
            mean_predicted: 0.45,
            observed_rate: 0.5,
            observed_rate_low: 0.25,
            observed_rate_high: 0.75,
          },
          {
            bin_low: 0.5,
            bin_high: 0.6,
            count: 0,
            mean_predicted: null,
            observed_rate: null,
            observed_rate_low: null,
            observed_rate_high: null,
          },
        ]}
      />,
    )

    expect(screen.getByRole('img', { name: /calibration reliability/i })).toBeInTheDocument()
    expect(container.querySelectorAll('circle')).toHaveLength(2)

    rerender(<ReliabilityPlot entries={[]} />)
    expect(screen.getByText('No non-empty calibration bins were returned.')).toBeInTheDocument()
  })

  it('plots Q-Q points and the normal reference line', () => {
    const { container } = render(
      <QqPlot
        qq={{
          applicable: true,
          n: 5,
          theoretical: [-1, -0.5, 0, 0.5, 1],
          sample: [-1.2, -0.4, 0.1, 0.6, 1.1],
          reference_intercept: 0,
          reference_slope: 1.1,
        }}
      />,
    )

    expect(screen.getByRole('img', { name: /Normal Q-Q/i })).toBeInTheDocument()
    expect(container.querySelectorAll('circle')).toHaveLength(5)
    expect(container.querySelectorAll('line').length).toBeGreaterThanOrEqual(3)
  })

  it('shows an explicit unsupported state for non-OLS influence', () => {
    render(
      <InfluenceSection
        influence={{ applicable: false, reason: 'Ridge is a penalized estimator.' }}
      />,
    )
    expect(screen.getByText('Influence diagnostics not applicable')).toBeInTheDocument()
    expect(screen.getByText('Ridge is a penalized estimator.')).toBeInTheDocument()
  })

  it('renders OLS coefficients and influence evidence with the in-sample warning', () => {
    const influence = {
      applicable: true,
      partition: 'fit + validation (refit rows)',
      model: 'OLS linear regression',
      n: 20,
      parameters: 2,
      residual_df: 18,
      max_leverage: 0.3,
      max_cooks: 0.7,
      thresholds: { leverage_2p_over_n: 0.2 },
      counts: { above_leverage_2p: 1, above_cooks_1: 0 },
      coefficients: [
        {
          term: 'const',
          estimate: 1,
          std_error: 0.2,
          ci_low: 0.58,
          ci_high: 1.42,
          statistic: 5,
          p_value: 0.0001,
        },
        {
          term: 'x1',
          estimate: 2,
          std_error: 0.4,
          ci_low: 1.16,
          ci_high: 2.84,
          statistic: 5,
          p_value: 0.0001,
        },
      ],
      points: [
        {
          row_id: 'row-000001',
          fitted: 1.1,
          residual: 0.2,
          leverage: 0.3,
          standardized_residual: 1.1,
          cooks_distance: 0.7,
        },
      ],
      top_influence: [
        {
          row_id: 'row-000001',
          fitted: 1.1,
          residual: 0.2,
          leverage: 0.3,
          standardized_residual: 1.1,
          cooks_distance: 0.7,
        },
      ],
      method: 'Leverage h_ii and Cook’s distance.',
      note: 'In-sample OLS diagnostics on the refit rows.',
    }
    render(<InfluenceSection influence={influence} />)
    expect(screen.getByText('OLS influence (in-sample)')).toBeInTheDocument()
    expect(screen.getAllByText('x1').length).toBeGreaterThan(0)
    expect(screen.getByText('row-000001')).toBeInTheDocument()
    expect(screen.getByText(/not held-out performance/i)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Leverage versus standardized residual/i })).toBeInTheDocument()
  })

  it('renders permutation importance with its test-partition caveat', () => {
    render(
      <ImportanceSection
        importance={{
          applicable: true,
          partition: 'test',
          n: 60,
          repeats: 5,
          metric: 'balanced_accuracy_drop',
          baseline_score: 0.5,
          rows: [
            { feature: 'x1', importance_mean: 0.12, importance_sd: 0.03 },
            { feature: 'x2', importance_mean: -0.01, importance_sd: 0.02 },
          ],
          method: 'Each predictor is permuted in the sealed test partition.',
          note: 'Descriptive only.',
        }}
      />,
    )
    expect(screen.getByText('Permutation importance — test partition')).toBeInTheDocument()
    expect(screen.getByText('x1')).toBeInTheDocument()
    expect(screen.getByText(/correlated predictors can share or mask importance/i)).toBeInTheDocument()
    expect(screen.getByText(/Not a causal effect/i)).toBeInTheDocument()
  })

  it('shows why permutation importance was skipped for a dummy baseline', () => {
    render(
      <ImportanceSection
        importance={{ applicable: false, reason: 'Not informative for a dummy baseline.' }}
      />,
    )
    expect(screen.getByText('Permutation importance not computed')).toBeInTheDocument()
    expect(screen.getByText('Not informative for a dummy baseline.')).toBeInTheDocument()
  })

  it('renders subgroup denominators, intervals and the empty state', () => {
    render(
      <SubgroupTable
        subgroup={{
          column: 'segment',
          partition: 'test',
          test_rows: 60,
          grouped_rows: 60,
          outside_bins: 0,
          minimum_recommended_rows: 20,
          interval_level: 0.95,
          outcome_measure: 'positive-class rate',
          note: 'Descriptive.',
          rows: [
            {
              group: 'alpha',
              n: 25,
              metric_denominator: 25,
              share: 25 / 60,
              metric_name: 'accuracy',
              metric: 0.4,
              ci_low: 0.23,
              ci_high: 0.59,
              outcome_mean: 0.6,
              outcome_measure: 'positive-class rate',
              warning: null,
            },
            {
              group: 'empty',
              n: 0,
              metric_denominator: 0,
              share: 0,
              metric_name: 'accuracy',
              metric: null,
              ci_low: null,
              ci_high: null,
              outcome_mean: null,
              outcome_measure: 'positive-class rate',
              warning: 'empty subgroup',
            },
          ],
        }}
      />,
    )
    expect(screen.getByRole('columnheader', { name: '95% interval' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'positive-class rate' })).toBeInTheDocument()
    expect(screen.getByText('23.0% – 59.0%')).toBeInTheDocument()
    expect(screen.getByText('empty subgroup')).toBeInTheDocument()
    expect(screen.getByText(/Each n is the denominator/i)).toBeInTheDocument()
  })
})
