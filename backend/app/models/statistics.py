"""S6 statistical workbench: ordinary least squares and binary logistic regression.

All inferential quantities come from :mod:`statsmodels`; nothing here invents a
p-value, a standard error or an interval. The module's job is to turn an
explicit :class:`StatisticsConfig` into a defensible design matrix and then to
report the fitted result together with the coding, the analysed population and
every reason the result may be misleading.

Design decisions that a reviewer must be able to check:

* **No silent specification changes.** A constant predictor, a duplicate
  predictor, a singular design, a single-class outcome or an unparsable outcome
  is an error with an explanation — never quietly dropped or re-encoded.
* **Categorical coding is explicit.** Every non-numeric predictor is encoded as
  indicator terms against a named reference level. The reference and the full
  level list are returned with the result.
* **Missingness is counted, not hidden.** The complete-case population and every
  per-column exclusion are reported. The ``fail`` policy refuses instead.
* **Inference only where defined.** OLS returns R², F and residual diagnostics;
  logistic regression returns log-likelihood, AIC/BIC, McFadden pseudo-R² and
  odds ratios, and never an OLS R² presented as classification accuracy.
* **Diagnostics come from the fitted object.** The plotted sample carries the
  actual row ids, observed values, fitted values, residuals or predicted
  probabilities. It is a sampled view of the analysed rows, and says so.
"""

from __future__ import annotations

import math
import platform
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as scipy_stats

from app.audit.dataset import Dataset
from app.core.errors import ValidationFailure
from app.models.contracts import (
    CONDITION_WARNING,
    MAX_CATEGORICAL_LEVELS,
    MAX_DIAGNOSTIC_POINTS,
    MAX_MODEL_ROWS,
    MAX_PREDICTORS,
    MIN_MODEL_ROWS,
    MIN_ROWS_PER_PARAMETER,
    SMALL_SAMPLE_PARAMETERS,
    StatisticsConfig,
    VIF_WARNING,
)

try:  # statsmodels has moved this exception between releases.
    from statsmodels.tools.sm_exceptions import PerfectSeparationError
except Exception:  # pragma: no cover - only on unexpected statsmodels builds
    PerfectSeparationError = type("PerfectSeparationError", (Exception,), {})

MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "missing", "?"}


def _missing_mask(raw: pd.Series) -> np.ndarray:
    """Empty cells and the conventional missing tokens, case-insensitively.

    The loader already turns empty CSV cells into NaN; the token list matches
    the explorer's documented convention so the two features never disagree
    about how many rows a column contributes.
    """
    text = raw.astype("string").fillna("").str.strip().str.lower()
    return (raw.isna() | text.isin(MISSING_TOKENS)).to_numpy(dtype=bool)


