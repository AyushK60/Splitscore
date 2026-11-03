"""S6 predictive machine learning (F10) with leakage-safe pipelines.

Contract (see ``docs/S6_ML_EVALUATION_CONTRACT.md``):

* the split is resolved from the study record or an S5 strategy **before** any
  preprocessing is fitted;
* training rows are carved into fit/validation, and the test partition is never
  read while imputers, encoders or models are fitted or selected;
* all learned preprocessing lives in a scikit-learn ``Pipeline`` /
  ``ColumnTransformer`` fitted on the fit partition only;
* candidates are compared on validation, one is selected, refitted on
  fit+validation, and evaluated on the sealed test partition exactly once;
* every reported number is computed from stored predictions and immutable row
  ids, with undefined metrics marked rather than defaulted to zero.

The module trains small, established estimators. It does not tune
hyperparameters, and it does not claim that a good test metric proves scientific
validity.
"""

from __future__ import annotations

import hashlib
import math
import platform
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.audit.canonical import ValueCanonicalizer
from app.audit.dataset import Dataset
from app.audit.engine import build_canonicalizer
from app.audit.types import AuditConfig, SplitConfig
from app.core.errors import ValidationFailure
from app.splits.strategies import (
    chronological_holdout,
    existing_split,
    generate_split,
    group_holdout,
    random_holdout,
    stratified_holdout,
    summarise,
)

Task = Literal["classification", "regression"]
SplitSource = Literal["existing", "generated"]
GeneratedStrategy = Literal["random", "stratified", "group", "chronological"]

TASKS: tuple[Task, ...] = ("classification", "regression")
GENERATED_STRATEGIES: tuple[GeneratedStrategy, ...] = (
    "random",
    "stratified",
    "group",
    "chronological",
)

CLASSIFICATION_MODELS = {"baseline": "Dummy prior", "logistic": "Logistic regression", "random_forest": "Random forest"}
REGRESSION_MODELS = {
    "baseline": "Dummy mean",
    "linear": "Linear regression",
    "ridge": "Ridge regression",
    "random_forest": "Random forest",
}

MAX_ROWS = 10_000
MAX_PREDICTORS = 30
MAX_CLASSES = 20
MAX_CATEGORIES = 30
MAX_TEST_PREDICTIONS = 2_000
MAX_ROC_POINTS = 100
MIN_FIT_ROWS = 20
MIN_VALIDATION_ROWS = 5
MIN_TEST_ROWS = 5
MIN_SUBGROUP_ROWS = 20
SUBGROUP_SHARE_WARNING = 0.05
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "missing", "?"}


@dataclass(frozen=True)
class PredictionConfig:
    task: Task
    outcome: str
    predictors: tuple[str, ...]
    positive_level: str | None = None
    split_source: SplitSource = "existing"
    split_strategy: GeneratedStrategy = "stratified"
    test_fraction: float = 0.25
    seed: int = 12345
    validation_fraction: float = 0.2
    models: tuple[str, ...] = ()
    subgroup_column: str | None = None
    subgroup_bins: tuple[float, ...] = ()


def _role_column(roles: dict[str, list[str]], role: str) -> str | None:
    for column, assigned in roles.items():
        if role in assigned:
            return column
    return None


def _missing_mask(raw: pd.Series) -> np.ndarray:
    text = raw.astype("string").fillna("").str.strip().str.lower()
    return (raw.isna() | text.isin(MISSING_TOKENS)).to_numpy(dtype=bool)


def _parse_numeric(raw: pd.Series) -> np.ndarray:
    parsed = pd.to_numeric(raw.astype("string").fillna("").str.strip(), errors="coerce")
    return np.array(parsed, dtype=float, copy=True)


def _prepare_design(
    dataset: Dataset, predictors: tuple[str, ...]
) -> tuple[pd.DataFrame, list[str], list[str], dict[str, Any]]:
    """Build a typed design frame. Unparsable numeric columns become categorical.

    Missing predictor values are left missing here: imputing them is a learned
    transformation and must happen inside the training-fitted pipeline.
    """
    frame = dataset.frame
    numeric_columns: list[str] = []
    categorical_columns: list[str] = []
    design = pd.DataFrame(index=frame.index)
    summary: dict[str, Any] = {"missing_by_column": {}, "categorical_levels": {}}

    for column in predictors:
        raw = frame[column]
        missing = _missing_mask(raw)
        parsed = _parse_numeric(raw)
        parsed[missing] = np.nan
        unparsable = (~missing) & np.isnan(parsed)
        non_missing = int((~missing).sum())
        summary["missing_by_column"][column] = int(missing.sum())

        if int(unparsable.sum()) == 0 and non_missing > 0:
            if float(np.nanstd(parsed)) == 0.0:
                raise ValidationFailure(
                    f"Predictor {column!r} is constant, so it carries no information.",
                    details={"column": column, "fix": "Remove it from the predictors."},
                )
            numeric_columns.append(column)
            design[column] = parsed
            continue

        text = raw.astype("string").fillna("").str.strip().astype(object)
        values = np.array([np.nan if is_missing else str(value) for value, is_missing in zip(text, missing, strict=True)])
        levels = sorted({str(value) for value, is_missing in zip(text, missing, strict=True) if not is_missing})
        if len(levels) < 2:
            raise ValidationFailure(
                f"Predictor {column!r} has fewer than two usable levels.",
                details={"column": column, "levels": levels},
            )
        if len(levels) > MAX_CATEGORIES:
            raise ValidationFailure(
                f"Predictor {column!r} has {len(levels)} categories; this build supports at most "
                f"{MAX_CATEGORIES}.",
                details={"column": column, "levels": len(levels), "limit": MAX_CATEGORIES},
            )
        categorical_columns.append(column)
        design[column] = values
        summary["categorical_levels"][column] = levels

    return design, numeric_columns, categorical_columns, summary


