/**
 * Role-patch normalisation: the rules that keep one column from holding two
 * roles, keep the feature list intact when a role is assigned, and never let a
 * stale split mapping survive a column change. These are the rules behind the
 * role-overlap and multi-role failures the backend reports, exercised directly.
 */
import { describe, expect, it } from 'vitest'

import { consistentRoles, normaliseRolePatch } from '../src/lib/roles'
import { COLUMNS, rolesFixture } from './fixtures'

const exists = (name: string) => (COLUMNS as readonly string[]).includes(name)

describe('normaliseRolePatch', () => {
  it('assigning a special role removes that column from features and keeps the rest, in order', () => {
    const roles = rolesFixture({
      target: null,
      features: ['monthly_spend', 'tenure_months', 'churned'],
    })

    const { roles: next, notes } = normaliseRolePatch(roles, { target: 'churned' })

    expect(next.target).toBe('churned')
    expect(next.features).toEqual(['monthly_spend', 'tenure_months'])
    expect(notes).toHaveLength(1)
    expect(notes[0]).toContain('Removed churned from the feature columns')
    expect(notes[0]).toContain('the other 2 features are unchanged')
  })

  it('a column can hold only one role: the older holder is released with an explanation', () => {
    const roles = rolesFixture({ target: null }) // entity owns customer_id

    const { roles: next, notes } = normaliseRolePatch(roles, { target: 'customer_id' })

    expect(next.target).toBe('customer_id')
    expect(next.entity).toBeNull()
    expect(notes.join(' ')).toContain('Removed the entity role from customer_id')
  })

  it('moving the split role clears its train/test labels so a stale mapping cannot be submitted', () => {
    const roles = rolesFixture() // split = split, labels train/test

    const { roles: next } = normaliseRolePatch(roles, { split: 'monthly_spend' })

    expect(next.split).toBe('monthly_spend')
    expect(next.split_train_value).toBeNull()
    expect(next.split_test_value).toBeNull()
  })

  it('a label patch on the unchanged split column keeps the labels', () => {
    const roles = rolesFixture({ split_train_value: null })

    const { roles: next } = normaliseRolePatch(roles, { split_train_value: 'training' })

    expect(next.split_train_value).toBe('training')
    expect(next.split_test_value).toBe('test')
  })

  it('clearing a special role does not silently re-add the column to features', () => {
    const roles = rolesFixture({ features: [] })

    const { roles: next, notes } = normaliseRolePatch(roles, { target: null })

    expect(next.target).toBeNull()
    expect(next.features).toEqual([])
    expect(notes.filter((note) => note.includes('feature'))).toEqual([])
  })

  it('clearing the split role clears its labels too', () => {
    const roles = rolesFixture()

    const { roles: next } = normaliseRolePatch(roles, {
      split: null,
      split_train_value: null,
      split_test_value: null,
    })

    expect(next.split).toBeNull()
    expect(next.split_train_value).toBeNull()
    expect(next.split_test_value).toBeNull()
    expect(next.features).toEqual(['tenure_months', 'monthly_spend'])
  })

  it('drops values that are not columns of this dataset and says so', () => {
    const roles = rolesFixture({ target: null })

    const { roles: next, notes } = normaliseRolePatch(
      roles,
      { target: 'removed_column' },
      exists,
    )

    expect(next.target).toBeNull()
    expect(notes.join(' ')).toContain('Cleared target role: removed_column')
  })

  it('a patch that names an unknown column never shadows a real role assignment', () => {
    const roles = rolesFixture({ target: null })

    const { roles: next } = normaliseRolePatch(roles, { target: 'gone' }, exists)

    expect(next.target).toBeNull()
    expect(next.entity).toBe('customer_id')
  })

  it('a feature is never also excluded metadata', () => {
    const roles = rolesFixture({ metadata_excluded: ['tenure_months', 'customer_id'] })

    const { roles: next } = normaliseRolePatch(roles, {})

    expect(next.metadata_excluded).toEqual(['customer_id'])
  })

  it('reordering features preserves every selected feature', () => {
    const roles = rolesFixture()

    const { roles: next } = normaliseRolePatch(roles, {
      features: ['monthly_spend', 'tenure_months'],
    })

    expect(next.features).toEqual(['monthly_spend', 'tenure_months'])
  })
})

describe('consistentRoles', () => {
  it('submits roles with no column both special and featured', () => {
    const roles = rolesFixture({
      features: ['tenure_months', 'churned'],
      target: 'churned',
    })

    const submitted = consistentRoles(roles)

    expect(submitted.features).toEqual(['tenure_months'])
    expect(submitted.target).toBe('churned')
  })
})
