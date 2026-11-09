/**
 * RoleEditor behaviour: rendering existing selections, producing the expected
   * role configuration from user edits, handling colliding selections, showing
 * the backend's own validation issues, and clearing the optional split role.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { RoleEditor } from '../src/components/RoleEditor'
import type { ColumnRoles, RoleIssue } from '../src/api/types'
import { loadedFixture, columnValuesFixture, rolesFixture, validationFixture } from './fixtures'

function renderEditor(initial: Partial<ColumnRoles> = {}, loaded = loadedFixture()) {
  const roles: ColumnRoles = { ...rolesFixture({ features: [], target: null, entity: null, split: null, split_train_value: null, split_test_value: null }), ...initial }
  const onChange = vi.fn()
  render(<RoleEditor loaded={loaded} roles={roles} onChange={onChange} />)
  return { roles, onChange }
}

function select(label: string): HTMLSelectElement {
  return screen.getByLabelText(label) as HTMLSelectElement
}

describe('existing role selections', () => {
  it('renders the loaded roles, the dataset columns and the feature state', () => {
    renderEditor(
      {
        features: ['tenure_months'],
        target: 'churned',
        entity: 'customer_id',
        split: 'split',
        split_train_value: 'train',
        split_test_value: 'test',
      },
    )

    expect(select('Split column')).toHaveValue('split')
    expect(select('Target column')).toHaveValue('churned')
    expect(select('Entity column')).toHaveValue('customer_id')
    // The split's own train/test values are shown for editing once selected.
    expect(screen.getByLabelText('Train value')).toHaveValue('train')
    expect(screen.getByLabelText('Test value')).toHaveValue('test')

    // Feature state: the selected feature is checked; columns taken by another
    // role are not even offered as features.
    expect(screen.getByRole('checkbox', { name: /tenure_months/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /monthly_spend/ })).not.toBeChecked()
    expect(screen.queryByRole('checkbox', { name: /churned/ })).toBeNull()
    expect(screen.queryByRole('checkbox', { name: /split/ })).toBeNull()

    // The legend counts the selection.
    expect(screen.getByText(/Which columns should the checks compare\? \(1 selected\)/)).toBeInTheDocument()
  })
})

describe('user edits', () => {
  it('selecting a target emits the expected role configuration', () => {
    const { onChange } = renderEditor()

    fireEvent.change(select('Target column'), { target: { value: 'churned' } })

    expect(onChange).toHaveBeenCalledWith({ target: 'churned' })
  })

  it('toggling a feature checkbox adds and removes the column', () => {
    const first = renderEditor()

    fireEvent.click(screen.getByRole('checkbox', { name: /tenure_months/ }))
    expect(first.onChange).toHaveBeenLastCalledWith({ features: ['tenure_months'] })
  })

  it('unchecking a selected feature emits the removed list', () => {
    const second = renderEditor({ features: ['tenure_months'] })
    fireEvent.click(screen.getByRole('checkbox', { name: /tenure_months/ }))
    expect(second.onChange).toHaveBeenLastCalledWith({ features: [] })
  })

  it('reordering features emits the reordered list and disables the ends', () => {
    const { onChange } = renderEditor({ features: ['tenure_months', 'monthly_spend'] })

    fireEvent.click(screen.getByRole('button', { name: 'Move tenure_months down' }))
    expect(onChange).toHaveBeenLastCalledWith({ features: ['monthly_spend', 'tenure_months'] })

    // Nothing above the first feature or below the last one.
    expect(screen.getByRole('button', { name: 'Move tenure_months up' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move monthly_spend down' })).toBeDisabled()
  })

  it('selecting a split emits cleared value editors and shows them when applied', () => {
    const first = renderEditor()

    fireEvent.change(select('Split column'), { target: { value: 'split' } })
    expect(first.onChange).toHaveBeenCalledWith({
      split: 'split',
      split_train_value: null,
      split_test_value: null,
    })
  })

  it('shows the train/test value editors once a split is applied', () => {
    renderEditor({ split: 'split', split_train_value: 'train', split_test_value: 'test' })
    expect(screen.getByLabelText('Train value')).toHaveValue('train')
    expect(screen.getByLabelText('Test value')).toHaveValue('test')
  })
})

describe('conflicting and invalid selections', () => {
  it('excludes columns taken by target, split and timestamp from the feature list', () => {
    renderEditor({ target: 'churned', split: 'split', timestamp: 'monthly_spend' })

    expect(screen.queryByRole('checkbox', { name: /churned/ })).toBeNull()
    expect(screen.queryByRole('checkbox', { name: /split/ })).toBeNull()
    expect(screen.queryByRole('checkbox', { name: /monthly_spend/ })).toBeNull()
    // Free columns remain selectable.
    expect(screen.getByRole('checkbox', { name: /customer_id/ })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /tenure_months/ })).toBeInTheDocument()
  })

  it('renders the backend validation issues verbatim, with hints', () => {
    const error: RoleIssue = {
      code: 'ROLE_FEATURE_IDENTIFIER',
      message: 'Row identifier “customer_id” looks unique per row; it cannot be a feature.',
      severity: 'error',
      column: 'customer_id',
      hint: 'Set it as the row identifier or exclude it.',
    }
    const warning: RoleIssue = {
      code: 'ROLE_NO_TARGET',
      message: 'No target column selected: supervised leakage checks cannot run.',
      severity: 'warning',
      column: null,
      hint: null,
    }
    const loaded = loadedFixture({
      validation: validationFixture({ ok: false, issues: [error, warning], resolved: null }),
    })
    renderEditor({}, loaded)

    expect(screen.getByText('1 blocking configuration problem')).toBeInTheDocument()
    expect(screen.getByText(/looks unique per row/)).toBeInTheDocument()
    expect(screen.getByText('Set it as the row identifier or exclude it.')).toBeInTheDocument()
    expect(screen.getByText(/1 warning - the audit can still run/)).toBeInTheDocument()
    expect(screen.getByText(/supervised leakage checks cannot run/)).toBeInTheDocument()
  })

  it('shows the ok callout only when the last validation passed', () => {
    renderEditor({}, loadedFixture())
    expect(screen.getByText('Column assignments do not conflict')).toBeInTheDocument()
    expect(screen.getByText(/not audit readiness/)).toBeInTheDocument()
  })
})

describe('observed split values', () => {
  function renderWithObserved(initial: Partial<ColumnRoles> = {}) {
    const roles: ColumnRoles = {
      ...rolesFixture({
        features: ['tenure_months'],
        split: 'split',
        split_train_value: 'train',
        split_test_value: 'test',
      }),
      ...initial,
    }
    const onChange = vi.fn()
    render(
      <RoleEditor
        loaded={loadedFixture()}
        roles={roles}
        onChange={onChange}
        observedValues={columnValuesFixture()}
      />,
    )
    return { roles, onChange }
  }

  it('maps labels from the observed values and their counts', () => {
    const { onChange } = renderWithObserved()

    expect(screen.getByLabelText('Train value')).toHaveValue('train')
    expect(screen.getByLabelText('Test value')).toHaveValue('test')
    expect(
      within(screen.getByLabelText('Train value')).getByRole('option', { name: /train - 24 rows/ }),
    ).toBeInTheDocument()
    expect(screen.getByText('24 train + 14 test rows', { exact: false })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Train value'), { target: { value: 'validation' } })
    expect(onChange).toHaveBeenCalledWith({ split_train_value: 'validation' })
  })

  it('names and counts values that are not mapped instead of hiding them', () => {
    renderWithObserved()

    expect(screen.getByText(/2 rows carry another label/)).toBeInTheDocument()
    expect(screen.getByText(/“validation”: 2/)).toBeInTheDocument()
    expect(screen.getByText(/never folded into train or test/)).toBeInTheDocument()
  })

  it('rejects a label that no row carries, with a fix', () => {
    renderWithObserved({ split_train_value: 'training' })

    expect(screen.getByText(/No row in split carries “training”/)).toBeInTheDocument()
    expect(screen.getByText(/Choose a value from the observed list/)).toBeInTheDocument()
  })

  it('refuses to use the same value for both sides', () => {
    renderWithObserved({ split_train_value: 'test', split_test_value: 'test' })

    expect(screen.getByText(/Train and test cannot both be “test”/)).toBeInTheDocument()
  })

  it('reports empty cells as missing, not as a third label', () => {
    renderWithObserved()

    expect(screen.getByText(/2 rows have an empty split value/)).toBeInTheDocument()
  })
})

describe('clearing the optional split role', () => {
  it('emits split: null and drops the value editors', () => {
    const first = renderEditor({ split: 'split', split_train_value: 'train', split_test_value: 'test' })

    fireEvent.change(select('Split column'), { target: { value: '__none__' } })
    expect(first.onChange).toHaveBeenCalledWith({
      split: null,
      split_train_value: null,
      split_test_value: null,
    })

  })

  it('hides the value editors and re-offers the column once the split is cleared', () => {
    renderEditor({ split: null })
    expect(screen.queryByLabelText('Train value')).toBeNull()
    expect(select('Split column')).toHaveValue('__none__')
  })
})
