/**
 * Typed API client.
 *
 * Every failure is turned into an `ApiError` carrying the backend's own `code`,
 * `message` and `details`, so the UI can render exactly what the server said
 * rather than a generic network message. Non-JSON responses (a proxy error page,
 * a crashed server) are reported as `unreachable` with the status code.
 */

import type {
  PlanConfig,
  SimilarityResponse,
  ApiErrorBody,
  AuditConfig,
  AuditResponse,
  ChecksResponse,
  ColumnRoles,
  ColumnValuesResponse,
  CompareResponse,
  DatasetLoadedResponse,
  DemoListResponse,
  HealthResponse,
  PreviewResponse,
  RoleValidationResult,
  SplitConfig,
  DictionaryResponse,
  ManifestResponse,
  ManifestValidation,
  ProfileResponse,
  RoleMapResponse,
  StudyResponse,
} from './types'

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

const BASE = ''

async function parseError(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }
  const envelope = body as ApiErrorBody | null
  if (envelope && typeof envelope === 'object' && envelope.error && typeof envelope.error.message === 'string') {
    return new ApiError(
      response.status,
      envelope.error.code ?? 'error',
      envelope.error.message,
      envelope.error.details ?? {},
    )
  }
  return new ApiError(
    response.status,
    'unreachable',
    `The server returned ${response.status} ${response.statusText} without a structured error body. Is the backend running on the expected port?`,
    {},
  )
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, init)
  } catch (cause) {
    throw new ApiError(
      0,
      'unreachable',
      'The SplitScope backend could not be reached. Start it with `python -m app.main` in backend/, then try again.',
      { cause: cause instanceof Error ? cause.message : String(cause) },
    )
  }
  if (!response.ok) {
    throw await parseError(response)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

function jsonInit(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  checks: () => request<ChecksResponse>('/api/checks'),
  demos: () => request<DemoListResponse>('/api/demos'),

  loadDemo: (demoId: string) =>
    request<DatasetLoadedResponse>(`/api/demos/${encodeURIComponent(demoId)}/load`, { method: 'POST' }),

  uploadDataset: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DatasetLoadedResponse>('/api/datasets', { method: 'POST', body: form })
  },

  dataset: (datasetId: string) =>
    request<DatasetLoadedResponse>(`/api/datasets/${encodeURIComponent(datasetId)}`),

  preview: (datasetId: string, offset: number, limit: number) =>
    request<PreviewResponse>(
      `/api/datasets/${encodeURIComponent(datasetId)}/preview?offset=${offset}&limit=${limit}`,
    ),

  validateRoles: (datasetId: string, roles: ColumnRoles) =>
    request<RoleValidationResult>(`/api/datasets/${encodeURIComponent(datasetId)}/roles/validate`, {
      ...jsonInit({ roles }),
    }),

  /** Observed values of one column with their row counts, for the train/test mapping step. */
  columnValues: (datasetId: string, column: string, limit = 100) =>
    request<ColumnValuesResponse>(
      `/api/datasets/${encodeURIComponent(datasetId)}/column-values?column=${encodeURIComponent(
        column,
      )}&limit=${limit}`,
    ),

  /**
   * Runs the audit. `generate` asks the server to build the split first; when it
   * is omitted the split column named in `roles` is read from the file.
   */
  audit: (datasetId: string, roles: ColumnRoles, config: AuditConfig, generate?: SplitConfig) =>
    request<AuditResponse>(
      '/api/audit',
      jsonInit(generate ? { dataset_id: datasetId, roles, config, generate } : { dataset_id: datasetId, roles, config }),
    ),

  compare: (
    datasetId: string,
    roles: ColumnRoles,
    config: AuditConfig,
    strategies: SplitConfig[],
    includeExistingSplit: boolean,
    plans: PlanConfig[] = [],
  ) =>
    request<CompareResponse>(
      '/api/splits/compare',
      jsonInit({
        dataset_id: datasetId,
        roles,
        config,
        strategies,
        plans,
        include_existing_split: includeExistingSplit,
      }),
    ),
}

/** Downloads a report or export produced by the backend. */
export async function downloadExport(path: string, body?: unknown): Promise<void> {
  const response = await fetch(`${BASE}${path}`, body === undefined ? undefined : jsonInit(body))
  if (!response.ok) {
    throw await parseError(response)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = /filename="?([^";]+)"?/.exec(disposition)
  const filename = match?.[1] ?? 'splitscope-export'

  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}


// --------------------------------------------------------------------------
// S3 research workspace
// --------------------------------------------------------------------------

