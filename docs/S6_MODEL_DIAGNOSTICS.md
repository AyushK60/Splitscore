# S6 model diagnostics (F11)

**Status: complete for the S6 exit gate.** The statistical workbench (F09) and the
predictive Model Lab (F10) are separate products. Their diagnostics are computed
from different fits, on different populations, and are labelled accordingly in
the UI. A predictive diagnostic is never presented as inferential evidence, and
an in-sample OLS diagnostic is never presented as held-out performance.

## Statistical workbench (F09)

These diagnostics come from the fitted statsmodels object and the analysed
complete-case rows.

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

## Predictive Model Lab (F10/F11)

All predictive diagnostics are computed from the selected pipeline, the stored
row-level test predictions, or the transformed refit design. The partition is
part of every payload and every figure caption.

| Diagnostic | Model / task | Partition | Method and quantity |
|---|---|---|---|
| Confusion matrix, per-class metrics | Binary or multiclass classification | Sealed test | `sklearn.metrics.confusion_matrix` and derived precision, recall, F1, accuracy, support |
| ROC curve and AUC | Binary classification | Sealed test | `roc_curve`/`roc_auc_score` on positive-class scores; at most 100 finite-threshold points |
| Precision–recall curve | Binary classification | Sealed test | `precision_recall_curve` on the same positive-class scores |
| Average precision (AP) | Binary classification | Sealed test | `average_precision_score`; also exposed as `pr_auc` for compatibility. AP is the step-wise sum `Σ (R_n − R_{n−1}) · P_n`, **not** trapezoidal PR area |
| Calibration table and reliability plot | Classification with probabilities | Sealed test | Ten equal-width probability bins on [0, 1]; mean predicted probability, observed positive rate, count and Wilson 95% interval per non-empty bin; empty bins are shown as empty |
| Brier score, ECE, MCE | Classification with probabilities | Sealed test | Brier = mean squared probability error; ECE = count-weighted mean absolute observed-minus-predicted gap; MCE = largest non-empty bin gap |
| Residual vs fitted | Regression | Sealed test | Stored fitted values and residuals; sampled rows with a stated stride |
| Normal Q–Q | Regression | Sealed test | Ordered raw residuals against normal plotting positions `(i − 0.5)/n`; reference line `mean + SD × z`; at least 3 finite residuals and non-zero SD required |
| OLS leverage and Cook's distance | Unpenalised OLS regression only | Refit rows (fit + validation) | `h_ii = x_iᵀ(XᵀX)⁻¹x_i`; `D_i = r_i² h_i / (p · MSE · (1 − h_i)²)` on the transformed design; thresholds `2p/n`, `3p/n`, `4/n`, `1` reported |
| OLS coefficient intervals | Unpenalised OLS regression only | Refit rows | Classical OLS standard errors and 95% t intervals on the transformed design |
| Permutation importance | Every non-dummy selected model | Sealed test | Each predictor permuted 5 times with a fixed seed; mean change in RMSE (increase) or balanced accuracy (drop), with SD; never used for selection |
| Subgroup metrics and intervals | Classification or regression | Sealed test | Accuracy with Wilson 95% interval, or MAE with normal-approximation 95% interval; exact denominator, share, support, and unadjusted-comparison note |

### Classification details

* The positive class is explicit. Prevalence, positive count and negative count
  are computed from the held-out labels, not assumed to be 0.5.
* AP/PR and ROC are emitted only when the outcome is binary and both classes are
  present in the test partition. Otherwise the field is `null`, the metric is
  listed in `metrics.undefined` with a reason, and no curve is drawn.
* A single-class test partition is therefore an explicit unsupported state, not a
  fabricated curve or a zero score.
* The PR curve is sampled to at most 100 points after AP is computed from all
  stored scores; sampling never changes AP or prevalence.
* Calibration bins use `np.digitize(..., right=True)` with interior edges, and
  the last bin includes probability 1. The UI states when only one non-empty bin
  exists, because a one-point reliability plot cannot describe calibration shape.

### Regression details