def _numeric_parse(raw: pd.Series, missing: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Parse a column numerically. Returns (values with NaN, unparsable mask)."""
    candidate = raw.astype("string").fillna("").str.strip()
    parsed = pd.to_numeric(candidate, errors="coerce")
    values = parsed.to_numpy(dtype=float)
    values[missing] = np.nan
    unparsed = (~missing) & np.isnan(values)
    return values, unparsed


def _text_levels(raw: pd.Series, missing: np.ndarray) -> tuple[np.ndarray, list[str]]:
    text = raw.astype("string").fillna("").str.strip().to_numpy(dtype=object)
    values = np.array(["" if is_missing else str(value) for value, is_missing in zip(text, missing, strict=True)])
    levels = sorted({value for value, is_missing in zip(values, missing, strict=True) if not is_missing})
    return values, levels


def _variance_inflation(design: np.ndarray, names: list[str]) -> list[dict[str, Any]]:
    """VIF by auxiliary regressions, using only the design matrix.

    Rows with zero variance are reported as infinite rather than dividing by
    zero. The intercept (when present) is excluded from the reported list.
    """
    results: list[dict[str, Any]] = []
    columns = design.shape[1]
    for index in range(1, columns):
        others = np.delete(design, index, axis=1)
        target = design[:, index]
        if float(np.nanstd(target)) == 0.0:
            results.append({"term": names[index], "vif": None, "note": "constant column"})
            continue
        coefficients, *_ = np.linalg.lstsq(others, target, rcond=None)
        residual = target - others @ coefficients
        total = float(((target - target.mean()) ** 2).sum())
        r_squared = 1.0 - float((residual**2).sum()) / total if total > 0 else 0.0
        vif = None if r_squared >= 1.0 else 1.0 / (1.0 - r_squared)
        results.append({"term": names[index], "vif": vif})
    return results


def _diagnostic_sample(count: int) -> tuple[np.ndarray, int]:
    stride = max(1, math.ceil(count / MAX_DIAGNOSTIC_POINTS))
    indices = np.arange(0, count, stride, dtype=int)
    return indices, stride


def _row(term: str, kind: str, **values: Any) -> dict[str, Any]:
    return {"term": term, "kind": kind, **values}


def _infer_predictors(
    dataset: Dataset,
    predictors: tuple[str, ...],
    missing: dict[str, np.ndarray],
    references: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Classify each predictor and parse it.

    Returns the coding specification plus parsed arrays. A column that is fully
    numeric is continuous; anything else is categorical with at most
    ``MAX_CATEGORICAL_LEVELS`` observed levels. A column that is *mostly*
    numeric but has unparsable values is an error when used as continuous,
    because guessing a coercion would change the data.
    """
    numeric: dict[str, np.ndarray] = {}
    categorical: dict[str, dict[str, Any]] = {}
    coding: list[dict[str, Any]] = []
    unparsable: dict[str, int] = {}

    for column in predictors:
        raw = dataset.frame[column]
        values, bad = _numeric_parse(raw, missing[column])
        unparsable[column] = int(bad.sum())
        if unparsable[column] == 0:
            if np.nanstd(values) == 0.0:
                raise ValidationFailure(
                    f"Predictor {column!r} is constant, so it cannot be estimated.",
                    details={"column": column, "fix": "Remove it from the predictors."},
                )
            numeric[column] = values
            coding.append(
                {
                    "column": column,
                    "kind": "continuous",
                    "reference": None,
                    "levels": None,
                    "missing_count": int(missing[column].sum()),
                    "unparsable_count": 0,
                }
            )
            continue

        if unparsable[column] / max(1, (~missing[column]).sum()) < 0.8:
            raise ValidationFailure(
                f"Predictor {column!r} has {unparsable[column]} unparsable non-missing value(s), "
                "so it was not treated as numeric.",
                details={
                    "column": column,
                    "unparsable_count": unparsable[column],
                    "fix": "Clean the column, or exclude it from the model.",
                },
            )

        values_text, levels = _text_levels(raw, missing[column])
        if len(levels) < 2:
            raise ValidationFailure(
                f"Categorical predictor {column!r} has only one observed level after missing values "
                "are removed.",
                details={"column": column, "levels": levels},
            )
        if len(levels) > MAX_CATEGORICAL_LEVELS:
            raise ValidationFailure(
                f"Categorical predictor {column!r} has {len(levels)} levels; this build supports at "
                f"most {MAX_CATEGORICAL_LEVELS}.",
                details={
                    "column": column,
                    "levels": len(levels),
                    "limit": MAX_CATEGORICAL_LEVELS,
                    "fix": "Declare a coarser coding, or exclude the column.",
                },
            )
        reference = references.get(column, levels[0])
        if reference not in levels:
            raise ValidationFailure(
                f"The reference level {reference!r} does not occur in {column!r}.",
                details={"column": column, "reference": reference, "levels": levels},
            )
        categorical[column] = {"values": values_text, "levels": levels, "reference": reference}
        coding.append(
            {
                "column": column,
                "kind": "categorical",
                "reference": reference,
                "levels": levels,
                "missing_count": int(missing[column].sum()),
                "unparsable_count": 0,
            }
        )
    return coding, {"numeric": numeric, "categorical": categorical, "unparsable": unparsable}


def fit_statistics(dataset: Dataset, config: StatisticsConfig) -> dict[str, Any]:
    """Fit the specified OLS or logistic model and return an auditable result."""
    if config.task not in {"ols", "logistic"}:
        raise ValidationFailure(f"Unknown task {config.task!r}.", details={"supported": ["ols", "logistic"]})
    if not 0 < config.alpha < 1:
        raise ValidationFailure("The confidence level must be between 0 and 1.")
    if not 1 <= len(config.predictors) <= MAX_PREDICTORS:
        raise ValidationFailure(
            f"Choose between 1 and {MAX_PREDICTORS} predictors.",
            details={"received": len(config.predictors)},
        )
    if len(set(config.predictors)) != len(config.predictors):
        raise ValidationFailure("The predictor list contains a duplicate column.")
    if config.outcome in config.predictors:
        raise ValidationFailure("The outcome cannot also be a predictor.")

    for column in (config.outcome, *config.predictors):
        if column not in dataset.frame.columns:
            raise ValidationFailure(
                f"Column {column!r} is not present in the dataset.",
                details={"available_columns": dataset.columns[:50]},
            )
    if dataset.row_count > MAX_MODEL_ROWS:
        raise ValidationFailure(
            f"This build fits models on at most {MAX_MODEL_ROWS:,} rows; the dataset has "
            f"{dataset.row_count:,}.",
            details={"rows": dataset.row_count, "limit": MAX_MODEL_ROWS},
        )

    modeled = (config.outcome, *config.predictors)
    missing = {column: _missing_mask(dataset.frame[column]) for column in modeled}
    coding, parsed = _infer_predictors(dataset, config.predictors, missing, dict(config.categorical_references))
    warnings: list[dict[str, str]] = []

    # ---- outcome ----------------------------------------------------------- #
    outcome_raw = dataset.frame[config.outcome]
    if config.task == "ols":
        outcome_values, bad_outcome = _numeric_parse(outcome_raw, missing[config.outcome])
        if int(bad_outcome.sum()):
            raise ValidationFailure(
                f"Outcome {config.outcome!r} has {int(bad_outcome.sum())} non-numeric value(s); OLS needs "
                "a numeric outcome.",
                details={
                    "column": config.outcome,
                    "unparsable_count": int(bad_outcome.sum()),
                    "fix": "Choose a numeric outcome, or encode this one outside SplitScope.",
                },
            )
        outcome_meta = {
            "kind": "continuous",
            "positive_level": None,
            "levels": None,
            "missing_count": int(missing[config.outcome].sum()),
            "unparsable_count": int(bad_outcome.sum()),
        }
        model_outcome = outcome_values
    else:
        outcome_text, outcome_levels = _text_levels(outcome_raw, missing[config.outcome])
        if len(outcome_levels) != 2:
            raise ValidationFailure(
                f"Logistic regression needs an outcome with exactly two observed levels; "
                f"{config.outcome!r} has {len(outcome_levels)}.",
                details={
                    "column": config.outcome,
                    "levels": outcome_levels,
                    "fix": "Choose a two-level outcome, or construct the binary indicator first.",
                },
            )
        if config.positive_level is None:
            raise ValidationFailure(
                "Choose which outcome level is coded as the positive class (1). SplitScope does not "
                "pick a coding for you.",
                details={"column": config.outcome, "levels": outcome_levels},
            )
        if config.positive_level not in outcome_levels:
            raise ValidationFailure(
                f"The positive level {config.positive_level!r} does not occur in {config.outcome!r}.",
                details={"column": config.outcome, "levels": outcome_levels},
            )
        model_outcome = (outcome_text == config.positive_level).astype(float)
        negatives = int((model_outcome == 0).sum())
        positives = int((model_outcome == 1).sum())
        outcome_meta = {
            "kind": "binary",
            "positive_level": config.positive_level,
            "negative_level": next(level for level in outcome_levels if level != config.positive_level),
            "levels": outcome_levels,
            "positive_count": positives,
            "negative_count": negatives,
            "missing_count": int(missing[config.outcome].sum()),
            "unparsable_count": 0,
        }
        if min(positives, negatives) < 10:
            warnings.append(
                {
                    "code": "rare_outcome_class",
                    "severity": "high",
                    "message": (
                        f"Only {min(positives, negatives)} row(s) are in the smaller outcome class. "
                        "Coefficients and confidence intervals are unstable and separation is likely."
                    ),
                }
            )
        elif min(positives, negatives) / max(1, positives + negatives) < 0.1:
            warnings.append(
                {
                    "code": "class_imbalance",
                    "severity": "medium",
                    "message": "One outcome class is below 10% of the analysed rows.",
                }
            )

    if float(np.nanstd(model_outcome)) == 0.0:
        raise ValidationFailure(
            f"Outcome {config.outcome!r} is constant in the analysed rows, so no model is defined.",
            details={
                "column": config.outcome,
                "fix": "Choose an outcome that varies, or check the selected rows.",
            },
        )

    # ---- analysed population ------------------------------------------------ #
    missing_any = np.zeros(dataset.row_count, dtype=bool)
    for column in modeled:
        missing_any |= missing[column]
    unparsable_any = np.zeros(dataset.row_count, dtype=bool)
    for index, column in enumerate(config.predictors):
        if coding[index]["kind"] == "continuous":
            _, bad = _numeric_parse(dataset.frame[column], missing[column])
            unparsable_any |= bad
    excluded_mask = missing_any | unparsable_any
    analyzed = ~excluded_mask

    excluded_counts: dict[str, int] = {}
    for column in modeled:
        excluded_counts[column] = int((missing[column] & ~unparsable_any).sum())

    if config.missing_policy == "fail" and int(excluded_mask.sum()):
        raise ValidationFailure(
            f"{int(excluded_mask.sum())} row(s) have a missing or unparsable value in a modelled "
            "column, and the missing-data policy is 'fail'.",
            details={
                "excluded_rows": int(excluded_mask.sum()),
                "missing_by_column": {k: v for k, v in excluded_counts.items() if v},
                "fix": "Choose the complete-case policy, or clean the data.",
            },
        )

    y = model_outcome[analyzed]
    n = int(y.size)
    if n > MAX_MODEL_ROWS:
        raise ValidationFailure(
            f"The complete-case population has {n:,} rows, above the {MAX_MODEL_ROWS:,} row limit.",
            details={"analyzed_rows": n, "limit": MAX_MODEL_ROWS},
        )

    # ---- design matrix ------------------------------------------------------ #
    columns: list[np.ndarray] = []
    names: list[str] = []
    if config.intercept:
        columns.append(np.ones(n))
        names.append("const")
    for column in config.predictors:
        if column in parsed["numeric"]:
            columns.append(parsed["numeric"][column][analyzed])
            names.append(column)
    for column, spec in parsed["categorical"].items():
        values = spec["values"][analyzed]
        for level in spec["levels"]:
            if level == spec["reference"]:
                continue
            columns.append((values == level).astype(float))
            names.append(f"{column}[{level}]")

    design = np.column_stack(columns) if columns else np.ones((n, 1))
    if not config.intercept and not columns:
        raise ValidationFailure("The model has no terms. Choose at least one predictor.")

    parameters = design.shape[1]
    minimum_rows = max(MIN_MODEL_ROWS, parameters + 2, parameters * MIN_ROWS_PER_PARAMETER)
    if n < minimum_rows:
        raise ValidationFailure(
            f"The complete-case population has {n} rows, which is below the minimum of "
            f"{minimum_rows} for a model with {parameters} parameters.",
            details={"analyzed_rows": n, "parameters": parameters, "minimum_rows": minimum_rows},
        )

    rank = int(np.linalg.matrix_rank(design))
    if rank < parameters:
        correlations = np.corrcoef(design, rowvar=False)
        suspect: list[str] = []
        for i in range(parameters):
            for j in range(i + 1, parameters):
                if abs(float(correlations[i, j])) > 0.999999:
                    suspect.append(f"{names[i]} ~ {names[j]}")
        raise ValidationFailure(
            "The design matrix is rank deficient: some terms are exact linear combinations of others, "
            "so the coefficients are not identified.",
            details={
                "rank": rank,
                "parameters": parameters,
                "duplicated_terms": suspect[:10],
                "terms": names,
                "fix": "Remove one of the redundant predictors or change the categorical reference level.",
            },
        )

    condition = float(np.linalg.cond(design))
    if condition > CONDITION_WARNING:
        warnings.append(
            {
                "code": "ill_conditioned_design",
                "severity": "medium",
                "message": (
                    f"The design matrix condition number is {condition:,.1f}; coefficient standard "
                    "errors may be unstable."
                ),
            }
        )
    if n < SMALL_SAMPLE_PARAMETERS * parameters:
        warnings.append(
            {
                "code": "small_sample",
                "severity": "medium",
                "message": (
                    f"{n} analysed rows for {parameters} parameters. Estimates are imprecise; treat "
                    "p-values and intervals as exploratory."
                ),
            }
        )

    vif = _variance_inflation(design, names)
    high_vif = [entry for entry in vif if entry["vif"] is not None and entry["vif"] > VIF_WARNING]
    if high_vif:
        warnings.append(
            {
                "code": "multicollinearity",
                "severity": "medium",
                "message": (
                    "Some predictors are strongly collinear (VIF > "
                    f"{VIF_WARNING:g}): "
                    + ", ".join(f"{entry['term']} ({entry['vif']:.1f})" for entry in high_vif[:6])
                    + ". Individual coefficients may be unstable even if the fitted values are not."
                ),
            }
        )
    if int(excluded_mask.sum()):
        warnings.append(
            {
                "code": "complete_case_population",
                "severity": "low",
                "message": (
                    f"{int(excluded_mask.sum())} of {dataset.row_count} rows were excluded under the "
                    "complete-case policy. The estimates describe the analysed rows, not the full file."
                ),
            }
        )

    # ---- fit ---------------------------------------------------------------- #
    if config.task == "ols":
        fit = _fit_ols(y, design, names, config.alpha)
        version_notes = "OLS with classical (homoskedastic) standard errors."
    else:
        fit = _fit_logistic(y, design, names, config.alpha)
        version_notes = "Binary logistic regression fitted by maximum likelihood."

    warnings.extend(fit.pop("warnings", []))

    sample_indices, stride = _diagnostic_sample(n)
    row_ids = [rid for rid, keep in zip(dataset.row_ids, analyzed.tolist(), strict=True) if keep]
    sample_rows = _sample_rows(
        task=config.task,
        sample_indices=sample_indices,
        row_ids=row_ids,
        y=y,
        fitted=fit["_fitted"],
        residual=fit["_residual"],
        probability=fit.get("_probability"),
    )
    fit.pop("_fitted", None)
    fit.pop("_residual", None)
    fit.pop("_probability", None)

    diagnostics: dict[str, Any] = {
        "vif": vif,
        "condition_number": condition,
        "sample": {
            "method": "systematic_grid",
            "stride": stride,
            "drawn_rows": int(sample_indices.size),
            "analyzed_rows": n,
            "description": (
                f"Every {stride}th analysed row (systematic grid, {sample_indices.size} of {n})"
                if stride > 1
                else f"All {n} analysed rows"
            ),
            "rows": sample_rows,
        },
    }
    if config.task == "ols":
        diagnostics["residual_summary"] = _summary(np.asarray(fit.pop("_residual_values"), dtype=float))
        diagnostics["fitted_summary"] = _summary(np.asarray(fit.pop("_fitted_values"), dtype=float))
    else:
        diagnostics["probability_summary"] = _summary(np.asarray(fit.pop("_probabilities"), dtype=float))

    specification = {
        "task": config.task,
        "task_label": "Ordinary least squares" if config.task == "ols" else "Binary logistic regression",
        "outcome": config.outcome,
        "predictors": list(config.predictors),
        "intercept": config.intercept,
        "missing_policy": config.missing_policy,
        "alpha": config.alpha,
        "positive_level": outcome_meta["positive_level"],
        "formula": _formula(config, coding),
        "coding": coding,
        "outcome_coding": outcome_meta,
        "notes": [
            "The formula is a notation summary of the fitted design; user input is never executed.",
            version_notes,
        ],
    }

    return {
        "kind": "statistical_model",
        "task": config.task,
        "specification": specification,
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "sha256": dataset.fingerprint_sha256,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
        },
        "population": {
            "rows_total": dataset.row_count,
            "analyzed": n,
            "excluded": int(excluded_mask.sum()),
            "excluded_missing_by_column": {k: v for k, v in excluded_counts.items() if v},
            "policy": config.missing_policy,
            "complete_case_note": (
                "Complete-case analysis: rows with any missing value in a modelled column are excluded "
                "before fitting and are reported here."
            ),
        },
        "coefficients": fit.pop("coefficients"),
        "fit": fit,
        "diagnostics": diagnostics,
        "warnings": warnings,
        "versions": _versions(),
    }


