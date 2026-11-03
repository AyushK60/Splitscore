# S6 statistical methods (F09)

**Status:** implemented and numerically validated for ordinary least squares and
binary logistic regression. Predictive ML (F10), full diagnostics (F11) and
subgroups (F15) are **not** implemented; see `S6_ML_EVALUATION_CONTRACT.md` and
`S6_AGENT_CONTINUATION.md`.

**Engine:** `backend/app/models/statistics.py` · **contracts:**
`backend/app/models/contracts.py` · **API:** `backend/app/api/routes_models.py`.

All inferential quantities come from `statsmodels` 0.15.0. SplitScope computes
no p-value, standard error, interval or test statistic itself. The code builds
an explicit design matrix, fits it, and reports the fitted object.

## 1. Specification

| Field | Meaning |
|---|---|
| `task` | `ols` (numeric outcome) or `logistic` (two-level outcome) |
| `outcome` | one column |
| `predictors` | 1–30 distinct columns, not including the outcome |
| `missing_policy` | `complete_case` (exclude and count) or `fail` (refuse) |
| `intercept` | included unless explicitly removed |
| `positive_level` | **required** for logistic; SplitScope never picks the coding |
| `categorical_references` | optional chosen reference per categorical predictor |
| `alpha` | confidence level for intervals (default 0.05) |

The run records the formula, every coding decision, the analysed population and
library versions. `formula` is a notation summary only; it is never executed, so
user input cannot run code.

## 2. Type handling and coding

* A predictor is **continuous** when every non-missing value parses as a number.
* Otherwise it is **categorical** and is encoded as indicator terms for every
  observed level except one explicit reference (default: the first level in
  sorted order; the choice is always reported).
* More than **12** categorical levels is refused with an explanation.
* A column that is mostly numeric but contains unparsable non-missing values is
  refused rather than coerced: guessing would silently change the data.
* Missing cells are empty values and the conventional tokens (`na`, `n/a`,
  `nan`, `null`, `none`, `missing`, `?`), case-insensitive.
* The logistic positive class is an explicit user choice; its negative level,
  both counts and the coding are returned.

## 3. Population and missing data

`complete_case` excludes any row with a missing or unparsable value in a
modelled column, before the design matrix is built. The result reports:

* rows in the dataset,
* rows analysed,
* rows excluded, and counts by column,
* the policy and a sentence stating that estimates describe the analysed rows.

`fail` refuses the fit when any modelled cell is missing. No imputation is
performed and no row is silently dropped without being counted. The complete
case is always reported even when zero rows are excluded.

## 4. OLS

Fitted with `statsmodels.OLS` (classical homoskedastic standard errors).
Reported:

* coefficient, standard error, confidence interval, t statistic, p-value;
* R², adjusted R², F statistic and its p-value, model/residual degrees of
  freedom, residual standard deviation;
* log-likelihood, AIC and BIC;
* residual summary and residual-versus-fitted diagnostics from the fitted
  values.

R² is shown **only** for OLS.

## 5. Binary logistic regression

Fitted with `statsmodels.Logit` by maximum likelihood.

* log-odds coefficient, standard error, interval, z statistic, p-value;
* odds ratio and its confidence interval (exponentiated);
* log-likelihood, null log-likelihood, likelihood ratio and its p-value,
  McFadden pseudo-R², AIC and BIC;
* positive/negative class counts and the coding;
* a sample of observed class and fitted probability.

No OLS R² is shown for a classifier.

## 6. Guardrails (all refusals, never silent fixes)

| Condition | Behaviour |
|---|---|
| Unknown/duplicate/outcome-as-predictor column | refusal naming the problem |
| Constant outcome | refusal |
| Single-class logistic outcome | refusal listing the observed levels |
| Missing positive level or level absent | refusal listing the levels |
| Constant predictor | refusal |
| Rank-deficient / singular design | refusal with rank, parameter count, duplicate-term candidates |
| Fewer rows than `max(12, p+2, 5p)` | refusal with the exact minimum |
| > 12 categorical levels | refusal with the limit |
| Perfect separation | refusal (`perfect_separation`) |
| Non-convergence | refusal; no coefficient table is emitted |
| Complete case under `fail` | refusal with excluded-row counts |
| Condition number > 1e6 | fit succeeded, **warning** |
| VIF > 10 | fit succeeded, **warning** naming the terms |
| Small sample (< 10 rows per parameter) | fit succeeded, **warning** |
| Rare class / class imbalance (<10 rows or <10%) | fit succeeded, **warning** |
| Rows excluded under complete case | fit succeeded, **low warning** |

Refusing a specification is deliberate: reporting coefficients from a singular,
separated or unconverged model would present unidentified numbers as estimates.

## 7. API

* `POST /api/datasets/{id}/models/statistics` — body is the specification;
  returns the result and stores a bounded model run.
* `GET /api/datasets/{id}/models/runs` — recent model runs for this dataset.
* `GET /api/models/runs/{run_id}` — the stored payload.
* `GET /api/models/runs/{run_id}/export` — the same payload as a JSON download.
  Exports contain no dataset rows.

Runs live in the existing in-memory, bounded, expiring store. They vanish on
restart or expiry; that is stated in the API and in the UI.

## 8. Limits of this implementation

* Classical (non-robust) standard errors only. Cluster-robust and bootstrap
  intervals are not implemented.
* Complete-case only; no multiple imputation or likelihood-based missing-data
  handling.
* No interaction terms, polynomial terms, weights, offsets or splines.
* Categorical predictors are indicator-coded; no automatic collapsing of rare
  levels.
* A statistical fit uses the **analysed rows**. It is not a train/test
  predictive evaluation and does not detect leakage. The UI says this before
  and after fitting.
* The engine does not read the split column, so the same rows may include both
  train and test observations. Predicting a held-out outcome belongs to F10.
* No multiple-testing correction across the coefficient table; p-values are
  per coefficient and should not be read as a family-wise claim.
