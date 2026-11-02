import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { ApiError, api, downloadExport } from '../api/client'
import type {
  AuditConfig,
  AuditResponse,
  ChecksResponse,
  ColumnRoles,
  ColumnValuesResponse,
  CompareResponse,
  DatasetLoadedResponse,
  DemoListResponse,
  Finding,
  HealthResponse,
  PlanConfig,
  PreviewResponse,
  RoleValidationResult,
  SplitConfig,
} from '../api/types'
import { DEFAULT_AUDIT_CONFIG, EMPTY_ROLES } from '../lib/defaults'
import { pluralise } from '../lib/format'
import { normaliseRolePatch } from '../lib/roles'
import type { SplitMode } from '../lib/readiness'

export type StatusKind = 'idle' | 'busy' | 'ok' | 'error'

export interface Status {
  kind: StatusKind
  message: string
  code?: string
  details?: Record<string, unknown>
}

export interface SelectedFinding {
  finding: Finding
  origin: 'audit' | 'comparison'
  contextLabel: string
}

interface AppState {
  health: HealthResponse | null
  checks: ChecksResponse | null
  demos: DemoListResponse | null
  dataset: DatasetLoadedResponse | null
  roles: ColumnRoles
  config: AuditConfig
  validation: RoleValidationResult | null
  /** True while a debounced re-validation of the current roles is in flight. */
  validationPending: boolean
  preview: PreviewResponse | null
  audit: AuditResponse | null
  comparison: CompareResponse | null
  selectedFinding: SelectedFinding | null
  status: Status
  busyLabel: string | null
  strategies: SplitConfig[]
  /** F05 evaluation plans included in the next comparison. */
  plans: PlanConfig[]
  includeExistingSplit: boolean
  /** Which entry path the user chose: audit the file's split, or generate one. */
  splitMode: SplitMode | null
  /** The split to generate when `splitMode` is 'generate'. */
  generateSplit: SplitConfig | null
  /**
   * Whether the user vouches for the current roles. Name-based suggestions from
   * an upload start unconfirmed; demo manifest roles are documented
   * configuration and start confirmed.
   */
  suggestionsConfirmed: boolean
  /**
   * Observed values of the current split column (existing-split path), so the
   * train/test mapping is chosen from what the file actually contains.
   */
  observedValues: ColumnValuesResponse | null
  /**
   * Explanations of the automatic adjustments the last role edit made (a column
   * leaving the feature list, a released special role, a cleared stale value).
   */
  roleNotes: string[]
}

interface AppActions {
  reloadCatalogue: () => Promise<void>
  refreshHealth: () => Promise<void>
  loadDemo: (demoId: string) => Promise<void>
  uploadFile: (file: File) => Promise<void>
  setRoles: (roles: ColumnRoles) => void
  patchRoles: (patch: Partial<ColumnRoles>) => void
  setConfig: (config: AuditConfig) => void
  setStrategies: (strategies: SplitConfig[]) => void
  setPlans: (plans: PlanConfig[]) => void
  setIncludeExistingSplit: (value: boolean) => void
  /** Answers the entry question; `null` re-opens it. */
  setSplitMode: (mode: SplitMode | null) => void
  setGenerateSplit: (split: SplitConfig | null) => void
  /** Fetches the observed values of `column`, or clears them when null. */
  loadColumnValues: (column: string | null) => Promise<void>
  /** The user vouches for the current roles (accepting or adjusting the guesses). */
  confirmSuggestions: () => void
  validateRoles: () => Promise<void>
  loadPreview: (offset: number, limit: number) => Promise<void>
  runAudit: () => Promise<boolean>
  runComparison: () => Promise<boolean>
  selectFinding: (finding: Finding, origin: 'audit' | 'comparison', contextLabel: string) => void
  clearSelectedFinding: () => void
  download: (path: string, body?: unknown) => Promise<void>
  dismissStatus: () => void
  reset: () => void
}

type Ctx = AppState & AppActions

const AppContext = createContext<Ctx | null>(null)

const IDLE_STATUS: Status = { kind: 'idle', message: '' }

/** Pause after the last role edit before re-validating with the server. */
const VALIDATION_DEBOUNCE_MS = 350

