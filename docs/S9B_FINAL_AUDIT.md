# S9B — Final Independent Audit

**Date:** 2026-11-06 · **Branch:** `v2-premium-visual-foundation` · **Auditor:** independent of the S9B implementation session.

## Verdict: **PASS**

Every required S9B functionality works, the applicable verification gates pass, and
independent numerical + visual checks reproduce the implementation's claims. No
critical or high-severity defect was found; no repair was necessary.

## Scope audited

The S9B implementation arrived in this session as an **uncommitted working tree**
(code, tests, docs and screenshots), with `STATUS.md` claiming completion. This
audit verified the claims independently rather than trusting them, and produced
the first S9B commits.

## Verification performed in this audit (all executed, not inherited)

| Gate | Command | Result |
|---|---|---|
| Backend suite | `.venv\Scripts\python -m pytest backend/tests -q` | **536 passed** (3 pre-existing warnings), 14 min 20 s |
| Synthetic leakage oracle | `python scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks, exit 0** |
| Frontend typecheck | `npm run typecheck` | clean |
| ESLint | `npm run lint` (`--max-warnings 0`) | clean |
| Frontend unit/component | `npm test` | **22 files, 205 passed** |
| Production build | `npm run build` | passes (`EstimationView` lazy chunk; main-bundle size warning pre-existing) |
| Full Playwright suite | `npx playwright test` (venv on PATH) | **33 passed** (29 earlier + 4 S9B journeys A–D), 4.4 min |
| Independent numerical check | in-process API run + independent recomputation | **PASS** (below) |

## Independent numerical verification (new evidence, not part of the S9B suite)

A standalone script drove the real API in-process (demo load → demonstration DAG
creation → readiness probe → three-estimator comparison, seed 12345, 200 bootstrap
reps) and recomputed the estimators with independent implementations:

| Quantity | Reported by engine | Independent recomputation | Verdict |
|---|---|---|---|
| Regression adjustment ATE | 1.7312 | OLS of `outcome ~ treatment + age + baseline_score + C(region)`: **1.7312** | match to 1e-6 |
| IPW ATE (Hájek) | 1.6799 | logistic propensity + Hájek difference: 1.6697 | within 0.15 (nuisance-pipeline difference) |
| AIPW ATE | 1.6638 | — | within 0.35 of the known generating effect 1.5 |
| Naive treated−control difference | — | 3.1724 | matches the documented confounded value |
| Overlap histogram | 20 bins, 21 edges | treated counts sum to 349 = treated rows | consistent |

This is the first time the S9A engine's output was compared against a from-scratch
statsmodels OLS / scikit-learn Hájek recomputation *through the S9B-facing API path*;
it confirms the studio displays engine numbers, not approximations of them.

## Functional audit against the S9B requirements

- **A. Estimation setup** — dataset + saved DAG + treatment/outcome/adjustment
  selection, explicit readiness probe (computes nothing, stores nothing), explicit
  run, configuration preserved across navigation, stored-run reload from history.
  Invalid scopes and adjustment sets are refused by the backend identification
  gate (422 with `open_backdoor_path`; journey B asserts the refusal end to end).
- **B. Effect comparison** — RA / IPW / AIPW dots and intervals from the shared
  analysis; zero-reference axis always drawn; failed estimators render as failed
  rows with the backend's reason, never as zeros (`summary-all-failed` state);
  unavailable intervals render "interval unavailable" with no interval mark;
  comparison is reported (largest pairwise difference), never resolved into a winner.
- **C. Covariate balance** — Love plot with distinct unadjusted (hollow) vs
  weighted (filled) series, categorical-level rows, 0.1 heuristic guide, sort
  control, imputation disclosure, and the explicit statement that balance does not
  establish exchangeability.
- **D. Propensity overlap and weights** — per-arm histograms from the new bounded
  20-bin `propensity_histogram` diagnostic (counts/shares only, no row scores),
  quantile rugs, medians, central-99% overlap band, Kish ESS table, extreme-weight
  and truncation disclosures; no value is invented client-side.
- **E. Reports/history/exports** — run history with stored-run reload, named
  staleness reasons (deterministic comparison over every request field; layout-only
  graph edits do not stale), dataset-expiry handling, SVG/PNG/CSV/JSON figure
  exports and verbatim run JSON, filenames and envelopes asserted in journey A.
  No unsupported export is advertised.

## Visual audit (screenshots opened and inspected, not just generated)

Reviewed: `desktop-1440`, `laptop-1024`, `tablet-768`, `mobile-390`, `setup`,
`effect-summary`, `balance`, `overlap`, `weights`, `methodology`,
`refused-configuration`, `stale-result` (all in `docs/screenshots/s9b/`).

Findings: five distinct, spacious analytical views; copper accents and the
established design language preserved; nine-stage header fits from 1024 up with
badges hidden ≤1040 px and the active stage visible at 390 px; figure scrolls
inside its card on phones with visible scroll affordance; no page-level overflow,
no clipped labels, no collapsed charts observed at any of the four widths.
No defect required repair.

## Repairs made in this audit

None. No functional, numerical-mapping, accessibility or visual defect survived
verification, so no code was changed and no existing assertion was touched.

## What S9B deliberately does not do (unchanged limitations)

- No subgroup/CATE, sensitivity, or counterfactual analysis (S9C scope).
- Runs are bounded in-memory (≈1 h TTL); no persistent history.
- Chromium-only Playwright; no real-world causal dataset (the demo's truth is
  known by construction).
- No S7 dossier integration (needs a versioned report-schema decision; figure and
  run exports cover the need in the interim).
