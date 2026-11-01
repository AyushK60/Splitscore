/**
 * Landing — the SplitScope product front door.
 *
 * One dominant hero illustration (HeroScene), a real explanation of what the
 * application does today, and working paths into the workbench. Nothing here
 * advertises an unimplemented capability as operational: the V2 research
 * surfaces are named only in a clearly marked roadmap strip, and every number
 * in the verification section is one this repository's own suites produce.
 */

import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'
import { HeroScene } from '../components/HeroScene'

type LandingProps = { onNavigate: (view: ViewId) => void }

const NAV_LINKS = [
  { href: '#lp-capabilities', label: 'Capabilities' },
  { href: '#lp-method', label: 'Method' },
  { href: '#lp-evidence', label: 'Evidence' },
]

const CAPABILITIES = [
  {
    id: 'detect',
    kicker: 'Detect contamination',
    body: 'Five evidence-based checks — exact duplicates, entity overlap, chronology, target copy and opt-in near-duplicates — each reporting severity, denominators and the exact rows behind the finding. Checks that cannot run are listed separately, never as a pass.',
    action: { label: 'Open the audit workflow', view: 'overview' as ViewId },
  },
  {
    id: 'compare',
    kicker: 'Compare split strategies',
    body: 'Audit the split you already have, then generate random, stratified, group and chronological alternatives and compare their consequences side by side. SplitScope shows the trade-offs and never declares a winner.',
    action: { label: 'See split comparison', view: 'comparison' as ViewId },
  },
  {
    id: 'report',
    kicker: 'Export the evidence',
    body: 'Every run can be downloaded as a JSON report, a self-contained HTML file or per-strategy assignment CSVs — with role settings, check coverage and row identifiers intact, so a reviewer can retrace each number.',
    action: { label: 'Go to reports', view: 'export' as ViewId },
  },
]

const STEPS = [
  {
    title: 'Load a dataset',
    body: 'Upload a CSV or open a bundled synthetic demo. The file is parsed into a bounded, in-memory store with a SHA-256 fingerprint; it is never written to disk.',
  },
  {
    title: 'Map column roles',
    body: 'State whether the file already marks train and test, then confirm split, target, entity, timestamp and feature columns. Suggestions are shown with their reason and never applied silently.',
  },
  {
    title: 'Run the audit',
    body: 'Each enabled check runs against the selected split and returns findings with severity, counts, denominators, assumptions and the exact row identifiers behind them.',
  },
  {
    title: 'Compare strategies',
    body: 'Generate alternative splits with a fixed seed and compare how each one changes entity overlap, chronology and duplicate exposure — consequences, not a verdict.',
  },
  {
    title: 'Export and retrace',
    body: 'Download the audit as JSON or HTML, plus the exact row assignments per strategy, so every claim in the report can be checked against the data you loaded.',
  },
]

const VERIFICATION = [
  { value: '218', label: 'backend tests', command: 'python -m pytest -q' },
  { value: '70', label: 'frontend tests', command: 'npm run test' },
  { value: '41 / 61', label: 'synthetic cases / checks', command: 'python scripts/evaluate_synthetic.py' },
  { value: '4', label: 'browser journeys', command: 'npm run test:e2e' },
]

const ROADMAP = ['Visual Explorer', 'Model Lab', 'Causal Lab', 'Assumption registry', 'Research dossier']

