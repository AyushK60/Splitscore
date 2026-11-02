import { useCallback, useEffect, useRef, useState } from 'react'

import { researchApi } from '../../api/client'
import type { ManifestResponse, ManifestValidation, StudyResponse } from '../../api/types'
import { useApp } from '../../state/AppState'

/**
 * Provenance: the identity of the analysed bytes and the manifest that records
 * it. Re-import is deliberately conservative — a mismatched fingerprint is
 * reported and nothing is applied to the wrong dataset.
 */

type Props = {
  datasetId: string
  study: StudyResponse
  onImported: (study: StudyResponse) => void
}

export function ProvenancePanel({ datasetId, study, onImported }: Props) {
  const { download } = useApp()
  const [manifest, setManifest] = useState<ManifestResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [validation, setValidation] = useState<ManifestValidation | null>(null)
  const [busy, setBusy] = useState(false)
  const [filename, setFilename] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const importedRef = useRef<unknown>(null)

  const load = useCallback(async () => {
    try {
      setManifest(await researchApi.manifest(datasetId))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The manifest could not be built.')
    }
  }, [datasetId])

  useEffect(() => {
    void load()
  }, [load])

  const pick = async (file: File | undefined) => {
    if (!file) return
    setError(null)
    setValidation(null)
    setFilename(file.name)
    try {
      const parsed = JSON.parse(await file.text()) as unknown
      importedRef.current = parsed
      setBusy(true)
      setValidation(await researchApi.validateManifest(datasetId, parsed, false))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'That file is not readable JSON.')
    } finally {
      setBusy(false)
    }
  }

  const apply = async () => {
    if (!importedRef.current) return
    setBusy(true)
    try {
      const result = await researchApi.validateManifest(datasetId, importedRef.current, true)
      setValidation(result)
      if (result.applied && result.study_state) onImported(result.study_state)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'The metadata could not be applied.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rs-card">
      <div className="rs-card__top">
        <div>
          <p className="rs-eyebrow">Provenance</p>
          <h2 className="rs-h2">Which bytes, which schema, which claims</h2>
          <p className="rs-lede">
            A manifest records dataset identity and your declarations. It never contains rows or cell
            values, and importing one cannot reconstruct the original file.
          </p>
        </div>
        <div className="rs-actions rs-actions--row">
          <button
            type="button"
            className="rs-btn rs-btn--primary"
            onClick={() => void download(researchApi.manifestExportPath(datasetId))}
          >
            Export manifest
          </button>
          <button
            type="button"
            className="rs-btn"
            onClick={() => void download(researchApi.studyExportPath(datasetId))}
          >
            Export study card
          </button>
        </div>
      </div>

      {error ? (
        <p className="rs-error" role="alert">
          {error}
        </p>
      ) : null}

      {manifest ? (
        <>
          <dl className="rs-dl rs-dl--wide">
            <div>
              <dt>Dataset fingerprint (SHA-256)</dt>
              <dd className="rs-mono rs-break">{manifest.dataset.sha256}</dd>
            </div>
            <div>
              <dt>Schema fingerprint</dt>
              <dd className="rs-mono rs-break">{manifest.dataset.schema_fingerprint}</dd>
            </div>
            <div>
              <dt>Dimensions</dt>
              <dd>
                {manifest.dataset.rows.toLocaleString()} rows × {manifest.dataset.columns} columns ·{' '}
                {manifest.dataset.encoding}
              </dd>
            </div>
            <div>
              <dt>Row identifiers</dt>
              <dd className="rs-mono">{manifest.dataset.row_id_scheme}</dd>
            </div>
            <div>
              <dt>Roles recorded</dt>
              <dd>
                {Object.keys(manifest.roles.assignments).length} columns ·{' '}
                {manifest.roles.role_validation.ok ? 'valid map' : 'map has conflicts'}
              </dd>
            </div>
            <div>
              <dt>Study</dt>
              <dd>
                {study.study_id} · revision {study.revision} · {String(study.card.title ?? 'untitled')}
              </dd>
            </div>
          </dl>

          <div className="rs-split">
            <p className="rs-eyebrow">Validate a manifest</p>
            <p className="rs-hint">
              Load a manifest exported earlier. SplitScope compares the dataset hash and the schema
              fingerprint before offering to apply any metadata.
            </p>
            <div className="rs-actions rs-actions--row">
              <input
                ref={fileRef}
                type="file"
                accept="application/json,.json"
                className="rs-file"
                onChange={(event) => void pick(event.target.files?.[0])}
              />
              {filename ? <span className="rs-meta">{filename}</span> : null}
            </div>

            {validation ? (
              <div className={`rs-check-result rs-check-result--${validation.status}`} role="status">
                <p className="rs-check-result__status">
                  {validation.ok ? 'Match' : validation.status.replace(/_/g, ' ')}
                </p>
                <p>{validation.message}</p>
                {validation.checks.length ? (
                  <ul className="rs-checks">
                    {validation.checks.map((check) => (
                      <li key={check.name} className={check.ok ? 'is-ok' : 'is-bad'}>
                        <strong>{check.name.replace(/_/g, ' ')}</strong> {check.message}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {validation.ok ? (
                  <button
                    type="button"
                    className="rs-btn rs-btn--primary"
                    onClick={() => void apply()}
                    disabled={busy || validation.applied}
                  >
                    {validation.applied ? 'Metadata applied' : 'Apply study metadata'}
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>

          <details className="rs-details">
            <summary>Manifest contents (JSON)</summary>
            <pre className="rs-json">{JSON.stringify(manifest, null, 2)}</pre>
          </details>

          <ul className="rs-issues">
            {manifest.warnings.map((warning) => (
              <li className="rs-issue rs-issue--warning" key={warning}>
                <strong>note</strong> {warning}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="rs-meta">Building the manifest…</p>
      )}
    </div>
  )
}