def _fit_ols(y: np.ndarray, design: np.ndarray, names: list[str], alpha: float) -> dict[str, Any]:
    try:
        result = sm.OLS(y, design).fit()
    except np.linalg.LinAlgError as exc:  # pragma: no cover - guarded by the rank check
        raise ValidationFailure(
            "The least-squares solution could not be computed because the design matrix is singular.",
            details={"error": str(exc)},
        ) from exc

    confidence = np.asarray(result.conf_int(alpha=alpha), dtype=float)
    coefficients: list[dict[str, Any]] = []
    for index, term in enumerate(names):
        coefficients.append(
            _row(
                term,
                "intercept" if term == "const" else "coefficient",
                estimate=float(result.params[index]),
                std_error=float(result.bse[index]),
                ci_low=float(confidence[index, 0]),
                ci_high=float(confidence[index, 1]),
                statistic=float(result.tvalues[index]),
                p_value=_finite(result.pvalues[index]),
            )
        )

    fitted = np.asarray(result.fittedvalues, dtype=float)
    residual = np.asarray(result.resid, dtype=float)
    return {
        "n": int(result.nobs),
        "df_model": float(result.df_model),
        "df_resid": float(result.df_resid),
        "r_squared": float(result.rsquared),
        "adjusted_r_squared": float(result.rsquared_adj),
        "f_statistic": _finite(result.fvalue),
        "f_p_value": _finite(result.f_pvalue),
        "sigma": float(np.sqrt(result.mse_resid)) if result.df_resid > 0 else None,
        "log_likelihood": float(result.llf),
        "aic": float(result.aic),
        "bic": float(result.bic),
        "method": "statsmodels.OLS",
        "coefficients": coefficients,
        "_fitted": fitted,
        "_residual": residual,
        "_fitted_values": fitted.tolist(),
        "_residual_values": residual.tolist(),
        "warnings": [],
    }


