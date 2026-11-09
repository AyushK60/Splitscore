/**
 * The run gate: one derivation answers "can I run the audit?" for the Data view
 * and the Results view alike. These tests pin the contract that no run button is
 * ever offered with a missing prerequisite, and that a caution (rows excluded
 * from the split, reported by the audit) never masquerades as a blocker.
 */
import { describe, expect, it } from 'vitest'

import { readiness, strategyName, type ReadinessInput } from '../src/lib/readiness'
import { columnTypesFixture, rolesFixture, validationFixture } from './fixtures'

function input(overrides: Partial<ReadinessInput> = {}): ReadinessInput {
  return {
    roles: rolesFixture(),
    validation: validationFixture(),
    suggestionsConfirmed: true,
    splitMode: 'existing',
    generate: null,
    columnTypes: columnTypesFixture(),
    ...overrides,
  }
}

describe('readiness: shared prerequisites', () => {
  it('is ready when every question is answered and the server has confirmed the roles', () => {
    const result = readiness(input())

    expect(result.ready).toBe(true)
    expect(result.blockers).toEqual([])
    expect(result.runLabel).toBe('Run audit')
  })

  it('blocks until the entry question is answered', () => {
    const result = readiness(input({ splitMode: null }))

    expect(result.ready).toBe(false)
    expect(result.blockers.join(' ')).toContain('does the file already say which rows are training and testing')
    expect(result.splitDescription).toBe('not chosen yet')
  })

  it('blocks until the user vouches for the guessed roles', () => {
    const result = readiness(input({ suggestionsConfirmed: false }))

    expect(result.ready).toBe(false)
    expect(result.blockers).toContain(
      'Confirm the suggested column roles - accept them or adjust them - before running the audit.',
    )
  })

  it('blocks while the server has not seen the current roles', () => {
    expect(readiness(input({ validation: null })).blockers).toContain(
      'The server has not confirmed the current column roles yet.',
    )
    expect(readiness(input({ validationPending: true })).blockers).toContain(
      'The server has not confirmed the current column roles yet.',
    )
  })

  it('turns each validation error into a blocker that names the fix', () => {
    const result = readiness(
      input({
        validation: validationFixture({
          ok: false,
          issues: [
            {
              code: 'ROLE_MISSING',
              message: 'A stratified split needs a target column.',
              severity: 'error',
              column: null,
              hint: 'Choose a target column in the guided questions.',
            },
          ],
        }),
      }),
    )

    expect(result.ready).toBe(false)
    expect(result.blockers).toEqual([
      'A stratified split needs a target column. Choose a target column in the guided questions.',
    ])
  })

  it('blocks when a column is both a feature and a special role', () => {
    const result = readiness(
      input({ roles: rolesFixture({ features: ['tenure_months', 'churned'], target: 'churned' }) }),
    )

    expect(result.ready).toBe(false)
    expect(result.blockers.join(' ')).toContain('churned is both a feature and another role')
  })

  it('blocks when nothing is selected to compare', () => {
    const result = readiness(input({ roles: rolesFixture({ features: [] }) }))

    expect(result.ready).toBe(false)
    expect(result.blockers).toContain(
      'No feature columns are selected, so there is nothing to compare.',
    )
  })
})

describe('readiness: existing split path', () => {
  it('needs a split column before it can run', () => {
    const result = readiness(
      input({ roles: rolesFixture({ split: null, split_train_value: null, split_test_value: null }) }),
    )

    expect(result.ready).toBe(false)
    expect(result.blockers.join(' ')).toContain('No split column is selected')
    expect(result.splitDescription).toBe('the split column in the file')
  })

  it('needs both labels mapped before it can run', () => {
    const result = readiness(
      input({ roles: rolesFixture({ split_test_value: null }) }),
    )

    expect(result.ready).toBe(false)
    expect(result.blockers.join(' ')).toContain('Map the values of split to train and test')
  })

  it('describes the mapping it will audit', () => {
    expect(readiness(input()).splitDescription).toBe('split = train (train) / test (test)')
  })

  it('treats rows without either label as a reported caution, not a blocker', () => {
    const columnTypes = columnTypesFixture()
    columnTypes.split = { ...columnTypes.split, missing_count: 12, missing_ratio: 0.1 }

    const result = readiness(input({ columnTypes }))

    expect(result.ready).toBe(true)
    expect(result.cautions).toHaveLength(1)
    expect(result.cautions[0]).toContain('12 rows have an empty split value')
  })
})

