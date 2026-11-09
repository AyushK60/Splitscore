import { useCallback, useEffect, useState } from 'react'

import { researchApi } from '../api/client'
import type { ColumnRoles, ResearchRole, RoleMapResponse, StudyResponse } from '../api/types'
import { DataDictionary } from '../components/research/DataDictionary'
import { DataProfile } from '../components/research/DataProfile'
import { ProvenancePanel } from '../components/research/ProvenancePanel'
import { StudyCardEditor } from '../components/research/StudyCardEditor'
import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'

/**
 * Study & Data workspace.
 *
 * Four panels over one dataset: the Study Card (declared), the dictionary
 * (declared roles over computed types), the profile (computed) and provenance
 * (identity). The role map saved here is the single authoritative mapping: the
 * "use in the audit" action hands its derived V1 roles to the workbench instead
 * of letting the two drift apart.
 */

type Tab = 'card' | 'dictionary' | 'profile' | 'provenance'

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'card', label: 'Study card' },
  { id: 'dictionary', label: 'Data dictionary' },
  { id: 'profile', label: 'Data profile' },
  { id: 'provenance', label: 'Provenance' },
]

function toResearchRoles(roles: ColumnRoles): Record<string, ResearchRole[]> {
  const map: Record<string, ResearchRole[]> = {}
  const add = (column: string, role: ResearchRole) => {
    const list = map[column] ?? []
    if (!list.includes(role)) list.push(role)
    map[column] = list
  }
  for (const feature of roles.features) add(feature, 'predictor')
  if (roles.target) add(roles.target, 'target')
  if (roles.entity) add(roles.entity, 'entity')
  if (roles.timestamp) add(roles.timestamp, 'timestamp')
  if (roles.split) add(roles.split, 'split')
  for (const column of roles.metadata_excluded) add(column, 'excluded')
  return map
}

type Props = { onNavigate: (view: ViewId) => void }

export function StudyView({ onNavigate }: Props) {
  const { dataset, roles, setRoles, confirmSuggestions, status, dismissStatus } = useApp()
  const datasetId = dataset?.dataset.dataset_id ?? null
  const [tab, setTab] = useState<Tab>('card')
  const [study, setStudy] = useState<StudyResponse | null>(null)
  const [profile, setProfile] = useState<Awaited<ReturnType<typeof researchApi.profile>> | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [seeding, setSeeding] = useState(false)

  const load = useCallback(async () => {
    if (!datasetId) return
    setLoading(true)
    setError(null)
    try {
      const [nextStudy, nextProfile] = await Promise.all([
        researchApi.study(datasetId),
        researchApi.profile(datasetId),
      ])
      setStudy(nextStudy)
      setProfile(nextProfile)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The study workspace could not load.')
    } finally {
      setLoading(false)
    }
  }, [datasetId])

  useEffect(() => {
    void load()
  }, [load])

  const applyToAudit = (derived: ColumnRoles) => {
    setRoles(derived)
    confirmSuggestions()
    onNavigate('audit')
  }

  const seedFromWorkbench = async () => {
    if (!datasetId) return
    setSeeding(true)
    try {
      const response = await researchApi.saveRoles(datasetId, {
        assignments: toResearchRoles(roles),
        split_train_value: roles.split_train_value,
        split_test_value: roles.split_test_value,
      })
      if (response.study) setStudy(response.study)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The roles could not be copied.')
    } finally {
      setSeeding(false)
    }
  }

  const onRolesSaved = (next: StudyResponse, _result: RoleMapResponse) => {
    setStudy(next)
  }

  if (!dataset) {
    return (
      <section className="rs">
        <div className="rs-empty">
          <p className="rs-eyebrow">Study &amp; data</p>
          <h1 className="rs-h1">No dataset is loaded</h1>
          <p className="rs-lede">
            The Study Card, dictionary and profile all describe one specific file. Load a dataset
            first; nothing is inferred from an empty workspace.
          </p>
          <button type="button" className="rs-btn rs-btn--primary" onClick={() => onNavigate('dataset')}>
            Load a dataset
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="rs" data-dataset-id={dataset.dataset.dataset_id}>
      <header className="rs-head">
        <div>
          <p className="rs-eyebrow">Study &amp; data</p>
          <h1 className="rs-h1">{dataset.dataset.name}</h1>
          <p className="rs-sub">
            {dataset.dataset.row_count.toLocaleString()} rows × {dataset.dataset.column_count}{' '}
            columns · {dataset.dataset.is_synthetic ? 'synthetic demo' : 'uploaded file'} ·{' '}
            <span className="rs-mono">{dataset.dataset.fingerprint_sha256.slice(0, 12)}…</span>
          </p>
        </div>
        <div className="rs-head__actions">
          <button type="button" className="rs-btn" onClick={() => onNavigate('dataset')}>
            Back to data
          </button>
          <button type="button" className="rs-btn" onClick={() => onNavigate('audit')}>
            Go to the audit
          </button>
        </div>
      </header>

      <nav className="rs-tabs" role="tablist" aria-label="Study and data sections">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            id={`rs-tab-${entry.id}`}
            aria-selected={tab === entry.id}
            aria-controls={`rs-panel-${entry.id}`}
            className="rs-tab"
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </nav>

      {status.kind === 'error' ? (
        <div className="rs-error" role="alert">
          {status.message}{' '}
          <button type="button" className="rs-link" onClick={dismissStatus}>
            Dismiss
          </button>
        </div>
      ) : null}

      <div
        role="tabpanel"
        id={`rs-panel-${tab}`}
        aria-labelledby={`rs-tab-${tab}`}
        className="rs-panel"
      >
        {loading ? <p className="rs-meta">Reading the dataset and the study record…</p> : null}
        {error ? (
          <p className="rs-error" role="alert">
            {error}
          </p>
        ) : null}

        {!loading && !error && tab === 'card' && study ? (
          <>
            {Object.keys(study.roles.assignments).length === 0 ? (
              <div className="rs-callout">
                <div>
                  <p className="rs-callout__title">No research roles yet</p>
                  <p>
                    The workbench has its own role selection for the audit. Copying it here makes the
                    study mapping the single source of truth - nothing is copied silently.
                  </p>
                </div>
                <button
                  type="button"
                  className="rs-btn rs-btn--primary"
                  onClick={() => void seedFromWorkbench()}
                  disabled={seeding}
                >
                  {seeding ? 'Copying…' : 'Copy the workbench roles'}
                </button>
              </div>
            ) : null}
            <StudyCardEditor study={study} datasetId={dataset.dataset.dataset_id} onSaved={setStudy} />
          </>
        ) : null}

        {!loading && !error && tab === 'dictionary' && study && profile ? (
          <DataDictionary
            datasetId={dataset.dataset.dataset_id}
            study={study}
            columns={profile.columns}
            onSaved={onRolesSaved}
            onUseInAudit={applyToAudit}
          />
        ) : null}

        {!loading && !error && tab === 'profile' && profile ? (
          <DataProfile profile={profile} onOpenDictionary={() => setTab('dictionary')} />
        ) : null}

        {!loading && !error && tab === 'provenance' && study ? (
          <ProvenancePanel
            datasetId={dataset.dataset.dataset_id}
            study={study}
            onImported={(next) => {
              setStudy(next)
              setTab('card')
            }}
          />
        ) : null}
      </div>
    </section>
  )
}