* Q–Q and residual plots describe the **sealed test residuals** of the selected
  model. They are predictive diagnostics; they do not validate OLS normality
  assumptions.
* Leverage, Cook's distance and coefficient intervals are **in-sample OLS
  diagnostics** on the refit (fit + validation) design. They describe influence
  and classical uncertainty, not held-out accuracy or causal effects.
* Influence is not computed for a dummy, ridge or tree model, even when one of
  those is the selected regressor. The UI displays a reason instead.
* The influence table reports the refit row count, parameter count, residual
  degrees of freedom, rank, condition number, threshold counts and the largest
  Cook's distances. Row labels are stored row ids.
* If the design is rank-deficient, has no residual degrees of freedom, has zero
  residual variance, or produces non-finite values, influence is marked
  inapplicable rather than partially reported.

### Permutation importance details

* Computed **after** the single test evaluation; it cannot affect selection.
* The partition, row count, repeat count, baseline metric and the exact scoring
  direction are stored and displayed.
* Correlated predictors can share or mask importance; this is stated in the UI
  and is not a causal decomposition.
* A dummy baseline is unsupported because permuting inputs cannot change its
  predictions.
* Limits: 2,000 test rows and 20 predictors. Larger partitions are marked
  unsupported instead of silently subsampled.

## Subgroup reporting (F15 preliminary scope)

Subgroups are computed on the sealed test partition using the actual selected
model's predictions.

* Classification: accuracy with a Wilson score 95% interval; positive and
  negative counts use the declared positive class.
* Regression: MAE with a normal-approximation 95% interval; the interval is
  undefined for a single-row subgroup.
* `n`, `share`, `metric_denominator`, `positive_count`, `negative_count` and
  `outcome_mean` reconcile to the test rows.
* Empty categorical levels and numeric bins are retained with `n = 0` and null
  metrics; numeric values outside the declared bins are counted in
  `outside_bins`.
* A subgroup is flagged when it has fewer than 20 rows or less than 5% of the
  test partition.
* Intervals are unadjusted for multiple comparisons. Differences between groups
  are predictive associations in this split, not causal treatment effects and
  not evidence of heterogeneity in an intervention effect.

## Applicability and honesty rules enforced in the UI

* A logistic fit shows probability diagnostics and odds ratios; it never shows
  an OLS R² or a residual-versus-fitted plot as if it were a regression.
* An OLS fit shows residual diagnostics and intervals; it never shows odds
  ratios.
* Influence is shown only when the selected model is an eligible OLS fit.
* PR/ROC/calibration are shown only for binary classification with both classes
  present.
* Unsupported states are text callouts with a reason; no placeholder curve or
  hardcoded image is used.
* Every diagnostic identifies its model, partition, population, method and
  limitations in the surrounding caption or context panel.

## Deferred beyond the S6 exit gate

These were considered and deliberately not added in this checkpoint:

* Learning curves (requires repeated refits across training sizes).
* Descriptive threshold exploration and a threshold table (the classifier
  remains fixed at 0.5; no test-set threshold tuning exists).
* Partial dependence and local (per-row) explanations.
* Multiclass ROC/PR and multiclass calibration.
* Formal normality, heteroskedasticity or influence test statistics.
* Multiplicity-adjusted subgroup intervals or formal heterogeneity tests.

They are optional later-scope capabilities, not claimed as delivered, and not
required by the approved S6 F11 core (PR/calibration; regression Q–Q/influence;
partition-specific permutation importance).

## Known limitations

* Statistical standard errors assume independent, homoskedastic errors. VIF and
  condition number describe the design, not the error structure.
* Predictive diagnostics describe one split and one fixture. They are not a
  measure of real-world safety or causality.
* The Q–Q plot is visual only; no normality test is performed.
* Influence diagnostics use the refit rows and classical OLS formulas; they do
  not extend to regularised or tree models.
* PR curves are binary-only and sampled for transport after AP is computed.
* Subgroup intervals are unadjusted and can be unstable in small groups.
* No diagnostic is computed for a refused fit, because no fit exists.
