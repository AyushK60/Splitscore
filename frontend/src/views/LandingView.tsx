/**
 * Landing - the SplitScope product front door.
 *
 * Art direction: "forensic archive". The page reads like a research plate at
 * night and a printed specification by day: bottle-ink and bone ivory, a copper
 * ember for anything the audit *finds*, celadon for structure. One motif - the
 * vertical split boundary - runs from the hero through every band, and the
 * display serif is the voice of the page while monospace handles instrument
 * labels.
 *
 * The hero is an instrument, not a decoration: four phases, each with a readout
 * that explains what it is showing, plus pause / replay / phase controls. The
 * records in it are a fixed illustration and say so in the plate.
 *
 * Honesty is structural, not decorative: the hero field is labelled, capability
 * rows only point at screens that exist, and the V2 workspaces are named as
 * not-yet-built in a single footnote.
 */
import { useRef, type CSSProperties } from 'react'

import type { ViewId } from '../lib/router'
import { useApp } from '../state/AppState'
import { HeroField } from '../components/HeroField'
import { HERO_PHASES, useHeroSequence } from '../lib/useHeroSequence'
import { useRevealOnScroll } from '../lib/useReveal'

type LandingProps = { onNavigate: (view: ViewId) => void }

/** Per-item stagger, read by the reveal transition. */
const delay = (ms: number) => ({ '--d': `${ms}ms` }) as CSSProperties

const NAV_LINKS = [
  { href: '#lp-capabilities', label: 'Capabilities' },
  { href: '#lp-method', label: 'Method' },
  { href: '#lp-evidence', label: 'Evidence' },
]

const HERO_FACTS = ['Local-first', 'Row-level evidence', 'No account', 'JSON · HTML · CSV']

type Capability = {
  num: string
  title: string
  body: string
  checks?: string[]
  action: string
  view: ViewId
}

const CAPABILITIES: Capability[] = [
  {
    num: '01',
    title: 'Detect contamination',
    body: 'An evidence suite reads the split from both sides. Each finding carries a severity, its denominators, the assumptions it depends on, and the exact rows behind it - a check that cannot run is listed as not run, never as a pass.',
    checks: [
      'exact duplicates',
      'near-duplicates',
      'entity overlap',
      'chronology',
      'target copy',
      'validation reuse',
      'pipeline boundary',
      'feature availability',
    ],
    action: 'Open the audit workflow',
    view: 'overview',
  },
  {
    num: '02',
    title: 'Trace a finding to its rows',
    body: 'Every result resolves to row identifiers and the values that matched, so a reviewer can inspect the evidence instead of trusting a score. Nothing is summarised away.',
    action: 'Load a dataset to trace',
    view: 'dataset',
  },
  {
    num: '03',
    title: 'Compare split strategies',
    body: 'Audit the split you already have, then generate random, stratified, group and chronological alternatives with a fixed seed and compare their consequences side by side. SplitScope shows the trade-offs and never declares a winner.',
    action: 'See split comparison',
    view: 'comparison',
  },
  {
    num: '04',
    title: 'Export and retrace',
    body: 'Compose one evidence dossier from the runs in this session, then download structured JSON, a self-contained printable HTML file or per-strategy assignment CSVs - with role settings, check coverage and row identifiers intact.',
    action: 'Go to reports',
    view: 'export',
  },
]

const STEPS = [
  {
    title: 'Load a dataset',
    body: 'A CSV or a bundled synthetic demo is parsed into a bounded in-memory store with a SHA-256 fingerprint - never written to disk.',
  },
  {
    title: 'Map column roles',
    body: 'Confirm split, target, entity, timestamp and feature columns. Suggestions show their reason and are never applied silently.',
  },
  {
    title: 'Run the audit',
    body: 'Each enabled check returns findings with severity, counts, denominators and the exact row identifiers behind them.',
  },
  {
    title: 'Compare strategies',
    body: 'Alternative splits are generated with a fixed seed and compared on entity overlap, chronology and duplicate exposure.',
  },
  {
    title: 'Export and retrace',
    body: 'The audit ships as JSON or HTML with the exact row assignments per strategy, so every claim can be rechecked.',
  },
]

