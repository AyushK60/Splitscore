import { StrictMode, useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'

import { AppProvider, useApp } from './state/AppState'
import { useHashRoute, type ViewId } from './lib/router'
import { OverviewView } from './views/OverviewView'
import { DatasetView } from './views/DatasetView'
import { AuditView } from './views/AuditView'
import { EvidenceView } from './views/EvidenceView'
import { ComparisonView } from './views/ComparisonView'
import { ExportView } from './views/ExportView'

import './styles/app.css'

function Shell() {
  const [view, navigate] = useHashRoute()
  const { status, busyLabel, dismissStatus, dataset, audit, comparison } = useApp()
  const mainRef = useRef<HTMLElement>(null)
  const firstRender = useRef(true)

  // A new step starts at its own top: without this the next view opens at the
  // scroll offset of the previous one, which reads as a half-loaded page.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
    mainRef.current?.focus({ preventScroll: true })
  }, [view])

  const body =
    view === 'overview' ? <OverviewView onNavigate={navigate} /> :
    view === 'dataset' ? <DatasetView onNavigate={navigate} /> :
    view === 'audit' ? <AuditView onNavigate={navigate} /> :
    view === 'evidence' ? <EvidenceView onNavigate={navigate} /> :
    view === 'comparison' ? <ComparisonView onNavigate={navigate} /> :
    view === 'export' ? <ExportView onNavigate={navigate} /> :
    <OverviewView onNavigate={navigate} />

  // The navigation follows the user's progress: steps appear as they become
  // usable, so the bar always reads as a short journey rather than a menu of
  // equally weighted destinations. "Evidence" is deliberately absent — it is
  // reached by opening a finding, not on its own.
  const steps: Array<{ id: ViewId; label: string; step: number }> = [
    { id: 'overview', label: 'Start', step: 1 },
    { id: 'dataset', label: 'Data', step: 2 },
    ...(dataset ? [{ id: 'audit' as ViewId, label: 'Results', step: 3 }] : []),
    ...(dataset ? [{ id: 'comparison' as ViewId, label: 'Compare', step: 4 }] : []),
    ...(audit || comparison ? [{ id: 'export' as ViewId, label: 'Export', step: 5 }] : []),
  ]

  return (
    <>
      <div className="app-topbar">
        <header className="app-header">
          <div className="app-header__inner">
            <div className="app-header__brand">
              <span className="app-header__mark" aria-hidden="true">
                {/* Train/test boundary: two panels split by a rule. */}
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <rect x="1" y="1" width="6" height="14" rx="1.5" fill="currentColor" opacity="0.9" />
                  <rect x="9" y="1" width="6" height="14" rx="1.5" fill="currentColor" opacity="0.45" />
                  <path d="M8 0.5v15" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </span>
              <span className="app-header__title">SplitScope</span>
              <span className="app-header__tagline">— check a train/test split for data leakage</span>
            </div>
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
          <div className="app-nav__inner">
            {steps.map(({ id, label, step }) => (
              <button
                key={id}
                type="button"
                aria-current={view === id ? 'page' : undefined}
                disabled={busyLabel !== null}
                onClick={() => navigate(id)}
              >
                <span className="app-nav__step" aria-hidden="true">{step}</span>
                {label}
              </button>
            ))}
          </div>
        </nav>
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
                      background: '#f5f5f5',
                      padding: 8,
                      borderRadius: 4,
                      fontFamily: 'ui-monospace, monospace',
                      fontSize: 12,
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
        {body}
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
      <Shell />
    </AppProvider>
  </StrictMode>,
)
