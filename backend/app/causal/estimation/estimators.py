"""The three S9A estimators: regression adjustment, IPW and cross-fitted AIPW.

All three estimate the **average treatment effect (ATE)** on one explicit
analysis cohort, given an explicit 0/1 treatment vector, a numeric outcome and
typed covariates. Preprocessing (imputation, scaling, one-hot encoding) lives
inside scikit-learn pipelines that are fitted **only on fitting rows** — for
the cross-fitted AIPW, within each training fold — so no transformation ever
learns from a row it scores.

Estimator mathematics (all under the identification assumptions verified by
the S8C gate, which this module does not re-check):

* **Regression adjustment (g-computation).** Fit m(t, x) = E[Y | T = t, X = x]
  on the cohort with the treatment as a design feature; predict m(1, X_i) and
  m(0, X_i) for every cohort row; ATE = mean_i[m(1, X_i) - m(0, X_i)]. The raw
  coefficient of T in this regression is *not* reported as the effect; the
  g-computation average is.
* **IPW (Hájek / normalised).** Fit e(x) = P(T = 1 | X = x). With
  w1 = T/e and w0 = (1-T)/(1-e):
  ATE = Σ w1 Y / Σ w1 - Σ w0 Y / Σ w0. Truncation, if the client explicitly
  requests it, is applied and reported; it is never on by default.
* **AIPW.** Cross-fitted nuisance predictions ê(X_i), m̂1(X_i), m̂0(X_i) come
  from models that never saw row i. The pseudo-outcome is

      ψ_i = m̂1(X_i) - m̂0(X_i) + T_i (Y_i - m̂1(X_i))/ê(X_i)
                            - (1 - T_i)(Y_i - m̂0(X_i))/(1 - ê(X_i)),

  and ATE = mean(ψ). This is the AIPW estimating equation itself, not the
  average of two estimators; double robustness is a property of *this* form.

Every function returns per-observation influence values when the estimator has
a closed-form influence function (IPW, AIPW); regression adjustment relies on
the refitting bootstrap instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import GroupKFold, KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.causal.estimation.contracts import EstimationLimits, EstimationRequest
from app.causal.estimation.preparation import (
    CATEGORICAL_KIND,
    NUMERIC_KIND,
    TREATMENT_COLUMN,
    CovariateSpec,
)

#: Nuisance-model identifiers echoed in the reproducibility metadata.
PROPENSITY_MODEL = "logistic_l2_C1.0"
OUTCOME_MODELS = {"linear": "linear_least_squares", "logistic": "logistic_l2_C1.0"}

MISSING_CATEGORY = "__splitscope_missing__"

PS_EXTREME_LOW = 0.01
PS_EXTREME_HIGH = 0.99


@dataclass
class EstimatorOutput:
    """One estimator's point result plus everything diagnostics need."""

    estimator: str
    estimate: float
    #: Modeled / weighted potential-outcome means where the estimator defines
    # them (RA, IPW); None for AIPW, whose estimating equation does not
    #: decompose into two separate means.
    mu1: float | None
    mu0: float | None
    influence: np.ndarray | None  # per-observation influence values, or None
    propensity: np.ndarray | None
    pseudo_outcome: np.ndarray | None
    model_spec: dict[str, Any]
    fold_counts: list[int] | None = None
    truncation: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "estimator": self.estimator,
            "estimate": self.estimate,
            "mu1": self.mu1,
            "mu0": self.mu0,
            "model_specification": self.model_spec,
            "fold_row_counts": self.fold_counts,
            "truncation": self.truncation,
            "warnings": list(self.warnings),
        }


