import { useEffect, useMemo, useState } from 'react'

import { researchApi } from '../../api/client'
import type {
  ColumnRoles,
  ProfileColumn,
  RoleMapResponse,
  StudyIssue,
  StudyResponse,
} from '../../api/types'

/**
 * Data dictionary and research-role editor.
 *
 * The table is computed; the role column is declared. A conflict is shown as the
 * server's own message and blocks saving, so the interface never implies that an
 * impossible combination was accepted.
 */

const ROLE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'entity', label: 'Entity / group identifier' },
  { value: 'timestamp', label: 'Timestamp' },
  { value: 'split', label: 'Split assignment' },
  { value: 'target', label: 'Outcome / target' },
  { value: 'predictor', label: 'Predictor' },
  { value: 'treatment', label: 'Treatment / exposure' },
  { value: 'confounder', label: 'Confounder' },
  { value: 'mediator', label: 'Mediator' },
  { value: 'effect_modifier', label: 'Effect modifier' },
  { value: 'instrument', label: 'Instrument' },
  { value: 'sensitive', label: 'Protected / sensitive attribute' },
  { value: 'future_only', label: 'Future-only variable' },
  { value: 'excluded', label: 'Excluded from analysis' },
]

const DECLARED_TYPES = [
  'not declared',
  'numeric',
  'integer',
  'categorical',
  'boolean',
  'datetime',
  'text',
  'identifier',
]

type Props = {
  datasetId: string
  study: StudyResponse
  columns: ProfileColumn[]
  onSaved: (study: StudyResponse, result: RoleMapResponse) => void
  onUseInAudit: (roles: ColumnRoles) => void
}

