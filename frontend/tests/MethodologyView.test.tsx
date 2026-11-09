/**
 * View E - Methodology & Interpretation.
 *
 * Pins the deterministic interpretation sentence, the provenance fields, the
 * exclusions, the known synthetic effect (kept separate from the estimate) and
 * the failed-estimator disclosure.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { MethodologyView } from '../src/estimation/MethodologyView'
import { failedResult, runPayload } from './estimationFixtures'

describe('MethodologyView', () => {
  it('states the estimand, cohort and method without asserting causality', () => {
    render(<MethodologyView payload={runPayload()} knownEffect={null} />)
    const statement = screen.getByTestId('interpretation').textContent ?? ''
    expect(statement).toContain('Under the assumptions encoded in the selected DAG')
    expect(statement).toContain('estimated average treatment effect')
    expect(statement).toContain('2.000 outcome units')
    expect(statement).toContain('120 analysed rows')
    expect(statement).toContain('not a proof that the effect is causal')
  })

  it('reports each estimator interval, or its unavailability, in the sentence', () => {
    const payload = runPayload()
    const ipw = payload.results[1]
    render(
      <MethodologyView
        payload={{
          ...payload,
          results: [
            payload.results[0],
            {
              ...ipw,
              uncertainty: {
                ...ipw.uncertainty!,
                status: 'unavailable',
                standard_error: null,
                ci_lower: null,
                ci_upper: null,
                unavailable_reason: 'Too few replicates succeeded.',
              },
            },
          ],
        }}
        knownEffect={null}
      />,
    )
    const statement = screen.getByTestId('interpretation').textContent ?? ''
    expect(statement).toContain('(interval unavailable)')
    expect(statement).toContain('1.700 to 2.300')
    expect(screen.getByTestId('methodology-view').textContent).toContain(
      'Too few replicates succeeded.',
    )
  })

  it('states the cohort accounting, exclusions and cross-fitting configuration', () => {
    render(<MethodologyView payload={runPayload()} knownEffect={null} />)
    expect(screen.getByText('missing outcome value')).toBeInTheDocument()
    expect(screen.getByText('5 folds, shuffled rows')).toBeInTheDocument()
    expect(screen.getByText('complete case')).toBeInTheDocument()
  })

  it('carries the provenance the backend returned', () => {
    render(<MethodologyView payload={runPayload()} knownEffect={null} />)
    expect(screen.getByText('run-s9b-fixture')).toBeInTheDocument()
    expect(screen.getByText('a'.repeat(64))).toBeInTheDocument()
    expect(screen.getByText('b'.repeat(64), { selector: '.estmethods__hash' })).toBeInTheDocument()
    expect(screen.getByText(/2026-11-06T09:00:00\+00:00/)).toBeInTheDocument()
    expect(screen.getByText(/1\.0\.0 · schema 1\.0\.0/)).toBeInTheDocument()
    expect(screen.getByText('3.11.9')).toBeInTheDocument()
  })

  it('surfaces a failed estimator in the failure paragraph', () => {
    render(
      <MethodologyView
        payload={runPayload({ results: [failedResult('aipw', 'The outcome model diverged.')] })}
        knownEffect={null}
      />,
    )
    const failures = screen.getByTestId('methodology-failures').textContent ?? ''
    expect(failures).toContain('1 of 1 estimators failed')
    expect(failures).toContain('The outcome model diverged.')
    expect(failures).toContain('never treated as a zero effect')
  })

  it('keeps the known synthetic effect separate from the estimate', () => {
    render(
      <MethodologyView
        payload={runPayload()}
        knownEffect={{
          value: 1.5,
          note: 'This figure is the population parameter of the simulator, not a result of this run.',
        }}
      />,
    )
    const note = screen.getByTestId('known-effect').textContent ?? ''
    expect(note).toContain('Known data-generating effect: 1.500 outcome units')
    expect(note).toContain('not a result of this run')
  })

  it('names the defaults the server applied', () => {
    render(<MethodologyView payload={runPayload()} knownEffect={null} />)
    expect(screen.getByText(/No train\/test partition named/)).toBeInTheDocument()
  })
})
