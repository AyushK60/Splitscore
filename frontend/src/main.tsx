import { Fragment, StrictMode, Suspense, lazy, useEffect, useRef, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'

import '@fontsource-variable/bricolage-grotesque/opsz.css'
import '@fontsource-variable/instrument-sans/wght.css'
import '@fontsource-variable/jetbrains-mono/wght.css'
import './styles/tokens.css'
import './styles/app.css'
import './styles/v2.css'
import './styles/landing.css'
import './styles/research.css'
import './styles/explore.css'
import './styles/models.css'
import './styles/s7.css'
import './styles/s8.css'
import './styles/s9.css'

import { AppProvider, useApp } from './state/AppState'
import { useHashRoute, type ViewId } from './lib/router'
import { ExploreProvider } from './explore/ExploreState'
import { CausalDraftProvider } from './causal/CausalDraftContext'
import { LandingView } from './views/LandingView'
import { OverviewView } from './views/OverviewView'
import { StudyView } from './views/StudyView'
import { ExploreView } from './views/ExploreView'
import { AuditView } from './views/AuditView'
import { EvidenceView } from './views/EvidenceView'
import { HistoryView } from './views/HistoryView'

/**
 * Code splitting (S11). The main bundle previously carried every workspace and
 * warned above the 500 kB budget. The heavy analytical views now load only when
 * their route is opened: each is its own chunk, the fallback is an honest
 * labelled card (see StageFallback below), and repeat visits are served from
 * cache. Lightweight early stages stay eager so the first steps never flash.
 */
const DatasetView = lazy(() =>
  import('./views/DatasetView').then((module) => ({ default: module.DatasetView })),
)
const ModelLabView = lazy(() =>
  import('./views/ModelLabView').then((module) => ({ default: module.ModelLabView })),
)
const ComparisonView = lazy(() =>
  import('./views/ComparisonView').then((module) => ({ default: module.ComparisonView })),
)
const ExportView = lazy(() =>
  import('./views/ExportView').then((module) => ({ default: module.ExportView })),
)

/**
 * The Causal Lab (S8B) is code-split: the graph editor is the largest single
 * workspace and is not needed on the other stages, so it is loaded only when
 * its route is opened. The CSS is small and stays eager so the first paint of
 * the route is not unstyled.
 */
const CausalLabView = lazy(() =>
  import('./causal/CausalLabView').then((module) => ({ default: module.CausalLabView })),
)

/**
 * The S9B Effect Estimation Studio is code-split for the same reason: its five
 * analytical figures and export machinery are only needed on this route.
 */
const EstimationView = lazy(() =>
  import('./estimation/EstimationView').then((module) => ({ default: module.EstimationView })),
)

/**
 * The S9C Causal Research stage is code-split like the other late stages: its
 * forest plot, robustness figures and scenario explorer load only on route.
 */
const ResearchView = lazy(() =>
  import('./research/ResearchView').then((module) => ({ default: module.ResearchView })),
)

/** Stage names used by the breadcrumb. "Audit results" is the third stage. */
const STAGE_LABEL: Record<ViewId, string> = {
  home: 'Home',
  overview: 'Start',
  dataset: 'Data',
  audit: 'Audit results',
  study: 'Study',
  explore: 'Explore',
  models: 'Model Lab',
  causal: 'Causal Lab',
  estimation: 'Effect estimation',
  research: 'Causal research',
  evidence: 'Evidence',
  comparison: 'Compare',
  history: 'History',
  export: 'Export',
}

/**
 * Contextual next steps. These are deliberately destinations that already
 * exist, not a wizard: Study and Explore stay optional whether or not an audit
 * has run, and no stage is marked complete by visiting another one.
 */
const NEXT_GUIDANCE: Record<ViewId, string> = {
  home: '',
  overview: 'Load a dataset, then confirm its split and roles in Data.',
  dataset: 'Run the audit once the split and roles are confirmed. Study and Explore stay optional.',
  audit: 'Open a finding\u2019s evidence, explore the data, or compare split strategies.',
  evidence: 'Evidence belongs to the selected finding; the full audit lives in Audit results.',
  study: 'Study metadata is optional context. Explore the dataset, or run the audit from Data.',
  explore: 'Selections are analysis context, not findings. Inspect them, run the audit, or compare.',
  models: 'Statistical fits describe analysed rows; predictive metrics describe a held-out split. Neither proves causation.',
  causal: 'Draw assumed relationships, document assumptions and validate the structure. A valid DAG is not evidence the assumptions are true.',
  estimation: 'Estimates are conditional on the DAG and the verified adjustment set. Inspect balance, overlap and effective sample size before reading an interval, and export the figure with its provenance.',
  research: 'Subgroup, robustness and what-if analyses reuse a stored estimation run’s study. They describe this sample under the same assumptions — they do not verify them.',
  comparison: 'A comparison shows consequences, not a winner. Assemble the evidence you have actually produced in the Export studio.',
  history: 'History is a projection of this session’s bounded in-memory run store. Expired runs are gone; export a manifest of anything you need to keep.',
  export: 'Compose a dossier from the runs in this session, then download JSON or a printable HTML artifact.',
}

const NEXT_ACTIONS: Partial<Record<ViewId, Array<{ label: string; view: ViewId }>>> = {
  dataset: [{ label: 'Review Study', view: 'study' }],
  audit: [
    { label: 'Explore data', view: 'explore' },
    { label: 'Compare splits', view: 'comparison' },
  ],
  evidence: [{ label: 'Back to Audit results', view: 'audit' }],
  study: [
    { label: 'Explore data', view: 'explore' },
    { label: 'Go to Data to run the audit', view: 'dataset' },
  ],
  explore: [
    { label: 'Run the audit', view: 'audit' },
    { label: 'Compare splits', view: 'comparison' },
  ],
  models: [
    { label: 'Run the audit', view: 'audit' },
    { label: 'Explore data', view: 'explore' },
  ],
  comparison: [
    { label: 'Audit results', view: 'audit' },
    { label: 'Export', view: 'export' },
  ],
  causal: [
    { label: 'Explore data', view: 'explore' },
    { label: 'Audit results', view: 'audit' },
  ],
  estimation: [
    { label: 'Causal research', view: 'research' },
    { label: 'Export', view: 'export' },
  ],
  research: [
    { label: 'Effect estimation', view: 'estimation' },
    { label: 'Export', view: 'export' },
  ],
  export: [
    { label: 'Audit results', view: 'audit' },
    { label: 'Compare splits', view: 'comparison' },
  ],
}

function Shell() {
  const [view, navigate] = useHashRoute()
  const { status, busyLabel, dismissStatus, dataset, audit, comparison } = useApp()
  const mainRef = useRef<HTMLElement>(null)
  const navRef = useRef<HTMLDivElement>(null)
  const firstRender = useRef(true)

  // A new step starts at its own top: without this the next view opens at the
  // scroll offset of the previous one, which reads as a half-loaded page.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    // `auto` would defer to the global `scroll-behavior: smooth` and animate
    // through the previous view. A new stage should open at its top at once.
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
    // The landing page renders its own <main id="main">; the workbench main is
    // reached through the ref, so focus lands on the content of either route.
    const target = mainRef.current ?? document.getElementById('main')
    target?.focus({ preventScroll: true })
  }, [view])

  // The primary nav scrolls horizontally at narrow widths. Keep the active step
  // in view, otherwise entering a late stage hides its own nav item off-screen.
  useEffect(() => {
    const nav = navRef.current
    if (!nav) return
    const centreActive = () => {
      const active = nav.querySelector<HTMLElement>('[aria-current="page"]')
      if (!active) return
      const centred = active.offsetLeft + active.offsetWidth / 2 - nav.clientWidth / 2
      nav.scrollLeft = Math.max(0, centred)
    }
    centreActive()
    window.addEventListener('resize', centreActive)
    return () => window.removeEventListener('resize', centreActive)
  }, [view])

  // The landing page carries its own navigation and footer: the workbench
  // chrome belongs to the workbench only.
  if (view === 'home') {
    return <LandingView onNavigate={navigate} />
  }

  /** Honest, labelled fallback for every code-split stage (no blank swap). */
  const stage = (label: string, node: ReactNode) => (
    <Suspense
      fallback={
        <div className="card" style={{ padding: 'var(--space-6)' }}>
          <p className="muted" style={{ margin: 0 }} role="status">Loading {label}…</p>
        </div>
      }
    >
      {node}
    </Suspense>
  )

  const body =
    view === 'overview' ? <OverviewView onNavigate={navigate} /> :
    view === 'dataset' ? stage('the Data workspace', <DatasetView onNavigate={navigate} />) :
    view === 'study' ? <StudyView onNavigate={navigate} /> :
    view === 'explore' ? (
      <ExploreProvider>
        <ExploreView onNavigate={navigate} />
      </ExploreProvider>
    ) :
    view === 'models' ? stage('the Model Lab', <ModelLabView onNavigate={navigate} />) :
    view === 'causal' ? stage('the Causal Lab', <CausalLabView onNavigate={navigate} />) :
    view === 'estimation' ? stage('the Effect Estimation Studio', <EstimationView onNavigate={navigate} />) :
    view === 'research' ? stage('the Causal Research stage', <ResearchView onNavigate={navigate} />) :
    view === 'history' ? (
      dataset ? (
        <HistoryView dataset={dataset} onNavigate={navigate} />
      ) : (
        <OverviewView onNavigate={navigate} />
      )
    ) :
    view === 'audit' ? <AuditView onNavigate={navigate} /> :
    view === 'evidence' ? <EvidenceView onNavigate={navigate} /> :
    view === 'comparison' ? stage('the split comparison', <ComparisonView onNavigate={navigate} />) :
    view === 'export' ? stage('the Report Studio', <ExportView onNavigate={navigate} />) :
    <OverviewView onNavigate={navigate} />

  // The navigation follows the order of the actual work: the audit is the third
  // stage and is reachable directly from Data. Study and Explore are optional
  // research activities shown after it, not gates in front of it. "Evidence" is
  // deliberately absent — it is reached by opening a finding.
  const steps: Array<{ id: ViewId; label: string; step: number }> = [
    { id: 'overview', label: 'Start', step: 1 },
    { id: 'dataset', label: 'Data', step: 2 },
    ...(dataset ? [{ id: 'audit' as ViewId, label: 'Audit results', step: 3 }] : []),
    ...(dataset ? [{ id: 'study' as ViewId, label: 'Study', step: 4 }] : []),
    ...(dataset ? [{ id: 'explore' as ViewId, label: 'Explore', step: 5 }] : []),
    ...(dataset ? [{ id: 'models' as ViewId, label: 'Model Lab', step: 6 }] : []),
    ...(dataset ? [{ id: 'causal' as ViewId, label: 'Causal Lab', step: 7 }] : []),
    ...(dataset ? [{ id: 'estimation' as ViewId, label: 'Effect estimation', step: 8 }] : []),
    ...(dataset ? [{ id: 'research' as ViewId, label: 'Causal research', step: 9 }] : []),
    ...(dataset ? [{ id: 'comparison' as ViewId, label: 'Compare', step: 10 }] : []),
    ...(dataset ? [{ id: 'history' as ViewId, label: 'History', step: 11 }] : []),
    ...(audit || comparison ? [{ id: 'export' as ViewId, label: 'Export', step: 12 }] : []),
  ]

  // Visual grouping of the rail only; the order, numbering and routes of the
  // steps above are unchanged.
  const GROUP_OF: Partial<Record<ViewId, string>> = {
    overview: 'Prepare',
    audit: 'Examine',
    causal: 'Causal',
    comparison: 'Report',
  }

  return (
    <>
      <div className="app-topbar">
        <div className="app-topbar__primary">
          <header className="app-header">
          <div className="app-header__inner">
            <button
              type="button"
              className="app-header__brand app-header__brand--home"
              title="Back to the SplitScope home page"
              onClick={() => navigate('home')}
            >
              <span className="app-header__mark" aria-hidden="true">
                {/* Train/test boundary: two panels split by a rule. */}
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <rect x="1" y="1" width="6" height="14" rx="1.5" fill="currentColor" opacity="0.9" />
                  <rect x="9" y="1" width="6" height="14" rx="1.5" fill="currentColor" opacity="0.45" />
                  <path d="M8 0.5v15" stroke="var(--accent)" strokeWidth="1.6" />
                </svg>
              </span>
              <span className="app-header__title">SplitScope</span>
              <span className="app-header__tagline">— research workbench · audit · study · explore · model · compare</span>
            </button>
            {busyLabel ? (
              <p className="app-header__meta" role="status" aria-live="polite">
                <span className="spinner" aria-hidden="true" /> {busyLabel}…
              </p>
            ) : (
              <span className="app-header__meta" aria-hidden="true" />
            )}
          </div>
          </header>

          <nav className="app-nav" aria-label="Primary">
            <div className="app-nav__inner" ref={navRef}>
              {steps.map(({ id, label, step }) => (
                <Fragment key={id}>
                  {GROUP_OF[id] ? (
                    <span className="app-nav__group" aria-hidden="true">{GROUP_OF[id]}</span>
                  ) : null}
                  <button
                    type="button"
                    aria-current={view === id ? 'page' : undefined}
                    disabled={busyLabel !== null}
                    onClick={() => navigate(id)}
                  >
                    <span className="app-nav__step" aria-hidden="true">{step}</span>
                    {label}
                  </button>
                </Fragment>
              ))}
            </div>
          </nav>
        </div>
      </div>

      <div className="app-context">
        <div className="app-crumb">
          <nav aria-label="Breadcrumb">
            <ol>
              <li>
                {view === 'overview' ? (
                  'Workspace'
                ) : (
                  <button
                    type="button"
                    className="app-crumb__link"
                    onClick={() => navigate('overview')}
                  >
                    Workspace
                  </button>
                )}
              </li>
              <li aria-current="page">{STAGE_LABEL[view]}</li>
            </ol>
          </nav>
          <p className="app-crumb__next">
            <span className="app-crumb__label">Next</span>
            <span>{NEXT_GUIDANCE[view]}</span>
            {(NEXT_ACTIONS[view] ?? []).map((action) => (
              <button
                key={action.view + action.label}
                type="button"
                className="app-crumb__action"
                onClick={() => navigate(action.view)}
              >
                {action.label}
              </button>
            ))}
          </p>
        </div>
      </div>

      <main id="main" ref={mainRef} className="app-main" tabIndex={-1}>
        {status.kind === 'error' ? (
          <section className="card" style={{ marginBottom: 16 }}>
            <div className="callout callout--danger" role="alert">
              <p className="callout__title">Something went wrong</p>
              <p style={{ margin: 0 }}>{status.message}</p>
              {Object.keys(status.details ?? {}).length ? (
                <details className="disclosure" style={{ marginTop: 8 }}>
                  <summary>Technical details</summary>
                  <pre
                    style={{
                      margin: 0,
                      background: 'var(--bg-sunken)',
                      padding: 8,
                      borderRadius: 6,
                      fontFamily: 'var(--mono)',
                      fontSize: 12,
                      overflowX: 'auto',
                    }}
                  >
                    {JSON.stringify(status.details, null, 2)}
                  </pre>
                </details>
              ) : null}
              <p style={{ margin: '8px 0 0' }}>
                <button type="button" className="btn btn--small" onClick={dismissStatus}>
                  Dismiss
                </button>
              </p>
            </div>
          </section>
        ) : null}
        {/* Keyed by stage: each workspace appears with the same quiet
            fade-and-rise (see .app-stage). The views already remount on stage
            change, so the key adds no state loss; the animation is opacity and
            transform only, never blocks input, and collapses to an instant
            swap under prefers-reduced-motion. */}
        <div key={view} className="app-stage">
          {body}
        </div>
      </main>

      <footer className="app-main app-footer">
        <p className="muted tiny" style={{ margin: 0 }}>
          SplitScope audits splits, not models. Findings are evidence about the split you selected —
          never a guarantee that data is safe or that a model will perform well.
        </p>
      </footer>
    </>
  )
}

const root = createRoot(document.getElementById('root')!)
root.render(
  <StrictMode>
    <AppProvider>
      {/* The unsaved causal draft survives ordinary navigation (S11-B): the
          provider lives above the route switch, the reducer is unchanged. */}
      <CausalDraftProvider>
        <Shell />
      </CausalDraftProvider>
    </AppProvider>
  </StrictMode>,
)