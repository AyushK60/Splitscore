# S6 baseline — repository state before S6 work

**Recorded:** 2026-11-03, before any S6 modification.

## Which repository is authoritative

The S6 instruction names `E:\Splitscore V2` as the working repository. That is
the tree this stage modifies.

**Important:** the editor workspace open during this session is `E:\Splitscore`,
which is a **stale pre-S3 copy** of the project:

| Tree | Branch | HEAD | Content |
|---|---|---|---|
| `E:\Splitscore V2` | `v2-premium-visual-foundation` | `660ea7c` | S0–S5 complete; the S5 checkpoint described in the prompt |
| `E:\Splitscore` (open workspace) | `v2-premium-visual-foundation` | `8c4b540` | landing-page redesign only, with S3 work uncommitted; **no explorer, no S4/S5** |

`E:\Splitscore` was not modified. All S6 changes, tests, screenshots and
commits below belong to `E:\Splitscore V2`. A future agent must open that
folder, not the stale copy.

## Git state at baseline

```
branch : v2-premium-visual-foundation
HEAD   : 660ea7ce931dd501ac70fcd2d7788f710e0183b4   (S5-D: verification, numerical validation and handoff)
stashes: none
tags   : none
```

Working tree was clean apart from pre-existing untracked files, which were
preserved and are **not** part of S6:

```
?? docs/screenshots/s3/_preview/
?? docs/screenshots/s5/_preview/
?? import requests.txt
?? scripts/_patch_s3_hero.py
```

No stash was applied or dropped; no existing file was deleted or rewritten
wholesale.

## Baseline verification (executed, not quoted)

| Check | Command | Result |
|---|---|---|
| Backend tests | `.venv/Scripts/python.exe -m pytest -q` in `backend/` | **340 passed**, 1 pre-existing Starlette/httpx deprecation warning |
| Synthetic oracle | `.venv/Scripts/python.exe scripts/evaluate_synthetic.py` | **41/41 cases, 61/61 checks, exit 0** |
| Frontend unit tests | `npm run test` in `frontend/` | **82 passed** (8 files) |
| Typecheck | `npm run typecheck` | clean |
| Lint | `npm run lint` (`--max-warnings 0`) | clean |
| Production build | `npm run build` | clean |
| Playwright | `SPLITSCOPE_E2E_PORT=8180 npx playwright test` | **11 passed** |

`scripts/generate_datasets.py --check` and `scripts/demo_journey.py` were not
re-run at baseline; no dataset or audit code was touched by S6-A.

## Runtime

| Component | Version |
|---|---|
| Python | 3.11.9 |
| pandas | 3.0.6 |
| numpy | 2.4.6 |
| scikit-learn | 1.9.1 |
| scipy | 1.17.1 |
| statsmodels | **not installed at baseline**; 0.15.0 installed for S6-B and pinned in `backend/requirements.txt` |
| Node / npm | 24.22.0 / 11.19.1 |
| Playwright | 1.51.0 (Chromium) |

The E2E config defaults to port 8123; an unrelated process on this machine
holds that port, so every run in this stage used `SPLITSCOPE_E2E_PORT=8180`
(the S5 convention). The committed default is unchanged.

## User-reported S5 defects — reproduced before repair

All four were reproduced in a real Chromium browser against the production
build. The Scatter defect was measured numerically.

| Defect | Reproduction | Baseline evidence |
|---|---|---|
| B1 Scatter grows without bound | Explore → Scatter, 360-row `chronology_violation` demo | `document.scrollHeight` **2174 → 2324 → 2474 → 2630 → 2774 → 2930 px** over 2.4 s; SVG grew to **2092 px** tall |
| B2 Header hover contrast | Hover a top-level nav item / the wordmark | Pale `bone` text on the pale `--accent-soft` fill painted by the global `button:hover` rule |
| B3 Misleading stage order | Nav order Start, Data, Study, Explore, Results…; “Run audit” from Data lands on stage 5 | The user reads mandatory stages 3–4 as skipped |
| B4 Parallel coordinates opaque to novices | Explore → Parallel coordinates | No explanation of lines/rails/brushing; no selection count in the plot; brush affordance was a bare `crosshair` |

## Scope boundary for S6

Approved: F09 (statistical/regression workbench), F10 (predictive ML), F11
(model diagnostics), preliminary F15 (subgroups). **S7 causal DAG work is out
of scope** and was not started.

Constraints carried forward from S5 that S6 must not weaken:

1. Declarations stay declarations; the app never infers availability, horizon
   or preprocessing-fit scope from raw data.
2. No universal scorecard number.
3. Similarity is screening, not proof of leakage.
4. One shared selection engine (`ExploreState`) for all charts.
5. The landing page is frozen.
6. No simulated metrics, fake coefficients or hardcoded diagnostic images.
