# S9C-B — Robustness and sensitivity methodology

Three reproducible refutation experiments, all sharing the gated cohort,
adjustment set and production estimator machinery. Every repetition is seeded
with `np.random.default_rng([seed, rep])` (or `[seed, gammaIndex, kappaIndex]`
on the sensitivity grid), so the whole series reproduces from the recorded
seed. Failures are recorded per repetition with their reason and never averaged
into the distribution.

## 1. Data subsampling

Each repetition draws a simple random subsample without replacement at the
requested fraction (0.10–0.90), refits the chosen estimator **from scratch**
(all nuisance models), and records the estimate. The payload reports the full
estimate series, a five-number summary with mean and SD, and the failure list.

**What it does not show:** stability under subsampling describes sampling
variability on this population. It is not evidence that the estimate is
unbiased — a stable estimate can be stably wrong under unmeasured confounding.
This caveat ships in the payload and beside the figure. When a cross-fitting
group column is set, an additional warning states that independent row sampling
can split entity clusters and that the reported variation understates
entity-level dependence.

## 2. Placebo treatment

Each repetition draws a uniformly random permutation of the observed 0/1
treatment vector (treated count preserved), refits the estimator on the
permuted assignment with the unchanged outcome and covariates, and records the
placebo estimate. The UI overlays the original estimate on the placebo
distribution.

**Procedure limits, stated in the payload:** the permutation assumes
exchangeable, independent assignment; it does not respect group structure or
temporal ordering (a group-column configuration adds an explicit warning that
the placebo distribution is not group-valid there). A placebo near zero shows
only that the estimator produces near-zero noise under this permutation scheme —
it does not verify that the original estimate is causal.

## 3. Hypothetical unmeasured confounder (simulation scenario)

For each cell of the fixed 5×5 grid — γ ∈ {0, 0.25, 0.5, 0.75, 1.0} (log-odds
shift of U on treatment) × κ ∈ {0, 0.1, 0.2, 0.3, 0.4} (shift of U on the
outcome, per outcome SD) — a binary confounder is simulated from

    logit P(U=1) = logit(p) + γ·T + κ·(Y − mean(Y))/sd(Y),

evaluated on the observed data (prevalence p is researcher-set, 0.05–0.95). U is
joined to the adjustment set as a numeric covariate and the chosen estimator is
refitted. Cell (0, 0) is a treatment/outcome-orthogonal noise draw and sits
close to the original estimate (tested to within 0.15 with the linear
regression-adjustment estimator).

**Status: hypothetical scenario, not a bound.** The simulated U is generated
from an assumed model, not recovered from the data; the grid shows how the
estimate would move if a binary confounder of exactly that structure existed
and were adjusted for. Real confounding can be stronger, multivariate, or
differently structured. The payload, the UI shading note, and the tests all
carry the caveat verbatim.

## Bounds and refusals

Repetitions 100–1000; fraction 0.10–0.90 with a subsample-size floor; prevalence
0.05–0.95; unknown experiment or estimator names are typed 422s. The full
parameter set, resolved seed and experiment kind are recorded in the payload's
reproducibility block and re-checked for staleness like any estimation run.
