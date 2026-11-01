/**
 * FindingCard behaviour: collapsed summary, expansion revealing the finding's
 * real evidence at each explanation level (quick / context / technical), the
 * counts-only variant, explanation switching, and the "no findings" summary
 * line. Every assertion is on backend-supplied evidence, never placeholders.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { FindingCard, FindingSummaryLine } from '../src/components/FindingCard'
import { resetExplanationLevel } from '../src/lib/explain'
import { findingFixture } from './fixtures'

function renderCard(overrides: Partial<Parameters<typeof FindingCard>[0]> = {}) {
  const finding = findingFixture()
  const props = { finding, contextLabel: 'candidate', ...overrides }
  render(<FindingCard {...props} />)
  return props
}

function expandCard() {
  const toggle = screen.getByRole('button', { name: /Entity overlap between train and test splits/ })
  fireEvent.click(toggle)
  return toggle
}

function setLevel(label: 'Quick explanation' | 'More context' | 'Technical details') {
  fireEvent.click(screen.getByRole('button', { name: label }))
}

beforeEach(() => {
  resetExplanationLevel()
})

describe('collapsed and expanded evidence', () => {
  it('shows the summary collapsed, then reveals the real evidence when expanded', () => {
    renderCard()

    // Collapsed: title, rule id, context and evidence summary are visible.
    expect(screen.getByText('Entity overlap between train and test splits')).toBeInTheDocument()
    expect(screen.getByText('SS-ENT-001 · candidate')).toBeInTheDocument()
    expect(screen.getByText(/2 entity value\(s\) are shared between the splits/)).toBeInTheDocument()
    // The evidence body is not rendered yet.
    expect(screen.queryByText('What you can try next')).toBeNull()

    const toggle = expandCard()
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    // Default level is "Quick explanation": the count sentence, why it matters
    // and the counts with their explicit units — nothing else.
    expect(screen.getByText('Why this matters')).toBeInTheDocument()
    expect(screen.getByText('Fixture rationale: many test rows belong to a training entity.')).toBeInTheDocument()
    expect(
      screen.getByText('Shared entity values: 2 of 4 values'),
    ).toBeInTheDocument()
    expect(screen.queryByText('What you can try next')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()

    // "More context": the mechanism, an example from the evidence and a next step.
    setLevel('More context')
    expect(
      screen.getByText(/Rows for the same person, customer or device landed on both sides/),
    ).toBeInTheDocument()
    expect(screen.getByText('Example 1: C-1')).toBeInTheDocument()
    expect(screen.getByText(/row ids:/).parentElement).toHaveTextContent('row-000001, row-000002')
    expect(screen.getByText('side')).toBeInTheDocument()
    expect(screen.getByText('both splits')).toBeInTheDocument()
    expect(screen.getByText('What you can try next')).toBeInTheDocument()
    expect(screen.getByText('Use a group holdout on the entity column.')).toBeInTheDocument()
    expect(screen.getByText('Limitations of this check')).toBeInTheDocument()
    expect(screen.getByText('Fixture limitation: the entity column must be trustworthy.')).toBeInTheDocument()

    // "Technical details": the check's own description, the counts table with
    // its denominators, the example list, assumptions and limitations verbatim.
    setLevel('Technical details')
    expect(screen.getByText('What was found')).toBeInTheDocument()
    expect(screen.getByText('Fixture description of the observed overlap.')).toBeInTheDocument()

    const countsTable = screen.getByRole('table')
    const countRow = within(countsTable).getByRole('row', { name: /Shared entity values/ })
    expect(countRow).toHaveTextContent('2') // affected
    expect(countRow).toHaveTextContent('4') // denominator
    expect(countRow).toHaveTextContent('values')

    expect(screen.getByText('Evidence examples')).toBeInTheDocument()
    expect(screen.getByText('Example 1: C-1')).toBeInTheDocument()
    expect(screen.getByText('Assumptions')).toBeInTheDocument()
    expect(screen.getByText('Fixture assumption: each row belongs to exactly one entity.')).toBeInTheDocument()
    expect(screen.getByText('Limitations of this check')).toBeInTheDocument()

    // Collapsing removes the body again.
    fireEvent.click(toggle)
    expect(screen.queryByText('What you can try next')).toBeNull()
    expect(screen.queryByText('Why this matters')).toBeNull()
  })

  it('states when a finding carries no examples instead of inventing rows', () => {
    renderCard({ finding: findingFixture({ examples: [], example_total: 0, examples_truncated: false }) })

    expandCard()
    setLevel('More context')
    expect(
      screen.getByText('This finding reports counts only; no example rows are attached.'),
    ).toBeInTheDocument()
    expect(screen.queryByText('Example 1:')).toBeNull()
  })

  it('says when examples were truncated to the configured maximum', () => {
    renderCard({ finding: findingFixture({ examples_truncated: true }) })
    expandCard()
    setLevel('Technical details')
    expect(screen.getByText(/truncated to the configured maximum/)).toBeInTheDocument()
  })

  it('offers the evidence-view action only when a handler is given', () => {
    renderCard()
    expandCard()
    expect(screen.queryByRole('button', { name: /Open in evidence view/ })).toBeNull()
  })

  it('calls the handler when the evidence-view action is used', () => {
    const onOpenEvidence = vi.fn()
    renderCard({ onOpenEvidence })
    expandCard()
    fireEvent.click(screen.getByRole('button', { name: /Open in evidence view/ }))
    expect(onOpenEvidence).toHaveBeenCalledTimes(1)
  })
})

describe('explanation levels', () => {
  it('switches between the three levels one at a time and keeps the choice', () => {
    renderCard()
    const toggle = expandCard()

    // Quick is the default: what happened and why it matters, no tables or mechanism.
    expect(screen.getByText('Why this matters')).toBeInTheDocument()
    expect(screen.queryByText('How this happens')).toBeNull()
    expect(screen.queryByText('Counting definitions')).toBeNull()
    expect(screen.getByRole('button', { name: 'Quick explanation' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )

    // More context replaces quick — it never stacks.
    setLevel('More context')
    expect(screen.getByText('How this happens')).toBeInTheDocument()
    expect(screen.queryByText('Why this matters')).toBeNull()
    expect(screen.queryByText('Counting definitions')).toBeNull()
    expect(screen.getByRole('button', { name: 'More context' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )

    // Technical replaces context.
    setLevel('Technical details')
    expect(screen.getByText('Counting definitions')).toBeInTheDocument()
    expect(screen.queryByText('How this happens')).toBeNull()
    expect(screen.getByText('SS-ENT-001')).toBeInTheDocument()

    // The selection survives collapsing and re-expanding the same finding.
    fireEvent.click(toggle)
    fireEvent.click(toggle)
    expect(screen.getByRole('button', { name: 'Technical details' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.getByText('Counting definitions')).toBeInTheDocument()
  })

  it('renders run context on the technical level when the view supplies it', () => {
    renderCard({
      technical: {
        columns: [{ label: 'Entity', value: 'customer_id' }],
        settings: [{ label: 'Strip whitespace', value: 'on' }],
        metrics: [{ key: 'shared', label: 'Shared entity values', value: 2, unit: null }],
        notRun: [
          {
            rule_id: 'SS-CHR-001',
            title: 'Training records extend beyond the earliest test timestamp',
            status: 'not_evaluated',
            reason: 'No timestamp column was selected.',
            details: {},
          },
        ],
      },
    })
    expandCard()
    setLevel('Technical details')
    expect(screen.getByText(/Entity: customer_id/)).toBeInTheDocument()
    expect(screen.getByText(/Strip whitespace = on/)).toBeInTheDocument()
    expect(screen.getByText(/Shared entity values: 2/)).toBeInTheDocument()
    expect(screen.getByText(/No timestamp column was selected\./)).toBeInTheDocument()
  })
})

describe('FindingSummaryLine', () => {
  it('reports the severity breakdown, and a distinct message when there are no findings', () => {
    const { rerender } = render(<FindingSummaryLine findings={[]} />)
    expect(screen.getByText('No findings from the enabled checks.')).toBeInTheDocument()

    rerender(<FindingSummaryLine findings={[findingFixture()]} />)
    expect(screen.getByText('1 finding: 1 high', { exact: false })).toBeInTheDocument()

    rerender(
      <FindingSummaryLine
        findings={[
          findingFixture(),
          findingFixture({ rule_id: 'SS-EXD-001', title: 'Other', severity: 'low' }),
        ]}
      />,
    )
    expect(screen.getByText('2 findings: 1 high, 1 low', { exact: false })).toBeInTheDocument()
  })
})
