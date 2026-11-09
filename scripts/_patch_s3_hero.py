from pathlib import Path

view = Path("frontend/src/views/LandingView.tsx")
text = view.read_text(encoding="utf-8")

start = text.index('            <aside className="lp-readout"')
end = text.index("            </aside>", start) + len("            </aside>")

aside = '''            <aside className="lp-readout" aria-label="Observatory readout">
              <div className="lp-readout__head">
                <p className="lp-readout__label">Plate 01 · boundary observatory</p>
                <p className="lp-readout__step">{phaseNumber} / 04</p>
              </div>

              <h2 className="lp-readout__title" aria-live="polite">
                {currentPhase.title}
              </h2>
              <p className="lp-readout__body">{currentPhase.body}</p>

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

              <p className="lp-readout__note">{currentPhase.hint}</p>

              <button
                type="button"
                className="lp-link lp-readout__cta"
                disabled={busy || !demoReady}
                onClick={() => void openDemo()}
              >
                Run this audit on the synthetic demo <span aria-hidden="true">↗</span>
              </button>
            </aside>'''

view.write_text(text[:start] + aside + text[end:], encoding="utf-8")
print("readout replaced")

css = Path("frontend/src/styles/s3.css")
css.write_text(
    css.read_text(encoding="utf-8")
    + """

/* -- S3 refinements -------------------------------------------------------- */

/* The entrance animation must not touch `transform`: each plate carries its
   position as an SVG transform attribute, and a CSS transform would replace it
   and stack every record at the origin. */
@keyframes obs-card-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@media (min-width: 1001px) {
  .lp .lp-hero__inner {
    grid-template-columns: minmax(0, 1fr) minmax(0, 420px);
  }
}

.lp-readout {
  min-height: 300px;
}

.lp-readout__evidence-label {
  font: 600 9px/1 var(--lp-mono);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgb(242 233 216 / 40%);
  margin-bottom: 8px;
}

.lp-readout__matches {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.lp-readout__matches li {
  padding: 4px 8px;
  border: 1px solid rgb(224 122 60 / 45%);
  background: rgb(224 122 60 / 10%);
  color: var(--lp-copper-light);
  font: 400 10px/1.2 var(--lp-mono);
  letter-spacing: 0.04em;
}

.lp-readout__evidence-note {
  margin-top: 8px;
  font: 400 9.5px/1.5 var(--lp-mono);
  color: rgb(242 233 216 / 34%);
}

/* The finding label sits in the scene, above the registers. */
.obs-finding {
  opacity: 0;
  transition: opacity 0.5s ease 0.4s;
}

.obs-scene[data-phase='discovery'] .obs-finding,
.obs-scene[data-phase='evidence'] .obs-finding {
  opacity: 1;
}

.obs-finding rect {
  fill: rgb(8 14 11 / 90%);
  stroke: rgb(224 122 60 / 55%);
  stroke-width: 1;
}

.obs-finding__id {
  fill: var(--lp-copper-light);
  font: 600 10px var(--lp-mono);
  letter-spacing: 0.1em;
}

.obs-finding__note {
  fill: rgb(242 233 216 / 56%);
  font: 400 9px var(--lp-mono);
}

.obs-finding__leader {
  stroke: rgb(224 122 60 / 40%);
  stroke-width: 1;
  stroke-dasharray: 2 3;
}

@media (prefers-reduced-motion: reduce) {
  .obs-finding {
    opacity: 1 !important;
  }
}
""",
    encoding="utf-8",
)
print("css appended")
