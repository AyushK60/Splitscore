# SplitScope V2 — Research Integrity & Causal Intelligence Studio
## Master Product, Research, UX and Engineering Blueprint

**Status:** APPROVED FEATURE SCOPE / DESIGN SPECIFICATION — NOT AN IMPLEMENTATION CLAIM  
**Revision:** 1.0 | **Prepared:** 2026-11-02  
**Repository:** Existing `Splitscore/` source, to be developed in place after a Git checkpoint.  
**Purpose:** Authoritative handoff for development agents, independent reviewers, and future academic demonstrations.  
**Reference image:** `docs/references/causality_workbench_reference.png` (user-supplied visual inspiration; not code or a promise to replicate its exact analysis).  
**Read this before coding:** All features in this document are accepted as target product scope. They are **not** all in the first milestone. Every feature must move through IMPLEMENTED → VERIFIED before it can be advertised as working.

---

# 1. Executive product definition

**Working name:** SplitScope V2. Product descriptor: **Research Integrity & Causal Intelligence Studio.** Retain the existing SplitScope brand unless the owner later approves a rename.

**Core promise:** A local-first, reproducible, visually ambitious research workbench for understanding whether data are fit for predictive evaluation; exploring multivariate structure; building and diagnosing supervised models; specifying causal assumptions; estimating conditional causal effects when identifiable; and exporting transparent, publication-supporting results.

**Product formulation:**

> Upload a dataset → define study purpose and variable roles → audit leakage / split validity → visually explore the data → build and compare valid predictive models → draw an explicit causal DAG → identify and estimate effects under stated assumptions → scrutinize subgroups, balance, robustness and counterfactual scenarios → export a reproducible research dossier.

**Distinctive combination:** Data leakage / reproducibility + scientifically annotated interactive analytics + causal inference + explanatory ML + research methodology, all backed by real computation and a distinctive product-grade interface.

**Primary audiences:** CS / AI postgraduate applicant demonstrating engineering depth; applied ML researcher; graduate research team; instructor; student building defensible observational or prediction analyses.

**North-star demonstration:** A visitor loads a synthetic study dataset, sees a visually rich multivariate canvas, detects an actual evaluation defect with traceable row evidence, corrects the split and watches metrics change; then builds a defensible DAG, checks identification and overlap, estimates an effect with diagnostics, challenges the result using sensitivity analysis, and exports a research dossier with source-traceable numbers.

## 1.1 Non-negotiable principles

1. **No fake analysis.** Every number, line, coefficient, heatmap or DAG label shown as an actual result must come from a traceable computation. Animated decoration is visually distinct from analysis.
2. **Do not break SplitScope V1.** Preserve the five audit rules, their definitions and evidence, generated/existing split workflows, comparison, demos, reporting, privacy controls and old verification suite.
3. **Prediction is not causality.** Correlation/feature importance/SHAP-like attribution is not a causal edge; a fitted causal estimator is not proof of an effect.
4. **No universal quality score.** Per-category leakage risk cards with counts/severity/evaluated coverage are allowed; an invented 0–100 “safe dataset” rating is not.
5. **Scientific uncertainty is visible.** Explicit assumptions, unidentifiable effects, sample limits, excluded records, confidence intervals where valid and a 'not evaluated' state.
6. **Local-first.** Core app runs without cloud API keys. Uploaded raw datasets remain local; no network telemetry by default. Export is an explicit action.
7. **Progressive power.** Guided modes for beginners and a deep technical workspace for advanced users; both operate on the same verified analysis objects.
8. **Visual excellence is a release condition.** The home page *and* the inside workbench should feel like the same high-end product, not a stylish landing page glued to basic forms.
9. **Accessible / fast / resilient.** Keyboard usage, contrast, reduced-motion support, desktop and smaller screens, error states, large-DAG and large-chart performance.
10. **Reproducible by construction.** Each run records dataset fingerprint, algorithm/version, assumptions, parameters, seed, transforms, study design and warnings.

## 1.2 Explicit exclusions

- Not an automatic research-paper writer, peer-review substitute or guarantee of publication.
- Not a fully automated causal-discovery system that claims to infer true causes from a correlation matrix.
- Not a model registry, multi-user SaaS, production experiment platform or authorization service in V2.
- Not a platform that executes arbitrary user Python/pickles/notebooks by default.
- Not a guarantee of zero leakage or unbiased estimates.
- Not an invitation to use private survey data without appropriate rights, consent and disclosure controls.

---

# 2. Grounded V1 inventory and migration boundary

The supplied `Splitscore.zip` contains a real application under `Splitscore/backend` and `Splitscore/frontend`. Much of the ZIP's bulk is `.venv`, `node_modules`, app backups and other generated/vendor assets; they must **not** be treated as the editable product source. The extracted code was inspected for this blueprint; previously reported tests were not independently rerun in this task.

## 2.1 Existing source map

| Current source | Responsibility | V2 disposition |
| --- | --- | --- |
| `backend/app/audit/rules/{exact_duplicates,entity_overlap,chronology,target_copy,near_duplicates}.py` | Five evidence-based leakage checks | **Preserve** behavior; add new detectors separately with new IDs and independent tests. |
| `backend/app/audit/{engine,catalogue,types,diagnostics,roles,dataset,io}.py` | Audit execution, documented capabilities, diagnostic separation, role validation, CSV parsing | Keep stable; introduce adapters/new read models rather than risky global rewrites. |
| `backend/app/splits/{strategies,comparison}.py` | Existing/random/stratified/group/chronological holdouts and comparison | Reuse; extend for evaluation plans, CV and horizon-aware strategies in a separate module. |
| `backend/app/core/{store,config}.py` | Bounded ephemeral datasets/runs; TTL and size limits | Preserve defaults; add versioned study/run metadata and opt-in persistence only after a privacy review. |
| `backend/app/api/{routes_datasets,routes_audit,routes_reports,schemas}.py` | Current HTTP API | Keep backward compatible; add versioned `research`, `viz`, `model`, `causal`, `studies` route groups. |
| `backend/app/reports/{json_report,html_report,csv_export}.py` | Existing report/export | Keep V1 reports intact; add a distinct V2 research dossier composer. |
| `backend/app/evaluation/*`, `backend/tests/*`, `scripts/evaluate_synthetic.py` | Synthetic evaluation and regression tests | Maintain and extend with oracle-based scientific benchmarks. |
| `frontend/src/state/AppState.tsx`, `frontend/src/lib/router.ts` | Global state and hash-based navigation | Incremental state migration to typed domain stores; preserve old deep links and behavior. |
| `frontend/src/views/{Overview,Dataset,Audit,Evidence,Comparison,Export}View.tsx` | Existing workflows | Rehost in consistent V2 shell; avoid deleting tested screens prematurely. |
| `frontend/src/components/charts.tsx` | Accessible CSS-based paired bars | Keep for simple reports; build separate interactive visualization subsystem. |
| `frontend/src/styles/app.css` | Existing minimal design system | Replace progressively with tokens/components; protect established accessibility behavior. |
| `frontend/e2e/*`, `frontend/tests/*` | Browser and component regression coverage | Extend journeys; maintain all existing paths. |
| `datasets/` | Six deliberately synthetic cases | Retain; create separate V2 research-demo dataset catalog. |

**Current confirmed source capabilities:** CSV ingestion; five named audit rules; existing/generated split selection; basic class/distribution diagnostics; row-level evidence; HTML/JSON/assignment exports; basic accessible charts; synthetic datasets; backend/frontend/E2E test infrastructure.

**Reported in existing documentation (not independently verified here):** 218 backend tests; 70 frontend tests; four browser journeys; synthetic 41-case/61-check evaluation. Maintain and independently revalidate these as *baseline*, rather than quoting them as current test results after modifications.

**Current documented defaults:** max upload 25 MiB, parsed data 256 MiB, 10k rows/100 columns, total store 384 MiB, near-duplicate analysis upper bound 500 combined rows, 8 datasets/16 runs, TTL 1 hour. Hard limits must be enforced by the server and advertised in UI. New computational workloads require additional bounded caps.

