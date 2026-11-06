/**
 * Effect Estimation Studio (S9B).
 *
 * The workspace between identification and reporting. It reads the dataset from
 * the app context and a *saved* causal graph from the S8A API, so entering the
 * studio never asks a researcher to rebuild a DAG. Every number on screen comes
 * from the S9A estimation endpoints; this component only configures requests,
 * orders responses and renders results.
 *
 * Load-bearing state distinctions:
 *  - readiness (checking / ready / blocked) is tied to one request signature,
 *    so a readiness answer for older settings can never authorise a run;
 *  - a run records the signature it was launched with; a later configuration or
 *    graph change turns the displayed result stale with named reasons rather
 *    than silently presenting old numbers as current;
 *  - response sequence counters discard out-of-order answers, so a slow earlier
 *    request cannot overwrite a newer result;
 *  - a failed estimator is rendered as failed, never as zero.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { api, causalApi, estimationApi } from '../api/client'
import type {
  CausalGraphPayload,
  CausalGraphSummary,
  CausalIdentificationResponse,
  EstimationRunPayload,
  EstimationRunSummary,
  EstimationValidateResponse,
  EstimatorName,
} from '../api/types'
import type { ViewId } from '../lib/router'
import { describeError, type ErrorInfo } from './estimationErrors'
import { useApp } from '../state/AppState'
import { BalanceView } from './BalanceView'
import { EffectSummary } from './EffectSummary'
import { estimationExport } from './downloadRun'
import {
  ESTIMATOR_DESCRIPTIONS,
  ESTIMATOR_LABELS,
  ESTIMATOR_ORDER,
  buildRequest,
  defaultConfig,
  diagnosticResult,
  overlapResult,
  requestSignature,
  stalenessReasons,
  type EstimationConfig,
  type EstimatorChoice,
} from './estimationModel'
import { formatAgo, formatInteger, formatNumber, unitsLabel } from './format'
import { MethodologyView } from './MethodologyView'
import { OverlapView } from './OverlapView'
import { WeightsView } from './WeightsView'

type TabId = 'summary' | 'balance' | 'overlap' | 'weights' | 'methods'

const TABS: Array<{ id: TabId; label: string; hint: string }> = [
  { id: 'summary', label: 'Effect summary', hint: 'Estimates and intervals' },
  { id: 'balance', label: 'Covariate balance', hint: 'Love plot' },
  { id: 'overlap', label: 'Overlap', hint: 'Fitted propensity distributions' },
  { id: 'weights', label: 'Weights', hint: 'Effective sample size' },
  { id: 'methods', label: 'Methodology', hint: 'Assumptions and reproducibility' },
]

type Readiness =
  | { kind: 'idle' }
  | { kind: 'checking'; signature: string }
  | { kind: 'ready'; signature: string; payload: EstimationValidateResponse }
  | { kind: 'blocked'; signature: string; title: string; message: string; details: string[] }

type RunState =
  | { kind: 'idle' }
  | { kind: 'running'; signature: string; label: string }
  | { kind: 'ready'; payload: EstimationRunPayload; signature: string; source: 'run' | 'stored' }

function localProblem(config: EstimationConfig): ErrorInfo | null {
  if (!config.treatmentNode || !config.outcomeNode) {
    return {
      title: 'Choose a treatment and an outcome',
      message:
        'Estimation needs exactly one treatment node and one outcome node, both anchored to measured columns of this dataset.',
      details: [],
      status: 0,
    }
  }
  if (config.treatmentNode === config.outcomeNode) {
    return {
      title: 'Treatment and outcome must differ',
      message: 'The same node cannot be both the treatment and the outcome.',
      details: [],
      status: 0,
    }
  }
  if (!config.treatedValue.trim() || !config.controlValue.trim()) {
    return {
      title: 'Map the two treatment values',
      message:
        'The treated and control values are matched to the data exactly as recorded. Nothing is inferred from the column name.',
      details: [],
      status: 0,
    }
  }
  if (config.treatedValue.trim() === config.controlValue.trim()) {
    return {
      title: 'Treatment mapping is ambiguous',
      message: 'The treated and control values must be different observed values.',
      details: [],
      status: 0,
    }
  }
  if (config.seed.trim() !== '' && !/^\d+$/.test(config.seed.trim())) {
    return {
      title: 'Seed must be a non-negative integer',
      message: 'Leave the seed empty to let the server draw and record one, or enter a whole number.',
      details: [],
      status: 0,
    }
  }
  if (config.truncationEnabled && config.truncationLower >= config.truncationUpper) {
    return {
      title: 'Truncation bounds are invalid',
      message: 'The lower bound must be strictly below the upper bound.',
      details: [],
      status: 0,
    }
  }
  return null
}

export function EstimationView({ onNavigate }: { onNavigate: (view: ViewId) => void }) {
  const { dataset } = useApp()
  const datasetId = dataset?.dataset.dataset_id ?? null
  const datasetFingerprint = dataset?.dataset.fingerprint_sha256 ?? null
  const datasetColumns = dataset?.dataset.columns ?? []

  const [graphs, setGraphs] = useState<CausalGraphSummary[]>([])
  const [graphId, setGraphId] = useState<string | null>(null)
  const [graph, setGraph] = useState<CausalGraphPayload | null>(null)
  const [graphBusy, setGraphBusy] = useState(false)
  const [graphError, setGraphError] = useState<ErrorInfo | null>(null)
  const [identification, setIdentification] = useState<CausalIdentificationResponse | null>(null)
  const [setVerdict, setSetVerdict] = useState<{ valid: boolean; message: string } | null>(null)
  const [columnValues, setColumnValues] = useState<Array<{ value: string; count: number }>>([])

  const [config, setConfig] = useState<EstimationConfig>(defaultConfig())
  const [estimatorChoice, setEstimatorChoice] = useState<EstimatorChoice>('compare')
  const [readiness, setReadiness] = useState<Readiness>({ kind: 'idle' })
  const [run, setRun] = useState<RunState>({ kind: 'idle' })
  const [runError, setRunError] = useState<ErrorInfo | null>(null)
  const [tab, setTab] = useState<TabId>('summary')
  const [diagEstimator, setDiagEstimator] = useState<EstimatorName | null>(null)
  const [history, setHistory] = useState<EstimationRunSummary[]>([])
  const [historyBusy, setHistoryBusy] = useState(false)
  const [historyNote, setHistoryNote] = useState<string | null>(null)

  const readinessSeq = useRef(0)
  const runSeq = useRef(0)
  // Graph listings can finish out of order (the initial load and the one that
  // follows creating the demonstration DAG). Only the newest may set state, so
  // an older empty listing can never erase a graph the user just created.
  const graphListSeq = useRef(0)
  const loadedDataset = useRef<string | null>(null)

  const graphFingerprint = graph?.spec_fingerprint_sha256 ?? null
  const request = useMemo(
    () => (graph ? buildRequest(config, graphFingerprint) : null),
    [config, graph, graphFingerprint],
  )
  const signature = useMemo(
    () => requestSignature(request, { datasetId, graphId, graphFingerprint }),
    [request, datasetId, graphId, graphFingerprint],
  )
  const signatureRef = useRef(signature)
  signatureRef.current = signature
  const requestRef = useRef(request)
  requestRef.current = request

  const payload = run.kind === 'ready' ? run.payload : null

  const staleReasons = useMemo(
    () =>
      payload
        ? stalenessReasons(payload, {
            datasetFingerprint,
            graphId,
            graphFingerprint,
            config,
          })
        : [],
    [payload, datasetFingerprint, graphId, graphFingerprint, config],
  )
  const stale = staleReasons.length > 0
  const staleNote = stale
    ? `Stale: ${staleReasons.map((reason) => reason.label).join(' ')}`
    : null

  const knownEffect = useMemo(() => {
    const demo = dataset?.demo
    if (!demo || demo.demo_id !== 'causal_effect') return null
    const metrics = demo.summary_metrics as Record<string, unknown>
    const trueAte = metrics['true_ate']
    if (typeof trueAte !== 'number') return null
    return {
      value: trueAte,
      note: 'The bundled demonstration dataset was generated with a constant treatment effect of exactly this size, plus measured confounding that biases the raw difference in means. The estimate above is computed from the data through the real S9A engine; the true effect is documented metadata and is never used in the computation.',
    }
  }, [dataset])

  // -- dataset/graph loading ------------------------------------------------- //

  const refreshHistory = useCallback(async () => {
    if (!datasetId) return
    setHistoryBusy(true)
    try {
      const listing = await estimationApi.runs(datasetId)
      setHistory(listing.runs)
      setHistoryNote(null)
    } catch (caught) {
      const info = describeError(caught, 'Run history could not be loaded')
      setHistoryNote(`${info.title}: ${info.message}`)
      setHistory([])
    } finally {
      setHistoryBusy(false)
    }
  }, [datasetId])

  useEffect(() => {
    if (!datasetId) {
      setGraphs([])
      setGraphId(null)
      setGraph(null)
      return
    }
    if (loadedDataset.current === datasetId) return
    loadedDataset.current = datasetId
    let cancelled = false
    setGraphBusy(true)
    setGraphError(null)
    setRun({ kind: 'idle' })
    setReadiness({ kind: 'idle' })
    setConfig(defaultConfig())
    setIdentification(null)
    const listSeq = ++graphListSeq.current
    ;(async () => {
      try {
        const [listing] = await Promise.all([causalApi.list(datasetId), refreshHistory()])
        if (cancelled || listSeq !== graphListSeq.current) return
        setGraphs(listing.graphs)
        if (listing.graphs.length > 0) setGraphId(listing.graphs[0].graph_id)
      } catch (caught) {
        if (!cancelled) setGraphError(describeError(caught, 'Causal graphs could not be loaded'))
      } finally {
        if (!cancelled) setGraphBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [datasetId, refreshHistory])

  useEffect(() => {
    if (!datasetId || !graphId) {
      setGraph(null)
      return
    }
    let cancelled = false
    setGraphBusy(true)
    setGraphError(null)
    setIdentification(null)
    setSetVerdict(null)
    ;(async () => {
      try {
        const loaded = await causalApi.get(datasetId, graphId)
        if (cancelled) return
        setGraph(loaded)
        setRun({ kind: 'idle' })
        setRunError(null)
        setDiagEstimator(null)
        setTab('summary')
        setConfig((previous) => ({
          ...previous,
          treatmentNode: loaded.analysis.treatment ?? '',
          outcomeNode: loaded.analysis.outcome ?? '',
          adjustmentNodes: [],
        }))
        if (loaded.analysis.treatment && loaded.analysis.outcome) {
          try {
            const identified = await causalApi.identify(datasetId, graphId, {
              treatment: loaded.analysis.treatment,
              outcome: loaded.analysis.outcome,
            })
            if (cancelled) return
            setIdentification(identified)
            const firstSet = identified.search?.sets[0]?.set
            if (firstSet) {
              setConfig((previous) => ({ ...previous, adjustmentNodes: [...firstSet] }))
            }
          } catch {
            // Identification is advisory here: the readiness probe enforces it.
            if (!cancelled) setIdentification(null)
          }
        }
      } catch (caught) {
        if (!cancelled) setGraphError(describeError(caught, 'The selected graph could not be loaded'))
      } finally {
        if (!cancelled) setGraphBusy(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [datasetId, graphId])

  // Observed values of the treatment column, so the mapping is chosen from what
  // the file really contains rather than from a guess.
  const treatmentColumn =
    graph?.nodes.find((node) => node.node_id === config.treatmentNode && node.observed)?.column ?? null
  useEffect(() => {
    if (!datasetId || !treatmentColumn) {
      setColumnValues([])
      return
    }
    let cancelled = false
    api
      .columnValues(datasetId, treatmentColumn, 40)
      .then((response) => {
        if (cancelled) return
        setColumnValues(
          response.values
            .filter((value) => value.value !== '')
            .map((value) => ({ value: value.value, count: value.count })),
        )
      })
      .catch(() => {
        if (!cancelled) setColumnValues([])
      })
    return () => {
      cancelled = true
    }
  }, [datasetId, treatmentColumn])

  // -- readiness ------------------------------------------------------------- //

  const localBlock = useMemo(() => localProblem(config), [config])
  const graphBlock = useMemo<ErrorInfo | null>(() => {
    if (!graph) {
      return {
        title: 'No saved causal graph',
        message:
          'Effect estimation runs against a saved causal graph. Draw and save the assumed structure in the Causal Lab, or create the demonstration graph below.',
        details: [],
        status: 0,
      }
    }
    if (!graph.validation.ok) {
      return {
        title: 'The saved graph is structurally invalid',
        message:
          'The backend rejected this graph for estimation. Fix the blocking errors in the Causal Lab, save, and return here.',
        details: graph.validation.errors.map((error) => `${error.code}: ${error.message}`),
        status: 0,
      }
    }
    if (!graph.analysis.treatment || !graph.analysis.outcome) {
      return {
        title: 'The graph has no treatment/outcome scope',
        message:
          'Choose one treatment and one outcome on the saved graph. The studio never guesses a scope from column names.',
        details: [],
        status: 0,
      }
    }
    return null
  }, [graph])

  const block = graphBlock ?? localBlock

  useEffect(() => {
    // A missing dataset or graph is itself a blocked state: the setup panel has
    // to explain the missing prerequisite instead of leaving the run disabled
    // with no reason on screen.
    if (!datasetId) return
    if (block) {
      readinessSeq.current += 1
      setReadiness({
        kind: 'blocked',
        signature,
        title: block.title,
        message: block.message,
        details: block.details,
      })
      return
    }
    const currentRequest = requestRef.current
    if (!currentRequest) return
    const seq = ++readinessSeq.current
    setReadiness({ kind: 'checking', signature })
    const timer = window.setTimeout(() => {
      estimationApi
        .validate(datasetId, graphId, currentRequest)
        .then((payloadResponse) => {
          if (seq !== readinessSeq.current) return
          setReadiness({ kind: 'ready', signature, payload: payloadResponse })
        })
        .catch((caught: unknown) => {
          if (seq !== readinessSeq.current) return
          const info = describeError(caught, 'The readiness probe refused this configuration')
          setReadiness({
            kind: 'blocked',
            signature,
            title: info.title,
            message: info.message,
            details: info.details,
          })
        })
    }, 420)
    return () => window.clearTimeout(timer)
  }, [signature, datasetId, graphId, graph, block])

  const readinessMatches = readiness.kind === 'ready' && readiness.signature === signature
  const canRun = readinessMatches && run.kind !== 'running'

  // -- run ------------------------------------------------------------------- //

  const runLabel =
    estimatorChoice === 'compare'
      ? 'Run comparison'
      : `Run ${ESTIMATOR_LABELS[estimatorChoice]}`

  const startRun = useCallback(async () => {
    if (!datasetId || !graphId || !request || readiness.kind !== 'ready') return
    const seq = ++runSeq.current
    const launchedSignature = signature
    setRunError(null)
    setRun({ kind: 'running', signature: launchedSignature, label: runLabel })
    try {
      const response =
        estimatorChoice === 'compare'
          ? await estimationApi.compare(datasetId, graphId, request, '')
          : await estimationApi.run(datasetId, graphId, request, estimatorChoice, '')
      if (seq !== runSeq.current) return
      setRun({ kind: 'ready', payload: response, signature: launchedSignature, source: 'run' })
      setDiagEstimator(null)
      setTab('summary')
      void refreshHistory()
    } catch (caught) {
      if (seq !== runSeq.current) return
      setRun({ kind: 'idle' })
      setRunError(describeError(caught, 'Estimation failed'))
    }
  }, [datasetId, graphId, request, readiness.kind, signature, estimatorChoice, runLabel, refreshHistory])

  const loadStoredRun = useCallback(
    async (runId: string) => {
      if (!datasetId) return
      const seq = ++runSeq.current
      setRunError(null)
      setRun({ kind: 'running', signature, label: 'Loading stored result' })
      try {
        const stored = await estimationApi.runDetail(datasetId, runId)
        if (seq !== runSeq.current) return
        setRun({ kind: 'ready', payload: stored, signature, source: 'stored' })
        setDiagEstimator(null)
        setTab('summary')
      } catch (caught) {
        if (seq !== runSeq.current) return
        setRun({ kind: 'idle' })
        setRunError(describeError(caught, 'The stored result could not be loaded'))
      }
    },
    [datasetId, signature],
  )

  const returnToLatest = useCallback(() => {
    if (run.kind === 'ready' && run.source === 'stored') {
      setRun({ kind: 'idle' })
      setRunError(null)
    }
  }, [run])

  // -- demonstration graph ---------------------------------------------------- //

  const [demoBusy, setDemoBusy] = useState(false)
  const createDemoGraph = useCallback(async () => {
    if (!datasetId) return
    setDemoBusy(true)
    setGraphError(null)
    try {
      const variables = ['age', 'baseline_score', 'region', 'treatment', 'outcome']
      const spec = {
        schema_version: '1.0.0',
        name: 'Confounding demonstration',
        description:
          'Demonstration DAG for the bundled confounded treatment-effect study: age, baseline score and region affect both assignment and outcome.',
        dataset_id: datasetId,
        nodes: variables.map((variable) => ({
          node_id: variable,
          label: variable,
          column: variable,
          observed: true,
          kind: 'covariate' as const,
          description: null,
          layout: null,
        })),
        edges: [
          { source: 'age', target: 'treatment', rationale: null, reference: null },
          { source: 'baseline_score', target: 'treatment', rationale: null, reference: null },
          { source: 'region', target: 'treatment', rationale: null, reference: null },
          { source: 'age', target: 'outcome', rationale: null, reference: null },
          { source: 'baseline_score', target: 'outcome', rationale: null, reference: null },
          { source: 'region', target: 'outcome', rationale: null, reference: null },
          { source: 'treatment', target: 'outcome', rationale: null, reference: null },
        ],
        analysis: { treatment: 'treatment', outcome: 'outcome' },
        assumptions: [],
      }
      const created = await causalApi.create(datasetId, spec)
      // Invalidate any listing already in flight, then fetch the authoritative
      // list for this dataset.
      const listSeq = ++graphListSeq.current
      const listing = await causalApi.list(datasetId)
      if (listSeq !== graphListSeq.current) return
      setGraphs(listing.graphs)
      setGraphId(created.graph_id)
    } catch (caught) {
      setGraphError(describeError(caught, 'The demonstration graph could not be created'))
    } finally {
      setDemoBusy(false)
    }
  }, [datasetId])

  // -- derived render data ---------------------------------------------------- //

  const diagnostics = useMemo(() => {
    if (!payload) return null
    const named = diagEstimator
      ? payload.results.find((result) => result.estimator === diagEstimator) ?? null
      : null
    return {
      selected: named ?? diagnosticResult(payload),
      overlap: overlapResult(payload),
    }
  }, [payload, diagEstimator])

  const provenance = useMemo(() => {
    if (!payload) return []
    const repro = payload.reproducibility
    return [
      `Run ${payload.run_id} · created ${payload.created_at_utc}`,
      `Dataset ${repro.dataset_id} · sha256:${repro.dataset_fingerprint_sha256.slice(0, 16)}…`,
      `Graph ${repro.graph_id} (revision ${repro.graph_revision}) · sha256:${repro.graph_spec_fingerprint_sha256.slice(0, 16)}…`,
      `Estimand ${payload.estimand.toUpperCase()} · adjustment set: ${repro.adjustment_nodes.length === 0 ? 'empty' : repro.adjustment_nodes.join(', ')} · cohort: ${repro.cohort.split_assignment_id ? `${repro.cohort.partition} partition` : 'all rows'}`,
      `Seeds: resolved ${repro.uncertainty.resolved_seed} · ${repro.uncertainty.method === 'bootstrap' ? `${repro.uncertainty.reps} refitting bootstrap replicates` : 'influence-function interval'}`,
      `SplitScope estimation ${repro.estimation_version} · schema ${repro.estimation_schema_version}`,
    ]
  }, [payload])

  const studyNote = payload
    ? `Estimates are average treatment effects of ${payload.analysis.treatment_column} on ${payload.analysis.outcome_column} in ${unitsLabel(payload.results.find((result) => result.units)?.units, payload.analysis.outcome_task)}, under the adjustment set verified against the drawn graph.`
    : ''

  const outcomeUnits = payload
    ? unitsLabel(payload.results.find((result) => result.units)?.units, payload.analysis.outcome_task)
    : 'outcome units'

  const availability = (() => {
    if (!dataset) return null
    if (readiness.kind === 'checking') return { tone: 'busy', text: 'Checking estimation readiness…' }
    if (readiness.kind === 'ready') {
      return {
        tone: 'ok',
        text: `Ready · ${formatInteger(readiness.payload.cohort_preview.rows_final)} rows would be analysed`,
      }
    }
    if (readiness.kind === 'blocked') return { tone: 'blocked', text: 'Not ready to estimate' }
    return { tone: 'idle', text: 'Readiness not checked yet' }
  })()

  // -- render ---------------------------------------------------------------- //

  if (!dataset || !datasetId) {
    return (
      <section className="card eststudio__intro">
        <p className="estfig__eyebrow">Causal Lab · Effect estimation</p>
        <h1>Effect Estimation Studio</h1>
        <p className="muted">
          The studio estimates average treatment effects on a loaded dataset and a saved causal
          graph. It never invents a study: load a dataset first, then draw the assumed structure.
        </p>
        <div className="eststudio__introactions">
          <button type="button" className="btn btn--primary" onClick={() => onNavigate('overview')}>
            Load a dataset
          </button>
        </div>
      </section>
    )
  }

  const demoDataset = dataset.demo?.demo_id === 'causal_effect'

  return (
    <section className="eststudio" aria-label="Effect Estimation Studio">
      <header className="eststudio__head">
        <div className="eststudio__headmain">
          <p className="estfig__eyebrow">Causal Lab · Effect estimation</p>
          <h1>Effect Estimation Studio</h1>
          <p className="eststudio__subtitle">
            Dataset <strong>{dataset.dataset.name}</strong>
            {graph ? (
              <>
                {' '}· graph <strong>{graph.name}</strong> · revision {graph.revision} · fingerprint{' '}
                <code>{graph.spec_fingerprint_sha256.slice(0, 12)}…</code>
              </>
            ) : null}
          </p>
          <ol className="esttrail" aria-label="Causal workflow">
            <li className="esttrail__item esttrail__item--done">Dataset</li>
            <li className={`esttrail__item${graph ? ' esttrail__item--done' : ''}`}>Causal DAG</li>
            <li className={`esttrail__item${identification?.status === 'backdoor_adjustment_available' ? ' esttrail__item--done' : ''}`}>
              Identification
            </li>
            <li className={`esttrail__item${payload ? ' esttrail__item--current' : ''}`}>Effect estimation</li>
            <li className={`esttrail__item${payload ? '' : ''}`}>Diagnostics</li>
            <li className="esttrail__item">Report</li>
          </ol>
        </div>
        <div className="eststudio__headmeta">
          {availability ? (
            <span className={`estready estready--${availability.tone}`} data-testid="readiness-chip">
              {availability.text}
            </span>
          ) : null}
          <button
            type="button"
            className="btn btn--small"
            onClick={() => onNavigate('causal')}
            title="Open the Causal Lab to edit or validate the assumed structure"
          >
            Open Causal Lab
          </button>
        </div>
      </header>

      {demoDataset ? (
        <div className="estdemo" data-testid="demo-banner">
          <div>
            <p className="estdemo__eyebrow">Synthetic demonstration study</p>
            <p className="estdemo__body">
              {dataset.demo?.title}. {dataset.demo?.teaching_point}
            </p>
            <p className="estdemo__known">
              Known data-generating average effect:{' '}
              <strong>{knownEffect ? `${formatNumber(knownEffect.value)} ${outcomeUnits}` : 'documented in the manifest'}</strong>{' '}
              — a property of the simulation, never an input to the estimator.
            </p>
          </div>
          {graphs.length === 0 ? (
            <button
              type="button"
              className="btn btn--primary btn--small"
              onClick={() => void createDemoGraph()}
              disabled={demoBusy}
              data-testid="create-demo-graph"
            >
              {demoBusy ? 'Creating…' : 'Create the demonstration DAG'}
            </button>
          ) : null}
        </div>
      ) : null}

      {stale && payload ? (
        <div className="eststale" role="alert" data-testid="stale-banner">
          <div>
            <p className="eststale__title">These results no longer describe the current study</p>
            <ul className="eststale__list">
              {staleReasons.map((reason) => (
                <li key={reason.code}>{reason.label}</li>
              ))}
            </ul>
            <p className="eststale__note">
              The numbers below are the real outputs of the earlier run. They have not been
              recomputed and are not current — rerun estimation to obtain results for the present
              configuration.
            </p>
          </div>
          <button
            type="button"
            className="btn btn--small"
            onClick={() => void startRun()}
            disabled={!canRun}
            title={canRun ? 'Recompute with the current configuration' : 'Resolve the readiness issues first'}
          >
            Rerun estimation
          </button>
        </div>
      ) : null}

      {runError ? (
        <div className="estalert" role="alert" data-testid="run-error">
          <div>
            <p className="estalert__title">{runError.title}</p>
            <p>{runError.message}</p>
            {runError.details.length > 0 ? (
              <ul className="estalert__details">
                {runError.details.map((detail) => (
                  <li key={detail}>{detail}</li>
                ))}
              </ul>
            ) : null}
          </div>
          {runError.status === 410 ? (
            <button type="button" className="btn btn--small" onClick={() => onNavigate('overview')}>
              Reload the dataset
            </button>
          ) : (
            <button type="button" className="btn btn--small" onClick={() => setRunError(null)}>
              Dismiss
            </button>
          )}
        </div>
      ) : null}

      <div className="eststudio__body">
        <aside className="eststudio__setup" aria-label="Analysis setup">
          <div className="estsetup__head">
            <h2>Analysis setup</h2>
            <span className="estsetup__state">
              {graphBusy ? 'loading graph…' : graph ? `graph rev ${graph.revision}` : 'no graph'}
            </span>
          </div>

          {graphError ? (
            <div className="estalert estalert--compact" role="alert">
              <p className="estalert__title">{graphError.title}</p>
              <p>{graphError.message}</p>
            </div>
          ) : null}

          <div className="estfield">
            <span className="estfield__label">Saved causal graph</span>
            {graphs.length === 0 ? (
              <p className="estfield__hint">
                No graph is saved for this dataset yet.{' '}
                <button type="button" className="estlink" onClick={() => onNavigate('causal')}>
                  Draw one in the Causal Lab
                </button>
                {demoDataset ? ' — or create the demonstration DAG above.' : '.'}
              </p>
            ) : (
              <select
                value={graphId ?? ''}
                onChange={(event) => setGraphId(event.target.value || null)}
                aria-label="Saved causal graph"
              >
                {graphs.map((entry) => (
                  <option key={entry.graph_id} value={entry.graph_id}>
                    {entry.name} · rev {entry.revision}
                    {entry.validation_ok ? '' : ' · invalid'}
                  </option>
                ))}
              </select>
            )}
          </div>

          {graph ? (
            <div className="estsetup__graphmeta">
              <p>
                <span className="estfield__label">Dataset fingerprint</span>
                <code>{graph.dataset_fingerprint_sha256.slice(0, 16)}…</code>
              </p>
              <p>
                <span className="estfield__label">Graph fingerprint</span>
                <code>{graph.spec_fingerprint_sha256.slice(0, 16)}…</code>
              </p>
              <p>
                <span className="estfield__label">Structural validation</span>
                {graph.validation.ok ? 'valid' : `${graph.validation.error_count} blocking error(s)`}
              </p>
            </div>
          ) : null}

          <label className="estfield">
            <span className="estfield__label">Treatment (one observed node)</span>
            <select
              value={config.treatmentNode}
              onChange={(event) =>
                setConfig((previous) => ({
                  ...previous,
                  treatmentNode: event.target.value,
                  adjustmentNodes: previous.adjustmentNodes.filter(
                    (node) => node !== event.target.value && node !== previous.outcomeNode,
                  ),
                }))
              }
              aria-label="Treatment node"
            >
              <option value="">Choose…</option>
              {(graph?.nodes ?? [])
                .filter((node) => node.observed && node.column)
                .map((node) => (
                  <option key={node.node_id} value={node.node_id}>
                    {node.label} ({node.column})
                  </option>
                ))}
            </select>
          </label>

          <label className="estfield">
            <span className="estfield__label">Outcome (one observed node)</span>
            <select
              value={config.outcomeNode}
              onChange={(event) =>
                setConfig((previous) => ({
                  ...previous,
                  outcomeNode: event.target.value,
                  adjustmentNodes: previous.adjustmentNodes.filter(
                    (node) => node !== event.target.value && node !== previous.treatmentNode,
                  ),
                }))
              }
              aria-label="Outcome node"
            >
              <option value="">Choose…</option>
              {(graph?.nodes ?? [])
                .filter((node) => node.observed && node.column)
                .map((node) => (
                  <option key={node.node_id} value={node.node_id}>
                    {node.label} ({node.column})
                  </option>
                ))}
            </select>
          </label>

          <div className="estfield estfield--split">
            <label>
              <span className="estfield__label">Treated value</span>
              <select
                value={config.treatedValue}
                onChange={(event) => setConfig((previous) => ({ ...previous, treatedValue: event.target.value }))}
                aria-label="Treated value"
              >
                {columnValues.length === 0 ? <option value={config.treatedValue}>{config.treatedValue}</option> : null}
                {columnValues.map((value) => (
                  <option key={value.value} value={value.value}>
                    {value.value} ({formatInteger(value.count)})
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span className="estfield__label">Control value</span>
              <select
                value={config.controlValue}
                onChange={(event) => setConfig((previous) => ({ ...previous, controlValue: event.target.value }))}
                aria-label="Control value"
              >
                {columnValues.length === 0 ? <option value={config.controlValue}>{config.controlValue}</option> : null}
                {columnValues.map((value) => (
                  <option key={value.value} value={value.value}>
                    {value.value} ({formatInteger(value.count)})
                  </option>
                ))}
              </select>
            </label>
          </div>
          {columnValues.length > 0 ? (
            <p className="estfield__hint" data-testid="treatment-values">
              {columnValues.length} observed value(s) in {treatmentColumn}; the mapping must cover
              exactly two of them.
            </p>
          ) : null}

          <fieldset className="estfield estfield--group">
            <legend className="estfield__label">Adjustment variables</legend>
            {identification?.search?.sets.length ? (
              <div className="estsetlist" data-testid="verified-sets">
                <p className="estfield__hint">Verified minimal backdoor sets from identification:</p>
                {identification.search.sets.slice(0, 4).map((candidate) => (
                  <button
                    key={candidate.set.join('|') || 'empty'}
                    type="button"
                    className="estsetchip"
                    onClick={() => {
                      setConfig((previous) => ({ ...previous, adjustmentNodes: [...candidate.set] }))
                      setSetVerdict(null)
                    }}
                  >
                    {candidate.set.length === 0 ? 'empty set' : candidate.set.join(' + ')}
                  </button>
                ))}
              </div>
            ) : identification ? (
              <p className="estfield__hint" data-testid="identification-unavailable">
                Identification did not report an admissible set
                {identification.status === 'search_incomplete' ? ' (the search was incomplete)' : ''}.
                You may still test a set explicitly; the backend refuses inadmissible ones.
              </p>
            ) : (
              <p className="estfield__hint">
                Graphical identification has not run for this graph. Any set you choose is verified
                by the readiness probe before estimation.
              </p>
            )}
            <div className="estchecks" data-testid="adjustment-options">
              {(graph?.nodes ?? [])
                .filter(
                  (node) =>
                    node.observed &&
                    node.column &&
                    node.node_id !== config.treatmentNode &&
                    node.node_id !== config.outcomeNode &&
                    datasetColumns.includes(node.column),
                )
                .map((node) => (
                  <label key={node.node_id} className="estcheck">
                    <input
                      type="checkbox"
                      checked={config.adjustmentNodes.includes(node.node_id)}
                      onChange={(event) => {
                        setSetVerdict(null)
                        setConfig((previous) => ({
                          ...previous,
                          adjustmentNodes: event.target.checked
                            ? [...new Set([...previous.adjustmentNodes, node.node_id])]
                            : previous.adjustmentNodes.filter((entry) => entry !== node.node_id),
                        }))
                      }}
                    />
                    <span>{node.label}</span>
                  </label>
                ))}
            </div>
            <div className="estactions">
              <button
                type="button"
                className="btn btn--small"
                disabled={!datasetId || !graphId || !config.treatmentNode || !config.outcomeNode}
                onClick={() => {
                  if (!datasetId || !graphId) return
                  causalApi
                    .evaluateAdjustment(datasetId, graphId, [...config.adjustmentNodes].sort())
                    .then((verdict) =>
                      setSetVerdict({
                        valid: verdict.valid,
                        message: verdict.valid
                          ? verdict.interpretation
                          : verdict.violations.map((violation) => violation.message).join(' '),
                      }),
                    )
                    .catch((caught: unknown) =>
                      setSetVerdict({
                        valid: false,
                        message: describeError(caught, 'The set could not be verified').message,
                      }),
                    )
                }}
                data-testid="verify-set"
              >
                Verify this set
              </button>
              {config.adjustmentNodes.length > 0 ? (
                <button
                  type="button"
                  className="btn btn--small"
                  onClick={() => {
                    setConfig((previous) => ({ ...previous, adjustmentNodes: [] }))
                    setSetVerdict(null)
                  }}
                >
                  Clear set
                </button>
              ) : null}
            </div>
            {setVerdict ? (
              <p
                className={`estsetverdict${setVerdict.valid ? ' estsetverdict--ok' : ' estsetverdict--bad'}`}
                data-testid="set-verdict"
              >
                {setVerdict.valid ? 'Admissible (graphically)' : 'Not admissible'} — {setVerdict.message}
              </p>
            ) : null}
          </fieldset>

          <fieldset className="estfield estfield--group">
            <legend className="estfield__label">Estimator</legend>
            <div className="estradios">
              <label className="estradio">
                <input
                  type="radio"
                  name="estimator"
                  checked={estimatorChoice === 'compare'}
                  onChange={() => setEstimatorChoice('compare')}
                />
                <span>
                  <strong>All three (comparison)</strong>
                  <em>One shared cohort and adjustment set; differences are reported, never resolved.</em>
                </span>
              </label>
              {ESTIMATOR_ORDER.map((name) => (
                <label key={name} className="estradio">
                  <input
                    type="radio"
                    name="estimator"
                    checked={estimatorChoice === name}
                    onChange={() => setEstimatorChoice(name)}
                  />
                  <span>
                    <strong>{ESTIMATOR_LABELS[name]}</strong>
                    <em>{ESTIMATOR_DESCRIPTIONS[name]}</em>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="estfield estfield--group">
            <legend className="estfield__label">Missing data</legend>
            <label className="estradio estradio--stacked">
              <input
                type="radio"
                name="missing"
                checked={config.missingPolicy === 'complete_case'}
                onChange={() => setConfig((previous) => ({ ...previous, missingPolicy: 'complete_case' }))}
              />
              <span>
                <strong>Complete case</strong>
                <em>Rows with any missing required value are excluded and counted.</em>
              </span>
            </label>
            <label className="estradio estradio--stacked">
              <input
                type="radio"
                name="missing"
                checked={config.missingPolicy === 'median_mode'}
                onChange={() => setConfig((previous) => ({ ...previous, missingPolicy: 'median_mode' }))}
              />
              <span>
                <strong>Median / mode imputation</strong>
                <em>Fitted inside each fold; disclosed in the balance view. It does not remove missing-data bias.</em>
              </span>
            </label>
          </fieldset>

          <fieldset className="estfield estfield--group">
            <legend className="estfield__label">Uncertainty</legend>
            <div className="estfield--split">
              <label>
                <span className="estfield__sublabel">Method</span>
                <select
                  value={config.uncertaintyMethod}
                  onChange={(event) =>
                    setConfig((previous) => ({
                      ...previous,
                      uncertaintyMethod: event.target.value === 'influence_function' ? 'influence_function' : 'bootstrap',
                    }))
                  }
                  aria-label="Uncertainty method"
                >
                  <option value="bootstrap">Refitting bootstrap</option>
                  <option value="influence_function">Influence function</option>
                </select>
              </label>
              <label>
                <span className="estfield__sublabel">Level</span>
                <select
                  value={String(config.uncertaintyLevel)}
                  onChange={(event) =>
                    setConfig((previous) => ({ ...previous, uncertaintyLevel: Number(event.target.value) }))
                  }
                  aria-label="Interval level"
                >
                  <option value="0.9">90%</option>
                  <option value="0.95">95%</option>
                  <option value="0.99">99%</option>
                </select>
              </label>
            </div>
            {config.uncertaintyMethod === 'bootstrap' ? (
              <label className="estfield">
                <span className="estfield__sublabel">Bootstrap replicates (100–2000)</span>
                <input
                  type="number"
                  min={100}
                  max={2000}
                  step={50}
                  value={config.bootstrapReps}
                  onChange={(event) =>
                    setConfig((previous) => ({ ...previous, bootstrapReps: Number(event.target.value) || 100 }))
                  }
                  aria-label="Bootstrap replicates"
                />
              </label>
            ) : (
              <p className="estfield__hint">
                Influence-function intervals exist for IPW and AIPW. Regression adjustment has no
                closed form in this implementation and reports its interval as unavailable.
              </p>
            )}
          </fieldset>

          <details className="estadvanced" open>
            <summary>Reproducibility seed</summary>
            <label className="estfield">
              <span className="estfield__sublabel">Seed (empty = server-drawn and recorded)</span>
              <input
                type="number"
                min={0}
                step={1}
                value={config.seed}
                placeholder="server-drawn"
                onChange={(event) => setConfig((previous) => ({ ...previous, seed: event.target.value }))}
                aria-label="Reproducibility seed"
              />
            </label>
          </details>

          <details className="estadvanced">
            <summary>Advanced design</summary>
            <label className="estfield">
              <span className="estfield__sublabel">Cross-fitting folds (2–10)</span>
              <input
                type="number"
                min={2}
                max={10}
                value={config.crossFitSplits}
                onChange={(event) =>
                  setConfig((previous) => ({
                    ...previous,
                    crossFitSplits: Math.min(10, Math.max(2, Number(event.target.value) || 2)),
                  }))
                }
                aria-label="Cross-fitting folds"
              />
            </label>
            <label className="estfield">
              <span className="estfield__sublabel">Group column for folds (optional)</span>
              <select
                value={config.groupColumn ?? ''}
                onChange={(event) =>
                  setConfig((previous) => ({ ...previous, groupColumn: event.target.value || null }))
                }
                aria-label="Cross-fitting group column"
              >
                <option value="">Shuffled rows</option>
                {datasetColumns.map((column) => (
                  <option key={column} value={column}>{column}</option>
                ))}
              </select>
            </label>
            <label className="estfield">
              <span className="estfield__sublabel">Split assignment id for the cohort (optional)</span>
              <input
                type="text"
                value={config.cohortAssignment}
                placeholder="all rows (default)"
                onChange={(event) =>
                  setConfig((previous) => ({ ...previous, cohortAssignment: event.target.value }))
                }
                aria-label="Cohort split assignment id"
              />
            </label>
            {config.cohortAssignment.trim() ? (
              <label className="estfield">
                <span className="estfield__sublabel">Partition</span>
                <select
                  value={config.cohortPartition}
                  onChange={(event) =>
                    setConfig((previous) => ({
                      ...previous,
                      cohortPartition: event.target.value === 'train' ? 'train' : 'test',
                    }))
                  }
                  aria-label="Cohort partition"
                >
                  <option value="test">test</option>
                  <option value="train">train</option>
                </select>
              </label>
            ) : null}
            <p className="estfield__hint">
              Split assignments are created by a split comparison in this session and expire with
              it. Leaving the field empty analyses every prepared row — the default this studio
              recommends.
            </p>
            <label className="estcheck estcheck--inline">
              <input
                type="checkbox"
                checked={config.truncationEnabled}
                onChange={(event) =>
                  setConfig((previous) => ({ ...previous, truncationEnabled: event.target.checked }))
                }
              />
              <span>Truncate propensities explicitly</span>
            </label>
            {config.truncationEnabled ? (
              <div className="estfield--split">
                <label>
                  <span className="estfield__sublabel">Lower (0.01–0.49)</span>
                  <input
                    type="number"
                    min={0.01}
                    max={0.49}
                    step={0.01}
                    value={config.truncationLower}
                    onChange={(event) =>
                      setConfig((previous) => ({ ...previous, truncationLower: Number(event.target.value) }))
                    }
                    aria-label="Truncation lower bound"
                  />
                </label>
                <label>
                  <span className="estfield__sublabel">Upper (0.51–0.99)</span>
                  <input
                    type="number"
                    min={0.51}
                    max={0.99}
                    step={0.01}
                    value={config.truncationUpper}
                    onChange={(event) =>
                      setConfig((previous) => ({ ...previous, truncationUpper: Number(event.target.value) }))
                    }
                    aria-label="Truncation upper bound"
                  />
                </label>
              </div>
            ) : null}
          </details>

          <div className="estsetup__run">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void startRun()}
              disabled={!canRun}
              data-testid="run-estimation"
              title={
                canRun
                  ? 'Runs the selected estimator(s) on the backend and stores the result in this session'
                  : readiness.kind === 'checking'
                    ? 'Waiting for the readiness probe'
                    : (readiness.kind === 'blocked' ? readiness.message : 'Configure a valid analysis first')
              }
            >
              {run.kind === 'running' ? 'Running…' : runLabel}
            </button>
            {readiness.kind === 'checking' ? (
              <p className="estfield__hint" role="status">
                <span className="spinner" aria-hidden="true" /> Checking readiness with the backend…
              </p>
            ) : null}
          </div>

          {readiness.kind === 'blocked' ? (
            <div className="estready-block" role="status" data-testid="readiness-blocked">
              <p className="estready-block__title">{readiness.title}</p>
              <p>{readiness.message}</p>
              {readiness.details.length > 0 ? (
                <ul className="estready-block__details">
                  {readiness.details.map((detail) => (
                    <li key={detail}>{detail}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {readiness.kind === 'ready' ? (
            <div className="estready-ok" data-testid="readiness-ok">
              <p className="estready-ok__title">Ready to estimate</p>
              <p>
                {formatInteger(readiness.payload.cohort_preview.rows_final)} rows would be analysed
                ({formatInteger(readiness.payload.cohort_preview.treated_rows)} treated,{' '}
                {formatInteger(readiness.payload.cohort_preview.control_rows)} control).{' '}
                {readiness.payload.cohort_preview.exclusions.length > 0
                  ? `${readiness.payload.cohort_preview.exclusions.reduce((sum, exclusion) => sum + exclusion.count, 0)} row(s) would be excluded.`
                  : 'No row exclusions.'}{' '}
                {readiness.payload.note}
              </p>
            </div>
          ) : null}
        </aside>

        <div className="eststudio__main">
          <details className="esthistory">
            <summary data-testid="history-summary">
              Run history ({history.length}){' '}
              {historyBusy ? <span className="spinner" aria-hidden="true" /> : null}
            </summary>
            <p className="esthistory__note">
              Estimation runs live in the backend's bounded in-memory session store: they expire
              after about an hour and the oldest are dropped once the store is full. Nothing here is
              a permanent archive.
            </p>
            {historyNote ? <p className="esthistory__error">{historyNote}</p> : null}
            <div className="esthistory__actions">
              <button type="button" className="btn btn--small" onClick={() => void refreshHistory()} disabled={historyBusy}>
                Refresh
              </button>
              {run.kind === 'ready' && run.source === 'stored' ? (
                <button type="button" className="btn btn--small" onClick={returnToLatest}>
                  Back to current results
                </button>
              ) : null}
            </div>
            {history.length === 0 ? (
              <p className="esthistory__note">No estimation runs are stored for this dataset in this session.</p>
            ) : (
              <ul className="esthistory__list">
                {history.map((entry) => (
                  <li key={entry.run_id} className="esthistory__row">
                    <div className="esthistory__meta">
                      <p className="esthistory__label">{entry.label}</p>
                      <p className="esthistory__sub">
                        <code>{entry.run_id}</code> · {formatAgo(entry.created_seconds_ago)}
                      </p>
                    </div>
                    <button
                      type="button"
                      className="btn btn--small"
                      onClick={() => void loadStoredRun(entry.run_id)}
                      disabled={run.kind === 'running'}
                    >
                      Load
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </details>

          {run.kind === 'running' ? (
            <div className="estworking" role="status" data-testid="estimation-running">
              <span className="spinner" aria-hidden="true" />
              <div>
                <p className="estworking__title">{run.label}</p>
                <p className="estworking__note">
                  The backend is fitting nuisance models and resampling for the interval. This can
                  take a few seconds on larger cohorts. Previous results stay readable below until
                  this run replaces them.
                </p>
              </div>
            </div>
          ) : null}

          {!payload ? (
            <section className="estempty" data-testid="estimation-empty">
              <p className="estfig__eyebrow">No estimate on screen</p>
              <h2>Configure the analysis, then run estimation</h2>
              <ol className="estempty__steps">
                <li>
                  <strong>Dataset and graph.</strong> The studio uses the dataset loaded in this
                  session and a saved causal graph, so nothing has to be redrawn.
                </li>
                <li>
                  <strong>Scope and adjustment set.</strong> Choose the treatment, the outcome and
                  the observed adjustment variables. Verification happens on the backend.
                </li>
                <li>
                  <strong>Run.</strong> The readiness probe estimates nothing; only the explicit run
                  stores a result.
                </li>
              </ol>
              {block ? (
                <div className="estempty__block">
                  <p className="estempty__blocktitle">{block.title}</p>
                  <p>{block.message}</p>
                  <button type="button" className="btn btn--small" onClick={() => onNavigate('causal')}>
                    Open the Causal Lab
                  </button>
                </div>
              ) : null}
              <p className="estempty__note">
                Diagnostics, methodology and figure exports appear here once a result exists. Every
                figure exports the exact plotted values, never a rebuilt copy.
              </p>
            </section>
          ) : (
            <>
              <div className="eststudio__resulthead">
                <div>
                  <p className="estfig__eyebrow">
                    {payload.comparison ? 'Comparison result' : 'Single-estimator result'} ·{' '}
                    {ESTIMATOR_ORDER.filter((name) =>
                      payload.results.some((result) => result.estimator === name),
                    )
                      .map((name) => ESTIMATOR_LABELS[name])
                      .join(' · ')}
                  </p>
                  <p className="eststudio__resultmeta" data-testid="result-meta">
                    Run <code>{payload.run_id}</code> · {formatInteger(payload.analysis.rows_final)} analysed rows ·{' '}
                    {outcomeUnits} · adjustment set{' '}
                    {payload.reproducibility.adjustment_nodes.length === 0
                      ? 'empty'
                      : payload.reproducibility.adjustment_nodes.join(', ')}
                    {run.kind === 'ready' && run.source === 'stored' ? ' · loaded from history' : ''}
                  </p>
                </div>
                <div className="eststudio__resultactions">
                  <button
                    type="button"
                    className="btn btn--small"
                    onClick={() => estimationExport(payload)}
                    title="Download this run's full metadata and estimates as JSON"
                  >
                    Run JSON
                  </button>
                  {run.kind === 'ready' && run.source === 'stored' ? (
                    <span className="estbadge estbadge--stored">stored run</span>
                  ) : null}
                  {stale ? <span className="estbadge estbadge--stale">stale</span> : null}
                  {payload.results.some((result) => result.status === 'failed') ? (
                    <span className="estbadge estbadge--partial">partial</span>
                  ) : null}
                </div>
              </div>

              <nav className="esttabs" aria-label="Estimation views">
                {TABS.map((entry) => (
                  <button
                    key={entry.id}
                    type="button"
                    className={`esttab${tab === entry.id ? ' esttab--on' : ''}`}
                    aria-current={tab === entry.id ? 'page' : undefined}
                    onClick={() => setTab(entry.id)}
                    data-testid={`tab-${entry.id}`}
                  >
                    <span className="esttab__label">{entry.label}</span>
                    <span className="esttab__hint">{entry.hint}</span>
                  </button>
                ))}
              </nav>

              {tab === 'balance' || tab === 'overlap' || tab === 'weights' ? (
                <div className="estdiagbar" aria-label="Diagnostics source">
                  <span className="estdiagbar__label">Diagnostics from</span>
                  {payload.results.map((result) => (
                    <button
                      key={result.estimator}
                      type="button"
                      className={`estdiagchip${diagnostics?.selected?.estimator === result.estimator ? ' estdiagchip--on' : ''}`}
                      onClick={() => setDiagEstimator(result.estimator)}
                      disabled={result.status === 'failed'}
                      title={
                        result.status === 'failed'
                          ? 'This estimator failed; it has no diagnostics'
                          : `Show ${ESTIMATOR_LABELS[result.estimator] ?? result.estimator} diagnostics`
                      }
                    >
                      {ESTIMATOR_LABELS[result.estimator] ?? result.estimator}
                      {result.status === 'failed' ? ' · failed' : ''}
                    </button>
                  ))}
                  {diagnostics?.selected ? (
                    <span className="estdiagbar__note">
                      {diagnostics.selected.diagnostics?.balance.weighted
                        ? 'weighted diagnostics'
                        : 'unweighted diagnostics (no weights applied)'}
                    </span>
                  ) : null}
                </div>
              ) : null}

              {tab === 'summary' ? (
                <EffectSummary payload={payload} studyNote={studyNote} provenance={provenance} />
              ) : null}
              {tab === 'balance' ? (
                diagnostics?.selected?.diagnostics?.balance ? (
                  <BalanceView result={diagnostics.selected} provenance={provenance} staleNote={staleNote} />
                ) : (
                  <section className="estfig estfig--empty" data-testid="balance-missing">
                    <h2>No covariate-balance diagnostics in this result</h2>
                    <p>Nothing is inferred from another estimator's run.</p>
                  </section>
                )
              ) : null}
              {tab === 'overlap' ? (
                diagnostics?.overlap ? (
                  <OverlapView result={diagnostics.overlap} provenance={provenance} />
                ) : (
                  <section className="estfig estfig--empty" data-testid="overlap-missing">
                    <h2>No propensity diagnostics in this result</h2>
                    <p>
                      Regression adjustment does not fit a propensity model, so there is no overlap
                      distribution to show. Run the comparison to obtain IPW and AIPW diagnostics.
                    </p>
                  </section>
                )
              ) : null}
              {tab === 'weights' ? (
                diagnostics?.overlap ? (
                  <WeightsView result={diagnostics.overlap} provenance={provenance} />
                ) : (
                  <section className="estfig estfig--empty" data-testid="weights-missing">
                    <h2>No weighting diagnostics in this result</h2>
                    <p>
                      Only the weighting estimators produce weights and effective sample sizes. This
                      result has none, and the studio does not substitute the raw row count.
                    </p>
                  </section>
                )
              ) : null}
              {tab === 'methods' ? (
                <MethodologyView
                  payload={payload}
                  knownEffect={knownEffect ? { value: knownEffect.value, note: knownEffect.note } : null}
                />
              ) : null}

              {stale ? (
                <p className="eststudio__footstale">
                  Results shown on this tab were computed under the earlier configuration named in
                  the banner above. They are not current.
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>
    </section>
  )
}