def _column_transformer(
    covariates: list[CovariateSpec],
    policy: str,
    *,
    include_treatment: bool = True,
) -> ColumnTransformer:
    """Leakage-safe preprocessing, fitted only where the pipeline is fitted.

    Numeric: median imputation (a no-op under the complete-case policy, which
    has already excluded missing values, and fold-fitted under ``median_mode``)
    then standardisation. Categorical: explicit missing level, then one-hot
    with ``handle_unknown='ignore'`` so a resample or fold that lacks one level
    of another cannot crash a fit. The treatment column joins the numeric
    branch only for outcome models (it is already 0/1); propensity models
    must never see it.
    """
    numeric_columns = [spec.column for spec in covariates if spec.kind == NUMERIC_KIND]
    categorical_columns = [spec.column for spec in covariates if spec.kind == CATEGORICAL_KIND]
    numeric_pipeline = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        [
            (
                "impute",
                SimpleImputer(strategy="constant", fill_value=MISSING_CATEGORY),
            ),
            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    numeric_all = [*numeric_columns]
    if include_treatment:
        numeric_all.append(TREATMENT_COLUMN)
    if not numeric_all:
        numeric_all = []
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric_all:
        transformers.append(("numeric", numeric_pipeline, numeric_all))
    if categorical_columns:
        transformers.append(("categorical", categorical_pipeline, categorical_columns))
    return ColumnTransformer(transformers=transformers, remainder="drop")


def _outcome_estimator(outcome_task: str):
    if outcome_task == "logistic":
        return LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    return LinearRegression()


def _outcome_design(
    frame: pd.DataFrame,
    covariates: list[CovariateSpec],
    treatment: np.ndarray | None = None,
    *,
    include_treatment: bool = True,
) -> pd.DataFrame:
    """The design frame for an outcome model, fit and predict sides agreeing."""
    if include_treatment and treatment is not None:
        design = frame[[spec.column for spec in covariates]].copy()
        design[TREATMENT_COLUMN] = treatment
        return design
    if covariates:
        return frame[[spec.column for spec in covariates]].copy()
    # Treatment-specific fold model with an empty adjustment set: the only
    # feature is the intercept.
    return pd.DataFrame({"__splitscope_intercept__": np.ones(len(frame))})


def _fit_outcome_model(
    frame: pd.DataFrame,
    treatment: np.ndarray,
    outcome: np.ndarray,
    covariates: list[CovariateSpec],
    policy: str,
    outcome_task: str,
    *,
    include_treatment: bool = True,
) -> Pipeline:
    """Fit m(t, x) on the given rows; the treatment is a design feature unless
    the model is already treatment-specific (the AIPW fold models)."""
    design = _outcome_design(frame, covariates, treatment, include_treatment=include_treatment)
    if covariates or include_treatment:
        preprocess: Any = _column_transformer(covariates, policy, include_treatment=include_treatment)
    else:
        preprocess = "passthrough"
    model = Pipeline(
        [
            ("preprocess", preprocess),
            ("model", _outcome_estimator(outcome_task)),
        ]
    )
    model.fit(design, outcome)
    return model


def _outcome_predict(model: Pipeline, design: pd.DataFrame, outcome_task: str) -> np.ndarray:
    """E[Y | X] under the fitted outcome model.

    For a binary outcome the model is logistic and the expectation is the
    predicted probability of the coded-1 outcome — never the class label.
    """
    if outcome_task == "logistic":
        return model.predict_proba(design)[:, 1]
    return np.asarray(model.predict(design), dtype=float)


def _potential_outcome_predictions(
    model: Pipeline,
    frame: pd.DataFrame,
    covariates: list[CovariateSpec],
    outcome_task: str,
) -> tuple[np.ndarray, np.ndarray]:
    """m(1, X) and m(0, X) for every row of ``frame``."""
    columns = [spec.column for spec in covariates]
    design_1 = frame[columns].copy()
    design_1[TREATMENT_COLUMN] = 1
    design_0 = frame[columns].copy()
    design_0[TREATMENT_COLUMN] = 0
    m1 = _outcome_predict(model, design_1, outcome_task)
    m0 = _outcome_predict(model, design_0, outcome_task)
    return m1, m0


def estimate_regression_adjustment(
    frame: pd.DataFrame,
    treatment: np.ndarray,
    outcome: np.ndarray,
    covariates: list[CovariateSpec],
    policy: str,
    outcome_task: str,
) -> EstimatorOutput:
    """G-computation ATE: average modeled difference of potential outcomes."""
    model = _fit_outcome_model(frame, treatment, outcome, covariates, policy, outcome_task)
    m1, m0 = _potential_outcome_predictions(model, frame, covariates, outcome_task)
    return EstimatorOutput(
        estimator="regression_adjustment",
        estimate=float(np.mean(m1 - m0)),
        mu1=float(np.mean(m1)),
        mu0=float(np.mean(m0)),
        influence=None,
        propensity=None,
        pseudo_outcome=None,
        model_spec={
            "outcome_model": OUTCOME_MODELS[outcome_task],
            "treatment_as_feature": True,
            "predict_under": ["treatment=1", "treatment=0"],
        },
    )


def _fit_propensity_model(
    frame: pd.DataFrame,
    treatment: np.ndarray,
    covariates: list[CovariateSpec],
    policy: str,
) -> Pipeline:
    """Fit e(x) = P(T = 1 | X = x).

    With an empty adjustment set (a randomised experiment on this graph) the
    model is intercept-only: e reduces to the marginal treated fraction, which
    is the correct propensity for that design.
    """
    if covariates:
        design: Any = frame[[spec.column for spec in covariates]]
        preprocess: Any = _column_transformer(covariates, policy, include_treatment=False)
    else:
        design = pd.DataFrame({"__splitscope_intercept__": np.ones(len(frame))})
        preprocess = "passthrough"
    model = Pipeline(
        [
            ("preprocess", preprocess),
            (
                "model",
                LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000),
            ),
        ]
    )
    model.fit(design, treatment)
    model.splitscope_intercept_only = not covariates  # type: ignore[attr-defined]
    return model