**Current missing capabilities:** trained supervised model execution, guarded preprocessing pipelines, statsmodels regression and diagnostic suite, general interactive multivariate plotting, DAG authoring/identification, causal estimators, explicit assumptions, subgroup inference, durable experiment history and publication export.

## 2.2 Integration rule

**Never turn an existing finding into a model evaluation conclusion.** The original auditor asks only whether specific conditions occur across a selected split. V2 produces distinct, typed result categories: `AUDIT_FINDING`, `DATA_DIAGNOSTIC`, `PREDICTIVE_METRIC`, `DESCRIPTIVE_STATISTIC`, `CAUSAL_IDENTIFICATION`, `CAUSAL_ESTIMATE`, `ASSUMPTION_WARNING`, `SENSITIVITY_RESULT`. The interface must show which category a number belongs to.

---

# 3. Audience journeys and information architecture

## 3.1 Three deliberately designed experiences

- **Guided Journey:** “Show me what is wrong with my dataset.” Low-friction demo: upload → explain roles → audit → visualized defect → safe split comparison → report.
- **Research Journey:** “I am designing a study.” Study Card → variable map → EDA → DAG → identification → estimand → estimator → diagnostics → sensitivity → dossier.
- **ML Engineering Journey:** “Are my model results trustworthy?” Feature availability → pipeline/splits → leakage audit → train/validation/test → baselines → metrics → error analysis → model card.

Users can switch workflows without losing dataset identity, and the UI never forces a DAG for a purely predictive task.

## 3.2 Proposed top navigation

1. **Home** — cinematic, interactive landing and curated demos.
2. **Workspace** — contextual overview, study card and dataset registry.
3. **Data & Integrity** — schema, role mapping, data quality, original leakage audit, split scenarios, preprocessing risk.
4. **Visual Explorer** — interactive research visualizations and linked brushing.
5. **Model Lab** — predictive ML, descriptive and inferential regression, model diagnostics.
6. **Causal Lab** — DAG editor, identification, estimation, overlap, heterogeneity and sensitivity.
7. **Experiments** — reproducibility/assumption registry, comparisons, local history.
8. **Reports** — research dossier, export-ready figures, machine-readable manifests.

Use contextual sub-navigation within the eight surfaces, rather than 25 flat top-level tabs. Build a stable workspace URL scheme preserving legacy `#/overview`, `#/dataset`, etc. Either incrementally extend the existing hash router or introduce a verified router adapter with redirects and E2E checks.

## 3.3 Crucial state relationships

- A `Study` holds metadata and optional local dataset reference.
- Dataset identity consists of canonical file fingerprint + shape + derived schema fingerprint, not just a display filename.
- `SplitPlan` is immutable per run and records the exact row IDs assigned.
- `AnalysisRun` records kind, inputs, normalized configuration, software versions and output hashes.
- `CausalGraph` is versioned separately from a dataset; it is a **research assumption artifact**, not a learned truth.
- `Estimand` derives from graph version, exposure, outcome and declared assumptions.
- `ModelFit` and `EffectEstimate` reference their exact data/split and formula/estimator configuration.
- `FigureSpec` references immutable analyzed data/run and visualization settings; exported graphs never substitute synthetic decorations.
- No silently stale analysis: changing variables, split, graph or selected population invalidates the dependent results and flags a rerun.

---

# 4. Visual identity, landing page and workspace design — mandatory

## 4.1 Reference-image translation

The supplied scientific dashboard has six labeled regions; they become **functional UX requirements**:

| Figure region | User's reference | V2 implementation requirement |
| --- | --- | --- |
| **(a)** | Basic controls and variables | Persistent variable/role/control inspector with dataset and current method controls; preserve selections. |
| **(b)** | Colored directed causality graph | Large, zoomable, editable **DAG workbench** with arrowheads, variable tags, node/edge inspectors and honest causal assumptions. |
| **(c)** | Parallel-coordinate display | Full-width or docked **parallel-coordinates canvas**, brushing, axis reorder/filter and row/selection highlighting. |
| **(d)** | Regression analysis | Interactive coefficient/model table with standard errors, fit stats, diagnostics and exact inference/method notes. |
| **(e)** | Subdivision controls | Cohorts/subgroup selectors, interaction terms, strata bins, sample-size notices and paired comparisons. |
| **(f)** | Colorful model-diagnostics heatmap | Real residual/coefficient/pairwise diagnostics matrix, with clear legend and meaning of each cell. |

**Do not copy the old screenshot's look verbatim.** Retain its analytical density and synchronized graph layout while rebuilding it with modern typography, whitespace, visual hierarchy, clarity, useful motion and accessible labels. Every panel must work and cross-filter consistently.

## 4.2 High-end aesthetic direction

**Art direction:** “Scientific Observatory × Precision Engineering × Editorial Research.” Premium research-software identity; not a generic SaaS template, generic purple gradient, stock dashboard or empty glass-card collage.

**Palette candidates (to refine in UI approval):** midnight/navy ink `#07111E`, blue-slate `#102539`, ivory canvas `#F4F7F8`, soft steel `#8AA1B1`, electric cyan `#49C6DC`, analysis teal `#20BFA5`, warning coral `#E76A58`, gold `#E9BC68`. Provide high-contrast light and dark workbench modes. Never encode train/test or risk level by color alone.

**Type:** modern restrained sans serif for UI/headlines, a readable monospaced face for numeric/method labels, tabular numerals for statistics. Load fonts efficiently and honor system fallback. Do not embed unlicensed type assets.

**Design signatures:** extremely sharp typography; thin technical grid/microgrid motifs; intentional annotated line-work; subtle layered transparency; restrained glow on selected graph elements; smooth focus/hover; high-density scientific panels that are still breathable.

## 4.3 Landing page exact visual brief (this is the first major visual milestone)

**First viewport on desktop (target ~1440×900):**

- Full-bleed polished hero with navigation and distinctive brand mark, not just centered copy.
- Left: concise headline **“From data leakage to causal insight.”** Supporting statement that mentions validation, visual exploration, modeling and reproducibility with no inflated guarantees.
- Primary CTA: **Launch Workbench**. Secondary: **Explore Interactive Demo**. A third understated link: **How it works / Research methodology**.
- Right/center: compelling **living scientific scene**: animated but intelligible network of variable nodes; an evolving DAG; synchronized train/test data ribbons; selected duplicate cases visibly linking train↔test; dynamically highlighted propagation through a mini parallel-coordinates plot. This is a visual *preview* grounded in labeled **synthetic demo data**, not a false live computation.
- Motion choreography: initial low-motion camera reveal; thin edges build in; node labels sharpen; selected train/test contamination glows and is detected; transition into a graph of hypotheses. Smooth, elegant, not chaotic particles.
- The hero can include a real runnable mini-interaction: choose `Leakage / Causality / Model Diagnostics`; the relevant scene changes instantly. Direct mouse/touch/keyboard interactions must work; add noninteractive fallback for reduced motion.
- A “research credibility strip” below hero with **real implemented capability labels** only. Do not advertise planned estimators as functional until verified.

**Second screen:** three distinct technical narratives with diagrams and “Open synthetic walkthrough”: `Detect contamination`, `Understand structure`, `Interrogate causal assumptions`. Each opens the relevant working path.

**Third screen:** scroll-driven but nonblocking product story with actual screenshots or real rendered sample panels and three concise methodological steps. No fabricated performance improvements, user counts, logos, paper citations or client claims.

**Fourth screen:** benchmark/evidence section using demo-ground-truth pairs and a real test summary once independently verified; explain exactly what the tests cover.

**Final CTA:** small visually strong interactive curve motif, explicit local-first guarantee qualified by runtime behavior; “Start with a demo” and “Upload dataset”.

**Performance/accessibility guardrails:** meaningful content visible immediately without JavaScript heavy animation; hero scene loaded lazily; `prefers-reduced-motion` supported; pause animation when offscreen; keyboard and touch equivalents; no infinite forced parallax; avoid aggressive scroll hijacking. Measure animation frame rate on reference laptop and low-end throttled desktop; cap memory and bundle size; require Core Web Vitals budget where measurable.