export const researchApi = {
  study: (dataset_id: string) => request<StudyResponse>(`/api/datasets/${dataset_id}/study`),
  saveStudy: (dataset_id: string, body: unknown) =>
    request<StudyResponse>(`/api/datasets/${dataset_id}/study`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  profile: (dataset_id: string) => request<ProfileResponse>(`/api/datasets/${dataset_id}/profile`),
  dictionary: (dataset_id: string) =>
    request<DictionaryResponse>(`/api/datasets/${dataset_id}/dictionary`),
  saveRoles: (dataset_id: string, body: unknown) =>
    request<RoleMapResponse>(`/api/datasets/${dataset_id}/roles`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  manifest: (dataset_id: string) =>
    request<ManifestResponse>(`/api/datasets/${dataset_id}/manifest`),
  validateManifest: (dataset_id: string, manifest: unknown, apply: boolean) =>
    request<ManifestValidation>(`/api/datasets/${dataset_id}/manifest/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ manifest, apply }),
    }),
  studyExportPath: (dataset_id: string) => `/api/datasets/${dataset_id}/study/export`,
  manifestExportPath: (dataset_id: string) => `/api/datasets/${dataset_id}/manifest/export`,
}

// --------------------------------------------------------------------------
// S4 Scientific Visual Explorer
// --------------------------------------------------------------------------

import type {
  CorrelationResponse,
  DistributionResponse,
  ExploreSchema,
  MissingnessResponse,
  RowsResponse,
  SelectionResponse,
  SeriesResponse,
} from './types'

function postInit(body: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export const exploreApi = {
  schema: (datasetId: string) =>
    request<ExploreSchema>(`/api/datasets/${encodeURIComponent(datasetId)}/explore/schema`),

  series: (datasetId: string, body: { columns: string[]; max_rows?: number; filters?: unknown[] }) =>
    request<SeriesResponse>(`/api/datasets/${encodeURIComponent(datasetId)}/explore/series`, postInit(body)),

  selection: (datasetId: string, predicates: unknown[]) =>
    request<SelectionResponse>(`/api/datasets/${encodeURIComponent(datasetId)}/explore/selection`, postInit({ predicates })),

  correlation: (datasetId: string, columns: string[], method: 'pearson' | 'spearman') =>
    request<CorrelationResponse>(`/api/datasets/${encodeURIComponent(datasetId)}/explore/correlation`, postInit({ columns, method })),

  distribution: (datasetId: string, body: { column: string; bins?: number; group_by?: string | null; filters?: unknown[] }) =>
    request<DistributionResponse>(`/api/datasets/${encodeURIComponent(datasetId)}/explore/distribution`, postInit(body)),

  missingness: (datasetId: string, body: { columns?: string[]; group_by?: string | null; filters?: unknown[] }) =>
    request<MissingnessResponse>(`/api/datasets/${encodeURIComponent(datasetId)}/explore/missingness`, postInit(body)),

  similarity: (datasetId: string, body: { max_pairs: number; columns?: string[] }) =>
    request<SimilarityResponse>(
      `/api/datasets/${encodeURIComponent(datasetId)}/explore/similarity`,
      postInit(body),
    ),

  rows: (datasetId: string, ids: string[], columns?: string[]) =>
    request<RowsResponse>(`/api/datasets/${encodeURIComponent(datasetId)}/explore/rows`, postInit({ ids, columns })),
}

// --------------------------------------------------------------------------
// S6 Model Lab — statistical workbench
// --------------------------------------------------------------------------

import type {
  ModelRunListResponse,
  PredictionRequest,
  PredictionResult,
  StatisticalModelResult,
  StatisticsRequest,
} from './types'

export const modelsApi = {
  fitStatistics: (datasetId: string, body: StatisticsRequest) =>
    request<StatisticalModelResult>(
      `/api/datasets/${encodeURIComponent(datasetId)}/models/statistics`,
      postInit(body),
    ),

  fitPrediction: (datasetId: string, body: PredictionRequest) =>
    request<PredictionResult>(
      `/api/datasets/${encodeURIComponent(datasetId)}/models/prediction`,
      postInit(body),
    ),

  runs: (datasetId: string) =>
    request<ModelRunListResponse>(`/api/datasets/${encodeURIComponent(datasetId)}/models/runs`),

  runExportPath: (runId: string) => `/api/models/runs/${encodeURIComponent(runId)}/export`,
}

// --------------------------------------------------------------------------
// S7 evidence dossier
// --------------------------------------------------------------------------

import type { DossierReport, DossierRequest } from './types'

export function dossierPath(datasetId: string, format: 'json' | 'html' = 'json'): string {
  return `/api/datasets/${encodeURIComponent(datasetId)}/reports/dossier?format=${format}`
}

export const reportsApi = {
  generate: (datasetId: string, body: DossierRequest) =>
    request<DossierReport>(dossierPath(datasetId, 'json'), postInit(body)),
  exportPath: dossierPath,
}