/** Stable identity for a role set, used to reject answers about older roles. */
function rolesKey(roles: ColumnRoles): string {
  return JSON.stringify([
    [...roles.features],
    roles.target,
    roles.entity,
    roles.timestamp,
    roles.split,
    roles.split_train_value,
    roles.split_test_value,
    [...roles.metadata_excluded],
  ])
}

function initialState(): AppState {
  return {
    health: null,
    checks: null,
    demos: null,
    dataset: null,
    roles: { ...EMPTY_ROLES },
    config: structuredClone(DEFAULT_AUDIT_CONFIG),
    validation: null,
    validationPending: false,
    preview: null,
    audit: null,
    comparison: null,
    selectedFinding: null,
    status: IDLE_STATUS,
    busyLabel: null,
    strategies: [
      { kind: 'random', label: 'Random holdout', test_fraction: 0.25, seed: 12345 },
      { kind: 'group', label: 'Group holdout', test_fraction: 0.25, seed: 12345 },
    ],
    plans: [],
    includeExistingSplit: true,
    // Undecided until the entry-path question is answered; a dataset whose
    // suggestions include a split column pre-selects the existing-split path.
    splitMode: null,
    generateSplit: null,
    suggestionsConfirmed: false,
    observedValues: null,
    roleNotes: [],
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppState>(initialState)
  const mounted = useRef(true)
  // Bumped whenever a new dataset becomes current (or the session is reset).
  // In-flight requests started for a previous dataset compare their token
  // against this and discard their result instead of writing stale audit,
  // comparison, validation or preview data into the new dataset's view.
  const generation = useRef(0)
  // Observed split-column values belong to one dataset and one column; this
  // token discards responses that arrive after the selection moved on.
  const columnValuesSeq = useRef(0)
  // Role validation is asynchronous and debounced. A response is only allowed
  // to become the visible validation if it still describes the current roles;
  // the sequence is bumped as soon as an edit happens, not when the debounce
  // fires, so an in-flight answer for the previous roles cannot land in the gap
  // and briefly make a stale configuration look runnable.
  const validationTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const validationSeq = useRef(0)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const describeError = useCallback((error: unknown, fallback: string): Status => {
    if (error instanceof ApiError) {
      return { kind: 'error', message: error.message, code: error.code, details: error.details }
    }
    return {
      kind: 'error',
      message: error instanceof Error ? error.message : fallback,
    }
  }, [])

  /** Runs an async action with a labelled busy state and uniform error handling. */
  const withBusy = useCallback(
    async <T,>(label: string, action: () => Promise<T>): Promise<T | null> => {
      setState((previous) => ({ ...previous, busyLabel: label, status: { kind: 'busy', message: label } }))
      try {
        const result = await action()
        if (mounted.current) {
          // Keep a status the action set deliberately; only clear the busy state.
          setState((previous) => ({
            ...previous,
            busyLabel: null,
            status: previous.status.kind === 'busy' ? IDLE_STATUS : previous.status,
          }))
        }
        return result
      } catch (error) {
        if (mounted.current) {
          setState((previous) => ({
            ...previous,
            busyLabel: null,
            status: describeError(error, `${label} failed.`),
          }))
        }
        return null
      }
    },
    [describeError],
  )

  const reloadCatalogue = useCallback(async () => {
    await withBusy('Loading checks and demos', async () => {
      const [health, checks, demos] = await Promise.all([api.health(), api.checks(), api.demos()])
      setState((previous) => ({ ...previous, health, checks, demos }))
    })
  }, [withBusy])

  // The check catalogue and the demo list are static for the lifetime of the
  // server process, so fetch them once when the app mounts. Nothing else in the
  // app requests them, and without this the overview stats, the check
  // catalogue and the demo picker stay in their "has not loaded yet" state
  // forever.
  useEffect(() => {
    void reloadCatalogue()
  }, [reloadCatalogue])

  // The store counters inside health (datasets, runs, memory used) change as
  // the user works, so the export page re-fetches health on every mount instead
  // of trusting the startup snapshot. Failures are ignored: the page still
  // renders with the last known values.
  const refreshHealth = useCallback(async () => {
    try {
      const health = await api.health()
      if (mounted.current) setState((previous) => ({ ...previous, health }))
    } catch {
      /* keep the previous health snapshot */
    }
  }, [])

  const applyLoaded = useCallback((loaded: DatasetLoadedResponse) => {
    generation.current += 1
    columnValuesSeq.current += 1
    validationSeq.current += 1
    if (validationTimer.current) clearTimeout(validationTimer.current)
    const hasSplitColumn = loaded.suggested_roles.split !== null
    setState((previous) => ({
      ...previous,
      dataset: loaded,
      roles: loaded.suggested_roles,
      config: {
        // Merge over the defaults so a recommended config from an older backend
        // (missing newer declaration fields) can never leave the editor reading
        // undefined structures.
        ...structuredClone(DEFAULT_AUDIT_CONFIG),
        ...(loaded.recommended_audit_config ?? {}),
      },
      validation: loaded.validation,
      validationPending: false,
      preview: null,
      audit: null,
      comparison: null,
      selectedFinding: null,
      strategies: previous.strategies,
      plans: previous.plans,
      // Only a demo's split column (manifest configuration) pre-selects the
      // existing-split path. An upload's split column is a name-based guess, so
      // an upload always starts at the entry-path question instead.
      splitMode: loaded.dataset.source === 'demo' && hasSplitColumn ? 'existing' : null,
      generateSplit: null,
      // Demo roles are documented manifest configuration; an upload's roles are
      // name-based guesses the user has not vouched for yet.
      suggestionsConfirmed: loaded.dataset.source === 'demo',
      observedValues: null,
      roleNotes: [],
      status: {
        kind: 'ok',
        message: `${loaded.dataset.name} loaded: ${loaded.dataset.row_count.toLocaleString()} rows × ${loaded.dataset.column_count} columns.`,
      },
    }))
  }, [])

  const loadDemo = useCallback(
    async (demoId: string) => {
      const result = await withBusy(`Loading demo ${demoId}`, () => api.loadDemo(demoId))
      if (result) applyLoaded(result)
    },
    [applyLoaded, withBusy],
  )

  const uploadFile = useCallback(
    async (file: File) => {
      const result = await withBusy(`Uploading ${file.name}`, () => api.uploadDataset(file))
      if (result) applyLoaded(result)
    },
    [applyLoaded, withBusy],
  )

  const setRoles = useCallback((roles: ColumnRoles) => {
    validationSeq.current += 1
    setState((previous) => ({ ...previous, roles, validation: null, validationPending: true }))
  }, [])

  const patchRoles = useCallback((patch: Partial<ColumnRoles>) => {
    validationSeq.current += 1
    setState((previous) => {
      const columns = new Set(previous.dataset?.dataset.columns ?? [])
      const exists = (name: string) => columns.size === 0 || columns.has(name)
      const { roles, notes } = normaliseRolePatch(previous.roles, patch, exists)
      return {
        ...previous,
        roles,
        // The server has not seen these roles yet; anything shown about them
        // from an earlier check is stale until the debounced re-check lands.
        validation: null,
        validationPending: true,
        // Every automatic adjustment is explained where the questions are
        // answered, not silently applied.
        roleNotes: notes,
      }
    })
  }, [])

  const setConfig = useCallback((config: AuditConfig) => {
    setState((previous) => ({ ...previous, config }))
  }, [])

  const setStrategies = useCallback((strategies: SplitConfig[]) => {
    setState((previous) => ({ ...previous, strategies }))
  }, [])

  const setPlans = useCallback((plans: PlanConfig[]) => {
    setState((previous) => ({ ...previous, plans }))
  }, [])

  const setIncludeExistingSplit = useCallback((value: boolean) => {
    setState((previous) => ({ ...previous, includeExistingSplit: value }))
  }, [])

  const setSplitMode = useCallback(
    (mode: SplitMode | null) => {
      setState((previous) => {
        // Pre-select a sensible default strategy when switching to the generated
        // path, so the user starts from an eligible candidate rather than nothing.
        const generateSplit =
          previous.generateSplit ??
          ({ kind: 'random', label: 'Random holdout', test_fraction: 0.25, seed: 12345 } as SplitConfig)
        const next: AppState = {
          ...previous,
          splitMode: mode,
          generateSplit: mode === 'generate' ? generateSplit : previous.generateSplit,
        }
        // Choosing "create a split" means the file's own split column takes no
        // part in this run. Clearing it keeps the submitted roles, the report
        // and the split that is actually audited in agreement — the file itself
        // is never modified, and choosing the existing path again offers the
        // suggestion once more.
        if (mode !== 'generate' || !previous.roles.split) return next
        validationSeq.current += 1
        const columns = new Set(previous.dataset?.dataset.columns ?? [])
        const exists = (name: string) => columns.size === 0 || columns.has(name)
        const { roles } = normaliseRolePatch(
          previous.roles,
          { split: null, split_train_value: null, split_test_value: null },
          exists,
        )
        return {
          ...next,
          roles,
          // The server has not seen these roles yet; re-validation follows.
          validation: null,
          validationPending: true,
          roleNotes: [
            `${previous.roles.split} is no longer a role column because you chose to create a split; the file itself is unchanged.`,
          ],
        }
      })
    },
    [],
  )

  const setGenerateSplit = useCallback((split: SplitConfig | null) => {
    setState((previous) => ({ ...previous, generateSplit: split }))
  }, [])

  // Observed values of the split column (existing-split path only), so the
  // train/test labels are mapped from values the file really contains.
  const loadColumnValues = useCallback(
    async (column: string | null) => {
      const seq = ++columnValuesSeq.current
      if (!column) {
        setState((previous) => (previous.observedValues === null ? previous : { ...previous, observedValues: null }))
        return
      }
      const dataset = state.dataset
      if (!dataset) return
      const token = generation.current
      try {
        const response = await api.columnValues(dataset.dataset.dataset_id, column, 50)
        if (!mounted.current || seq !== columnValuesSeq.current || token !== generation.current) return
        if (!response || response.column !== column) return
        setState((previous) => ({ ...previous, observedValues: response }))
      } catch {
        // The mapping stays usable through the text inputs; only the observed
        // values list is unavailable. Never surface this as an error.
        if (!mounted.current || seq !== columnValuesSeq.current || token !== generation.current) return
        setState((previous) => (previous.observedValues === null ? previous : { ...previous, observedValues: null }))
      }
    },
    [state.dataset],
  )

  const confirmSuggestions = useCallback(() => {
    setState((previous) => ({ ...previous, suggestionsConfirmed: true }))
  }, [])

  // Live role validation. Every role edit re-checks with the server after a
  // short pause, so the issues next to the controls and the run gate always
  // describe the roles as they now are, never a stale upload-time result.
  const scheduleValidation = useCallback(
    (roles: ColumnRoles, datasetId: string) => {
      if (validationTimer.current) clearTimeout(validationTimer.current)
      const seq = ++validationSeq.current
      validationTimer.current = setTimeout(() => {
        void (async () => {
          try {
            const result = await api.validateRoles(datasetId, roles)
            if (!mounted.current || seq !== validationSeq.current) return
            setState((previous) => {
              // Belt and braces: the sequence already discards old requests,
              // but never attach an answer to roles it did not describe.
              if (rolesKey(previous.roles) !== rolesKey(roles)) return previous
              return {
                ...previous,
                validation: result ?? previous.validation,
                validationPending: false,
              }
            })
          } catch {
            // Keep the previous validation; the run gate stays closed because
            // validationPending is cleared only on a landed response.
            if (!mounted.current || seq !== validationSeq.current) return
            setState((previous) => ({ ...previous, validationPending: false }))
          }
        })()
      }, VALIDATION_DEBOUNCE_MS)
    },
    [],
  )

  useEffect(
    () => () => {
      if (validationTimer.current) clearTimeout(validationTimer.current)
    },
    [],
  )

  useEffect(() => {
    const datasetId = state.dataset?.dataset.dataset_id
    if (!datasetId || !state.validationPending) return
    scheduleValidation(state.roles, datasetId)
  }, [state.dataset, state.roles, state.validationPending, scheduleValidation])

  const validateRoles = useCallback(async () => {
    const dataset = state.dataset
    if (!dataset) return
    const token = generation.current
    if (validationTimer.current) clearTimeout(validationTimer.current)
    validationSeq.current += 1
    await withBusy('Validating column roles', async () => {
      const validation = await api.validateRoles(dataset.dataset.dataset_id, state.roles)
      if (token !== generation.current || !validation) return
      setState((previous) => {
        if (rolesKey(previous.roles) !== rolesKey(state.roles)) return previous
        return { ...previous, validation, validationPending: false }
      })
    })
  }, [state.dataset, state.roles, withBusy])

  const loadPreview = useCallback(
    async (offset: number, limit: number) => {
      const dataset = state.dataset
      if (!dataset) return
      const token = generation.current
      await withBusy('Loading dataset preview', async () => {
        const preview = await api.preview(dataset.dataset.dataset_id, offset, limit)
        if (token !== generation.current) return
        setState((previous) => ({ ...previous, preview }))
      })
    },
    [state.dataset, withBusy],
  )

  const runAudit = useCallback(async () => {
    const dataset = state.dataset
    if (!dataset) return false
    const token = generation.current
    const generate = state.splitMode === 'generate' ? state.generateSplit ?? undefined : undefined
    const result = await withBusy('Running the audit', () =>
      api.audit(dataset.dataset.dataset_id, state.roles, state.config, generate),
    )
    if (!result) return false
    if (token !== generation.current) return false
    setState((previous) => ({
      ...previous,
      audit: result,
      selectedFinding: null,
      status: { kind: 'ok', message: result.result.evaluation.headline },
    }))
    return true
  }, [state.dataset, state.roles, state.config, state.splitMode, state.generateSplit, withBusy])

  const runComparison = useCallback(async () => {
    const dataset = state.dataset
    if (!dataset) return false
    const token = generation.current
    // The existing-split candidate only exists when the roles name a split
    // column; asking for it without one is a 422 the user cannot act on.
    const includeExisting = state.includeExistingSplit && state.roles.split !== null
    const result = await withBusy('Comparing candidate splits', () =>
      api.compare(
        dataset.dataset.dataset_id,
        state.roles,
        state.config,
        state.strategies,
        includeExisting,
        state.plans,
      ),
    )
    if (!result) return false
    if (token !== generation.current) return false
    setState((previous) => ({
      ...previous,
      comparison: result,
      selectedFinding: null,
      status: {
        kind: 'ok',
        message: `Compared ${result.result.rows.length} ${pluralise(
          result.result.rows.length,
          'split',
        )} with the same checks and settings.`,
      },
    }))
    return true
  }, [state.dataset, state.roles, state.config, state.strategies, state.plans, state.includeExistingSplit, withBusy])

  const selectFinding = useCallback(
    (finding: Finding, origin: 'audit' | 'comparison', contextLabel: string) => {
      setState((previous) => ({ ...previous, selectedFinding: { finding, origin, contextLabel } }))
    },
    [],
  )

  const clearSelectedFinding = useCallback(() => {
    setState((previous) => ({ ...previous, selectedFinding: null }))
  }, [])

  const download = useCallback(
    async (path: string, body?: unknown) => {
      await withBusy('Preparing the download', async () => {
        await downloadExport(path, body)
        setState((previous) => ({ ...previous, status: { kind: 'ok', message: 'Download started.' } }))
      })
    },
    [withBusy],
  )

  const dismissStatus = useCallback(() => {
    setState((previous) => ({ ...previous, status: IDLE_STATUS }))
  }, [])

  const reset = useCallback(() => {
    generation.current += 1
    validationSeq.current += 1
    if (validationTimer.current) clearTimeout(validationTimer.current)
    setState((previous) => ({
      ...initialState(),
      health: previous.health,
      checks: previous.checks,
      demos: previous.demos,
      status: { kind: 'ok', message: 'Cleared the loaded dataset and results.' },
    }))
  }, [])

  const value = useMemo<Ctx>(
    () => ({
      ...state,
      reloadCatalogue,
      refreshHealth,
      loadDemo,
      uploadFile,
      setRoles,
      patchRoles,
      setConfig,
      setStrategies,
      setPlans,
      setIncludeExistingSplit,
      setSplitMode,
      setGenerateSplit,
      loadColumnValues,
      confirmSuggestions,
      validateRoles,
      loadPreview,
      runAudit,
      runComparison,
      selectFinding,
      clearSelectedFinding,
      download,
      dismissStatus,
      reset,
    }),
    [
      state,
      reloadCatalogue,
      refreshHealth,
      loadDemo,
      uploadFile,
      setRoles,
      patchRoles,
      setConfig,
      setStrategies,
      setPlans,
      setIncludeExistingSplit,
      setSplitMode,
      setGenerateSplit,
      loadColumnValues,
      confirmSuggestions,
      validateRoles,
      loadPreview,
      runAudit,
      runComparison,
      selectFinding,
      clearSelectedFinding,
      download,
      dismissStatus,
      reset,
    ],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp(): Ctx {
  const context = useContext(AppContext)
  if (context === null) {
    throw new Error('useApp must be used inside <AppProvider>')
  }
  return context
}