## 4.4 Inside-the-app identity (equally mandatory)

Do not revert to plain white stacked forms after the attractive landing page.

**Desktop workbench arrangement:**

```text
┌─ Product masthead: SplitScope  / Study name / Current dataset / Run status / Export ──────────┐
│ Rail: Workspace | Integrity | Explore | Model Lab | Causal Lab | Experiments | Reports           │
├───────────────┬──────────────────────────────────────────────────────┬─────────────────────────┤
│ LEFT          │ MAIN CANVAS                                          │ RIGHT INSPECTOR         │
│ variable map  │ DAG / linked visualizations / model diagnostics     │ selected variable/edge  │
│ study filters │ zoom • pan • layout • compare • annotate            │ statistics/assumptions  │
│ experiment    │ full-screen toggle • panels • snapshots             │ warnings/analysis steps │
├───────────────┴──────────────────────────────────────────────────────┴─────────────────────────┤
│ BOTTOM DOCK: Parallel coordinates | residuals | subgroup plot | row evidence | method log       │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Resizable panels, preset layouts (`Overview`, `Graph focus`, `Multivariate`, `Review evidence`, `Report capture`), independent full-screen for essential plots.
- Persistent workspace side rail, a visually considered inspector, compact utility toolbar, semantic legends and run-source badges.
- Dataset/sample size and filter chips visible whenever the view is filtered; zero silent changes to denominators.
- Smooth coordinated interactions: brush in parallel coordinates → highlight same row/entity in scatter, subgroup tables and leakage examples; click causal edge → show edge assumption; select subgroup → recalculate only explicitly compatible diagnostics, otherwise warn.
- Tooltip may show counts and explanations but essential information must be accessible without hover. Drill down to exact row IDs with privacy-safe display options.
- Desktop ≥1280 px uses full docking. Narrow laptop collapses inspectors. Tablet uses one dominant graph and drawers. Phone can inspect results and select variables, with dedicated simplified graph view; don't promise desktop-level editor density on a 390px screen.
- Both dark and light variants need cohesive charts, labels, error dialogs, loading states, empty views and downloadable figures. Prefer a lighter print/report theme regardless of live UI theme.

## 4.5 Visualization interaction contract

Each visualization supports, where meaningful: hover details, click-to-inspect, selection and brushing, keyboard focus, legends, axis labels and units, color-blind-safe categories, search, reset-to-overview, undo of filters, deterministic figure export, and a display of sample/filter/transform definitions. Display “sampled N of M” and sampling seed when rendering large datasets.

**Forbidden visual anti-patterns:** fake axis values, out-of-date plots after filter changes, gradients that hide contradictory numbers, inaccessible color-only codes, impressive but non-functional graph controls, charts computed only from frontend mock arrays while called “real”, graphs marked “causal” merely from correlations.

---

# 5. Complete functional feature catalog — all accepted features

Each feature below is a committed target for the V2 program. `Core V2` indicates the foundation, `Later V2` indicates higher-cost research sophistication; neither means omitted.

## F01 — Study Card & data provenance (Core V2)

A researcher-supplied metadata object with study title, objective/research question, domain, unit of analysis, population/sampling method, collection period, dataset owner / rights note, consent/use permissions field, target task, outcome definition, predictor availability time, dataset version/hash, missingness conventions, design type (cross-sectional/longitudinal/experimental/observational), measurement scale/coding, data dictionary and exclusion rules. Optional anonymity/privacy flags. Completeness checklist; clearly distinguish missing, user asserted, and computed values. Export as a machine-readable Study Card.

**Acceptance:** Load sample; edit variables; refresh without losing in-memory changes during session; export/import; preserve declared-vs-inferred provenance; no auto-completion of uncertain methodology.

## F02 — Advanced dataset ingestion, profiling and role mapping (Core V2)

Preserve CSV, optionally add TSV and `.xlsx` with sandboxed size-limited readers; SPSS `.sav` is optional only after dependency/legal/privacy review and verified metadata preservation. Detect data types, missingness, cardinality, duplicates, range anomalies, outliers as *candidates*, time schema, missing-value tokens, declared encoding/units, column roles. Explicit roles: entity/group, timestamp, split, target/outcome, treatment/exposure, confounder, mediator, effect modifier, predictor, instrument, protected/sensitive attribute (user-assigned only), future-only and exclude. Show incompatible role conflicts and field-level warnings. Preserve raw uploaded file unchanged.

**Acceptance:** Parse real and maliciously malformed examples; no silent truncation; clear reason on rejection; stable row IDs; consistent mapping across all modules.

## F03 — Original five leakage checks preserved (Core V2)

Exact cross-split feature duplicates, entity overlap, out-of-order chronology, target-copy feature detection and opt-in numeric near-duplicate candidates. Keep severity definitions, denominators, exact row evidence, opt-in bounds and skip reasons. The original audit logic remains a stable independent subsystem.

**Acceptance:** V1 golden tests and rule IDs pass without changed meaning; baseline regression suite remains green; every result links to reproducible evidence.

## F04 — Expanded leakage assurance (Core V2 → Later V2)

Add individually documented checks, not a generic AI “leakage detector”:

- **Feature availability ledger:** user enters whether values would be known at prediction/decision time; highlight future features, derived features and impossible availability.
- **Preprocessing-fit boundary audit:** when pipeline is configured within V2, prove scaler/imputer/feature selector/encoder is fit only on training folds; record fit scope and correct CV nesting. **Do not claim to detect this from raw CSV alone.**
- **Target proxy candidates:** encoded copies, suspicious near-perfect identifiers/associations and strongly predictive surrogate candidates. Classify as *review candidates*, never proof of leakage.
- **Label-derived aggregates and lookahead tests:** where declared lineage/timestamps exist; e.g., post-outcome events, future rolling aggregations and group encodings; don't flag without necessary metadata.
- **Validation/test reuse risk:** track whether test set was used for model selection or tuning in the platform.
- **High-cardinality entity memorization diagnostics:** quantitative candidates with train/test overlap context.
- **Temporal horizon checks:** gap/purge and look-ahead windows for time-aware evaluation, with user-declared horizon.

**Acceptance:** At least one synthetic positive, negative and ambiguous fixture per new check; known limitations and exact triggered provenance recorded.

## F05 — Split Comparison & evaluation-plan designer (Core V2)

Existing, random, stratified, group and chronological splits; extend to repeated stratified CV, group CV, time series rolling-origin/expanding-window and appropriate gap/purged time split for declared temporal tasks. Preserve exact assignment downloads and comparable row counts. Show risk consequences plus performance distribution when model is actually trained. Explain why random holdout may violate independence and why shift alone is not leakage. No universal “best split”.

**Acceptance:** Every strategy deterministic for seed; assignments exhaustive, disjoint and plausible; no training fold preprocess fitted on test fold.

## F06 — Leakage risk scorecard **by category**, not one score (Core V2)

Visually rich set of grouped metrics: `Duplicate/Similarity`, `Entity`, `Time`, `Target`, `Pipeline`, `Validation Reuse`. Each card shows severity, count, affected units/denominator, checks run/skipped, evidence clickthrough, optional trend across alternative splits. Risk state must include `NOT CHECKED` and `NOT APPLICABLE`. Never average categories into “96/100 Safe”.

**Acceptance:** Risk cards derived solely from typed audited outcomes and correct denominators; disagreement/skip behavior tested.

## F07 — Train/test similarity explorer (Core V2)

A visually distinctive cross-split relation explorer: side-by-side train/test clouds, similarity matrix (bounded/sampled), nearest-neighbor candidate arcs, density/overlap views, pair inspector with exact row IDs and differing feature values. Allow filtering by entity, distance threshold, label, split, feature subset; explain metric (Chebyshev, cosine or Gower-like for mixed type where implemented) and normalization; show if only numeric fields assessed. Confidence not falsely implied by “similarity score”. Map selection back to findings, parallel coordinates and provenance; disclose sampling.

**Acceptance:** On synthetic known-pair fixture highlight exact expected matches; no cross-split similarity labeled proven leakage; robust nonnumeric/missing-type handling.

## F08 — Exploratory Analytics / multivariate visualization suite (Core V2)

**Mandatory**: interactive parallel coordinates with reorderable numeric axes and brushing, correlation matrix/heatmap (Pearson and Spearman with missingness/pair count), multi-panel scatter matrix, faceted distributions, box/violin distributions as appropriate, target-class and numerical histograms, missingness matrix/heatmap, high-dimensional embedding only as a labeled projection (optional), train/test overlays, feature distribution shift, entity/time distribution plots and row data inspector.

Cross filtering: selection state belongs to a common filter engine keyed to immutable row IDs. Panels display active row count and why excluded. Distinguish rendered downsample from calculation sample. Default render cap per chart with reproducible sampling method and indicator.

**Acceptance:** Cross-selection of an identified row/entity reflected across 3 distinct plots and evidence panel; chart JSON/SVG/PNG exports; accurate labels and legends.

## F09 — Statistical/Regression workbench (Core V2)

Descriptive summaries and valid ordinary least squares / logistic regression through an established statistics library. Explicit intercept handling, feature encoding and missing-data policy, formula builder, target coding and reference groups. Show coefficients, confidence intervals, standard errors, statistic, p-value (where defined), appropriate R²/adjusted R², log likelihood/AIC/BIC, model size and population, coding and provenance, rank-deficiency warnings. Optional robust or cluster-robust SE when justified and implemented. Hypothesis tests, correlation analysis with multiple-testing context, bootstrap CIs for selected supported quantities.

**Acceptance:** Numerical outputs match independent statsmodels/R reference values on fixed small datasets within defined tolerances; inappropriate measures absent (e.g., R² not presented as a classification accuracy).

## F10 — Predictive ML Model Lab (Core V2)

A necessary addition to make this a substantive **ML** project rather than only statistical research visualization. Task selection: classification vs regression. Basic validated models: baseline/dummy, linear/logistic, regularized linear, tree or random forest. Optional gradient boosting after safeguards. All preprocessing through scikit-learn Pipeline/ColumnTransformer fitted only to train folds. Train/validation/test policy; stratified/group/time evaluation matched to study. Classification: confusion matrix, per-class precision/recall/F1, ROC-AUC/PR-AUC only when mathematically applicable, calibration/reliability, error cohorts. Regression: MAE/RMSE/R² with residual diagnostics. Cross-validation intervals or fold distributions; class-imbalance and small-sample warnings. Hyperparameter tuning on validation/training only, sealed test until final evaluation. Compare metrics before and after repairing a leakage-prone split using matched configurations, without sensationalizing results.

**Acceptance:** End-to-end real model training; independently reproduce metrics; test for intentional preprocessing leak; never train on held-out test rows or choose hyperparameters using them.

## F11 — Model diagnostics & interpretation (Core V2)

Residual-vs-fitted and Q–Q (for appropriate linear models), leverage/Cook’s distance, multicollinearity/VIF, heteroskedasticity checks, coefficient/interval forest plot, calibration curve, classification confusion matrix, learning curves, error subgroup matrix, model comparison table, correlation/residual heatmap, threshold tuning confined to validation data. Permutation importance only on specified evaluation partitions; optional local explanations later, explicitly **predictive**, not causal.

**Acceptance:** All relevant plots use actual predictions/residuals; expose diagnostics applicability, sample size, model/run ID, warning states; no hardcoded matrix image passed as computed result.

## F12 — Causal DAG editor — visual centerpiece (Core V2)

Zoomable/pannable node-edge canvas with variable search, grouping by role (exposure/outcome/confounder/mediator/collider/possible instrument/effect modifier), observed vs unobserved node appearance, directional signed edges only if user declares sign or it is experimentally grounded. Add/remove/reposition edges; multi-select; drag, undo/redo, keyboard shortcuts, auto-layout/manual layout, minimap, find node, zoom to selection, smart routing, focus path, variable inspector and history. Prevent or clearly flag cycles, impossible references and disconnected exposure/outcome. Graph role depends on the structure/estimand: **do not stamp a variable “confounder” based solely on its name or raw correlation**. Show a legend “hypothesized relationships, not discovered facts”. Export/import versioned JSON and GraphML/DOT where suitable.

**Acceptance:** Edit a DAG, reject a directed cycle with a comprehensible explanation, save/reload, graph view matches saved topology, inspect edges, keyboard navigation, 50+ node performance budget.

## F13 — Causal identification and adjustment engine (Core V2)

Given a **user-specified DAG**, exposure, outcome and assumptions: check causal path; indicate ancestors, backdoor paths and candidate adjustment sets; warn on collider conditioning, post-treatment variables and suspected unobserved confounders; apply d-separation and validated graph algorithms; evaluate whether supported estimand is identified. Use DoWhy or independently verified NetworkX graph logic under a clear contract. Report identification, adjustment choice and reasoning trace. Preserve distinction between identified/unidentified/unsupported, and never silently “proceed despite unidentifiability”.

**Acceptance:** Hand-checked graphs: one simple confounder, collider, mediator, instrument, unobserved confounding and no backdoor paths; compare with reputable reference results.

## F14 — Causal estimation & balance diagnostics (Core V2 → Later V2)

Initial clearly bounded scope: **binary treatment** and numeric or supported binary outcome, observational backdoor setting, explicit ATE / ATT choice. Supported methods grow incrementally: regression adjustment, propensity-score weighting (IPTW with transparent stabilized/truncated weights), matching (with limitations), bootstrap uncertainty, and eventually doubly robust AIPW / DML after validated nuisance-model cross-fitting. Show effect units, CI, estimator formula/implementation, adjustment set, analytic population, exclusions. Balance diagnostics: standardized mean differences before/after adjustment, Love plot, propensity overlap distributions, extreme-weight warnings, effective sample size and positivity/overlap failure. Refuse estimates if unsupported conditions are unmet.

**Acceptance:** Synthetic known-treatment-effect data and negative controls; coverage tests; reference comparisons; warnings on separation, zero overlap, missing outcome and insufficient effective sample size.

## F15 — Subgroup and heterogeneity workbench (Core V2 → Later V2)

Variable-defined groups, bins with explicit thresholds, user-defined cohorts, selected interaction terms, regression subgroup diagnostics, leakage/findings segmented by subgroup, subgroup estimates with CI, SMD/overlap by subgroup, optional CATE using supported DML/CausalForest methods after reliability tests. Small subgroup suppression or high-uncertainty flags, user-specified protected-variable handling, multiple comparison caveat. Selection synced to main graph/plot and model diagnostics.

**Acceptance:** Cohort denominators reconcile to population; no empty/small subgroup presented as a confident discovery; compare synthetic heterogeneous-effect fixture to known generative truth.

## F16 — Counterfactual / what-if scenario studio (Later V2)

Two separate labeled modes:

**A. Predictive scenario:** edit valid observed predictor values and visualize a model’s predicted outcome distribution; explicitly mark “conditional model prediction, not a causal counterfactual”.

**B. Intervention scenario:** when a supported causal estimand is identified and estimate validated, show population-level `do(T=t)` comparison and uncertainties, with inputs, overlap region, assumptions and contrast clearly visible. Never promise the unobservable true individual potential outcome. For synthetic structural causal models with known equations, allow exact simulation explicitly labeled “synthetic ground-truth demonstration”.

**Acceptance:** Missing identification prevents intervention estimate; scenario only permits in-support changes; forecast-vs-intervention mode text unambiguous; charts reflect actual fitted models.

## F17 — Assumption registry & invalid-setup warning engine (Core V2)

Versioned entries: assumption ID, title, scope (`study/split/model/DAG/estimator`), source (`user-entered/library-derived/check result`), status (`asserted/verified-as-testable/violated/unknown/not-testable`), rationale, supporting evidence, risk note, affected outputs, timestamps. Key examples: exchangeability/no unmeasured confounding, consistency, positivity, SUTVA/no interference, temporal precedence, independent units/cluster structure, correct variable measurement, ignorability or no informative missingness where needed, model specification, predictive deployment availability. Automatic validation catches cycles, post-treatment adjustment, impossible treatment coding, insufficient sample, single class, lack of overlap, repeated-subject independence failures. Many causal assumptions remain **untestable from observed data** and must be represented as such.

**Acceptance:** Every causal estimate links to assumption IDs and displays unresolved assumptions; new violation invalidates dependent model state.

## F18 — Sensitivity, falsification & robustness suite (Later V2)

DoWhy-style refutation checks where suitable: placebo treatment, subset removal, bootstrap, random common cause, simulated unobserved confounding; multi-estimator specification curves, covariate-set sensitivity, leave-one-variable-out with warning, overlap trimming sensitivity, alternative split designs. Optional Rosenbaum-type sensitivity bounds only when method/support is clearly matched; report methodological limits. Reproducible random seeds and repeated trials. Avoid saying “passed refutation = causal truth”.

**Acceptance:** Known fragile estimates respond to the corresponding perturbation; stable synthetic cases behave as expected; uncertainty and trial settings retained.

## F19 — Reproducibility manifest, lineage, snapshots (Core V2)

Each run records: study ID and version; dataset SHA-256 and parsed-schema hash; row-ID scheme; raw data dimensions; inclusion/exclusion counts; feature roles; split strategy and membership/seed; workflow/task; preprocessing graph and fit partition; model formula, estimator and exact hyperparameters; DAG graph version; adjustment variables; environment/Python/JS dependency versions; timestamps; bounded data sample policy; code version/git commit when available; result artifact digests; warnings/not-evaluated checks; created figure IDs. Export a manifest JSON with versioned schema and separate human-readable methods appendix. Re-import must validate matching dataset fingerprint or warn when raw data are unavailable.

**Acceptance:** Two independent runs on pinned environment/seed reproduce relevant deterministic outputs; changes to data/schema/config change manifest identity; no raw secrets embedded in manifest.

## F20 — Local experiment history / notebook-like timeline (Core V2)

Ordered run cards with immutable references, status, duration, dataset/graph versions, parameters, warnings and figures. Comparison view diffing split, selected variables, estimand and estimates; side-by-side plot viewer with consistent axes. Save/export a portable study bundle **opt-in only**. Current V1 memory TTL cannot silently promise persistence: either (a) provide downloadable `.splitscope` JSON bundle with metadata/figures but not raw data, or (b) separately design a secure, explicit on-disk project store after privacy review. Mark ephemeral items accurately.

**Acceptance:** Preserve session history up to documented bounds; exported bundle reimports into new session with missing-data caveats; no unauthorized raw file persistence.

## F21 — Research report & methodology dossier generator (Core V2)

A generated **descriptive, evidence-backed** report, not a fabricated study narrative. Contents: title/research objective, data provenance, study design as user-supplied, variable definitions, missing data, sample flow, split and leakage audit, descriptive EDA, ML method and metrics, DAG graph and theoretical assumptions, estimand/identification, estimates and CI, covariate balance, subgroup/sensitivity analyses, warnings, limitations, reproducibility manifest, figure/table appendix, versioned references/method references. Provide a **Methods Draft** with confirmed statements only and placeholders for claims requiring human verification; a **Results Table** that uses actual stored metrics. Optional report views inspired by STROBE (observational) and TRIPOD+AI (prediction in applicable settings); these are reporting guides, not certificates of valid design.

**Acceptance:** Every table number traces to result ID; unavailable analyses omitted or explicitly `not performed`; no implied consent/IRB approval or causal identification; export HTML + PDF + JSON first, DOCX and reproducible notebook/script later when independently supported.

## F22 — Export-ready scientific figures and tables (Core V2)

PNG/SVG with sensible dimensions/DPI, editable vector axes/text where possible, print-safe backgrounds, caption, axis units, provenance in metadata, manifest reference and stable figure number. Tables as CSV and/or XLSX, TeX table export later. Graphs as DAG JSON, SVG, GraphML. Source data exports must respect privacy controls; aggregate-only mode for sensitive studies. Ensure exports reflect current filters and active population with exact caption, not cached older plots.

**Acceptance:** Figure numbers and values reconcile to report; export reproducible from manifest; no text clipping, unreadable axes or missing legend.

## F23 — Research method navigator & interpretive assistance (Core V2)

Context-aware, deterministic guidance: does your objective require prediction, descriptive association or causal estimation? Which split? Which roles must be supplied? Which estimands are supported? Show a decision tree and methodological explanations with links to official docs. Optional future local LLM wording assistance only as an explicitly separate opt-in; never let it fabricate numbers, silently select variables or make unsupported causal claims.

**Acceptance:** Method gate blocks incompatible tasks; no hallucinated citations; users can inspect assumptions before running.

## F24 — Benchmark and academic validation harness (Core V2)

Independent synthetic ground-truth generators: exact/group/chronology leakage; clean control; preprocessing-induced leakage; confounded treatment; randomized treatment; collider adjustment trap; mediation; weak/no overlap; known ATE/CATE; time-varying future feature; model under/overfitting; sample-size degradation. Compare calculations against trusted references such as statsmodels/scikit-learn/DoWhy and hand-computed fixtures. Track precision, recall only where meaningful and independently labeled cases exist; estimation error and interval coverage on repetitions; deterministic regressions; browser visual truth and performance metrics. Publish limitations and reproducibility commands.

**Acceptance:** Benchmark harness runs without network or private data; oracle code independently written; a falsified expectation cannot be silently modified merely to green the suite.

---

# 6. Scientific and methodological contracts

## 6.1 Predictive learning safeguards

- Separate dataset roles `train`, `validation` and `test`. Test is reserved; training and tuning must not inspect it.
- Every transformation that has learned parameters must fit only on training fold; all performance comparisons maintain paired evaluation design where appropriate.
- Leakage inspection **from data** and leakage prevention **inside configured pipelines** are separate products with separate evidentiary claims.
- An outlier, distribution shift, high correlation, duplicate within test or low accuracy is not automatically leakage.
- No data-dependent hyperparameter selection on sealed test. One final test evaluation must be clearly marked; new experiments require a new declared protocol.
- Model metrics need task, class distribution, dataset size, split plan, baseline, uncertainty where appropriate.

These boundaries follow established scikit-learn leakage-prevention guidance: split before fitting transformations, use pipelines and keep test data out of model selection. See reference R1.

## 6.2 Causal inference safeguards

- A DAG is a transparent theoretical claim; direction cannot be automatically established from correlation.
- Identification and estimation are separate: estimated regression coefficient is not automatically a causal effect.
- Preserve explicit estimand choice (`ATE`, `ATT`, supported conditional quantities), target population and treatment definition.
- Effect estimation is refused or qualified if identification fails, model conditions are unsupported or positivity/overlap is inadequate.
- Pre/post-treatment role matters; avoid indiscriminate adjustment for mediators or colliders.
- Balance may improve yet unmeasured confounding can remain.
- Selection and subgroup filters change target population; recalculate estimand and denominators or flag invalidation.
- Counterfactual individual truth is unobservable in ordinary observational data; show estimand distributions/conditional predictions with support warnings.
- Auto-discovery, if ever added, should only suggest testable *hypotheses* and must log method and epistemic limitations.

The product can use DoWhy's **model → identify → estimate → refute** sequence (R3) and add heterogeneous estimators via EconML only after testing prerequisites (R4).

## 6.3 Statistical inference safeguards

- Do not conflate p-values, effect size, practical significance or validation performance.
- Display alpha/CI choices and sample assumptions; handle singular matrices, separation, zero variance, ill-conditioned models, invalid degrees of freedom and extreme class imbalance.
- Robust standard errors and bootstrap are options with explicit applicability, not replacements for careful design.
- Subgroup p-hacking risk should be disclosed; predeclared vs exploratory subgroups differentiated.
- Missingness handling is explicitly recorded. Complete-case estimates target analyzed population; no silent imputation on whole dataset before split.
- Do not imply a visually colorful “diagnostics matrix” gives an overall model-validity score.

## 6.4 Privacy and research ethics

- Dataset stays in process memory unless user explicitly exports or opts into durable local storage.
- Add PII candidate detection for visibility, not confident sensitive-attribute labeling; allow hide/redact row fields in dashboards/reports.
- No clipboard/export of raw individual records without explicit action; allow aggregate-only dossier.
- Study Card permission status is *user-declared*, not an app endorsement of consent or research clearance.
- Report all unsupported methods, skipped checks and subset exclusions; never suppress warnings for visual polish.

---

# 7. Architecture, contracts and runtime

## 7.1 Keep the known stack, add modular scientific engines

**Backend baseline:** FastAPI + Pydantic + pandas/numpy/scikit-learn (currently pinned in requirements).  
**New research packages (candidates, not automatically compatible):** statsmodels, NetworkX, DoWhy, SciPy; EconML only after a controlled, separately pinned compatibility and numerical-validation stage. Optional pyreadstat for SPSS `.sav`, optional openpyxl for XLSX. Do not install everything on Stage 1.

**Frontend baseline:** React + TypeScript + Vite, existing tests and E2E.  
**Visualization candidates:** `@xyflow/react` for DAG editing, Plotly.js for parallel coordinates, statistical heatmaps/diagnostics and figure data; ECharts as an alternative for select dense charts, not a simultaneous duplicate dependency everywhere. D3 for dedicated overlays only where justified. UI uses custom tokenized components with purposeful animation (CSS / Framer Motion-compatible library if verified); use Canvas/WebGL where large datasets require performance. Choose and measure rather than adding a heavy, mutually redundant stack.

**Do not** take third-party library versions for granted: pin compatible versions, test Python 3.11 and Windows installation plus Node build, verify licenses and lock transitive dependencies.

## 7.2 Proposed file modules (additive initially)

```text
backend/app/
  audit/                     # existing V1 checker, stable
  splits/                    # existing V1 strategies, stable
  core/                      # existing store/config; extend consciously
  research/
    schema.py                # StudyCard, VariableDictionary, RoleMap, provenance
    registry.py              # methods, registry and assumptions
    studies.py               # study metadata, importer/exporter
  quality/
    profiling.py             # stats and column-level quality
    feature_availability.py  # prediction-time availability policies
    pipeline_guard.py        # allowed pipeline operations / fit-scope audit
    advanced_checks.py       # separately enumerated new leakage checks
  explore/
    specs.py                 # typed PlotSpec and filter expression
    aggregates.py            # server-derived bounded series
    sampling.py              # deterministic chart downsampling
  models/
    contracts.py             # Task, ModelSpec, FitResult, EvaluationPlan
    preprocessing.py         # train-only pipeline builder
    prediction.py            # fit/score/baselines
    statistics.py            # OLS/GLM and coefficient reports
    diagnostics.py           # residuals, calibration, influence, VIF, etc.
  causal/
    graph.py                 # versioned DAG and validation
    identification.py        # adjustment, identification and proof trace
    estimators.py            # allowed estimators / ATE/ATT
    balance.py               # overlap, SMD, effective sample size
    heterogeneity.py         # subgroup and supported CATE
    refutation.py            # sensitivity and robustness
    scenarios.py             # predictive-vs-intervention modes
  experiments/
    manifest.py              # run fingerprint and dependency graph
    history.py               # ephemeral or user opted-in snapshots
    comparison.py            # run diffs
  reports_v2/
    dossier.py               # report composer
    methods.py               # verified methods text from artifacts
    figures.py               # image/table exports
  api/
    routes_research.py       # additive API
    routes_explore.py
    routes_models.py
    routes_causal.py
    routes_experiments.py
    routes_dossier.py