def _preprocessor(numeric_columns: list[str], categorical_columns: list[str], *, scale: bool) -> ColumnTransformer:
    transformers: list[tuple[str, Any, list[str]]] = []
    if numeric_columns:
        steps: list[tuple[str, Any]] = [("impute", SimpleImputer(strategy="median"))]
        if scale:
            steps.append(("scale", StandardScaler()))
        transformers.append(("num", Pipeline(steps), numeric_columns))
    if categorical_columns:
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical_columns,
            )
        )
    return ColumnTransformer(transformers, remainder="drop", sparse_threshold=0)


def _estimator(task: Task, family: str, seed: int) -> Any:
    if task == "classification":
        if family == "baseline":
            return DummyClassifier(strategy="prior")
        if family == "logistic":
            return LogisticRegression(max_iter=2000)
        if family == "random_forest":
            return RandomForestClassifier(n_estimators=200, min_samples_leaf=2, random_state=seed, n_jobs=1)
    else:
        if family == "baseline":
            return DummyRegressor(strategy="mean")
        if family == "linear":
            return LinearRegression()
        if family == "ridge":
            return Ridge(alpha=1.0)
        if family == "random_forest":
            return RandomForestRegressor(n_estimators=200, min_samples_leaf=2, random_state=seed, n_jobs=1)
    raise ValidationFailure(f"Model family {family!r} is not supported for {task}.", details={"task": task})


def _needs_scaling(family: str) -> bool:
    return family in {"logistic", "linear", "ridge"}


def _build_pipeline(
    task: Task,
    family: str,
    numeric_columns: list[str],
    categorical_columns: list[str],
    seed: int,
) -> Pipeline:
    return Pipeline(
        [
            ("pre", _preprocessor(numeric_columns, categorical_columns, scale=_needs_scaling(family))),
            ("model", _estimator(task, family, seed)),
        ]
    )


