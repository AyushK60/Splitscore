# S6 model diagnostics (F11, partial)

**Scope of this checkpoint:** coefficient intervals, residual-versus-fitted,
residual summary, collinearity (VIF), design conditioning, warnings, and the
sampled diagnostic rows behind the plots. Everything shown is computed from the
fitted statsmodels object and the analysed row ids.

## Implemented

| Diagnostic | Applies to | Source | Notes |
|---|---|---|---|
| Coefficient interval plot | OLS, logistic | `params`, `conf_int(alpha)` | Point estimate plus reported interval; zero rule; axis min/max labelled |
| Coefficient table | both | `params`, `bse`, `tvalues`, `pvalues`, odds ratios | Odds ratios only for logistic |
| Residual vs fitted | OLS | `fittedvalues`, `resid` | Sample stride stated; residual = observed − fitted |
| Residual summary | OLS | fitted residuals | mean, SD, min, quartiles, max |
| VIF | both | design matrix auxiliary regressions | Warns above 10; intercept excluded |
| Condition number | both | design matrix | Warns above 1e6 |
| Fit statistics | OLS: R², adj. R², F, df, σ, AIC/BIC. Logistic: LL, LR, McFadden R², AIC/BIC | statsmodels result | R² never shown for logistic |
| Predicted-probability sample | logistic | `predict(design)` | First rows of the systematic diagnostic sample |
| Complete-case accounting | both | masks before fitting | Excluded rows and per-column counts |

The diagnostic sample is a **systematic grid** with a stated stride; it is never
presented as the whole dataset when it is not. Sampling affects only the plotted
rows, not the fit, which always uses the full analysed population.

## Deliberately not implemented yet

These are not shown anywhere; no placeholder or hardcoded image is used:

* Q–Q plot and formal normality diagnostics.
* Leverage, Cook's distance and influence plots.
* Heteroskedasticity tests (Breusch–Pagan/White) and robust SE variants.
* Calibration/reliability curve, ROC and PR curves, threshold analysis.
* Confusion matrix and classification metrics (belong to F10).
* Permutation importance, partial dependence and local explanations.
* Learning curves and error-cohort tables.
* Subgroup error analysis (F15).

## Applicability rules enforced in the UI

* A logistic fit shows probability diagnostics and odds ratios; it never shows
  an OLS R² or a residual-versus-fitted plot as if it were a regression.
* An OLS fit shows residual diagnostics and intervals; it never shows odds
  ratios.
* Diagnostics are only rendered from a returned result object; before a fit the
  UI shows an explanatory placeholder.
* Warning severity is semantic (`high`, `medium`, `low`) and rendered in text as
  well as colour.

## Known limitations

* Classical standard errors assume homoskedastic, independent errors. Neither
  assumption is tested here; VIF and condition number describe the design, not
  the error structure.
* A visually pleasing residual cloud is not evidence that the model is correct.
* The coefficient interval plot uses the same interval as the table; it adds no
  new inference.
* No diagnostic is computed for a refused fit, because no fit exists.
