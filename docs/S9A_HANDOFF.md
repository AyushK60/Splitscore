# S9A handoff

**Status: COMPLETE for the S9A exit gate.**
**Branch:** `v2-premium-visual-foundation` · **Starting HEAD:** `0c5bf2d` (S8C) ·
**Implementation commit:** the single commit adding the S9A files (hash in
`git log` and the final response).

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

**Ready.** Everything the workbench needs is already structured and stable:
per-estimator results with `status`/`failure`, `units`, uncertainty blocks
(including unavailable states), balance rows (`column`, `level`,
`smd_unweighted`, `smd_weighted`), overlap blocks (propensity quantiles,
extremes, ESS, warnings), row accounting, comparison block, and
`stale`/`staleness_reason` on stored runs. The frontend only needs typed API
contracts; the payloads contain no pre-rendered graphs.

## S9C readiness

**Ready to extend.** Subgroup effects can reuse `run_estimation` with a cohort
filter (per-group rows are already identified by stable row ids); sensitivity
analysis (e.g., omitted-variable bounds) should be a new estimator-adjacent
module that consumes the same gate. The reproducibility block already carries
everything needed to re-run a stored analysis deterministically.