frontend/src/
  design/                    # tokens, navigation, reusable shell primitives
  features/landing/          # cinematic genuine synthetic demo
  features/workspace/        # studies, role map, overview
  features/integrity/        # V1 adapter + new risk cards and inspector
  features/explore/          # parcoords, heatmaps, selection/brush store
  features/models/           # fit controls and real diagnostic views
  features/causal/           # DAG canvas, identification, estimator panels
  features/experiments/      # timeline and manifest
  features/reports/          # dossier and export
  shared/                    # typed API client, chart registry, guards
```

V1 files are **not** deleted at start. Hide route migration behind a tested application shell and feature flags. Avoid a rewrite of both app halves in one agent run.

## 7.3 Versioned contracts and source-of-truth strategy

- Introduce `StudyCardV1`, `VariableRoleMapV1`, `DAGSpecV1`, `PlotSpecV1`, `ModelSpecV1`, `AnalysisRunV1`, `CausalEstimateV1`, `ReproManifestV1`, `ReportSpecV1` with explicit schema versions and migrations.
- Use strong discriminated result enums and Pydantic validation. Serialize numeric NaN/Inf safely (`null` + explicit note) rather than invalid JSON.
- Every plot gets its server-calculated data and `dataset_id`, `run_id`, `filter_hash`, `sample_n`, `population_n`, `method`, `seed`, `timestamp/version`.
- Filtering uses explicit filter AST and immutable row identifiers; never accept arbitrary expression strings, raw SQL or Python from user.
- Heavy computations run in bounded worker tasks with timeouts/cancellation and concurrency caps; CPU and RAM budgets enforced on server.
- The backend alone computes authoritative statistics. Frontend computes only presentation transforms and trivial derived display formatting.
- Datasets expire safely; UI handles `410 Expired` with non-destructive recovery instructions. No silent mismatch of cached graphs to a newly uploaded same-named CSV.

## 7.4 Example wire contracts (illustrative, not finalized wire format)

```json
{
  "schema_version": "study.v1",
  "study_id": "study-demo-01",
  "dataset": {"sha256": "<sha256>", "rows": 1200, "columns": 16},
  "purpose": "causal",
  "unit_of_analysis": "participant",
  "target_population": "declared study sample",
  "variable_roles": {"outcome": ["Y"], "treatment": ["T"], "entity": ["person_id"]},
  "assumptions": [{"id": "A1", "type": "exchangeability", "status": "user_asserted"}]
}
```

```json
{
  "schema_version": "analysis_result.v1",
  "result_type": "causal_estimate",
  "dataset_sha256": "<sha256>",
  "dag_version": "dag-003",
  "estimand": "ATE",
  "method": "backdoor.ipw",
  "estimate": null,
  "ci_95": null,
  "status": "NOT_EVALUATED",
  "reason": "Illustrative contract; run the real backend before displaying a number"
}
```

These placeholders MUST NEVER appear as real completed calculations in the shipped demo.

---

# 8. Curated demonstrator experiences and sample data

The strongest CV demo needs a *narrative with falsifiable ground truth*, not just a screenshot gallery.

| Demo | Intended storyline | Technical checks |
| --- | --- | --- |
| **D01: Subscription leakage** | Repeated customer entities cause deceptively optimistic evaluation; compare random/group splitting. | Entity overlap, split consistency, model metric shift, row evidence. |
| **D02: Future information trap** | A feature recorded after the prediction moment creates target proxy/temporal leakage. | Availability registry, chronological split, pipeline warning, difference in valid/invalid evaluation. |
| **D03: Confounded intervention** | Simple synthetic exposure→outcome setting with a measurable confounder. | DAG, backdoor adjustment, ATE, unadjusted vs adjusted, balance, CI. |
| **D04: Collider trap** | Conditioning on a collider creates spurious association. | Identification warning, graph path highlighting, robust estimate distinction. |
| **D05: No-overlap cohort** | Treated and untreated groups are near perfectly separable. | Propensity distribution, effective N, positivity failure, blocked/inconclusive estimator. |
| **D06: Heterogeneous effect** | Known synthetic subgroup-dependent treatment effect. | Subgroup/CATE estimates with uncertainties and comparison to generative truth. |
| **D07: Survey-style observational research** | Cross-sectional behavioral dataset with multiple covariates, missingness, and a careful methodological narrative. | Study Card, EDA, OLS/logit, DAG assumptions, subgroup interpretation. |
| **D08: Clean negative control** | No identified defect under configured checks. | Appropriate absence of findings without claim of globally leakage-free data. |

**Demo data policy:** Each synthetic generator has documented equations/ground-truth manifest, random seed and expected-result oracles. Synthetic labels always visible. No real person's data committed. If later demonstrating on external public datasets, record license/source and do not pretend a real-world causal truth is known.

---

# 9. Stage-by-stage development roadmap and quality gates

**All 24 features are in accepted scope.** This roadmap orders them for integration safety, measurable output and visual quality. An agent must not reinterpret “later stage” as “drop feature”. No promise that all stages fit into a single overnight run. Estimate by verified acceptance gates, not token/hours alone.

| Stage | Goal | Dominant features | Exit gate |
| --- | --- | --- | --- |
| **S0 — Baseline & protection** | Create clean Git branch/checkpoint, inventory, independent baseline tests, architecture contracts, current screenshots, source/license/security review. | V1 preservation | All reproducible existing tests assessed; documented failures separated from environment constraints; no destructive changes. |
| **S1 — Design system & cinematic landing** | Build modern brand, animated authentic synthetic hero, responsive landing, authentic demo cards, light/dark tokens, shared shell primitives. | Visual design + reference | Desktop/mobile screenshots, keyboard/reduced-motion tests, real navigation, no fabricated claims; no V1 regression. |
| **S2 — Premium research workspace** | Add workbench shell, resizable panel layouts, controls/inspectors/docks, visual design consistency across V1 screens, typed route/adapters. | UX infrastructure | V1 complete workflow still functions in new shell; no empty/dead tabs marketed as live. |
| **S3 — Study/data foundation** | Study Card, data dictionary, variable roles, provenance, schema/profile and optional file formats, reproducibility schemas. | F01, F02, F19 core | Dataset/roles stable, invalid role failures clear, bounded upload, dataset hash and study export verified. |
| **S4 — Scientific visual Explorer** | Parallel coordinates, correlation/missingness heatmap, distributions, scatter matrix, linked brushing and export; all tied to real data. | F08, F22 preliminary | Click/brush across at least three real plots; deterministic sampling, accurate captions and figure exports. |
| **S5 — Integrity V2** | Split visualizations, similarity explorer, category scorecard, feature availability, preprocessing contract warnings, evaluation-plan extensions. | F03–F07 | Original rule regression; synthetic controls; display genuine testable leakage-prevention behavior vs mere CSV inference. |
| **S6 — Statistical & predictive ML engine** | OLS/logit, baselines, guarded pipelines, classification/regression model comparison, real diagnostics and subgroup exploratory views. | F09–F11, F15 preliminary | Independent numerical oracles; no fit on test; correct metrics and uncertainty; meaningful diagnostics panels like reference d/f. |
| **S7 — Interactive causal workbench** | DAG/role editor, cycles, saved graph version, keyboard/minimap, identification/adjustment, assumption registry. | F12, F13, F17 | Hand-specified causal graph test suite; consistent inferred adjustment logic; no automatic causation-from-correlation claims. |
| **S8 — Causal estimation & overlap** | Binary treatment estimators, identification gate, covariate balance, positivity, confidence intervals and subgroup estimates. | F14, F15 | Reference-oracle numerical agreement and synthetic-effect benchmark; explicit unsupported/unknown states. |
| **S9 — Counterfactual & robustness lab** | Prediction vs intervention what-if, sensitivity/refutation, heterogeneity advanced methods where verified, improved scientific visualizations. | F16, F18, F15 advanced | Truthful scenario mode separation and meaningful sensitivity counterexamples; no false certainty. |
| **S10 — Experiments, dossier, exports** | Assumptions and run history, manifest, comparison timeline, figures, methods/result dossier and reporting-guideline checklists. | F19–F23 | Export/import reproducibility test; trace every number; HTML/PDF/JSON integrity; optional DOCX tested separately. |
| **S11 — Research verification, usability & release** | Independent audit, adversarial tests, accessibility, synthetic & held-out benchmark studies, provenance validation, performance, packaging, docs, final UI review. | F24 + whole product | All required suites pass on canonical Windows setup; end-to-end browser journeys; complete source and truthful README, CV claims verified. |

**Order preference:** The owner wants the **landing page early**; therefore S1 must precede expensive backend research features. But a beautiful homepage is only checkpoint 1, not the finished product. Later S2 applies the visual grammar to the workbench **before** science-heavy components land.

## 9.1 Shared end-of-stage gate

Each stage must supply: (1) changed-file manifest, (2) screenshots/video evidence where UI changed, (3) real operations tested, (4) new unit/integration/E2E cases, (5) exact commands and outputs with pass/fail/skip, (6) known limitations and risks, (7) clean Git commit ID and a one-screen handoff, (8) no hidden mock data served as results. If any gate fails, stop and report; do not advance to next-stage feature claims.

## 9.2 Suggested milestone grouping for future FreeBuff scheduling

- **Visual/product-design agent:** S1–S2; small commits, browser screenshots, no research-engine rewrites.
- **Engineering/data-integrity agent:** S0/S3/S5; strict regression-first.
- **Statistics/ML agent:** S6, numerical-oracle focus.
- **Causal graph/estimation agent:** S7–S9, assumption-first.
- **Reporting/verification agent:** S10–S11, independent oracle/baseline audit.

**Model/hour selection is intentionally deferred** at the owner's request. Individual one-hour session capacities and required human attendance/session policies must be checked when making the execution prompts. Never rely on a five-hour unattended single-prompt miracle; instead use exact deterministic checkpoints.

---

# 10. Acceptance demonstration and evidence plan

**Public demo should show this exact 10–15 minute storyline (synthetic data):**

1. Open cinematic landing, interact with real synthetic preview, click `Explore Interactive Demo`.
2. Load D01; show Study Card, dataset roles/size, sample/permissions note.
3. Display linked parallel coordinates, correlation heatmap, train/test overlays and selectable samples.
4. Run old leakage checks; inspect one genuine affected pair and its row IDs.
5. Open similarity graph; brush affected rows in parallel coordinates; compare group split and resulting leakage findings.
6. Run a safe baseline model using train-only preprocessing; contrast validated evaluation plans, not optimistic cherry-picked scores.
7. Switch to D03 with a controlled, known generative causal model; draw/select edges; inspect DAG and adjustment set.
8. Estimate effect only once identified; show observed vs adjusted effect, CI, balance plot and assumptions.
9. Select a subgroup and explain sample-size/uncertainty; show sensitivity check and what-if scenario with predictive/intervention distinction.
10. Export research dossier with figure, assumptions, dataset hash, exact method and reproducibility manifest; verify references in report link to real runs.

**Release evidence minimum:**

- Baseline audit regressions unchanged (or explicitly documented intentional changes).
- V2 new scientific calculation oracles; exploratory plot source correctness tests.
- A complete positive and negative fixture for each declared new capability; deliberate failures for unsupported setups.
- Four+ distinct browser paths: original V1 workflow; visual explorer; predictive model flow; DAG/causal estimation; dossier; mobile and keyboard journeys.
- Independent audit of target leakage, CV fit boundaries, adjustment graph correctness, estimator mathematics, missingness handling, report traceability and untrusted data/file safety.
- Screenshots at ~1440×900, 1280×800, 768px tablet and 390px phone; both landing and inside workbench.
- Clear provenance and fair comparison case study: contaminated vs corrected ML evaluation **on synthetic known data**, not a claim that every change always improves performance.
- Benchmarks: upload parsing, multivariate rendering, DAG 50+ nodes, model fit and effect estimation with sensible bounded data and cancellation; resource limits documented.

**Never mark RELEASE READY** purely because unit tests pass or the landing page looks impressive. Functional and scientific claims need independent evidence.

---

# 11. Risk register and fallback design

| Risk | Severity | Mitigation / fallback |
| --- | --- | --- |
| Causal graph is drawn but algorithms cannot identify correctly | Critical | DAG editor ships with validated graph checks and “identification unavailable” state; estimation gated by reference tests. |
| A model pipeline leaks test information | Critical | Immutable split assignments; `Pipeline` fit boundary; oracle tests that deliberately attempt leakage. |
| V1 audit results change while modernizing | High | Golden-rule tests, adapter architecture, incremental commits and snapshot comparison. |
| Beautiful fake chart placeholders survive | Critical | Typed result provenance, no display as computed without backed run ID; strict demo-mode labels. |
| Causal estimates interpreted as proof | High | Estimand/assumption card, identification checks, method/uncertainty and sensitivity warnings beside charts. |
| Numerical library/OS version compatibility | High | Python 3.11 venv; lock/CI test each library before it enters runtime; degrade unavailable methods explicitly. |
| Uploading research data violates privacy | High | Local only, avoid automatic disk persistence, redaction, bounded memory, consent/provenance field. |
| Rendering 10k rows × many variables blocks UI | Medium/High | Deterministic samples, worker aggregation, progressive plot simplification and performance tests. |
| Feature explosion causes incoherent UX | High | Guided/advanced progressive disclosure, navigation taxonomy, one research state/provenance architecture. |
| Unbounded automated agent modifies whole repo | High | Scope each milestone to files/contracts, require diff review and independently verified checkpoint. |
| On-paper 100% scope produces half-working feature set | High | Maintain matrix of Planned / Implemented / Tested / Independently Verified; release only gates passed. |
| User expects data formats not currently supported | Medium | Clearly label CSV-only current; add XLSX/SPSS after correct metadata and safe parsing tests. |

---

# 12. Engineering standards, development rules and source-control safety

1. **First task:** create an ordinary Git branch/checkpoint before modifying any existing source. The supplied ZIP already acts as user's backup, but source-level rollback/commit remains mandatory.
2. Work in the actual repository, not `.freebuff/` backups. Never commit `.venv`, `node_modules`, downloaded node binaries, cache, reports containing private data, or the original backup ZIP.
3. Preserve currently pinned and working dependencies until a particular feature requires a specific upgrade; run compatibility tests.
4. Make interface changes incremental with accessibility and visual-snapshot evidence.
5. All new calculations have a deterministic typed API, exact input constraints, scientific method note, numerical oracle and runtime bound.
6. Distinguish `Not implemented`, `Unavailable due to environment`, `Not evaluated`, `Unsupported`, `Insufficient evidence`, `Failed`, `Succeeded`; never turn error into `0` or “clean”.
7. Every task should produce both frontend and backend acceptance as applicable; visually attractive non-functional buttons are forbidden.
8. All sources/documents/license references must be real and verifiable. No fabricated citations, awards, user testimonials, academic accuracy numbers or performance claims.
9. Maintain an updated `docs/FEATURE_MATRIX_V2.md` with source files, endpoints, tests and objective status for all F01–F24.
10. Status of baseline and new tests must be independently reproducible, not based only on agent narration.

---

# 13. Product and research reference sources (verified public foundations)

**R1. Scikit-learn — Common pitfalls and avoiding data leakage.**  
https://github.com/scikit-learn/scikit-learn/blob/main/doc/common_pitfalls.rst

**R2. Scikit-learn — Permutation importance, scope and cautions.**  
https://scikit-learn.org/stable/modules/generated/sklearn.inspection.permutation_importance.html

**R3. DoWhy / PyWhy — Identify, estimate and refute causal models.**  
https://github.com/py-why/dowhy and https://www.pywhy.org/dowhy/v0.14/dowhy.html

**R4. EconML — Orthogonal/Double ML and heterogeneous effects.**  
https://econml.azurewebsites.net/spec/estimation/dml.html

**R5. Statsmodels — Regression diagnostics and specification tests.**  
https://www.statsmodels.org/stable/diagnostic.html

**R6. React Flow — Accessible interactive DAG graph UI primitives.**  
https://reactflow.dev/learn/advanced-use/accessibility

**R7. Plotly JS — Parallel coordinates and heatmaps.**  
https://plotly.com/javascript/reference/parcoords/ and https://plotly.com/javascript/reference/heatmap/

**R8. STROBE (EQUATOR) — Reporting observational research.**  
https://equator-network.org/reporting-guidelines/strobe/index.html

**R9. TRIPOD+AI — Reporting clinical prediction models (only relevant to appropriate study types).**  
https://pmc.ncbi.nlm.nih.gov/articles/11019967/

These are **implementation and reporting references**, not proof that SplitScope V2 currently implements those methods. Future academic output must cite the exact applicable methodological sources and software versions used by the completed implementation.

---

# 14. Handoff instructions for development agents (brief, not the stage prompt)

**Project state:** existing SplitScope V1 source; all V2 feature requests F01–F24 accepted, but not yet implemented. `docs/PRODUCT_BLUEPRINT_V2.md` is the authoritative scope source. `docs/references/causality_workbench_reference.png` is the visual interaction inspiration. Current V1 functionality is valuable and must be preserved.

**Owner's taste:** Enterprise-grade website with cinematic but genuine science-based landing interactions and unusually rich inside-the-workbench visuals; the specific a–f regions from the reference image (control panel, causal DAG, parallel coordinates, regression panel, subgroup panel, heatmap) are mandatory; everything must be functional, scientifically meaningful and visually cohesive. Prefer original, modern product aesthetics to generic templates. Do not merely polish landing and leave a plain interior.

**Absolute first development assignment when authorized:** S0 only — read both documents, inspect actual source (skip huge vendored folders), validate baseline tests and run paths, capture screenshots, create an immutable Git checkpoint, record change constraints and propose bounded S1 files. Do not begin S1 features before S0 gate. No model is selected yet.

**Implementation sequence after approval:** S1 landing → S2 premium shell → S3 study data → S4 multivariate visualizations → S5 integrity → S6 modeling → S7 causal graph → S8 estimators → S9 robustness/counterfactual → S10 report/experiments → S11 independent release audit.

**Every agent must obey:** no premature release claims; no fake research values; exact result provenance; safety of private data; existing-feature regression protection; scoped commits, tests and evidence; explicit honest “not implemented / not evaluated” states.

---

# 15. Scope verification checklist — owner accepted feature mapping

| User-accepted request | Blueprint feature | Visual surface |
| --- | --- | --- |
| Causal DAG editor | F12–F13 | Causal Lab central graph |
| Statistical and regression workbench | F09 | Model Lab d-style regression panel |
| Subgroup / heterogeneity | F15 | e-style subgroup controller, cohort plots |
| Rich multivariate visualizations | F08 | c-style parallel coordinates and heatmaps |
| Causal estimation tools | F14 | Estimator tab and effect plots |
| Research report/methodology generator | F21 | Dossier/report builder |
| Study Card / Data Card | F01 | Workspace setup and Data dictionary |
| Assumption registry | F17 | Global assumption inspector |
| Reproducibility manifest | F19 | Experiment and export manifest |
| Leakage risk scorecard by category | F06 | Integrity overview |
| Train/test similarity explorer | F07 | Cross-split relation canvas |
| Counterfactual what-if | F16 | Scenario studio |
| Sensitivity analysis | F18 | Robustness subtab |
| Balance diagnostics | F14 | Balance Love plot, overlap and SMD |
| Invalid causal setup warnings | F13, F17 | DAG/estimator contextual warnings |
| Experiment history | F20 | Experiment timeline and run comparison |
| Export-ready figures/tables | F22 | Visual/export utilities |
| Advanced ML to make CV technically strong | F04, F05, F10, F11, F24 | Pipeline-fit guard, ML metrics, benchmarks |
| Highly graphical animated landing | §4.3, S1 | Authentic interactive synthetic scene |
| Premium consistent inner UI | §4.4, S2 | Workbench shell and docked analytical panels |
| Preserve existing SplitScope | §2, F03, S0 | Entire verified audit flow |

**Scope status:** Accepted requirements documented. **No V2 feature has been represented here as shipped or independently verified.** The next decision is an implementation model/session strategy for S0 and S1, once the owner approves this blueprint.
