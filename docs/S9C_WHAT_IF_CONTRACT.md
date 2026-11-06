# S9C-C — What-if scenario contract

## What is computed

`POST /api/datasets/{id}/causal-graphs/{gid}/estimation/whatif` refits the
verified **g-computation outcome model** m(t, x) on the gated analysis cohort
(the same model and pipeline family the estimation studio uses for regression
adjustment) and reports:

- `profile_scenario` — the model's expected outcome under treatment = 1 and
  treatment = 0 for one stated baseline covariate profile, plus the contrast;
- `cohort_scenario` — the same model averaged over every analysed row
  (m(1, X) − m(0, X) mean), which equals the regression-adjustment ATE
  (tested to 1e-12 against `run_estimation`).

## What it is not

- **Not observed outcomes and not individual counterfactuals.** Every number is
  a model-based conditional expectation under explicit assumptions; the payload
  and the UI say so on every render.
- **Not interval-bearing.** No confidence interval, SE or p-value is attached
  to a scenario. The model specification block states this and points to the
  estimation studio's bootstrap interval for the cohort-level effect. A test
  asserts the strings `ci_lower`, `ci_upper` and `standard_error` never appear
  in a scenario payload.
- **Not an intervention on baseline covariates.** The treatment state is the
  only interventional variable. Changing a profile field is a conditional-model
  scenario; the payload says so.

## Profile rules

| Rule | Behaviour |
|---|---|
| Keys must be adjustment covariates | Anything else is a typed refusal (this also makes setting a treatment descendant impossible — it can never be in the backdoor adjustment set). |
| Numeric fields | Parsed as floats; a value outside the cohort's observed range is answered with a named extrapolation warning ("SplitScope does not silently extend findings beyond the observed support"). |
| Categorical fields | Must be an observed level (`CovariateSpec.levels`); an unobserved category is refused rather than silently one-hot-zeroed. |
| Unset fields | Cohort median (numeric) / mode (categorical), each listed in `profile_scenario.disclosures` with its source, and summarised in a warning. |
| Size | At most 30 explicit fields. |

## Reproducibility

The scenario is deterministic given the cohort (no randomness), and the
payload's reproducibility block records dataset/graph fingerprints, the full
estimation request the scenario inherits, the model kind and the profile
field counts. Stored runs are re-checked for staleness by the existing
fingerprint mechanism; the API test verifies a structural graph edit flips a
stored what-if run to `stale: true`.
