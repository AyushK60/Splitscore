# S9A handoff

**Status: COMPLETE for the S9A exit gate — independently audited.**
**Branch:** `v2-premium-visual-foundation` · **Starting HEAD:** `0c5bf2d` (S8C) ·
**Implementation commit:** `158c833` · **Audit-repair commit:** the commit
adding `docs/S9A_INDEPENDENT_AUDIT.md` (hash in `git log`).

## Independent audit outcome (2026-11-06)

A separate audit pass (`docs/S9A_INDEPENDENT_AUDIT.md`) re-derived every
estimator formula, built an independent numpy/statsmodels reference harness
(16 tests), and ran an adversarial suite (15 tests). Four defects were
confirmed and repaired, each with a permanent regression test:

* **HIGH** — non-finite covariate values reached scikit-learn and caused a 500;
  now excluded with reason `invalid_covariate_value`.
* **HIGH** — `GroupKFold` with fewer groups than splits caused a 500; now a
  structured per-estimator failure.
* **HIGH** — a single-class cross-fitting propensity fold caused a 500; now a
  structured per-estimator failure (plus a safety net converting residual
  library `ValueError`s from the estimator layer into `failed` results).
* **MEDIUM** — balance SMDs reported null under `median_mode`; now computed on
  the imputed values the models see, with a `diagnostic_imputation` disclosure.

Final verification on the post-audit tree: backend **530 passed**, synthetic
oracle **41/41 / 61 checks**, frontend **145**, typecheck clean, Playwright
**29 passed**, ruff clean on all S9A files (`docs/S9A_FINAL_VERIFICATION.md`).

## What shipped

* **Estimation package** `backend/app/causal/estimation/` —
  `contracts.py` (versioned strict request schema + hard bounds),
  `preparation.py` (explicit cohort, two-value treatment mapping, numeric
  outcome validation, value-based covariate typing per the Model Lab
  convention, full row accounting),
  `estimators.py` (g-computation RA, Hájek IPW, cross-fitted AIPW on
  leakage-safe sklearn pipelines),
  `uncertainty.py` (influence-function intervals; fully refitting seeded
  bootstrap with honest unavailable states),
  `diagnostics.py` (pre/post-weighting SMDs incl. category levels, propensity
  summaries, extremes, Kish ESS, structured warnings),
  `service.py` (mandatory S8C identification gate, orchestration, shared-cohort
  comparison, fingerprint staleness).
* **API** `backend/app/api/routes_causal_estimation.py` — five routes
  (`estimation/validate`, `estimation/run`, `estimation/compare`,
  `GET estimation-runs`, `GET estimation-runs/{id}`) registered in `main.py`;
  runs stored in the existing bounded store (`RunKind` extended with
  `"estimation"`); every S8A lifecycle rule inherited (410 expiry, 404
  cross-dataset, single error envelope, 409 fingerprint conflict).
* **45 new backend tests** — 34 engine (known-effect DGPs, gate refusals,
  missing-data accounting, leakage detection, honest failure states,
  reproducibility, independent statsmodels/formula cross-checks) + 11 API
  (real upload path, ownership, expiry, staleness, strict schema).
* **Six documentation files** (this set) and the STATUS.md milestone entry.

## Verification (all re-run this session)

Backend **499 passed** · synthetic oracle **41/41 / 61/61** · frontend unit
**145 passed** · typecheck clean · Playwright **29 passed** · ruff clean on all
new/changed files. Details: `docs/S9A_VERIFICATION.md`.

## Not done (by design)

* **No frontend UI for estimation.** S9B owns the visual Effect Estimation
  Studio; S9A adds no components and no fake buttons. The API payloads are
  the stable contract for it.
* **No ATT/CATE/mediation/IV/front-door.** The only estimand is `ate` via a
  verified classical backdoor set. A backdoor failure is never presented as
  general non-identifiability.
* **No cluster-robust inference.** Intervals assume independent observations
  and say so in every payload; grouped cross-fitting is supported, cluster SEs
  are not (a candidate S9C item).
* **No automatic adjustment-set selection.** The client names the set; the
  server verifies it. A "suggest a verified set" convenience belongs to S9B
  and can reuse the S8C search payload.
* **No sensitivity analysis / subgroup effects** — S9C territory.

## Known limitations

* Nuisance models are deliberately simple, named, and versioned (L2 logistic /
  OLS via sklearn). No hyperparameter search, no Super Learner, no
  custom/user-supplied models (by design — no user code reaches the backend).
* The IPW influence-function SE treats the propensity as fixed (documented,
  typically conservative); the refitting bootstrap is the alternative.
* Binary outcomes are supported as recorded probability differences; there is
  no logit-link ATE on the odds scale.
* Bootstrap of cross-fitted AIPW refits the whole fold pipeline per replicate
  (bounded at 2000 reps, 10k rows) — correct but not fast; the payload
  records reps succeeded/failed.
* Missing-data support is complete-case or fold-fitted median/mode imputation.
  Nothing fancier is claimed, and imputation never removes missing-data bias.

## S9B readiness

**GO.** Everything the workbench needs is structured, stable, and now
independently audited. Verified endpoints and response structures S9B can
rely on (full shapes in `docs/S9A_API_CONTRACT.md`):

* `POST /api/datasets/{id}/causal-graphs/{gid}/estimation/validate` →
  `{readiness, gate, cohort_preview, limits}` (estimates and stores nothing).
* `POST …/estimation/run` → one result entry: `{status: "estimated"|"failed",
  estimator, estimate, units, treated_mean, control_mean, sample_size,
  uncertainty: {status, method, standard_error, ci_lower, ci_upper,
  bootstrap, assumptions}, diagnostics: {balance: {covariates[...],
  diagnostic_imputation?}, overlap: {...}}, warnings}` + `run_id`.
* `POST …/estimation/compare` → three result entries + `comparison`
  (`estimates`, `max_pairwise_difference`, `interpretation`,
  `shared_analysis`).
* `GET /api/datasets/{id}/estimation-runs` and
  `GET …/estimation-runs/{run_id}` → stored runs with `stale` /
  `staleness_reason` (layout drags never stale; structural edits always do).
* Error surface S9B must branch on: 409 `infeasible_operation` (fingerprint
  mismatch), 410 `expired_or_evicted`, 422 `validation_error` (gate/schema,
  with `details.verification.violations` or `details.unmatched_values_with_counts`),
  404 `not_found`, 413 `limit_exceeded`.

## S9C readiness

**Ready to extend.** Subgroup effects can reuse `run_estimation` with a cohort
filter (per-group rows are already identified by stable row ids); sensitivity
analysis (e.g., omitted-variable bounds) should be a new estimator-adjacent
module that consumes the same gate. The reproducibility block already carries
everything needed to re-run a stored analysis deterministically.
