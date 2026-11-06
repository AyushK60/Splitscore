# S9C Independent Scientific Audit

**Auditor:** independent session (S9C audit assignment), 2026-11-07
**Branch:** `v2-premium-visual-foundation`, starting commit `befea1e`
**Method:** every headline claim re-derived with independently implemented
machinery; every suspected defect reproduced before repair; no production
estimator used as its own oracle.

## 1. Scope and method

The audit covered the three S9C services (`backend/app/causal/estimation/`
→ `subgroups.py`, `robustness.py`, `whatif.py`), their routes in
`routes_causal_estimation.py`, the shared S9A estimator core
(`estimators.py`, `preparation.py`, `service.py`), and the Causal Research
frontend (`frontend/src/research/`).

Independent oracles were implemented in
`backend/tests/test_s9c_independent_audit.py` (15 tests). None of them
imports production estimation code to produce an expectation:

- a **from-scratch cross-fitted AIPW** written directly from the estimating
  equation (own fold construction, own nuisance fitting);
- **exact closed-form Hájek IPW** on an intercept-only propensity design
  (a randomised experiment), including the influence-function SE;
- **statsmodels OLS g-computation** re-fitting every simulated-confounder
  grid cell — a different library and pipeline from the production sklearn
  path;
- **hand-derived OLS predictions** on a noise-free linear DGP where the
  fitted what-if model is known exactly;
- **seed traceability**: robustness repetition 0 re-drawn from the recorded
  `[seed, r]` generator and re-estimated independently.

## 2. Verification results (what was independently confirmed)

| Claim | Independent check | Result |
| --- | --- | --- |
| Subgroup ATEs recover known heterogeneous effects | DGP with per-group effects 0.4/0.8/1.2/1.6 across x1 quartiles, n=1600 | recovered within 0.3 (≈2 SE) |
| Subgroup estimates agree with an independently cross-fitted AIPW | own implementation vs payload, confounded DGP, n=900 | within 3 SE; SEs within 40% |
| Overall ATE is the row-weighted mixture of subgroup ATEs | payload identity | exact to 1e-9 |
| Group SE `sd(ψ|g)/√n` and contrast SE `√(var_a/n_a+var_b/n_b)` | recomputed at levels 0.90/0.95/0.99 | exact to 1e-9/1e-12 |
| IPW Hájek point estimate, arm means and IF SE | exact closed form on randomised design | exact to 1e-9 |
| Subgroup stage consumes the same estimating equation as the studio | same seed ⇒ identical folds; overall == studio AIPW ATE | 1e-9 |
| Sensitivity grid (γ, κ) × 25 cells, regression adjustment | statsmodels re-simulation + re-fit of every cell | all cells ≤ 1e-7 |
| Sensitivity (0,0) cell ≈ original; grid reacts to parameters | recomputed | confirmed |
| Subsampling repetition 0 traces to `[seed, 0]` | independent redraw + statsmodels refit | exact to 1e-7 |
| Placebo preserves treated count; reproducible bitwise; centres near zero for randomised data | payload + rerun | confirmed |
| What-if profile predictions | hand-derived OLS on noise-free linear DGP | exact to 1e-6; cohort contrast exactly the true effect |
| What-if refuses treatment/outcome/unknown profile fields | production refusal paths | confirmed |
| Cross-fitted AIPW pseudo-outcome finiteness | estimator raises `EstimationFailure` on any non-finite row | confirmed (makes unfiltered contrast variance safe) |
| Subgroup variable outside the adjustment set works | API-level scenario tested | works — `prepare_cohort` carries the full dataset frame; suspected KeyError was a false hypothesis, refuted by reproduction |
| Stale graph fingerprint refused on all three S9C routes | new API tests (409 `infeasible_operation`) | confirmed |
| Every payload JSON-serialisable with recorded reproducibility block | `json.dumps` + fingerprint/version assertions | confirmed |
| Severe imbalance (90/10) and degenerate groups | unavailable status, never fabricated | confirmed |
| Missing subgroup values excluded and disclosed | existing case 10 + audit review | confirmed |