const PROOF = [
  { value: '536', label: 'backend tests', command: 'python -m pytest -q', span: 'span-5' },
  { value: '205', label: 'frontend tests', command: 'npm run test', span: 'span-3' },
  { value: '41 / 61', label: 'synthetic cases / checks', command: 'evaluate_synthetic.py', span: 'span-4' },
  { value: '33', label: 'browser tests', command: 'npm run test:e2e', span: 'span-4' },
  { value: '7', label: 'bundled synthetic demos', command: 'labelled synthetic throughout', span: 'span-4' },
  { value: '3', label: 'export formats', command: 'JSON · HTML · CSV', span: 'span-4' },
]

const NEXT_STEPS = [
  'Choose a file or demo',
  'Confirm column roles',
  'Run the leakage checks',
  'Compare split strategies',
  'Export the evidence',
]

export function LandingView({ onNavigate }: LandingProps) {
  const { demos, loadDemo, busyLabel, status } = useApp()
  const rootRef = useRef<HTMLDivElement>(null)
  useRevealOnScroll(rootRef)
  const { phase, playing, cycle, reducedMotion, toggle, replay, jump, inspect } = useHeroSequence()

  const featured = demos?.featured_journey
  const featuredDemo = demos?.demos.find((demo) => demo.demo_id === featured?.demo_id)
  const demoReady = Boolean(featuredDemo?.file_present)
  const busy = busyLabel !== null

  const currentPhase = HERO_PHASES.find((item) => item.id === phase) ?? HERO_PHASES[0]
  const phaseNumber = String(HERO_PHASES.findIndex((item) => item.id === phase) + 1).padStart(2, '0')
  const showEvidence = phase === 'evidence'

  const openDemo = async () => {
    if (!featuredDemo) return
    await loadDemo(featuredDemo.demo_id)
    onNavigate('dataset')
  }

  return (
    <div className="lp" ref={rootRef}>
      <a className="skip-link" href="#main">
        Skip to main content
      </a>

      <header className="lp-nav">
        <div className="lp-nav__inner">
          <a className="lp-brand" href="#/" aria-label="SplitScope home">
            <span className="lp-brand__mark" aria-hidden="true">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <rect x="2" y="2" width="7.5" height="16" rx="1" fill="currentColor" opacity="0.92" />
                <rect
                  x="10.5"
                  y="2"
                  width="7.5"
                  height="16"
                  rx="1"
                  fill="currentColor"
                  opacity="0.22"
                />
                <path d="M10 1v18" stroke="var(--accent)" strokeWidth="1.2" />
              </svg>
            </span>
            <span className="lp-brand__name">SplitScope</span>
            <span className="lp-brand__meta">Research integrity studio</span>
          </a>

          <nav className="lp-nav__links" aria-label="Landing sections">
            {NAV_LINKS.map((link) => (
              <a key={link.href} href={link.href}>
                {link.label}
              </a>
            ))}
          </nav>

          <button
            type="button"
            className="lp-btn lp-btn--line lp-btn--sm"
            onClick={() => onNavigate('overview')}
          >
            Launch workbench
          </button>
        </div>
      </header>

      <main id="main" tabIndex={-1} className="lp-main">
        {/* ------------------------------- 01 hero ----------------------------- */}
        <section className="lp-hero" aria-labelledby="lp-title">
          <div className="lp-hero__inner">
            <div className="lp-hero__copy">
              <p className="lp-kicker">
                <span className="lp-kicker__rule" aria-hidden="true" />
                Local-first · the split is the product
              </p>

              <h1 id="lp-title" className="lp-title">
                <span className="lp-title__line">
                  <span>Audit the</span>
                </span>
                <span className="lp-title__line">
                  <span>train/test split</span>
                </span>
                <span className="lp-title__line">
                  <span>
                    <em>before</em> a model
                  </span>
                </span>
                <span className="lp-title__line">
                  <span>sees it.</span>
                </span>
              </h1>

              <p className="lp-hero__lead">
                SplitScope audits the boundary between training and test data before a model ever
                sees it - five evidence-based checks, the exact rows behind every finding, and
                split alternatives you can compare. Evaluation you can defend starts with knowing
                what your split actually shares.
              </p>

              <div className="lp-hero__actions">
                <button
                  type="button"
                  className="lp-btn lp-btn--solid lp-btn--lg"
                  onClick={() => onNavigate('overview')}
                >
                  Launch Workbench
                  <span className="lp-btn__arrow" aria-hidden="true">
                    →
                  </span>
                </button>
                <button
                  type="button"
                  className="lp-btn lp-btn--ghost lp-btn--lg"
                  disabled={busy || !demoReady}
                  onClick={() => void openDemo()}
                >
                  {busy ? busyLabel : 'Explore Interactive Demo'}
                </button>
              </div>

              <ul className="lp-hero__facts" aria-label="Product properties">
                {HERO_FACTS.map((fact) => (
                  <li key={fact}>{fact}</li>
                ))}
              </ul>

              {status.kind === 'error' ? (
                <p className="lp-hero__warn" role="status">
                  The catalogue has not loaded: {status.message} The workbench still opens -
                  uploading and demo loading need the local API.
                </p>
              ) : null}
            </div>

            <figure className="lp-plate" aria-label="Boundary observatory, an illustrative plate">
              <div className="lp-plate__head">
                <p className="lp-readout__label">Plate 01 · boundary observatory</p>
                <p className="lp-readout__step">{phaseNumber} / 04</p>
              </div>

              <div className="lp-hero__field" aria-hidden="true">
                <HeroField phase={phase} paused={!playing || reducedMotion} cycle={cycle} />
              </div>

              <div className="lp-console">
                <div className="lp-console__controls" role="group" aria-label="Observatory controls">
                  <button
                    type="button"
                    className="lp-console__btn"
                    onClick={toggle}
                    disabled={reducedMotion}
                    aria-label={
                      playing ? 'Pause the observatory sequence' : 'Resume the observatory sequence'
                    }
                  >
                    <svg className="lp-icon" viewBox="0 0 16 16" aria-hidden="true">
                      {playing ? <path d="M5 3v10M11 3v10" /> : <path d="M5 3l8 5-8 5z" />}
                    </svg>
                    {playing ? 'Pause' : 'Play'}
                  </button>
                  <button
                    type="button"
                    className="lp-console__btn"
                    onClick={replay}
                    disabled={reducedMotion}
                    aria-label="Replay the observatory sequence from the beginning"
                  >
                    <svg className="lp-icon" viewBox="0 0 16 16" aria-hidden="true">
                      <path d="M3 8a5 5 0 1 0 1.6-3.7M3 2.5v3h3" />
                    </svg>
                    Replay
                  </button>
                  <button
                    type="button"
                    className="lp-console__btn"
                    onClick={inspect}
                    aria-pressed={phase === 'evidence'}
                    aria-label="Inspect the implicated pair of records"
                  >
                    <svg className="lp-icon" viewBox="0 0 16 16" aria-hidden="true">
                      <circle cx="7" cy="7" r="4" />
                      <path d="M10 10l3.5 3.5" />
                    </svg>
                    Inspect pair
                  </button>
                </div>

                <ol className="lp-console__rail" aria-label="Observatory phases">
                  {HERO_PHASES.map((item, index) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className="lp-console__phase"
                        data-active={phase === item.id}
                        aria-current={phase === item.id ? 'step' : undefined}
                        onClick={() => jump(item.id)}
                      >
                        <span className="lp-console__tick" aria-hidden="true" />
                        <span className="lp-console__num">
                          {String(index + 1).padStart(2, '0')}
                        </span>
                        <span className="lp-console__name">{item.short}</span>
                      </button>
                    </li>
                  ))}
                </ol>

                {reducedMotion ? (
                  <p className="lp-console__note">
                    Reduced motion is on: the instrument is shown as a single still frame of the
                    evidence stage.
                  </p>
                ) : null}
              </div>

              <figcaption className="lp-readout" aria-label="Observatory readout">
                <div className="lp-readout__main">
                  <h2 className="lp-readout__title" aria-live="polite">
                    {currentPhase.title}
                  </h2>
                  <p className="lp-readout__body">{currentPhase.body}</p>
                  <p className="lp-readout__note">{currentPhase.hint}</p>
                </div>

                <div className="lp-readout__side">
                  <div
                    className="lp-readout__evidence"
                    data-show={showEvidence ? 'true' : 'false'}
                    aria-hidden={showEvidence ? undefined : true}
                  >
                    <p className="lp-readout__evidence-label">Matched fields</p>
                    <ul className="lp-readout__matches">
                      <li>customer_id</li>
                      <li>signup_ts</li>
                      <li>plan_tier</li>
                      <li>region</li>
                    </ul>
                    <p className="lp-readout__evidence-note">
                      Illustrative pair · row-000412 / row-000887 · not a computed result
                    </p>
                  </div>

                  <button
                    type="button"
                    className="lp-link lp-readout__cta"
                    disabled={busy || !demoReady}
                    onClick={() => void openDemo()}
                  >
                    Run this audit on the synthetic demo <span aria-hidden="true">↗</span>
                  </button>
                </div>
              </figcaption>
            </figure>
          </div>

          <div className="lp-hero__index">
            <span>01 - Boundary observatory</span>
            <span className="lp-hero__index-mid">Illustrative fixture · not a computed result</span>
            <span>Scroll ↓</span>
          </div>
        </section>

        {/* --------------------------- 02 capabilities ------------------------- */}
        <section className="lp-band lp-band--paper" id="lp-capabilities" aria-labelledby="lp-cap-h">
          <div className="lp-band__grid">
            <div className="lp-band__rail">
              <p className="lp-index">02 - Capabilities</p>
              <h2 id="lp-cap-h" className="lp-h2" data-reveal="">
                Four things it can prove, <em>row by row</em>.
              </h2>
              <p className="lp-lede" data-reveal="" style={delay(80)}>
                Every action below opens a working screen. Every figure comes from the local audit
                engine and resolves to the rows you loaded.
              </p>
            </div>

            <div className="lp-band__body">
              <div className="lp-ledger">
                {CAPABILITIES.map((cap, index) => (
                  <article className="lp-entry" key={cap.num} data-reveal="" style={delay(index * 70)}>
                    <p className="lp-entry__num" aria-hidden="true">
                      {cap.num}
                    </p>
                    <div className="lp-entry__main">
                      <h3 className="lp-entry__title">{cap.title}</h3>
                      <p className="lp-entry__body">{cap.body}</p>
                      {cap.checks ? (
                        <ul className="lp-entry__checks" aria-label="Implemented leakage checks">
                          {cap.checks.map((check) => (
                            <li key={check}>{check}</li>
                          ))}
                        </ul>
                      ) : null}
                      <button type="button" className="lp-link" onClick={() => onNavigate(cap.view)}>
                        {cap.action}
                        <span aria-hidden="true">↗</span>
                      </button>
                    </div>
                  </article>
                ))}
              </div>

              <p className="lp-footnote" data-reveal="">
                <span className="lp-footnote__label">In this build</span>
                Visual Explorer · Model Lab · Causal Lab with graphical identification · Effect
                estimation · and the Report / Export Studio are available from the workbench.
                Identification and estimation are conditional on the assumed graph; nothing here
                proves a causal effect.
              </p>
            </div>
          </div>
        </section>

        {/* ------------------------------ 03 method ---------------------------- */}
        <section className="lp-band lp-band--ink" id="lp-method" aria-labelledby="lp-method-h">
          <div className="lp-band__wide">
            <div className="lp-method__head">
              <div>
                <p className="lp-index lp-index--ink">03 - Method</p>
                <h2 id="lp-method-h" className="lp-h2 lp-h2--ink" data-reveal="">
                  Five steps, <em>one confirmation gate</em>.
                </h2>
              </div>
              <p className="lp-lede lp-lede--ink" data-reveal="" style={delay(80)}>
                The workflow is deliberately short: from raw file to exported evidence, with a human
                confirmation wherever a judgment is required.
              </p>
            </div>

            <ol className="lp-timeline" data-reveal="">
              {STEPS.map((step, index) => (
                <li key={step.title} data-reveal="" style={delay(index * 90)}>
                  <span className="lp-timeline__num" aria-hidden="true">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="lp-timeline__dot" aria-hidden="true" />
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </li>
              ))}
            </ol>

            <div className="lp-method__foot" data-reveal="" style={delay(180)}>
              <p>
                Start with the guided demo - no file, no setup: roles, target and entity are
                pre-filled, and you can change every one of them.
              </p>
              <button
                type="button"
                className="lp-btn lp-btn--solid"
                disabled={busy || !demoReady}
                onClick={() => void openDemo()}
              >
                Open the synthetic walkthrough
              </button>
            </div>
          </div>
        </section>

        {/* ----------------------------- 04 evidence --------------------------- */}
        <section
          className="lp-band lp-band--paper lp-band--proof"
          id="lp-evidence"
          aria-labelledby="lp-evidence-h"
        >
          <div className="lp-band__grid">
            <div className="lp-band__rail">
              <p className="lp-index">04 - Evidence</p>
              <h2 id="lp-evidence-h" className="lp-h2" data-reveal="">
                Verified <em>on this build</em>.
              </h2>
              <p className="lp-lede" data-reveal="" style={delay(80)}>
                These are the repository's own suites and the exact commands that produce them.
                Nothing here is a projection.
              </p>
            </div>

            <div className="lp-band__body">
              <div className="lp-proof" data-reveal="">
                {PROOF.map((cell) => (
                  <div className={`lp-proof__cell ${cell.span}`} key={cell.label}>
                    <p className="lp-proof__value">{cell.value}</p>
                    <p className="lp-proof__label">{cell.label}</p>
                    <code className="lp-proof__command">{cell.command}</code>
                  </div>
                ))}
              </div>

              <blockquote className="lp-pullquote" data-reveal="" style={delay(120)}>
                Every check reports its denominators, its assumptions and the rows behind the
                finding.
              </blockquote>

              <p className="lp-caveat" data-reveal="" style={delay(160)}>
                The synthetic evaluation proves each check implements its stated definition on
                hand-built fixtures. It is <em>not</em> a measure of real-world detection accuracy.
              </p>
            </div>
          </div>
        </section>

        {/* ------------------------------ 05 begin ----------------------------- */}
        <section className="lp-final" aria-labelledby="lp-final-h">
          <div className="lp-final__inner">
            <div className="lp-final__copy">
              <p className="lp-index">05 - Begin</p>
              <h2 id="lp-final-h" className="lp-final__title" data-reveal="">
                Audit the split <em>before</em> you trust the score.
              </h2>
              <p className="lp-lede" data-reveal="" style={delay(80)}>
                Open a synthetic demo in one click, or load your own CSV - it stays in server memory
                and expires with the session.
              </p>
              <div className="lp-hero__actions" data-reveal="" style={delay(140)}>
                <button
                  type="button"
                  className="lp-btn lp-btn--solid lp-btn--lg"
                  disabled={busy || !demoReady}
                  onClick={() => void openDemo()}
                >
                  Start with a demo
                </button>
                <button
                  type="button"
                  className="lp-btn lp-btn--ghost lp-btn--lg"
                  onClick={() => onNavigate('dataset')}
                >
                  Upload dataset
                </button>
              </div>
            </div>

            <ol className="lp-final__steps" data-reveal="" style={delay(120)}>
              {NEXT_STEPS.map((line, index) => (
                <li key={line}>
                  <span aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                  {line}
                </li>
              ))}
            </ol>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-footer__top">
          <p className="lp-footer__brand">SplitScope</p>
          <p className="lp-footer__tag">Research Integrity &amp; Causal Intelligence Studio</p>
        </div>
        <p className="lp-footer__statement">
          SplitScope audits splits, not models. Findings are evidence about the split you selected -
          never a guarantee that data is safe or that a model will perform well.
        </p>
        <p className="lp-footer__meta">
          Local-first · no accounts · no outbound network calls · datasets held in bounded, in-memory
          storage with a one-hour TTL
        </p>
      </footer>
    </div>
  )
}