def _predict_propensity(model: Pipeline, frame: pd.DataFrame, covariates: list[CovariateSpec]) -> np.ndarray:
    if getattr(model, "splitscope_intercept_only", False):
        design: Any = pd.DataFrame({"__splitscope_intercept__": np.ones(len(frame))})
    else:
        design = frame[[spec.column for spec in covariates]]
    return model.predict_proba(design)[:, 1]


def _apply_truncation(
    propensity: np.ndarray,
    truncation: dict[str, float] | None,
) -> tuple[np.ndarray, dict[str, Any] | None, list[str]]:
    """Apply *explicitly requested* truncation; never clip silently."""
    if truncation is None:
        return propensity, None, []
    lower = float(truncation["lower"])
    upper = float(truncation["upper"])
    affected_low = int((propensity < lower).sum())
    affected_high = int((propensity > upper).sum())
    truncated = np.clip(propensity, lower, upper)
    warning = (
        f"Propensity truncation was explicitly requested ({lower}-{upper}); "
        f"{affected_low} score(s) were raised and {affected_high} lowered. Truncation trades "
        "bias in the estimand for variance control: the reported estimate is for the "
        "truncated-weight estimand, not the untruncated ATE."
    )
    payload = {
        "lower": lower,
        "upper": upper,
        "scores_raised": affected_low,
        "scores_lowered": affected_high,
        "requested": True,
    }
    return truncated, payload, [warning]


def estimate_ipw(
    frame: pd.DataFrame,
    treatment: np.ndarray,
    outcome: np.ndarray,
    covariates: list[CovariateSpec],
    policy: str,
    truncation: dict[str, float] | None = None,
) -> EstimatorOutput:
    """Hájek (normalised) IPW ATE with a fitted propensity model."""
    model = _fit_propensity_model(frame, treatment, covariates, policy)
    propensity = _predict_propensity(model, frame, covariates)
    truncated, truncation_payload, warnings = _apply_truncation(propensity, truncation)

    eps = np.finfo(float).eps
    denominator = np.maximum(1.0 - truncated, eps)
    w1 = treatment / np.maximum(truncated, eps)
    w0 = (1.0 - treatment) / denominator
    sum_w1 = float(np.sum(w1))
    sum_w0 = float(np.sum(w0))
    if sum_w1 <= 0 or sum_w0 <= 0:
        raise EstimationFailure(
            "A treatment arm received total weight zero under the fitted propensity model; "
            "the Hájek estimator is undefined.",
            details={"min_propensity": float(np.min(truncated)), "max_propensity": float(np.max(truncated))},
        )
    mu1 = float(np.sum(w1 * outcome) / sum_w1)
    mu0 = float(np.sum(w0 * outcome) / sum_w0)
    n = len(treatment)
    # Per-observation influence values of the ratio estimators (propensity
    # treated as fixed; the refitting bootstrap is the alternative).
    phi1 = n * w1 * (outcome - mu1) / sum_w1
    phi0 = n * w0 * (outcome - mu0) / sum_w0
    influence = phi1 - phi0
    return EstimatorOutput(
        estimator="ipw",
        estimate=mu1 - mu0,
        mu1=mu1,
        mu0=mu0,
        influence=influence,
        propensity=propensity,
        pseudo_outcome=None,
        model_spec={
            "propensity_model": PROPENSITY_MODEL,
            "weighting": "hajek_normalized",
        },
        truncation=truncation_payload,
        warnings=warnings,
    )


