/**
 * Dataset view: the guided setup between "a file is loaded" and "an audit can
 * run".
 *
 * Three short steps, in the order a person actually needs them:
 *   1. Where does the split come from — the file, or a split created now?
 *   2. (created splits) which strategy, with its eligibility spelled out.
 *   3. What does each column mean — the guided role questions, the confirmation
 *      of any guess, and one run gate whose blockers name the action that
 *      clears them.
 *
 * The preview shows values exactly as they appear in the file. Nothing here
 * reinterprets a cell, and the column-type summary is reported as a ratio rather
 * than a verdict so the user can see how confident the inference actually is.
 */

import { useEffect, useRef, useState } from 'react'

import { AuditConfigEditor } from '../components/AuditConfigEditor'
import { RoleEditor } from '../components/RoleEditor'
import { Callout, Card, EmptyState, Spinner, Table } from '../components/ui'
import type { SplitConfig } from '../api/types'
import { bytes, integer, percent, pluralise, truncate } from '../lib/format'
import type { ViewId } from '../lib/router'
import { readiness, splitModeLabel } from '../lib/readiness'
import { useApp } from '../state/AppState'

const PREVIEW_PAGE = 25

const DEFAULT_GENERATE: SplitConfig = {
  kind: 'random',
  label: 'Random holdout',
  test_fraction: 0.25,
  seed: 12345,
}

interface StrategyOption {
  kind: SplitConfig['kind']
  label: string
  /** The role column the strategy needs; null means it works on any file. */
  needs: 'target' | 'entity' | 'timestamp' | null
  what: string
}

/** The generated-split strategies, each with its eligibility spelled out. */
const STRATEGIES: StrategyOption[] = [
  {
    kind: 'random',
    label: 'Random holdout',
    needs: null,
    what: 'Each row goes to train or test at random, with a fixed seed so the same split can be reproduced exactly.',
  },
  {
    kind: 'stratified',
    label: 'Stratified holdout',
    needs: 'target',
    what: 'Train and test keep roughly the same target proportions, so a rare class is not lost from one side.',
  },
  {
    kind: 'group',
    label: 'Group holdout',
    needs: 'entity',
    what: 'All rows of one person, device or item land on the same side — repetition of an entity never straddles the split.',
  },
  {
    kind: 'chronological',
    label: 'Chronological holdout',
    needs: 'timestamp',
    what: 'The earliest rows train and the latest rows test, like predicting the future from the past.',
  },
]

const STRATEGY_LABELS: Record<string, string> = Object.fromEntries(
  STRATEGIES.map((option) => [option.kind, option.label]),
)

const TEST_SHARES = [5, 10, 15, 20, 25, 30, 40, 50]