export function LandingView({ onNavigate }: LandingProps) {
  const { demos, loadDemo, busyLabel, status } = useApp()
  const featured = demos?.featured_journey
  const featuredDemo = demos?.demos.find((demo) => demo.demo_id === featured?.demo_id)
  const demoReady = Boolean(featuredDemo?.file_present)
  const busy = busyLabel !== null

  const openDemo = async () => {
    if (!featuredDemo) return
    await loadDemo(featuredDemo.demo_id)
    onNavigate('dataset')
  }

  return (
    <div className="lp">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>

      <header className="lp-nav">
        <div className="lp-nav__inner">
          <a className="lp-brand" href="#/" aria-label="SplitScope home">
            <span className="lp-brand__mark" aria-hidden="true">
              <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
                <rect x="1" y="1" width="6" height="14" rx="1.5" fill="currentColor" opacity="0.95" />
                <rect x="9" y="1" width="6" height="14" rx="1.5" fill="currentColor" opacity="0.45" />
                <path d="M8 0.5v15" stroke="currentColor" strokeWidth="1.5" />
              </svg>
            </span>
            <span className="lp-brand__word">SplitScope</span>
            <span className="lp-brand__tag">Research integrity</span>
          </a>

          <nav className="lp-nav__links" aria-label="Landing">
            {NAV_LINKS.map((link) => (
              <a key={link.href} href={link.href}>
                {link.label}
              </a>
            ))}
          </nav>

          <div className="lp-nav__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => onNavigate('overview')}
            >
              Launch Workbench
            </button>
          </div>
        </div>
      </header>

      <main id="main" tabIndex={-1} className="lp-main">
        {/* ------------------------------- hero ------------------------------ */}
        <section className="lp-hero" aria-labelledby="lp-title">
          <div className="lp-hero__text">
            <p className="lp-eyebrow">Local-first · runs entirely on your machine</p>
            <h1 id="lp-title">From data leakage to causal insight.</h1>
            <p className="lp-lead">
              SplitScope audits the boundary between training and test data before a model ever
              sees it — five evidence-based checks, the exact rows behind every finding, and split
              alternatives you can compare. Evaluation you can defend starts with knowing what your
              split actually shares.
            </p>

            <div className="lp-hero__actions">
              <button
                type="button"
                className="btn btn--big btn--primary"
                onClick={() => onNavigate('overview')}
              >
                Launch Workbench
              </button>
              <button
                type="button"
                className="btn btn--big btn--onDark"
                disabled={busy || !demoReady}
                onClick={() => void openDemo()}
              >
                {busy ? busyLabel : 'Explore Interactive Demo'}
              </button>
            </div>

            <p className="lp-hero__note">
              {featuredDemo ? (
                <>
                  The demo opens <strong>{featuredDemo.title}</strong>, a bundled{' '}
                  <strong>synthetic</strong> dataset with roles already filled in — labelled
                  synthetic everywhere it appears.
                </>
              ) : (
                <>
                  The demo opens a bundled <strong>synthetic</strong> dataset with roles already
                  filled in — labelled synthetic everywhere it appears.
                </>
              )}{' '}
              Your own CSV stays in server memory and is never written to disk.
            </p>

            {status.kind === 'error' ? (
              <p className="lp-hero__warn" role="status">
                The backend catalogue has not loaded: {status.message} The workbench still opens —
                upload and demo loading need the local API.
              </p>
            ) : null}
          </div>

          <HeroScene />
        </section>

        {/* --------------------------- capability strip ---------------------- */}
        <section className="lp-strip" aria-label="What is implemented today">
          <ul>
            <li>
              <strong>5</strong> evidence-based leakage checks
            </li>
            <li>
              <strong>Row-level</strong> evidence for every finding
            </li>
            <li>
              <strong>4</strong> split strategies compared
            </li>
            <li>
              <strong>JSON · HTML · CSV</strong> exports
            </li>
            <li>
              <strong>6</strong> bundled synthetic demos
            </li>
            <li>
              <strong>Local-first</strong> — no network calls at runtime
            </li>
          </ul>
        </section>

        {/* --------------------------- capabilities -------------------------- */}
        <section className="lp-section" id="lp-capabilities" aria-labelledby="lp-cap-h">
          <div className="lp-section__head">
            <p className="lp-eyebrow">What the workbench does today</p>
            <h2 id="lp-cap-h">Real capabilities, not a feature list</h2>
            <p className="lp-section__lede">
              Every action below opens a working screen in the application. Each result it produces
              is computed by the local audit engine and traceable to the rows you loaded.
            </p>
          </div>

          <div className="lp-cards">
            {CAPABILITIES.map((card, index) => (
              <article className="lp-card" key={card.id}>
                <span className="lp-card__index" aria-hidden="true">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <h3>{card.kicker}</h3>
                <p>{card.body}</p>
                <button
                  type="button"
                  className="lp-card__action"
                  onClick={() => onNavigate(card.action.view)}
                >
                  {card.action.label}
                  <span aria-hidden="true">→</span>
                </button>
              </article>
            ))}
          </div>

          <aside className="lp-roadmap" aria-label="Planned V2 workspaces">
            <p className="lp-roadmap__label">Planned for SplitScope V2 — not available yet</p>
            <ul>
              {ROADMAP.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <p className="lp-roadmap__note">
              These workspaces are specified in the V2 blueprint and are not implemented in this
              build. Nothing on this page links to them.
            </p>
          </aside>
        </section>

        {/* ------------------------------ method ----------------------------- */}
        <section className="lp-section lp-section--method" id="lp-method" aria-labelledby="lp-method-h">
          <div className="lp-section__head">
            <p className="lp-eyebrow">Method</p>
            <h2 id="lp-method-h">How an audit runs</h2>
            <p className="lp-section__lede">
              The workflow is deliberately short: five steps from raw file to exported evidence,
              with a confirmation gate wherever a human judgment is required.
            </p>
          </div>

          <ol className="lp-steps">
            {STEPS.map((step, index) => (
              <li key={step.title}>
                <span className="lp-steps__num" aria-hidden="true">
                  {index + 1}
                </span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>

          <div className="lp-method__cta">
            <p>
              Start with the guided demo — no file, no setup: the roles, target and entity are
              pre-filled and you can change every one of them.
            </p>
            <button
              type="button"
              className="btn btn--primary"
              disabled={busy || !demoReady}
              onClick={() => void openDemo()}
            >
              Open the synthetic walkthrough
            </button>
          </div>
        </section>

        {/* ----------------------------- evidence ---------------------------- */}
        <section className="lp-section lp-section--evidence" id="lp-evidence" aria-labelledby="lp-evidence-h">
          <div className="lp-section__head">
            <p className="lp-eyebrow">Evidence</p>
            <h2 id="lp-evidence-h">Verified on this build</h2>
            <p className="lp-section__lede">
              These are the repository's own suites and the commands that produce them. The
              synthetic evaluation proves the checks implement their stated definitions on
              hand-built fixtures — it is not a measure of real-world detection accuracy.
            </p>
          </div>

          <ul className="lp-verify">
            {VERIFICATION.map((item) => (
              <li key={item.label}>
                <span className="lp-verify__value">{item.value}</span>
                <span className="lp-verify__label">{item.label}</span>
                <code>{item.command}</code>
              </li>
            ))}
          </ul>
        </section>

        {/* ------------------------------- final ----------------------------- */}
        <section className="lp-final" aria-labelledby="lp-final-h">
          <div className="lp-final__inner">
            <h2 id="lp-final-h">Audit the split before you trust the score.</h2>
            <p>
              Open a synthetic demo in one click, or load your own CSV — it stays in server memory
              and expires with the session.
            </p>
            <div className="lp-final__actions">
              <button
                type="button"
                className="btn btn--big btn--primary"
                disabled={busy || !demoReady}
                onClick={() => void openDemo()}
              >
                Start with a demo
              </button>
              <button
                type="button"
                className="btn btn--big btn--onDark"
                onClick={() => onNavigate('dataset')}
              >
                Upload dataset
              </button>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-footer__inner">
          <p className="lp-footer__brand">
            <strong>SplitScope</strong> — Research Integrity & Causal Intelligence Studio
          </p>
          <p>
            SplitScope audits splits, not models. Findings are evidence about the split you
            selected — never a guarantee that data is safe or that a model will perform well.
          </p>
          <p className="lp-footer__meta">
            Local-first · no accounts · no outbound network calls · datasets held in bounded,
            in-memory storage with a one-hour TTL
          </p>
        </div>
      </footer>
    </div>
  )
}