## 3. Confirmed defects and repairs

### AUDIT-1 (HIGH, repaired) — Forest-plot uncertainty whiskers never painted

**Symptom.** In the Causal Research subgroup view the forest plot showed only
point dots. The reported intervals (e.g. `0.789 – 2.284`) had no visible
whiskers: the primary heterogeneity figure silently understated uncertainty.

**Root cause.** The `--est-teal` palette was defined on `.eststudio` (the S9B
stage container) only. The research stage renders the shared chart rules
(`.estrow__interval`, `.estrow__cap`, `.estrow__dot`) *outside* that scope, so
`stroke: color-mix(in srgb, var(--est-teal) 55%, transparent)` was invalid at
computed-value time and computed to `none`. Verified live: computed stroke was
`none` while `stroke-width` (same rule) applied at 3.5px.

**Repair.** Hoisted `--est-copper/--est-copper-soft/--est-teal/--est-teal-soft`
to `:root` in `frontend/src/styles/s9.css`. Verified in the live DOM:
computed stroke became `color(srgb 0.039 0.427 0.49 / 0.55)` with 3.5px width.

**Regression guard.** Journey A of `e2e/s9c-research.spec.ts` now asserts the
first whisker's computed stroke is not `none`, its width is 3.5px, and its
painted bounding-box width exceeds 50px.

### AUDIT-2 (MEDIUM, repaired) — Intermittent failure in `CausalIdentification.test.tsx`

**Reproduction.** Failed 2 times in ~23 consecutive single-file runs (≈1-in-10)
across two different tests, both asserting on the identification panel
immediately after entering identification mode.

**Root cause.** Test-side race, not a product defect. After the lab mounts, the
saved-graph selection (`causalApi.list` → `get` → `dispatch load`) settles
asynchronously; during that window `state.graphId` is null and the panel
legitimately shows the save gate. The tests clicked/run before hydration
finished. The component's own loading sequence was reviewed and is correct.

**Repair.** `enterIdentificationMode()` now awaits the save gate's clearance
before interacting (testing eventual state, not an intermediate loading
state; no assertions removed or timeouts raised). Soak: **15/15 consecutive
passes** after the fix.

### AUDIT-3 (LOW, repaired) — What-if numeric placeholder clipped

`type="number"` inputs clip long placeholders in Chromium; "cohort median"
displayed as "cohort media", readable as a wrong value. Placeholder shortened
to `median` — the field hint below already carries the full wording.

## 4. Scientific-integrity review of the disclosed limitations

- The subgroup payload's provenance notes (cross-fitted on the whole cohort,
  no per-group refit), the multiple-comparisons note, and the exploratory/
  prespecified intent labelling are present, accurate and rendered.
- Robustness payloads carry the three caveats verbatim; the sensitivity
  experiment is consistently described as a hypothetical scenario, *not* a
  bound. The fixed 5×5 grid is disclosed. Placebo permutation limitations
  under group structure are disclosed when a cross-fit group column is set.
- The what-if payload distinguishes modeled conditional expectations from
  observed/counterfactual outcomes, attaches no interval, restricts profiles
  to the verified adjustment set (structurally excluding treatment
  descendants), and warns on out-of-support profiles.
- No robustness metric is invented; failed repetitions and cells are
  disclosed, never averaged away.

## 5. Remaining limitations (documented, non-blocking)

1. Subgroup uncertainty treats the shared cross-fitted nuisance fitting as
   fixed; the disclosed provenance note covers this honestly. (No change —
   the disclosure is the correct treatment.)
2. `CausalIdentification.test.tsx` root cause was test-side; the component's
   brief save-gate flicker during graph hydration remains (arguably correct
   loading feedback).
3. Known S9C gaps from the handoff (dossier integration, persistent history)
   are exactly the S10 scope.

## 6. Verdict

**CONDITIONAL PASS → PASS after repairs.** All confirmed CRITICAL/HIGH
defects were repaired and regression-guarded; the full verification matrix
is recorded in `S9C_FINAL_VERIFICATION.md`.
