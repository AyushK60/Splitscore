import { useEffect, useMemo, useState } from 'react'

import { researchApi } from '../../api/client'
import type { StudyField, StudyResponse } from '../../api/types'

/**
 * Study Card editor.
 *
 * The card is the researcher's own statement, so the editor never pre-fills a
 * field with a guess: blank means "not declared" and stays that way. Required
 * completion is shown as a count of declared fields, explicitly not as a score.
 */

type Props = {
  study: StudyResponse
  datasetId: string
  onSaved: (study: StudyResponse) => void
}

function toDraft(card: Record<string, unknown>): Record<string, string> {
  const draft: Record<string, string> = {}
  for (const [key, value] of Object.entries(card)) {
    if (Array.isArray(value)) {
      draft[key] = value.join(', ')
    } else if (value === null || value === undefined) {
      draft[key] = ''
    } else {
      draft[key] = String(value)
    }
  }
  return draft
}

export function StudyCardEditor({ study, datasetId, onSaved }: Props) {
  const [draft, setDraft] = useState<Record<string, string>>(() => toDraft(study.card))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    setDraft(toDraft(study.card))
  }, [study.study_id, study.revision, study.card])

  const sections = useMemo(() => {
    const grouped = new Map<string, StudyField[]>()
    for (const field of study.fields) {
      const list = grouped.get(field.section) ?? []
      list.push(field)
      grouped.set(field.section, list)
    }
    return [...grouped.entries()]
  }, [study.fields])

  const options = study.select_options ?? {}
  const completed = study.completion

  const save = async () => {
    setSaving(true)
    setError(null)
    setNotice(null)
    try {
      const card: Record<string, unknown> = { ...study.card }
      for (const field of study.fields) {
        const raw = (draft[field.name] ?? '').trim()
        card[field.name] = raw === '' ? null : raw
      }
      const saved = await researchApi.saveStudy(datasetId, {
        card,
        split_train_value: study.split_values.train,
        split_test_value: study.split_values.test,
        column_declarations: Object.entries(study.column_declarations).map(([column, values]) => ({
          column,
          ...values,
        })),
      })
      onSaved(saved)
      setNotice(`Saved as revision ${saved.revision}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The study card could not be saved.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rs-card">
      <div className="rs-card__top">
        <div>
          <p className="rs-eyebrow">Study card</p>
          <h2 className="rs-h2">What this study is asking</h2>
          <p className="rs-lede">
            Everything here is your declaration. SplitScope records it with the dataset fingerprint
            and never fills in a design, a consent status or an outcome on your behalf.
          </p>
        </div>
        <div className="rs-completion" aria-live="polite">
          <p className="rs-completion__value">
            {completed.declared}
            <span>/{completed.required}</span>
          </p>
          <p className="rs-completion__label">required fields declared</p>
          <div className="rs-meter" aria-hidden="true">
            <span style={{ width: `${Math.round(completed.ratio * 100)}%` }} />
          </div>
          {completed.missing.length ? (
            <p className="rs-completion__missing">
              Missing: {completed.missing.map((name) => name.replace(/_/g, ' ')).join(', ')}
            </p>
          ) : (
            <p className="rs-completion__missing">All required fields are declared.</p>
          )}
        </div>
      </div>

      <p className="rs-note">
        This count measures completeness of the metadata only. It is not a scientific-validity or
        ethics score.
      </p>

      {sections.map(([section, fields]) => (
        <details
          className="rs-section"
          key={section}
          open={section === 'Purpose' || section === 'Design'}
        >
          <summary className="rs-section__legend">
            {section}
            <span className="rs-section__count">
              {fields.filter((field) => field.declared).length}/{fields.length} declared
            </span>
          </summary>
          <div className="rs-grid">
            {fields.map((field) => {
              const value = draft[field.name] ?? ''
              const wide = field.kind === 'longtext'
              return (
                <label className={wide ? 'rs-field rs-field--wide' : 'rs-field'} key={field.name}>
                  <span className="rs-field__label">
                    {field.label}
                    {field.required ? <span className="rs-req">required</span> : null}
                    <span className={field.declared ? 'rs-chip rs-chip--ok' : 'rs-chip'}>
                      {field.declared ? 'declared' : 'not declared'}
                    </span>
                  </span>
                  {field.kind === 'select' ? (
                    <select
                      className="rs-input"
                      value={value}
                      onChange={(event) =>
                        setDraft((previous) => ({ ...previous, [field.name]: event.target.value }))
                      }
                    >
                      <option value="">Not stated</option>
                      {(options[field.name] ?? []).map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : field.kind === 'longtext' ? (
                    <textarea
                      className="rs-input rs-input--area"
                      rows={3}
                      value={value}
                      onChange={(event) =>
                        setDraft((previous) => ({ ...previous, [field.name]: event.target.value }))
                      }
                    />
                  ) : (
                    <input
                      className="rs-input"
                      type="text"
                      value={value}
                      onChange={(event) =>
                        setDraft((previous) => ({ ...previous, [field.name]: event.target.value }))
                      }
                    />
                  )}
                  <span className="rs-hint">{field.help}</span>
                </label>
              )
            })}
          </div>
        </details>
      ))}

      <div className="rs-actions">
        <button type="button" className="rs-btn rs-btn--primary" onClick={() => void save()} disabled={saving}>
          {saving ? 'Saving…' : 'Save study card'}
        </button>
        <span className="rs-meta">
          Revision {study.revision} · last saved {new Date(study.updated_at_utc).toLocaleString()}
        </span>
      </div>

      {notice ? <p className="rs-ok">{notice}</p> : null}
      {error ? (
        <p className="rs-error" role="alert">
          {error}
        </p>
      ) : null}

      {study.issues.length ? (
        <ul className="rs-issues">
          {study.issues.map((issue) => (
            <li key={issue.code} className={`rs-issue rs-issue--${issue.severity}`}>
              <strong>{issue.severity}</strong> {issue.message}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="rs-storage">{study.storage_note}</p>
    </div>
  )
}