def _fit_logistic(y: np.ndarray, design: np.ndarray, names: list[str], alpha: float) -> dict[str, Any]:
    if len(np.unique(y)) < 2:
        raise ValidationFailure(
            "The outcome has a single class in the analysed rows, so logistic regression is not defined.",
            details={
                "levels": [float(value) for value in np.unique(y)],
                "fix": "Choose an outcome with both classes present in the complete-case population.",
            },
        )
    try:
        result = sm.Logit(y, design).fit(disp=0, maxiter=200)
    except PerfectSeparationError as exc:
        raise ValidationFailure(
            "Perfect separation: a predictor (or combination) predicts the outcome perfectly, so the "
            "maximum-likelihood coefficients do not exist.",
            details={
                "reason": "perfect_separation",
                "fix": "Remove the separating predictor, collapse its categories, or collect more data.",
            },
        ) from exc
    except np.linalg.LinAlgError as exc:  # pragma: no cover - guarded by the rank check
        raise ValidationFailure(
            "The logistic likelihood could not be maximised because the design matrix is singular.",
            details={"error": str(exc)},
        ) from exc
    except ValueError as exc:
        raise ValidationFailure(
            "The logistic model could not be fitted with this specification.",
            details={"error": str(exc)},
        ) from exc

    converged = bool(getattr(result, "mle_retvals", {}).get("converged", True))
    if not converged:
        raise ValidationFailure(
            "The maximum-likelihood optimisation did not converge, so no coefficient table is reported.",
            details={
                "reason": "non_convergence",
                "iterations": getattr(result, "mle_retvals", {}).get("iterations"),
                "fix": "Simplify the model, remove collinear or separating predictors, or add rows.",
            },
        )

    confidence = np.asarray(result.conf_int(alpha=alpha), dtype=float)
    coefficients: list[dict[str, Any]] = []
    for index, term in enumerate(names):
        estimate = float(result.params[index])
        coefficients.append(
            _row(
                term,
                "intercept" if term == "const" else "coefficient",
                estimate=estimate,
                std_error=float(result.bse[index]),
                ci_low=float(confidence[index, 0]),
                ci_high=float(confidence[index, 1]),
                statistic=float(result.tvalues[index]),
                p_value=_finite(result.pvalues[index]),
                odds_ratio=float(np.exp(estimate)),
                odds_ratio_ci_low=float(np.exp(confidence[index, 0])),
                odds_ratio_ci_high=float(np.exp(confidence[index, 1])),
            )
        )

    probabilities = np.asarray(result.predict(design), dtype=float)
    warnings: list[dict[str, str]] = []
    if float(np.min(probabilities)) < 1e-10 or float(np.max(probabilities)) > 1 - 1e-10:
        warnings.append(
            {
                "code": "possible_separation",
                "severity": "high",
                "message": (
                    "Some fitted probabilities are numerically 0 or 1. This suggests (quasi-)complete "
                    "separation; treat the affected coefficients as unbounded rather than precise."
                ),
            }
        )
    return {
        "n": int(result.nobs),
        "df_model": float(result.df_model),
        "df_resid": float(result.df_resid),
        "log_likelihood": float(result.llf),
        "null_log_likelihood": float(result.llnull),
        "likelihood_ratio": float(result.llr),
        "likelihood_ratio_p_value": _finite(result.llr_pvalue),
        "mcfadden_pseudo_r_squared": float(result.prsquared),
        "aic": float(result.aic),
        "bic": float(result.bic),
        "converged": converged,
        "method": "statsmodels.Logit",
        "coefficients": coefficients,
        "_fitted": probabilities,
        "_residual": np.zeros_like(probabilities),
        "_probability": probabilities,
        "_probabilities": probabilities.tolist(),
        "warnings": warnings,
    }