export function DataDictionary({ datasetId, study, columns, onSaved, onUseInAudit }: Props) {
  const [assignments, setAssignments] = useState<Record<string, string[]>>(study.roles.assignments)
  const [selected, setSelected] = useState<string>(columns[0]?.column ?? '')
  const [declared, setDeclared] = useState<Record<string, Record<string, string>>>(() => {
    const initial: Record<string, Record<string, string>> = {}
    for (const column of columns) {
      initial[column.column] = {
        declared_type: column.declared_type ?? '',
        description: column.description ?? '',
        unit: column.unit ?? '',
        measurement_scale: column.measurement_scale ?? '',
      }
    }
    return initial
  })
  const [result, setResult] = useState<RoleMapResponse | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [splitTrain, setSplitTrain] = useState(study.split_values.train ?? '')
  const [splitTest, setSplitTest] = useState(study.split_values.test ?? '')

  useEffect(() => {
    setAssignments(study.roles.assignments)
  }, [study.roles.assignments])

  const issuesByColumn = useMemo(() => {
    const map = new Map<string, StudyIssue[]>()
    for (const issue of result?.issues ?? []) {
      if (!issue.column) continue
      const list = map.get(issue.column) ?? []
      list.push(issue)
      map.set(issue.column, list)
    }
    return map
  }, [result])

  const current = selected ? columns.find((column) => column.column === selected) : undefined

  const toggleRole = (column: string, role: string) => {
    setAssignments((previous) => {
      const roles = previous[column] ?? []
      const next = roles.includes(role) ? roles.filter((item) => item !== role) : [...roles, role]
      const copy = { ...previous }
      if (next.length) copy[column] = next
      else delete copy[column]
      return copy
    })
  }

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const response = await researchApi.saveRoles(datasetId, {
        assignments,
        split_train_value: splitTrain || null,
        split_test_value: splitTest || null,
      })
      setResult(response)
      onSaved(response.study, response)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The role map could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rs-card">
      <div className="rs-card__top">
        <div>
          <p className="rs-eyebrow">Data dictionary</p>
          <h2 className="rs-h2">Type, completeness and meaning</h2>
          <p className="rs-lede">
            Types, missing counts and cardinality are computed from the file. Descriptions, units and
            roles are yours — a role describes what you claim a column means, never what its name
            suggests.
          </p>
        </div>
        <div className="rs-stat">
          <p className="rs-stat__value">{columns.length}</p>
          <p className="rs-stat__label">columns</p>
        </div>
      </div>

      <div className="rs-table-wrap">
        <table className="rs-table">
          <caption className="rs-caption">
            Computed properties are read-only. Role chips open the editor for that column.
          </caption>
          <thead>
            <tr>
              <th scope="col">Column</th>
              <th scope="col">Detected</th>
              <th scope="col">Declared</th>
              <th scope="col">Missing</th>
              <th scope="col">Distinct</th>
              <th scope="col">Roles</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((column) => {
              const issues = issuesByColumn.get(column.column) ?? []
              const hasError = issues.some((issue) => issue.severity === 'error')
              return (
                <tr
                  key={column.column}
                  className={selected === column.column ? 'is-selected' : undefined}
                  data-problem={hasError ? 'true' : undefined}
                >
                  <th scope="row">
                    <button type="button" className="rs-rowlink" onClick={() => setSelected(column.column)}>
                      {column.column}
                    </button>
                    {hasError ? <span className="rs-flag rs-flag--error">conflict</span> : null}
                  </th>
                  <td>
                    <span className="rs-type">{column.detected_type}</span>
                  </td>
                  <td>{column.declared_type ?? <span className="rs-dim">—</span>}</td>
                  <td className="rs-num">
                    {column.missing_count} ({Math.round(column.missing_ratio * 100)}%)
                  </td>
                  <td className="rs-num">{column.distinct_count}</td>
                  <td>
                    <div className="rs-chips">
                      {(assignments[column.column] ?? []).length ? (
                        (assignments[column.column] ?? []).map((role) => (
                          <span className="rs-chip rs-chip--role" key={role}>
                            {role.replace(/_/g, ' ')}
                          </span>
                        ))
                      ) : (
                        <span className="rs-dim">unassigned</span>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {current ? (
        <section className="rs-inspector" aria-label={`Roles and declarations for ${current.column}`}>
          <div className="rs-inspector__head">
            <div>
              <p className="rs-eyebrow">Column</p>
              <h3 className="rs-h3">{current.column}</h3>
              <p className="rs-hint">
                {current.detected_type}: {current.detected_type_reason} Examples:{' '}
                {current.examples.length ? current.examples.join(' · ') : 'none'}.
              </p>
            </div>
            <p className="rs-num">
              {current.missing_count} missing · {current.distinct_count} distinct
            </p>
          </div>

          <div className="rs-roles">
            {ROLE_OPTIONS.map((role) => (
              <label className="rs-check" key={role.value}>
                <input
                  type="checkbox"
                  checked={(assignments[current.column] ?? []).includes(role.value)}
                  onChange={() => toggleRole(current.column, role.value)}
                />
                <span>{role.label}</span>
              </label>
            ))}
          </div>

          <div className="rs-grid rs-grid--tight">
            <label className="rs-field">
              <span className="rs-field__label">Confirmed type</span>
              <select
                className="rs-input"
                value={declared[current.column]?.declared_type ?? ''}
                onChange={(event) =>
                  setDeclared((previous) => ({
                    ...previous,
                    [current.column]: { ...(previous[current.column] ?? {}), declared_type: event.target.value },
                  }))
                }
              >
                {DECLARED_TYPES.map((type) => (
                  <option key={type} value={type === 'not declared' ? '' : type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
            <label className="rs-field">
              <span className="rs-field__label">Unit</span>
              <input
                className="rs-input"
                value={declared[current.column]?.unit ?? ''}
                onChange={(event) =>
                  setDeclared((previous) => ({
                    ...previous,
                    [current.column]: { ...(previous[current.column] ?? {}), unit: event.target.value },
                  }))
                }
              />
            </label>
            <label className="rs-field rs-field--wide">
              <span className="rs-field__label">Description</span>
              <input
                className="rs-input"
                value={declared[current.column]?.description ?? ''}
                onChange={(event) =>
                  setDeclared((previous) => ({
                    ...previous,
                    [current.column]: { ...(previous[current.column] ?? {}), description: event.target.value },
                  }))
                }
              />
            </label>
          </div>

          {issuesByColumn.get(current.column)?.length ? (
            <ul className="rs-issues">
              {issuesByColumn.get(current.column)!.map((issue, index) => (
                <li key={`${issue.code}-${index}`} className={`rs-issue rs-issue--${issue.severity}`}>
                  <strong>{issue.severity}</strong> {issue.message}
                  {issue.hint ? <span className="rs-issue__hint">{issue.hint}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      <div className="rs-split">
        <p className="rs-eyebrow">Split labels</p>
        <p className="rs-hint">
          Only needed when one column is marked as the split. Rows carrying neither value are
          reported as unassigned, never folded into a side.
        </p>
        <div className="rs-grid rs-grid--tight">
          <label className="rs-field">
            <span className="rs-field__label">Train value</span>
            <input className="rs-input" value={splitTrain} onChange={(event) => setSplitTrain(event.target.value)} />
          </label>
          <label className="rs-field">
            <span className="rs-field__label">Test value</span>
            <input className="rs-input" value={splitTest} onChange={(event) => setSplitTest(event.target.value)} />
          </label>
        </div>
      </div>

      <div className="rs-actions">
        <button type="button" className="rs-btn rs-btn--primary" onClick={() => void save()} disabled={saving}>
          {saving ? 'Validating…' : 'Save roles and declarations'}
        </button>
        {result?.ok ? (
          <button
            type="button"
            className="rs-btn"
            onClick={() => onUseInAudit(result.derived_roles)}
          >
            Use these roles in the audit
          </button>
        ) : null}
        {result ? (
          <span className={result.ok ? 'rs-ok' : 'rs-error'} role="status">
            {result.ok
              ? `Saved. ${result.warnings} warning(s).`
              : `${result.errors} conflict(s) blocked the save; the previous map is still active.`}
          </span>
        ) : null}
      </div>

      {error ? (
        <p className="rs-error" role="alert">
          {error}
        </p>
      ) : null}

      <p className="rs-storage">{study.storage_note}</p>
    </div>
  )
}