describe('readiness: generated split path', () => {
  it('needs a strategy before it can run', () => {
    const result = readiness(input({ splitMode: 'generate', generate: null }))

    expect(result.ready).toBe(false)
    expect(result.blockers).toContain('Choose how to split the rows - no strategy is selected yet.')
    expect(result.runLabel).toBe('Run audit (generate the split now)')
  })

  it('a random holdout needs no extra column', () => {
    const result = readiness(
      input({
        splitMode: 'generate',
        generate: { kind: 'random', label: 'Random holdout', test_fraction: 0.2, seed: 7 },
      }),
    )

    expect(result.ready).toBe(true)
    expect(result.splitDescription).toBe('Random holdout generated now (20% test, seed 7)')
  })

  it('a stratified holdout needs a target column', () => {
    const result = readiness(
      input({
        roles: rolesFixture({ target: null }),
        splitMode: 'generate',
        generate: { kind: 'stratified', label: 'Stratified holdout', test_fraction: 0.2, seed: 7 },
      }),
    )

    expect(result.ready).toBe(false)
    expect(result.blockers).toContain('A stratified holdout needs a target column to stratify by.')
  })

  it('a group holdout needs an entity column', () => {
    const result = readiness(
      input({
        roles: rolesFixture({ entity: null }),
        splitMode: 'generate',
        generate: { kind: 'group', label: 'Group holdout', test_fraction: 0.2, seed: 7 },
      }),
    )

    expect(result.ready).toBe(false)
    expect(result.blockers).toContain('A group holdout needs an entity/group column.')
  })

  it('a chronological holdout needs a timestamp column', () => {
    const result = readiness(
      input({
        splitMode: 'generate',
        generate: { kind: 'chronological', label: 'Chronological holdout', test_fraction: 0.2, seed: 7 },
      }),
    )

    expect(result.ready).toBe(false)
    expect(result.blockers).toContain('A chronological holdout needs a timestamp column.')
  })
})

describe('readiness: column consistency is not workflow readiness', () => {
  it('reports consistent columns while the entry question is still unanswered', () => {
    const result = readiness(input({ splitMode: null }))

    expect(result.columnState).toBe('consistent')
    expect(result.columnSummary).toContain('No column holds two roles')
    // The audit is not ready, but not because of the columns.
    expect(result.ready).toBe(false)
    expect(result.workflowBlockers.join(' ')).toContain('Answer the first question')
    expect(result.columnBlockers).toEqual([])
  })

  it('does not let a successful validation hide missing split labels', () => {
    // Simulates the stale success that used to look like readiness: the server
    // saw a configuration without a split, and the user has since chosen one.
    const result = readiness(
      input({
        roles: rolesFixture({ split: 'split', split_train_value: null, split_test_value: null }),
        splitMode: 'existing',
      }),
    )

    expect(result.columnState).toBe('consistent')
    expect(result.ready).toBe(false)
    expect(result.splitState).toBe('incomplete')
    expect(result.workflowBlockers.join(' ')).toContain('Map the values of split to train and test')
  })

  it('blocks equal train and test labels in plain language', () => {
    const result = readiness(
      input({
        roles: rolesFixture({ split_train_value: 'test', split_test_value: 'test' }),
      }),
    )

    expect(result.ready).toBe(false)
    expect(result.splitState).toBe('incomplete')
    expect(result.workflowBlockers.join(' ')).toContain('Choose different values for train and test')
  })

  it('summarises column problems instead of repeating the inline validation text', () => {
    const result = readiness(
      input({
        validation: validationFixture({
          ok: false,
          issues: [
            {
              code: 'role_overlap',
              message: 'Column "churned" is assigned both as a feature and as the target column.',
              severity: 'error',
              column: 'churned',
              hint: 'Remove it from the feature list.',
            },
          ],
        }),
      }),
    )

    expect(result.columnState).toBe('conflicted')
    // The full text is available to views without the editor…
    expect(result.blockers[0]).toContain('assigned both as a feature')
    // …while the Data view's run gate points at it instead of duplicating it.
    expect(result.workflowBlockers.join(' ')).toContain('Resolve the 1 blocking column problem')
    expect(result.workflowBlockers.join(' ')).not.toContain('assigned both as a feature')
  })

  it('marks the split as answered even when the columns still need confirmation', () => {
    const result = readiness(input({ suggestionsConfirmed: false }))

    expect(result.splitState).toBe('ready')
    expect(result.columnState).toBe('consistent')
    expect(result.ready).toBe(false)
    expect(result.workflowBlockers.join(' ')).toContain('Confirm the suggested column roles')
  })
})

describe('strategyName', () => {
  it('names every strategy the UI offers and passes unknown ones through', () => {
    expect(strategyName('random')).toBe('Random holdout')
    expect(strategyName('stratified')).toBe('Stratified holdout')
    expect(strategyName('group')).toBe('Group holdout')
    expect(strategyName('chronological')).toBe('Chronological holdout')
    expect(strategyName('existing')).toBe('The split already in the file')
    expect(strategyName('something_new')).toBe('something_new')
  })
})