export function DatasetView({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const {
    dataset,
    roles,
    config,
    preview,
    status,
    busyLabel,
    roleNotes,
    validation,
    validationPending,
    suggestionsConfirmed,
    splitMode,
    generateSplit,
    observedValues,
    uploadFile,
    patchRoles,
    setConfig,
    loadPreview,
    validateRoles,
    loadColumnValues,
    setSplitMode,
    setGenerateSplit,
    confirmSuggestions,
    runAudit,
    reset,
  } = useApp()

  const [offset, setOffset] = useState(0)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    setOffset(0)
  }, [dataset?.dataset.dataset_id])

  // Observed values of the split column, fetched only on the existing-split
  // path so the labels are mapped from values the file really contains.
  const observedColumn = splitMode === 'existing' ? roles.split : null
  useEffect(() => {
    void loadColumnValues(observedColumn)
  }, [observedColumn, loadColumnValues])

  const numericFeatures = dataset
    ? roles.features.filter((name) => dataset.column_types[name]?.looks_numeric).length
    : 0
  const numericRatio = roles.features.length ? numericFeatures / roles.features.length : null

  if (!dataset) {
    return (
      <div className="stack">
        <Card title="Load a dataset">
          <EmptyState
            title="No dataset is loaded"
            action={
              <>
                <button type="button" className="btn btn--primary" onClick={() => fileInput.current?.click()}>
                  Choose a CSV file
                </button>{' '}
                <button type="button" className="btn" onClick={() => onNavigate('overview')}>
                  Or pick an included demo
                </button>
              </>
            }
          >
            SplitScope reads CSV only in this version. Uploads stay in server memory and expire; they
            are never written to disk.
          </EmptyState>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,.txt,.tsv,text/csv"
            className="visually-hidden"
            tabIndex={-1}
            aria-hidden="true"
            onChange={async (event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (file) await uploadFile(file)
            }}
          />
          {busyLabel ? <Spinner label={busyLabel} /> : null}
          {status.kind === 'error' ? (
            <Callout tone="danger" title={`Upload rejected (${status.code ?? 'error'})`}>
              <p style={{ marginTop: 0 }}>{status.message}</p>
              {Object.keys(status.details ?? {}).length ? (
                <dl className="evidence-details">
                  {Object.entries(status.details ?? {}).map(([key, value]) => (
                    <div key={key} style={{ display: 'contents' }}>
                      <dt>{key}</dt>
                      <dd>{typeof value === 'string' ? value : JSON.stringify(value)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </Callout>
          ) : null}
        </Card>
      </div>
    )
  }

  const summary = dataset.dataset
  const demo = dataset.demo
  const limits = dataset.dataset_limits
  const suggested = dataset.suggested_roles
  const hasSuggestions = Boolean(
    suggested.target || suggested.entity || suggested.timestamp || suggested.split,
  )
  const questionsStep = splitMode === 'generate' ? 3 : 2
  const currentTestPct = Math.round((generateSplit ?? DEFAULT_GENERATE).test_fraction * 100)
  const shareOptions = TEST_SHARES.includes(currentTestPct)
    ? TEST_SHARES
    : [...new Set([...TEST_SHARES, currentTestPct])].sort((a, b) => a - b)

  const ready = readiness({
    roles,
    validation,
    validationPending,
    suggestionsConfirmed,
    splitMode,
    generate: generateSplit,
    columnTypes: dataset.column_types,
  })

  function pickStrategy(kind: SplitConfig['kind']) {
    const base = generateSplit ?? DEFAULT_GENERATE
    setGenerateSplit({ ...base, kind, label: STRATEGY_LABELS[kind] ?? kind })
  }

  return (
    <div className="stack">
      {!demo ? (
        <Callout tone="info" title="Uploaded file — treated as untrusted data">
          Every cell is rendered as text and escaped wherever it appears. The SHA-256 fingerprint
          identifies this exact input for reproducibility; it is not anonymization.
        </Callout>
      ) : null}

      <section className="dataset-head">
        <div className="dataset-head__identity">
          <h1 style={{ marginBottom: 2 }}>
            {summary.name}{' '}
            {summary.is_synthetic ? (
              <span className="badge badge--info" title="Generated teaching data, not real people or events">
                Synthetic demo
              </span>
            ) : null}
          </h1>
          <p className="muted" style={{ margin: 0 }}>
            {integer(summary.row_count)} rows × {integer(summary.column_count)} columns
            {demo ? ` · ${demo.title}` : ''}
          </p>
        </div>
        <div className="dataset-head__meta">
          <span className="badge badge--neutral">{demo ? 'Demo' : 'Uploaded file'}</span>
          <span className="badge badge--neutral">
            {roles.features.length} {pluralise(roles.features.length, 'feature')}
          </span>
          <div className="row" style={{ gap: 6 }}>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,.txt,.tsv,text/csv"
              className="visually-hidden"
              tabIndex={-1}
              aria-hidden="true"
              onChange={async (event) => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (file) await uploadFile(file)
              }}
            />
            <button type="button" className="btn btn--small" onClick={() => fileInput.current?.click()}>
              Replace file
            </button>
            <button type="button" className="btn btn--small btn--ghost" onClick={reset}>
              Clear
            </button>
          </div>
        </div>
      </section>

      <ol className="setup-progress" aria-label="Setup progress">
        <li data-state="done">
          <span className="setup-progress__dot" aria-hidden="true">✓</span>
          <span>
            <strong>File loaded</strong>
            <span className="setup-progress__hint">{integer(summary.row_count)} rows read</span>
          </span>
        </li>
        <li data-state={splitMode ? 'done' : 'current'}>
          <span className="setup-progress__dot" aria-hidden="true">{splitMode ? '✓' : '1'}</span>
          <span>
            <strong>Split source</strong>
            <span className="setup-progress__hint">{splitModeLabel(splitMode)}</span>
          </span>
        </li>
        <li
          data-state={
            !splitMode
              ? 'todo'
              : ready.columnState === 'consistent' && suggestionsConfirmed
                ? 'done'
                : 'current'
          }
        >
          <span className="setup-progress__dot" aria-hidden="true">
            {ready.columnState === 'consistent' && suggestionsConfirmed ? '✓' : '2'}
          </span>
          <span>
            <strong>Column roles</strong>
            <span className="setup-progress__hint">
              {ready.columnState === 'checking'
                ? 'Checking with the server'
                : ready.columnState === 'conflicted'
                  ? 'Needs attention'
                  : suggestionsConfirmed
                    ? `${roles.features.length} features`
                    : 'Confirm the suggestions'}
            </span>
          </span>
        </li>
        <li data-state={ready.ready ? 'done' : 'todo'}>
          <span className="setup-progress__dot" aria-hidden="true">{ready.ready ? '✓' : '3'}</span>
          <span>
            <strong>Run audit</strong>
            <span className="setup-progress__hint">
              {ready.ready ? 'Ready' : `${ready.workflowBlockers.length} remaining`}
            </span>
          </span>
        </li>
      </ol>


      {demo ? (
        <Callout tone="synthetic" title={`Synthetic demo: ${demo.title}`}>
          <p style={{ marginTop: 0 }}>{demo.teaching_point}</p>
          <p className="small muted" style={{ marginBottom: 0 }}>
            Generated teaching data — not real people or events. Seed {demo.seed}.
          </p>
          <details className="disclosure" style={{ marginBottom: 0 }}>
            <summary>How this demo was generated</summary>
            <p className="small" style={{ margin: 0 }}>
              {demo.generation_method}
            </p>
          </details>
        </Callout>
      ) : null}

      {/* Step 1 — the entry question, collapsed to a summary once answered. */}
      <Card title="Step 1 — Does your file already say which rows are training and testing?">
        {splitMode === null ? (
          <>
            <p className="small muted" style={{ marginTop: 0 }}>
              Every audit compares a training side against a testing side. Tell SplitScope where
              those sides come from — you can change this answer at any time, and the file itself is
              never modified either way.
            </p>
            <div className="grid-2 entry-grid">
              <div className="entry-option">
                <span className="entry-option__tag">Existing split · recommended if you have one</span>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => setSplitMode('existing')}
                >
                  Yes — check my existing split.
                </button>
                <p className="small" style={{ margin: '8px 0 0' }}>
                  Pick the column that holds the labels — for example{' '}
                  <span className="mono">split</span> with values{' '}
                  <span className="mono">train</span> / <span className="mono">test</span> — and map
                  its two values. SplitScope then audits exactly the split the file describes.
                </p>
              </div>
              <div className="entry-option">
                <span className="entry-option__tag">Generated split</span>
                <button
                  type="button"
                  className="btn"
                  onClick={() => setSplitMode('generate')}
                >
                  No — help me create a split.
                </button>
                <p className="small" style={{ margin: '8px 0 0' }}>
                  Choose random, stratified, group or chronological. The strategy, the seed and every
                  row's side are recorded in the report and downloadable as a CSV. The audit then
                  assesses this proposed split — your file is not edited.
                </p>
              </div>
            </div>
            <p className="hint" style={{ marginTop: 10 }}>
              Not sure? If your file has a column whose values look like{' '}
              <span className="mono">train</span> / <span className="mono">test</span> (or{' '}
              <span className="mono">0</span> / <span className="mono">1</span> with a documented
              meaning), choose the first option. Otherwise let SplitScope create a reproducible
              split.
            </p>
          </>
        ) : (
          <div className="row row--between" style={{ alignItems: 'flex-start', gap: 12 }}>
            <p className="small" style={{ margin: 0 }}>
              {splitMode === 'existing'
                ? 'Using the split that is already in the file. '
                : 'Creating a split when the audit runs. '}
              Split: {ready.splitDescription}
            </p>
            <button type="button" className="btn btn--small" onClick={() => setSplitMode(null)}>
              Change this answer
            </button>
          </div>
        )}
      </Card>

      {/* Step 2 — generated splits only: the strategy and its eligibility. */}
      {splitMode === 'generate' ? (
        <Card title="Step 2 — Choose how to split the rows">
          <p className="small muted" style={{ marginTop: 0 }}>
            The split is generated when the audit runs and stored beside it: the same strategy, seed
            and settings reproduce the same rows on each side. Your CSV is never edited.
          </p>
          <fieldset>
            <legend>Split strategy</legend>
            <div className="grid-2">
              {STRATEGIES.map((option) => {
                const available = option.needs === null || roles[option.needs] !== null
                const selected = (generateSplit ?? DEFAULT_GENERATE).kind === option.kind
                return (
                  <label
                    key={option.kind}
                    className={`strategy-option${available ? '' : ' strategy-option--off'}`}
                  >
                    <input
                      type="radio"
                      name="generate-strategy"
                      value={option.kind}
                      checked={selected}
                      disabled={!available}
                      onChange={() => pickStrategy(option.kind)}
                    />
                    <span>
                      <strong>{option.label}</strong>
                      <span className="hint">{option.what}</span>
                      <span className="hint">
                        {available
                          ? option.needs
                            ? `Available — uses the ${option.needs} column you chose.`
                            : 'Available for any file.'
                          : `Unavailable — this strategy needs the ${option.needs} column; choose one in step ${questionsStep} below.`}
                      </span>
                    </span>
                  </label>
                )
              })}
            </div>
          </fieldset>
          <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
            <div className="field">
              <label htmlFor="generate-fraction">Test share of rows</label>
              <select
                id="generate-fraction"
                value={currentTestPct}
                onChange={(event) => {
                  const pct = Number(event.target.value)
                  if (!Number.isFinite(pct)) return
                  setGenerateSplit({ ...(generateSplit ?? DEFAULT_GENERATE), test_fraction: pct / 100 })
                }}
              >
                {shareOptions.map((pct) => (
                  <option key={pct} value={pct}>
                    {pct}%
                  </option>
                ))}
              </select>
              <span className="hint">
                Rows held out for testing. Stratified and group splits aim at this share; the
                achieved share is reported.
              </span>
            </div>
            <div className="field">
              <label htmlFor="generate-seed">Seed</label>
              <input
                id="generate-seed"
                type="number"
                min={0}
                step={1}
                value={(generateSplit ?? DEFAULT_GENERATE).seed}
                onChange={(event) => {
                  const seed = Number(event.target.value)
                  if (!Number.isFinite(seed) || seed < 0) return
                  setGenerateSplit({ ...(generateSplit ?? DEFAULT_GENERATE), seed: Math.round(seed) })
                }}
              />
              <span className="hint">
                The same strategy, fraction and seed always produce the same split.
              </span>
            </div>
          </div>
        </Card>
      ) : null}

      {/* The guided questions, the confirmation of any guess, and the run gate. */}
      <Card
        title={`Step ${questionsStep} — Answer a few questions about your columns`}
        actions={
          <button
            type="button"
            className="btn btn--small"
            onClick={() => void validateRoles()}
            disabled={busyLabel !== null}
          >
            Re-check roles
          </button>
        }
      >
        {roleNotes.length ? (
          <p className="small muted" role="status" style={{ margin: '0 0 4px' }}>
            {roleNotes.join(' ')}
          </p>
        ) : null}
        <p className="small muted" style={{ marginTop: 0 }}>
          Roles tell SplitScope what each column means:{' '}
          <strong>target</strong> is the value a model would predict;{' '}
          <strong>entity</strong> is the person, customer or device that may appear in several rows;{' '}
          <strong>split</strong> says which rows are training and which are testing.{' '}
          {dataset.suggested_roles_confidence === 'recommended'
            ? 'These suggestions come from the demo’s own manifest. Check them, then run the audit.'
            : 'Check every question below — the audit only ever uses roles you can see here.'}
        </p>
        <RoleEditor
          loaded={dataset}
          roles={roles}
          onChange={patchRoles}
          validation={validation}
          validationPending={validationPending}
          observedValues={observedValues}
          showSplit={splitMode === 'existing'}
        />

        {!suggestionsConfirmed ? (
          <Callout tone="info" title="Confirm the suggested column roles">
            <p style={{ marginTop: 0 }}>
              {hasSuggestions
                ? 'The selections above are a name- and type-based guess about this file. Look through each question, correct anything the guess got wrong, then confirm — nothing runs on a guess.'
                : 'No column roles could be guessed for this file, so nothing is pre-selected. Answer what you can, use “not applicable / I don’t know” for the rest, then confirm.'}
            </p>
            <p style={{ marginBottom: 0 }}>
              <button
                type="button"
                className="btn btn--primary"
                disabled={busyLabel !== null}
                onClick={confirmSuggestions}
              >
                Confirm these column roles
              </button>
            </p>
          </Callout>
        ) : null}

        <div className="run-bar" data-ready={ready.ready ? 'true' : 'false'}>
          <div className="run-bar__status">
            <p className="run-bar__summary" style={{ margin: '0 0 2px' }}>
              <span
                className={`status-dot status-dot--${ready.ready ? 'ok' : ready.columnState === 'checking' ? 'wait' : 'warn'}`}
                aria-hidden="true"
              />
              <strong>{ready.ready ? 'Ready to run' : 'Not ready yet'}</strong>
              <span className="muted"> · Split: {ready.splitDescription}</span>
            </p>
            {ready.workflowBlockers.length ? (
              <ul className="list-tight small" style={{ margin: 0 }}>
                {ready.workflowBlockers.map((blocker) => (
                  <li key={blocker} className="warn-text">
                    {blocker}
                  </li>
                ))}
              </ul>
            ) : null}
            {ready.cautions.length ? (
              <ul className="list-tight small" style={{ margin: 0 }}>
                {ready.cautions.map((caution) => (
                  <li key={caution} className="warn-text">
                    {caution}
                  </li>
                ))}
              </ul>
            ) : null}
            {!ready.workflowBlockers.length && !ready.cautions.length ? (
              <p className="small muted" style={{ margin: 0 }}>
                Every prerequisite is answered. Running the audit applies every enabled check to this
                split.
              </p>
            ) : null}
          </div>
          <button
            type="button"
            className="btn btn--primary"
            disabled={!ready.ready || busyLabel !== null}
            onClick={async () => {
              const ok = await runAudit()
              if (ok) onNavigate('audit')
            }}
          >
            {ready.runLabel} →
          </button>
        </div>
      </Card>

      <details className="disclosure">
        <summary>File details</summary>
        <div className="kv">
          <dt>Source</dt>
          <dd>
            {summary.source}
            {summary.demo_id ? ` · demo ${summary.demo_id}` : ''}
          </dd>
          <dt>SHA-256</dt>
          <dd className="mono tiny break">{summary.fingerprint_sha256}</dd>
          <dt>Loaded</dt>
          <dd>{summary.created_at_utc}</dd>
          <dt>Internal row ids</dt>
          <dd>
            Assigned by SplitScope as <span className="mono">row-000001</span> upward. They do not
            depend on whether the file has its own identifier column, and they are what every finding
            cites.
          </dd>
          <dt>Limits in force</dt>
          <dd className="small">
            {bytes(limits.max_upload_bytes)} upload · {integer(limits.max_rows)} rows ·{' '}
            {integer(limits.max_columns)} columns · minimum {integer(limits.min_rows)} rows
          </dd>
        </div>
        {summary.warnings.length ? (
          <Callout tone="warn" title="Notices recorded while reading the file">
            <ul className="list-tight">
              {summary.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </Callout>
        ) : null}
      </details>

      <details className="disclosure">
        <summary>Data preview (optional)</summary>
        <p className="small muted" style={{ marginTop: 0 }}>
          {preview?.note ??
            'Values are shown exactly as they appear in the file. Nothing is re-typed or normalised for display.'}
        </p>
        <div className="row" style={{ gap: 6, marginBottom: 8 }}>
          <button
            type="button"
            className="btn btn--small"
            disabled={offset === 0 || busyLabel !== null}
            onClick={async () => {
              const next = Math.max(0, offset - PREVIEW_PAGE)
              setOffset(next)
              await loadPreview(next, PREVIEW_PAGE)
            }}
          >
            ← Previous
          </button>
          <button
            type="button"
            className="btn btn--small"
            disabled={busyLabel !== null}
            onClick={() => void loadPreview(offset, PREVIEW_PAGE)}
          >
            Load rows {offset + 1}–{offset + PREVIEW_PAGE}
          </button>
          <button
            type="button"
            className="btn btn--small"
            disabled={offset + PREVIEW_PAGE >= summary.row_count || busyLabel !== null}
            onClick={async () => {
              const next = offset + PREVIEW_PAGE
              setOffset(next)
              await loadPreview(next, PREVIEW_PAGE)
            }}
          >
            Next →
          </button>
        </div>

        {busyLabel && busyLabel.includes('preview') ? <Spinner label={busyLabel} /> : null}

        {!preview ? (
          <p className="small muted">
            No rows fetched yet — the preview is fetched on demand, so a large dataset is never sent
            to the browser unnecessarily.
          </p>
        ) : (
          <>
            <Table
              caption={`Rows ${preview.offset + 1}–${Math.min(
                preview.offset + preview.rows.length,
                preview.total_rows,
              )} of ${integer(preview.total_rows)}. Each row is labelled with its stable internal row id.`}
              head={
                <tr>
                  <th scope="col">Row id</th>
                  {preview.columns.map((column) => (
                    <th key={column} scope="col">
                      {column}
                      {roles.features.includes(column) ? (
                        <span className="hint">feature</span>
                      ) : column === roles.target ? (
                        <span className="hint">target</span>
                      ) : column === roles.entity ? (
                        <span className="hint">entity</span>
                      ) : column === roles.timestamp ? (
                        <span className="hint">timestamp</span>
                      ) : column === roles.split ? (
                        <span className="hint">split</span>
                      ) : null}
                    </th>
                  ))}
                </tr>
              }
            >
              {preview.rows.map((row, rowIndex) => (
                <tr key={preview.row_ids[rowIndex]}>
                  <th scope="row" className="mono tiny">
                    {preview.row_ids[rowIndex]}
                  </th>
                  {row.map((cell, cellIndex) => (
                    <td key={`${preview.row_ids[rowIndex]}-${preview.columns[cellIndex]}`}>
                      {cell === '' ? (
                        <span className="muted tiny italic">(empty = missing)</span>
                      ) : (
                        <span className="mono tiny">{truncate(cell, 60)}</span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </Table>
            {preview.truncated_columns ? (
              <p className="tiny muted">
                Only the first {preview.columns.length} columns are shown, matching the configured
                column limit.
              </p>
            ) : null}
          </>
        )}
      </details>

      <details className="disclosure">
        <summary>Column profile (optional)</summary>
        <p className="small muted" style={{ marginTop: 0 }}>
          These ratios describe what is in the file. They are used to reject impossible role choices
          and to decide whether the chronology and near-duplicate checks can run; they are not
          findings.
        </p>
        <Table
          head={
            <tr>
              <th scope="col">Column</th>
              <th scope="col" className="num">
                Numeric
              </th>
              <th scope="col" className="num">
                Date-parseable
              </th>
              <th scope="col" className="num">
                Distinct
              </th>
              <th scope="col" className="num">
                Missing
              </th>
              <th scope="col">Example values</th>
            </tr>
          }
        >
          {summary.columns.map((column) => {
            const info = dataset.column_types[column]
            if (!info) return null
            return (
              <tr key={column}>
                <th scope="row" className="mono tiny">
                  {column}
                </th>
                <td className="num">{percent(info.numeric_parse_ratio, 0)}</td>
                <td className="num">{percent(info.datetime_parse_ratio, 0)}</td>
                <td className="num">{integer(info.distinct_values)}</td>
                <td className="num">{percent(info.missing_ratio, 1)}</td>
                <td className="mono tiny break">
                  {info.example_values.length ? info.example_values.join(' · ') : '—'}
                </td>
              </tr>
            )
          })}
        </Table>
      </details>

      <details className="disclosure">
        <summary>Audit settings (advanced)</summary>
        <p className="small muted" style={{ marginTop: 0 }}>
          Every threshold below is recorded in the report, so a finding can always be traced back to
          the configuration that produced it. Changing a threshold changes what is reported, never
          what the data is. The defaults work well — you do not need this section for a first run.
        </p>
        <AuditConfigEditor
          config={config}
          onChange={setConfig}
          hasTarget={roles.target !== null}
          hasEntity={roles.entity !== null}
          hasTimestamp={roles.timestamp !== null}
          numericFeatureRatio={numericRatio}
        />
      </details>
    </div>
  )
}