class EstimationFailure(Exception):
    """A numerically honest failure: the estimator could not produce a value."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


def _crossfit_folds(
    request: EstimationRequest,
    treatment: np.ndarray,
    frame: pd.DataFrame,
    n_rows: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Deterministic folds; group-aware when a group column is named."""
    splits = request.cross_fit.splits
    if request.cross_fit.group_column:
        groups = frame[request.cross_fit.group_column].to_numpy()
        unique_groups = pd.unique(groups)
        if len(unique_groups) < splits:
            raise EstimationFailure(
                "The group column has fewer distinct entities than cross_fit.splits, so "
                "group-aware folds cannot be formed.",
                details={
                    "unique_groups": int(len(unique_groups)),
                    "splits": splits,
                    "fix": "Reduce cross_fit.splits, or drop the group column (recording "
                    "that folds are then not group-aware).",
                },
            )
        splitter = GroupKFold(n_splits=splits)
        return list(splitter.split(np.zeros((n_rows, 1)), groups=groups))
    splitter = KFold(n_splits=splits, shuffle=True, random_state=request.uncertainty.seed or 0)
    return list(splitter.split(np.arange(n_rows)))


def _fit_fold_outcome_models(
    frame: pd.DataFrame,
    treatment: np.ndarray,
    outcome: np.ndarray,
    covariates: list[CovariateSpec],
    policy: str,
    outcome_task: str,
    train_idx: np.ndarray,
) -> tuple[Any, Any]:
    """Treatment-specific outcome models m1, m0 fitted on one training fold."""
    train_frame = frame.iloc[train_idx].reset_index(drop=True)
    train_t = treatment[train_idx]
    train_y = outcome[train_idx]
    treated_idx = np.flatnonzero(train_t == 1)
    control_idx = np.flatnonzero(train_t == 0)
    minimum = min(EstimationLimits.MIN_ROWS_PER_ARM, len(train_t) // 2)
    if len(treated_idx) < minimum or len(control_idx) < minimum:
        raise EstimationFailure(
            "A cross-fitting training fold does not contain enough rows of both treatment "
            "arms to fit treatment-specific outcome models.",
            details={
                "fold_treated_rows": int(len(treated_idx)),
                "fold_control_rows": int(len(control_idx)),
                "splits": "reduce cross_fit.splits or restrict the cohort",
            },
        )
    treated_frame = train_frame.iloc[treated_idx].reset_index(drop=True)
    control_frame = train_frame.iloc[control_idx].reset_index(drop=True)
    m1_specific = _fit_outcome_model(
        treated_frame,
        np.ones(len(treated_idx)),
        train_y[treated_idx],
        covariates,
        policy,
        outcome_task,
        include_treatment=False,
    )
    m0_specific = _fit_outcome_model(
        control_frame,
        np.zeros(len(control_idx)),
        train_y[control_idx],
        covariates,
        policy,
        outcome_task,
        include_treatment=False,
    )
    return m1_specific, m0_specific


def estimate_aipw(
    frame: pd.DataFrame,
    treatment: np.ndarray,
    outcome: np.ndarray,
    covariates: list[CovariateSpec],
    policy: str,
    outcome_task: str,
    request: EstimationRequest,
) -> EstimatorOutput:
    """Cross-fitted AIPW via the influence-function pseudo-outcome equation."""
    n_rows = len(treatment)
    folds = _crossfit_folds(request, treatment, frame, n_rows)
    e_hat = np.full(n_rows, np.nan)
    m1_hat = np.full(n_rows, np.nan)
    m0_hat = np.full(n_rows, np.nan)
    fold_counts: list[int] = []
    for train_idx, test_idx in folds:
        fold_counts.append(int(len(test_idx)))
        train_t = treatment[train_idx]
        if train_t.min() == train_t.max():
            raise EstimationFailure(
                "A cross-fitting training fold contains only one treatment class, so the "
                "propensity model is not defined on it.",
                details={
                    "fold_treated_rows": int((train_t == 1).sum()),
                    "fold_control_rows": int((train_t == 0).sum()),
                    "fix": "Reduce cross_fit.splits, or rebalance/restrict the cohort. The "
                    "estimator refused to substitute a degenerate model.",
                },
            )
        ps_model = _fit_propensity_model(
            frame.iloc[train_idx].reset_index(drop=True),
            train_t,
            covariates,
            policy,
        )
        e_hat[test_idx] = _predict_propensity(
            ps_model, frame.iloc[test_idx].reset_index(drop=True), covariates
        )
        m1_model, m0_model = _fit_fold_outcome_models(
            frame, treatment, outcome, covariates, policy, outcome_task, train_idx
        )
        test_frame = frame.iloc[test_idx].reset_index(drop=True)
        design_test = _outcome_design(test_frame, covariates, include_treatment=False)
        m1_hat[test_idx] = _outcome_predict(m1_model, design_test, outcome_task)
        m0_hat[test_idx] = _outcome_predict(m0_model, design_test, outcome_task)

    truncation_spec = (
        {"lower": request.propensity_truncation.lower, "upper": request.propensity_truncation.upper}
        if request.propensity_truncation is not None
        else None
    )
    truncated, truncation_payload, warnings = _apply_truncation(e_hat, truncation_spec)
    eps = np.finfo(float).eps
    # Machine-epsilon guard against division by zero only — this is not
    # statistical truncation (that lives in _apply_truncation, explicitly
    # requested and reported). Extreme fitted scores remain extreme and are
    # reported by the overlap diagnostics.
    e_safe = np.clip(truncated, eps, 1.0 - eps)
    psi = (
        m1_hat
        - m0_hat
        + treatment * (outcome - m1_hat) / e_safe
        - (1.0 - treatment) * (outcome - m0_hat) / (1.0 - e_safe)
    )
    if not np.all(np.isfinite(psi)):
        raise EstimationFailure(
            "The AIPW pseudo-outcome is not finite for at least one row; the estimator "
            "refused to return a number.",
            details={"non_finite_rows": int((~np.isfinite(psi)).sum())},
        )
    estimate = float(np.mean(psi))
    influence = psi - estimate
    strategy = "group_kfold" if request.cross_fit.group_column else "shuffled_kfold"
    if not request.cross_fit.group_column:
        warnings.append(
            "Cross-fitting used shuffled folds. If observations are repeated per entity or "
            "chronologically ordered, independent shuffling can leak entity-level structure "
            "across folds; name cross_fit.group_column where grouping applies."
        )
    return EstimatorOutput(
        estimator="aipw",
        estimate=estimate,
        mu1=None,
        mu0=None,
        influence=influence,
        propensity=e_hat,
        pseudo_outcome=psi,
        model_spec={
            "propensity_model": PROPENSITY_MODEL,
            "outcome_models": OUTCOME_MODELS[outcome_task],
            "cross_fitting": {
                "strategy": strategy,
                "splits": request.cross_fit.splits,
                "seed": request.uncertainty.seed if strategy == "shuffled_kfold" else None,
                "group_column": request.cross_fit.group_column,
                "out_of_fold_predictions": True,
            },
        },
        fold_counts=fold_counts,
        truncation=truncation_payload,
        warnings=warnings,
    )


__all__ = [
    "EstimationFailure",
    "EstimatorOutput",
    "estimate_aipw",
    "estimate_ipw",
    "estimate_regression_adjustment",
]