def _sample_rows(
    *,
    task: str,
    sample_indices: np.ndarray,
    row_ids: list[str],
    y: np.ndarray,
    fitted: np.ndarray,
    residual: np.ndarray,
    probability: np.ndarray | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in sample_indices:
        entry: dict[str, Any] = {
            "row_id": row_ids[int(index)],
            "observed": float(y[int(index)]),
            "fitted": float(fitted[int(index)]),
        }
        if task == "logistic":
            assert probability is not None
            entry["probability"] = float(probability[int(index)])
        else:
            entry["residual"] = float(residual[int(index)])
        rows.append(entry)
    return rows


def _summary(values: np.ndarray) -> dict[str, Any]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"count": 0}
    return {
        "count": int(finite.size),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite, ddof=1)) if finite.size > 1 else None,
        "min": float(np.min(finite)),
        "q25": float(np.quantile(finite, 0.25)),
        "median": float(np.median(finite)),
        "q75": float(np.quantile(finite, 0.75)),
        "max": float(np.max(finite)),
    }


def _finite(value: Any) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def _formula(config: StatisticsConfig, coding: list[dict[str, Any]]) -> str:
    by_column = {entry["column"]: entry for entry in coding}
    terms: list[str] = []
    for column in config.predictors:
        entry = by_column[column]
        if entry["kind"] == "categorical":
            terms.append(f"C({column}, Treatment('{entry['reference']}'))")
        else:
            terms.append(column)
    expression = " + ".join(terms) if terms else "1"
    if not config.intercept:
        expression += " - 1"
    return f"{config.outcome} ~ {expression}"


def _versions() -> dict[str, str]:
    import scipy

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "statsmodels": sm.__version__,
        "scipy": scipy.__version__,
    }


__all__ = ["fit_statistics"]