def _reshuffle_indices(indices: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return indices[rng.permutation(indices.size)]


def _carve_validation(
    dataset: Dataset,
    *,
    outcome: str,
    strategy: str,
    roles: dict[str, list[str]],
    outcome_text: np.ndarray,
    validation_fraction: float,
    seed: int,
    canonicalizer: ValueCanonicalizer,
    train_indices: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Split training rows into fit/validation using the same strategy family.

    The test partition is not involved. Group and chronological plans keep their
    constraint inside the training rows too, so a validation score cannot be
    inflated by the same entity or by future rows appearing in both halves.
    """
    if not 0.05 <= validation_fraction <= 0.5:
        raise ValidationFailure(
            "The validation fraction must be between 0.05 and 0.5.",
            details={"validation_fraction": validation_fraction},
        )
    subset = dataset.frame.iloc[train_indices].reset_index(drop=True)
    try:
        if strategy == "group":
            entity = _role_column(roles, "entity")
            if not entity:
                raise ValidationFailure("A group split needs an entity column declared in the study.")
            generated = group_holdout(
                subset,
                entity_column=entity,
                test_fraction=validation_fraction,
                seed=seed + 1,
                canonicalizer=canonicalizer,
            )
        elif strategy == "chronological":
            timestamp = _role_column(roles, "timestamp")
            if not timestamp:
                raise ValidationFailure("A chronological split needs a timestamp column declared in the study.")
            generated = chronological_holdout(
                subset, timestamp_column=timestamp, test_fraction=validation_fraction
            )
        elif strategy == "stratified":
            generated = stratified_holdout(
                subset,
                target_column=outcome,
                test_fraction=validation_fraction,
                seed=seed + 1,
                canonicalizer=canonicalizer,
            )
        else:
            generated = random_holdout(len(subset), validation_fraction, seed + 1)
    except ValidationFailure:
        raise
    except Exception as exc:  # typed strategy errors are SplitScopeError subclasses
        raise ValidationFailure(
            f"The validation partition could not be carved from the training rows: {exc}",
            details={"strategy": strategy, "validation_fraction": validation_fraction},
        ) from exc

    fit_indices = train_indices[np.flatnonzero(generated.masks.train)]
    validation_indices = train_indices[np.flatnonzero(generated.masks.test)]
    if fit_indices.size < MIN_FIT_ROWS or validation_indices.size < MIN_VALIDATION_ROWS:
        raise ValidationFailure(
            f"Carving validation left {fit_indices.size} fit and {validation_indices.size} validation "
            f"rows; at least {MIN_FIT_ROWS} and {MIN_VALIDATION_ROWS} are required.",
            details={
                "fit_rows": int(fit_indices.size),
                "validation_rows": int(validation_indices.size),
            },
        )
    return fit_indices, validation_indices


def _classification_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, probabilities: np.ndarray | None, labels: list[str]
) -> dict[str, Any]:
    matrix = confusion_matrix(y_true, y_pred, labels=list(range(len(labels))))
    support = matrix.sum(axis=1)
    predicted = matrix.sum(axis=0)
    total = int(matrix.sum())
    per_class: list[dict[str, Any]] = []
    recalls: list[float] = []
    for index, label in enumerate(labels):
        true_positive = int(matrix[index, index])
        n_support = int(support[index])
        n_predicted = int(predicted[index])
        precision = true_positive / n_predicted if n_predicted else None
        recall = true_positive / n_support if n_support else None
        if recall is not None:
            recalls.append(recall)
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall > 0
            else (0.0 if precision is not None and recall is not None else None)
        )
        per_class.append(
            {
                "label": label,
                "support": n_support,
                "predicted": n_predicted,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "accuracy": true_positive / n_support if n_support else None,
            }
        )

    undefined: list[dict[str, str]] = []
    present = [index for index, count in enumerate(support) if count > 0]
    if len(present) < len(labels):
        missing = [labels[index] for index, count in enumerate(support) if count == 0]
        undefined.append(
            {
                "metric": "per-class metrics",
                "reason": f"test partition contains no rows for class(es): {', '.join(missing)}",
            }
        )

    roc_auc: float | None = None
    pr_auc: float | None = None
    roc_points: dict[str, Any] | None = None
    if len(labels) == 2 and probabilities is not None and len(present) == 2:
        positive = probabilities
        try:
            roc_auc = float(roc_auc_score(y_true, positive))
            pr_auc = float(average_precision_score(y_true, positive))
            fpr, tpr, thresholds = roc_curve(y_true, positive)
            # sklearn starts the threshold grid at +inf. JSON has no infinity,
            # so keep only finite thresholds; the plotted curve is unaffected.
            finite = [index for index, value in enumerate(thresholds) if math.isfinite(float(value))]
            stride = max(1, math.ceil(len(finite) / MAX_ROC_POINTS))
            kept = finite[::stride]
            roc_points = {
                "fpr": [round(float(fpr[index]), 6) for index in kept],
                "tpr": [round(float(tpr[index]), 6) for index in kept],
                "thresholds": [round(float(thresholds[index]), 6) for index in kept],
                "auc": roc_auc,
            }
        except ValueError as exc:
            undefined.append({"metric": "ROC-AUC", "reason": str(exc)})
    else:
        reason = (
            "ROC-AUC requires a binary outcome and probabilities"
            if len(labels) != 2
            else "both classes must be present in the test partition"
        )
        undefined.append({"metric": "ROC-AUC", "reason": reason})
        undefined.append({"metric": "PR-AUC", "reason": reason})

    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(np.mean(recalls)) if recalls else None,
        "classes": labels,
        "confusion_matrix": matrix.tolist(),
        "per_class": per_class,
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "roc_curve": roc_points,
        "undefined": undefined,
        "n": total,
    }


def _regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    residual = y_true - y_pred
    variance = float(np.var(y_true))
    undefined: list[dict[str, str]] = []
    r2: float | None = None
    if variance > 0:
        r2 = float(r2_score(y_true, y_pred))
    else:
        undefined.append({"metric": "R²", "reason": "the test outcome has zero variance"})
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(math.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": r2,
        "n": int(y_true.size),
        "residual_summary": _summary(residual),
        "undefined": undefined,
    }


def _summary(values: np.ndarray) -> dict[str, Any]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"count": 0}
    return {
        "count": int(finite.size),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite, ddof=1)) if finite.size > 1 else None,
        "min": float(np.min(finite)),
        "median": float(np.median(finite)),
        "max": float(np.max(finite)),
    }


def _calibration(y_true: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> list[dict[str, Any]]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    slots = np.clip(np.digitize(probabilities, edges[1:-1], right=True), 0, bins - 1)
    entries: list[dict[str, Any]] = []
    for index in range(bins):
        mask = slots == index
        count = int(mask.sum())
        entries.append(
            {
                "bin_low": round(float(edges[index]), 3),
                "bin_high": round(float(edges[index + 1]), 3),
                "count": count,
                "mean_predicted": float(probabilities[mask].mean()) if count else None,
                "observed_rate": float(y_true[mask].mean()) if count else None,
            }
        )
    return entries


def _subgroups(
    *,
    dataset: Dataset,
    config: PredictionConfig,
    test_indices: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    labels: list[str] | None,
    task: Task,
) -> dict[str, Any] | None:
    column = config.subgroup_column
    if not column:
        return None
    if column not in dataset.frame.columns:
        raise ValidationFailure(
            f"Subgroup column {column!r} is not present in the dataset.",
            details={"available_columns": dataset.columns[:50]},
        )
    raw = dataset.frame.iloc[test_indices][column].reset_index(drop=True)
    missing = _missing_mask(raw)
    text = raw.astype("string").fillna("").str.strip().astype(object)
    parsed = _parse_numeric(raw)
    is_numeric = _missing_mask(raw).sum() == 0 and int(np.isnan(parsed).sum()) == 0

    groups: list[tuple[str, np.ndarray]] = []
    outside = 0
    if is_numeric:
        bins = list(config.subgroup_bins)
        if len(bins) < 2:
            raise ValidationFailure(
                "A numeric subgroup column needs explicit bin edges (at least two).",
                details={"column": column, "received": bins},
            )
        if bins != sorted(bins) or len(set(bins)) != len(bins):
            raise ValidationFailure(
                "Subgroup bin edges must be strictly increasing.",
                details={"column": column, "received": bins},
            )
        bucketed = np.digitize(parsed, bins[1:-1], right=False)
        outside = int(((parsed < bins[0]) | (parsed > bins[-1]) | np.isnan(parsed)).sum())
        for index in range(len(bins) - 1):
            mask = (bucketed == index) & (parsed >= bins[0]) & (parsed <= bins[-1]) & ~np.isnan(parsed)
            closing = "]" if index == len(bins) - 2 else ")"
            groups.append((f"[{bins[index]:g}, {bins[index + 1]:g}{closing}", mask))
    else:
        levels = sorted({str(value) for value, is_missing in zip(text, missing, strict=True) if not is_missing})
        if len(levels) > MAX_CATEGORIES:
            raise ValidationFailure(
                f"Subgroup column {column!r} has {len(levels)} levels; this build supports at most "
                f"{MAX_CATEGORIES}.",
                details={"column": column, "levels": len(levels)},
            )
        for level in levels:
            mask = np.array(
                [
                    (not is_missing) and str(value) == level
                    for value, is_missing in zip(text, missing, strict=True)
                ],
                dtype=bool,
            )
            groups.append((level, mask))
        if bool(missing.any()):
            groups.append(("(missing)", np.asarray(missing, dtype=bool)))

    total = int(test_indices.size)
    rows: list[dict[str, Any]] = []
    for label, mask in groups:
        n = int(mask.sum())
        if n == 0:
            rows.append(
                {
                    "group": label,
                    "n": 0,
                    "share": 0.0,
                    "metric": None,
                    "warning": "empty subgroup",
                }
            )
            continue
        truth = y_true[mask]
        prediction = y_pred[mask]
        if task == "classification":
            metric = float(accuracy_score(truth, prediction))
            metric_name = "accuracy"
        else:
            metric = float(mean_absolute_error(truth, prediction))
            metric_name = "MAE"
        warning = None
        if n < MIN_SUBGROUP_ROWS or n / total < SUBGROUP_SHARE_WARNING:
            warning = (
                f"small subgroup: {n} test row(s), below "
                f"{MIN_SUBGROUP_ROWS} rows or {SUBGROUP_SHARE_WARNING:.0%} of the test partition"
            )
        entry: dict[str, Any] = {
            "group": label,
            "n": n,
            "share": round(n / total, 6) if total else 0.0,
            "metric_name": metric_name,
            "metric": metric,
            "warning": warning,
        }
        entry["outcome_mean"] = float(np.mean(truth))
        rows.append(entry)

    return {
        "column": column,
        "partition": "test",
        "test_rows": total,
        "grouped_rows": int(sum(row["n"] for row in rows)),
        "outside_bins": outside,
        "minimum_recommended_rows": MIN_SUBGROUP_ROWS,
        "rows": rows,
        "note": (
            "Subgroup metrics describe predictive error in the sealed test partition. They are not "
            "causal effect heterogeneity."
        ),
    }


def _resolve_split(
    dataset: Dataset,
    config: PredictionConfig,
    roles: dict[str, list[str]],
    split_labels: tuple[str | None, str | None],
    canonicalizer: ValueCanonicalizer,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any], str]:
    if config.split_source == "existing":
        split_column = _role_column(roles, "split")
        train_value, test_value = split_labels
        if not split_column or not train_value or not test_value:
            raise ValidationFailure(
                "The study has no confirmed split column and labels, so an existing-split evaluation "
                "cannot be built.",
                details={
                    "split_column": split_column,
                    "train_value": train_value,
                    "test_value": test_value,
                    "fix": "Confirm the split in Data, or choose a generated split for this run.",
                },
            )
        masks, summary = existing_split(
            dataset,
            split_column=split_column,
            train_value=train_value,
            test_value=test_value,
            strategy_id="existing",
            label="Existing split column",
        )
        return (
            np.flatnonzero(masks.train),
            np.flatnonzero(masks.test),
            summary.model_dump(),
            "existing",
        )

    strategy = config.split_strategy
    if strategy not in GENERATED_STRATEGIES:
        raise ValidationFailure(f"Unknown split strategy {strategy!r}.")
    if not 0.05 <= config.test_fraction <= 0.5:
        raise ValidationFailure(
            "The test fraction must be between 0.05 and 0.5.",
            details={"test_fraction": config.test_fraction},
        )
    generated = generate_split(
        dataset,
        resolved_entity=_role_column(roles, "entity"),
        resolved_target=_role_column(roles, "target") or config.outcome,
        resolved_timestamp=_role_column(roles, "timestamp"),
        config=SplitConfig(
            kind=strategy,
            label=f"{strategy} holdout",
            test_fraction=config.test_fraction,
            seed=config.seed,
        ),
        canonicalizer=canonicalizer,
    )
    summary = summarise(
        strategy_id=strategy,
        label=f"{strategy} holdout",
        kind=strategy,
        generated=generated,
    )
    return (
        np.flatnonzero(generated.masks.train),
        np.flatnonzero(generated.masks.test),
        summary.model_dump(),
        strategy,
    )


def _membership_digest(ids: list[str]) -> str:
    digest = hashlib.sha256()
    for row_id in ids:
        digest.update(row_id.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def fit_prediction(
    dataset: Dataset,
    config: PredictionConfig,
    *,
    roles: dict[str, list[str]],
    split_labels: tuple[str | None, str | None],
) -> dict[str, Any]:
    """Fit and evaluate predictive models under the documented contract."""
    if config.task not in TASKS:
        raise ValidationFailure(f"Unknown task {config.task!r}.", details={"supported": list(TASKS)})
    if dataset.row_count > MAX_ROWS:
        raise ValidationFailure(
            f"This build trains models on at most {MAX_ROWS:,} rows; the dataset has "
            f"{dataset.row_count:,}.",
            details={"rows": dataset.row_count, "limit": MAX_ROWS},
        )
    if not 1 <= len(config.predictors) <= MAX_PREDICTORS:
        raise ValidationFailure(f"Choose between 1 and {MAX_PREDICTORS} predictors.")
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
    if config.subgroup_column and config.subgroup_column == config.outcome:
        raise ValidationFailure("The subgroup column cannot be the outcome.")

    allowed = CLASSIFICATION_MODELS if config.task == "classification" else REGRESSION_MODELS
    families = tuple(config.models) if config.models else tuple(allowed)
    unknown = [family for family in families if family not in allowed]
    if unknown:
        raise ValidationFailure(
            f"Unsupported model family for {config.task}: {', '.join(unknown)}.",
            details={"supported": list(allowed)},
        )
    if len(families) == 0:
        raise ValidationFailure("Choose at least one model family.")

    # ---- outcome ----------------------------------------------------------- #
    outcome_raw = dataset.frame[config.outcome]
    outcome_missing = _missing_mask(outcome_raw)
    outcome_text = outcome_raw.astype("string").fillna("").str.strip().to_numpy(dtype=object)

    if config.task == "classification":
        levels = sorted(
            {str(value) for value, is_missing in zip(outcome_text, outcome_missing, strict=True) if not is_missing}
        )
        if len(levels) < 2:
            raise ValidationFailure(
                f"Classification needs at least two outcome classes; {config.outcome!r} has "
                f"{len(levels)}.",
                details={"column": config.outcome, "levels": levels},
            )
        if len(levels) > MAX_CLASSES:
            raise ValidationFailure(
                f"Outcome {config.outcome!r} has {len(levels)} classes; this build supports at most "
                f"{MAX_CLASSES}.",
                details={"column": config.outcome, "levels": len(levels), "limit": MAX_CLASSES},
            )
        code = {level: index for index, level in enumerate(levels)}
        y = np.array(
            [
                -1 if is_missing else code[str(value)]
                for value, is_missing in zip(outcome_text, outcome_missing, strict=True)
            ],
            dtype=int,
        )
        if len(levels) == 2:
            if config.positive_level is None:
                raise ValidationFailure(
                    "Choose which outcome level is the positive class (1).",
                    details={"column": config.outcome, "levels": levels},
                )
            if config.positive_level not in code:
                raise ValidationFailure(
                    f"The positive level {config.positive_level!r} does not occur in {config.outcome!r}.",
                    details={"column": config.outcome, "levels": levels},
                )
        else:
            if config.positive_level is not None:
                raise ValidationFailure(
                    "A positive class applies only to a binary outcome.",
                    details={"levels": levels},
                )
        counts = np.bincount(y[y >= 0], minlength=len(levels))
        small = [levels[index] for index, count in enumerate(counts) if count < 5]
        if small:
            raise ValidationFailure(
                "Every class needs at least 5 rows for a train/validation/test evaluation; "
                f"too few: {', '.join(small)}.",
                details={"class_counts": {levels[i]: int(counts[i]) for i in range(len(levels))}},
            )
        outcome_meta = {
            "kind": "classification",
            "labels": levels,
            "positive_level": config.positive_level,
            "class_counts": {levels[i]: int(counts[i]) for i in range(len(levels))},
        }
    else:
        parsed = _parse_numeric(outcome_raw)
        unparsable = (~outcome_missing) & np.isnan(parsed)
        if int(unparsable.sum()):
            raise ValidationFailure(
                f"Outcome {config.outcome!r} has {int(unparsable.sum())} non-numeric value(s); "
                "regression needs a numeric outcome.",
                details={"column": config.outcome, "unparsable_count": int(unparsable.sum())},
            )
        y = parsed
        valid_outcome = ~np.isnan(y)
        if float(np.nanstd(y[valid_outcome])) == 0.0:
            raise ValidationFailure(
                f"Outcome {config.outcome!r} is constant in the observed rows.",
                details={"column": config.outcome},
            )
        outcome_meta = {
            "kind": "regression",
            "mean": float(np.nanmean(y)),
            "std": float(np.nanstd(y, ddof=1)),
            "missing_count": int(outcome_missing.sum()),
        }

    # Complete-case outcome handling is required: an unobserved label cannot be
    # imputed or used to score a model. Predictor missings are handled inside the
    # pipeline instead.
    valid_outcome = ~outcome_missing if config.task == "classification" else np.isfinite(y)

    canonicalizer = build_canonicalizer(AuditConfig())
    train_indices_full, test_indices_full, split_summary, strategy = _resolve_split(
        dataset, config, roles, split_labels, canonicalizer
    )
    train_indices = train_indices_full[valid_outcome[train_indices_full]]
    test_indices = test_indices_full[valid_outcome[test_indices_full]]
    if test_indices.size < MIN_TEST_ROWS:
        raise ValidationFailure(
            f"The test partition has {test_indices.size} usable rows; at least {MIN_TEST_ROWS} are "
            "required.",
            details={"test_rows": int(test_indices.size)},
        )
    if train_indices.size < MIN_FIT_ROWS + MIN_VALIDATION_ROWS:
        raise ValidationFailure(
            f"The training partition has {train_indices.size} usable rows, too few to carve fit and "
            "validation partitions.",
            details={"train_rows": int(train_indices.size)},
        )

    fit_indices, validation_indices = _carve_validation(
        dataset,
        outcome=config.outcome,
        strategy=strategy,
        roles=roles,
        outcome_text=outcome_text,
        validation_fraction=config.validation_fraction,
        seed=config.seed,
        canonicalizer=canonicalizer,
        train_indices=train_indices,
    )

    overlap = set(fit_indices.tolist()) & set(test_indices.tolist())
    if overlap or set(validation_indices.tolist()) & set(test_indices.tolist()):
        raise ValidationFailure("Internal split error: the test partition overlaps a training partition.")

    design, numeric_columns, categorical_columns, design_summary = _prepare_design(
        dataset, config.predictors
    )
    X = design
    # ---- candidate comparison on validation -------------------------------- #
    candidates: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for family in families:
        pipeline = _build_pipeline(config.task, family, numeric_columns, categorical_columns, config.seed)
        try:
            pipeline.fit(X.iloc[fit_indices], y[fit_indices])
            prediction = pipeline.predict(X.iloc[validation_indices])
            if config.task == "classification":
                score = float(balanced_accuracy_score(y[validation_indices], prediction))
                metric = "balanced_accuracy"
                secondary = {
                    "accuracy": float(accuracy_score(y[validation_indices], prediction)),
                }
            else:
                rmse = float(math.sqrt(mean_squared_error(y[validation_indices], prediction)))
                score = -rmse
                metric = "-rmse"
                secondary = {"mae": float(mean_absolute_error(y[validation_indices], prediction))}
            candidates.append(
                {
                    "family": family,
                    "label": allowed[family],
                    "status": "fitted",
                    "selection_metric": metric,
                    "selection_score": score,
                    "validation": secondary,
                    "parameters": _params(pipeline),
                }
            )
            if best is None or score > best["selection_score"]:
                best = {"family": family, "pipeline": pipeline, "selection_score": score}
        except ValidationFailure:
            raise
        except Exception as exc:
            candidates.append(
                {
                    "family": family,
                    "label": allowed[family],
                    "status": "failed",
                    "error": str(exc),
                }
            )
    if best is None:
        raise ValidationFailure(
            "Every candidate estimator failed to fit on this specification.",
            details={"candidates": candidates},
        )

    # ---- one final fit and one sealed test evaluation ----------------------- #
    final_indices = np.concatenate([fit_indices, validation_indices])
    final_pipeline = _build_pipeline(
        config.task, best["family"], numeric_columns, categorical_columns, config.seed
    )
    final_pipeline.fit(X.iloc[final_indices], y[final_indices])
    test_prediction = final_pipeline.predict(X.iloc[test_indices])
    probabilities: np.ndarray | None = None
    if config.task == "classification" and hasattr(final_pipeline, "predict_proba"):
        try:
            probabilities = np.asarray(final_pipeline.predict_proba(X.iloc[test_indices]), dtype=float)
        except Exception:
            probabilities = None

    if config.task == "classification":
        binary_probabilities: np.ndarray | None = None
        if probabilities is not None and probabilities.ndim == 2 and probabilities.shape[1] == 2:
            positive_index = (
                int(np.where(np.array(outcome_meta["labels"]) == config.positive_level)[0][0])
                if config.positive_level
                else 1
            )
            binary_probabilities = probabilities[:, positive_index]
        metrics = _classification_metrics(
            y[test_indices].astype(int),
            test_prediction.astype(int),
            binary_probabilities,
            outcome_meta["labels"],
        )
        calibrated = (
            _calibration(y[test_indices].astype(float), binary_probabilities)
            if binary_probabilities is not None
            else None
        )
        predicted_ids = [
            dataset.row_ids[index] for index in test_indices[test_prediction != y[test_indices]]
        ]
        error_rows = _classification_errors(
            dataset, test_indices, y, test_prediction, binary_probabilities, outcome_meta["labels"]
        )
        diagnostics = {
            "confusion_matrix": metrics["confusion_matrix"],
            "per_class": metrics["per_class"],
            "roc_curve": metrics["roc_curve"],
            "calibration": calibrated,
            "errors": error_rows,
            "error_count": len(predicted_ids),
            "undefined": metrics["undefined"],
        }
    else:
        metrics = _regression_metrics(y[test_indices].astype(float), test_prediction.astype(float))
        residuals = y[test_indices].astype(float) - test_prediction.astype(float)
        diagnostics = {
            "residual_summary": metrics["residual_summary"],
            "sample": _regression_sample(dataset, test_indices, y, test_prediction, residuals),
            "undefined": metrics["undefined"],
        }

    subgroup = _subgroups(
        dataset=dataset,
        config=config,
        test_indices=test_indices,
        y_true=y[test_indices],
        y_pred=test_prediction,
        labels=outcome_meta.get("labels"),
        task=config.task,
    )

    # ---- preprocessing provenance (learned on fit/validation only) ---------- #
    preprocessor = final_pipeline.named_steps["pre"]
    learned: dict[str, Any] = {"numeric_medians": {}, "categorical_modes": {}}
    if "num" in preprocessor.named_transformers_:
        imputer = preprocessor.named_transformers_["num"].named_steps["impute"]
        for column, value in zip(numeric_columns, np.asarray(imputer.statistics_), strict=True):
            learned["numeric_medians"][column] = float(value)
    if "cat" in preprocessor.named_transformers_:
        imputer = preprocessor.named_transformers_["cat"].named_steps["impute"]
        for column, value in zip(categorical_columns, np.asarray(imputer.statistics_, dtype=object), strict=True):
            learned["categorical_modes"][column] = None if value is None else str(value)

    warnings: list[dict[str, str]] = []
    if int((~valid_outcome).sum()):
        warnings.append(
            {
                "code": "outcome_rows_excluded",
                "severity": "low",
                "message": (
                    f"{int((~valid_outcome).sum())} row(s) have a missing outcome and were excluded "
                    "from every partition. They cannot be scored."
                ),
            }
        )
    if test_indices.size < 30:
        warnings.append(
            {
                "code": "small_test_partition",
                "severity": "medium",
                "message": (
                    f"The test partition has {test_indices.size} rows. Metrics are imprecise and "
                    "subgroup comparisons are especially fragile."
                ),
            }
        )
    if config.task == "classification":
        counts = outcome_meta["class_counts"]
        smallest = min(counts.values())
        if smallest / max(1, sum(counts.values())) < 0.1:
            warnings.append(
                {
                    "code": "class_imbalance",
                    "severity": "medium",
                    "message": "The smallest class is below 10% of the observed outcome rows.",
                }
            )
        if metrics.get("roc_auc") is None:
            warnings.append(
                {
                    "code": "roc_undefined",
                    "severity": "low",
                    "message": "ROC-AUC is undefined for this test partition; see metrics.undefined.",
                }
            )
    if any(candidate["status"] == "failed" for candidate in candidates):
        warnings.append(
            {
                "code": "candidate_estimator_failed",
                "severity": "low",
                "message": "At least one candidate estimator failed to fit; see the candidate table.",
            }
        )
    warnings.append(
        {
            "code": "selection_uses_validation",
            "severity": "low",
            "message": (
                f"The model was selected by {candidates[[c['family'] for c in candidates].index(best['family'])]['selection_metric']} "
                "on the validation partition. The test partition was evaluated once, after selection."
            ),
        }
    )

    selection = next(candidate for candidate in candidates if candidate["family"] == best["family"])
    test_ids = [dataset.row_ids[index] for index in test_indices]
    if config.task == "classification":
        predictions = _classification_predictions(
            dataset,
            test_indices,
            y,
            test_prediction,
            binary_probabilities,
            outcome_meta["labels"],
        )
    else:
        predictions = _regression_predictions(dataset, test_indices, y, test_prediction)
    return {
        "kind": "prediction_model",
        "task": config.task,
        "specification": {
            "task": config.task,
            "outcome": config.outcome,
            "predictors": list(config.predictors),
            "positive_level": config.positive_level,
            "subgroup_column": config.subgroup_column,
            "subgroup_bins": list(config.subgroup_bins),
            "seed": config.seed,
            "validation_fraction": config.validation_fraction,
            "selection_rule": (
                "highest balanced accuracy on validation"
                if config.task == "classification"
                else "lowest RMSE on validation"
            ),
            "test_evaluations": 1,
            "notes": [
                "All learned preprocessing was fitted inside the pipeline on the fit partition only.",
                "The test partition was not read for imputation, encoding, model selection or tuning.",
                "A test metric does not prove scientific validity or deployment safety.",
            ],
        },
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "sha256": dataset.fingerprint_sha256,
            "row_count": dataset.row_count,
            "column_count": dataset.column_count,
        },
        "split": {
            "source": config.split_source,
            "strategy": strategy,
            "seed": config.seed if config.split_source == "generated" else None,
            "summary": split_summary,
            "partitions": {
                "fit": int(fit_indices.size),
                "validation": int(validation_indices.size),
                "test": int(test_indices.size),
            },
            "partition_row_ids_sha256": {
                "fit": _membership_digest([dataset.row_ids[i] for i in fit_indices]),
                "validation": _membership_digest([dataset.row_ids[i] for i in validation_indices]),
                "test": _membership_digest(test_ids),
            },
            "test_row_ids_sha256": _membership_digest(test_ids),
        },
        "outcome": outcome_meta,
        "design": {
            **design_summary,
            "numeric": numeric_columns,
            "categorical": categorical_columns,
            "preprocessing": {
                "numeric": "median imputation" + (", standardisation" if _needs_scaling(best["family"]) else ""),
                "categorical": "most-frequent imputation, one-hot encoding (unknown levels ignored)",
                "fit_partition": "fit (+ validation for the final refit)",
                "learned_on_rows": int(final_indices.size),
                "learned": learned,
            },
        },
        "candidates": candidates,
        "selected": {
            "family": best["family"],
            "label": allowed[best["family"]],
            "validation": {
                "metric": selection["selection_metric"],
                "score": selection["selection_score"],
                **selection.get("validation", {}),
            },
            "parameters": selection["parameters"],
            "refit_rows": int(final_indices.size),
        },
        "evaluation": {
            "partition": "test",
            "n": int(test_indices.size),
            "metrics": metrics,
            "diagnostics": diagnostics,
            "predictions": predictions,
        },
        "subgroups": subgroup,
        "warnings": warnings,
        "versions": _versions(),
    }


def _classification_predictions(
    dataset: Dataset,
    test_indices: np.ndarray,
    y: np.ndarray,
    prediction: np.ndarray,
    probabilities: np.ndarray | None,
    labels: list[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for position, index in enumerate(test_indices[:MAX_TEST_PREDICTIONS]):
        rows.append(
            {
                "row_id": dataset.row_ids[int(index)],
                "observed": labels[int(y[index])],
                "predicted": labels[int(prediction[position])],
                "probability_positive": (
                    float(probabilities[position]) if probabilities is not None else None
                ),
            }
        )
    return {
        "rows": rows,
        "test_rows": int(test_indices.size),
        "truncated": bool(test_indices.size > MAX_TEST_PREDICTIONS),
        "cap": MAX_TEST_PREDICTIONS,
    }


def _regression_predictions(
    dataset: Dataset,
    test_indices: np.ndarray,
    y: np.ndarray,
    prediction: np.ndarray,
) -> dict[str, Any]:
    rows = [
        {
            "row_id": dataset.row_ids[int(index)],
            "observed": float(y[index]),
            "predicted": float(prediction[position]),
        }
        for position, index in enumerate(test_indices[:MAX_TEST_PREDICTIONS])
    ]
    return {
        "rows": rows,
        "test_rows": int(test_indices.size),
        "truncated": bool(test_indices.size > MAX_TEST_PREDICTIONS),
        "cap": MAX_TEST_PREDICTIONS,
    }


def _classification_errors(
    dataset: Dataset,
    test_indices: np.ndarray,
    y: np.ndarray,
    prediction: np.ndarray,
    probabilities: np.ndarray | None,
    labels: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for position, index in enumerate(test_indices):
        truth = int(y[index])
        predicted = int(prediction[position])
        if truth == predicted:
            continue
        rows.append(
            {
                "row_id": dataset.row_ids[int(index)],
                "observed": labels[truth],
                "predicted": labels[predicted],
                "probability_positive": (
                    float(probabilities[position]) if probabilities is not None else None
                ),
            }
        )
        if len(rows) >= 25:
            break
    return rows


def _regression_sample(
    dataset: Dataset,
    test_indices: np.ndarray,
    y: np.ndarray,
    prediction: np.ndarray,
    residual: np.ndarray,
) -> dict[str, Any]:
    size = int(test_indices.size)
    stride = max(1, math.ceil(size / 500))
    positions = np.arange(0, size, stride)
    rows = [
        {
            "row_id": dataset.row_ids[int(test_indices[position])],
            "observed": float(y[test_indices[position]]),
            "predicted": float(prediction[position]),
            "residual": float(residual[position]),
        }
        for position in positions
    ]
    return {
        "method": "systematic_grid",
        "stride": stride,
        "drawn_rows": len(rows),
        "test_rows": size,
        "description": (
            f"Every {stride}th test row ({len(rows)} of {size})"
            if stride > 1
            else f"All {size} test rows"
        ),
        "rows": rows,
    }


def _params(pipeline: Pipeline) -> dict[str, Any]:
    estimator = pipeline.named_steps["model"]
    values: dict[str, Any] = {"class": type(estimator).__name__}
    for name in ("n_estimators", "min_samples_leaf", "alpha", "max_iter"):
        if hasattr(estimator, name):
            values[name] = getattr(estimator, name)
    if hasattr(estimator, "random_state"):
        values["random_state"] = getattr(estimator, "random_state")
    return values


def _versions() -> dict[str, str]:
    import scipy

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit-learn": sklearn.__version__,
        "scipy": scipy.__version__,
    }


__all__ = [
    "CLASSIFICATION_MODELS",
    "PredictionConfig",
    "REGRESSION_MODELS",
    "fit_prediction",
]
