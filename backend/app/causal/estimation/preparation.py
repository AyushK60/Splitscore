"""Data preparation for causal estimation: cohort, treatment, outcome, covariates.

Everything here is explicit and audited. The module produces the analysis
cohort with full row accounting (counts, reasons, missingness summaries), an
explicit two-value treatment encoding, a validated numeric outcome, and typed,
*parsed* covariate columns that drive the leakage-safe preprocessing pipelines
in :mod:`app.causal.estimation.estimators`.

The dataset layer stores every uploaded column as text, so column typing is
value-based and follows the documented Model Lab convention exactly: a column
that parses fully as numbers is continuous, a column that is ≥80% unparsable
is categorical, anything in between is refused (guessing a coercion would
change the data). Missing cells and the conventional missing tokens
(``na``, ``n/a``, ``null`` …) are the same in every module.

Non-negotiables enforced here:

* the treatment mapping must cover every observed value of the treatment
  column — an ambiguous encoding is refused with the offending values listed,
  never silently resolved;
* a degenerate treatment (one arm below the minimum) is refused;
* rows are never silently dropped: every exclusion has a reason and a count,
  and the payload reports rows before and after every stage;
* preprocessing is *specified* here but *fitted* by the estimators inside
  their folds, so no transformation ever sees held-out rows (S9A leakage rule).

Column resolution (graph node → dataset column) happens in the service layer;
this module works on plain column names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import EstimationLimits, EstimationRequest
from app.core.errors import LimitExceededError, NotFoundError, ValidationFailure

TREATMENT_COLUMN = "__splitscope_treatment__"
OUTCOME_COLUMN = "__splitscope_outcome__"

NUMERIC_KIND = "numeric"
CATEGORICAL_KIND = "categorical"

#: Missing tokens, matching the Model Lab and explorer conventions verbatim.
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "missing", "?"}

#: Row-id samples kept per exclusion reason (full counts always reported).
_EXCLUSION_SAMPLE = 20


def _missing_mask(raw: pd.Series) -> np.ndarray:
    """Missing = NaN, empty cell, or a conventional missing token (case-insensitive)."""
    text = raw.astype("string").fillna("").str.strip().str.lower()
    return (raw.isna() | text.isin(MISSING_TOKENS)).to_numpy(dtype=bool)


def _numeric_parse(raw: pd.Series, missing: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Parse a column numerically. Returns (values with NaN, unparsable mask)."""
    candidate = raw.astype("string").fillna("").str.strip()
    parsed = pd.to_numeric(candidate, errors="coerce")
    values = parsed.to_numpy(dtype="float64")
    values[missing] = np.nan
    unparsed = (~missing) & np.isnan(values)
    return values, unparsed


@dataclass
class ExclusionReason:
    """One counted, explained set of excluded rows."""

    reason: str
    detail: str
    count: int
    sample_row_ids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "detail": self.detail,
            "count": self.count,
            "sample_row_ids": list(self.sample_row_ids),
        }


@dataclass
class CovariateSpec:
    """One adjustment covariate as it enters the design matrix."""

    column: str
    kind: str  # NUMERIC_KIND | CATEGORICAL_KIND
    levels: list[str] | None = None
    missing_in_cohort: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "kind": self.kind,
            "levels": list(self.levels) if self.levels else None,
            "missing_in_cohort": self.missing_in_cohort,
        }


@dataclass
class PreparedData:
    """The fully prepared analysis cohort plus its complete accounting."""

    frame: pd.DataFrame  # parsed covariate columns + treatment/outcome columns
    row_ids: list[str]
    treatment: np.ndarray  # 0/1
    outcome: np.ndarray  # float
    covariates: list[CovariateSpec]
    outcome_task: str  # "linear" | "logistic"
    outcome_coding: dict[str, Any]
    rows_dataset: int
    rows_cohort_frame: int
    rows_final: int
    treated_count: int
    control_count: int
    exclusions: list[ExclusionReason]
    missing_policy: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "rows_in_dataset": self.rows_dataset,
            "rows_in_analysis_cohort_frame": self.rows_cohort_frame,
            "rows_final": self.rows_final,
            "treated_rows": self.treated_count,
            "control_rows": self.control_count,
            "exclusions": [e.to_payload() for e in self.exclusions],
            "covariates": [c.to_payload() for c in self.covariates],
            "outcome_task": self.outcome_task,
            "outcome_coding": self.outcome_coding,
            "missing_data_policy": self.missing_policy,
        }


def _value_matches(value: Any, target: str) -> bool:
    """Match a raw cell against one requested treatment value.

    Matched by exact string equality after stripping, or by numeric equality
    when both sides parse as floats (so ``"1"`` matches ``1.0``). Nothing else
    is coerced: ``"Treated"`` does not match ``"treated"``, and no meaning is
    inferred from the column name.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    text = str(value).strip()
    wanted = target.strip()
    if text == wanted:
        return True
    try:
        return float(text) == float(wanted)
    except ValueError:
        return False


def _partition_mask(
    dataset: Dataset, request: EstimationRequest
) -> tuple[np.ndarray, ExclusionReason | None]:
    """Positional mask restricting the cohort to one named split partition."""
    if request.cohort.split_assignment_id is None:
        return np.ones(dataset.row_count, dtype=bool), None
    if request.cohort.partition is None:
        raise ValidationFailure(
            "A split assignment was named for the analysis cohort but no partition was selected.",
            details={
                "split_assignment_id": request.cohort.split_assignment_id,
                "fix": "Set cohort.partition to 'train' or 'test'.",
            },
        )
    from app.api.deps import get_context

    try:
        assignment = get_context().store.get_assignment(request.cohort.split_assignment_id)
    except NotFoundError as error:
        raise ValidationFailure(
            "The split assignment named for the analysis cohort is not available.",
            details={
                "split_assignment_id": request.cohort.split_assignment_id,
                "fix": "Re-run the split comparison, or drop the cohort restriction to use "
                "all rows.",
            },
        ) from error
    if assignment.summary.dataset_id != dataset.dataset_id:
        raise ValidationFailure(
            "The named split assignment belongs to a different dataset.",
            details={
                "split_assignment_id": request.cohort.split_assignment_id,
                "assignment_dataset_id": assignment.summary.dataset_id,
                "requested_dataset_id": dataset.dataset_id,
            },
        )
    chosen = set(
        assignment.train_row_ids
        if request.cohort.partition == "train"
        else assignment.test_row_ids
    )
    mask = np.array([row_id in chosen for row_id in dataset.row_ids], dtype=bool)
    reason = ExclusionReason(
        reason="outside_named_partition",
        detail=(
            f"Rows outside the '{request.cohort.partition}' partition of split assignment "
            f"'{request.cohort.split_assignment_id}' are not part of the declared analysis "
            "cohort. Causal estimation uses one explicit population; it does not combine a "
            "predictive fit partition with its holdout."
        ),
        count=int((~mask).sum()),
    )
    return mask, reason


def _covariate_parse(
    frame: pd.DataFrame,
    column: str,
) -> tuple[CovariateSpec, pd.Series]:
    """Type and parse one covariate column (value-based, Model Lab convention).

    Returns the spec and the parsed column: float64 with NaN for numeric
    covariates, stripped text with NaN for missing under categorical ones.
    """
    raw = frame[column]
    missing = _missing_mask(raw)
    values, unparsed = _numeric_parse(raw, missing)
    unparsable_count = int(unparsed.sum())
    non_missing = int((~missing).sum())

    if unparsable_count == 0:
        spec = CovariateSpec(column=column, kind=NUMERIC_KIND)
        spec.missing_in_cohort = int(missing.sum())
        return spec, pd.Series(values, index=frame.index)

    if unparsable_count / max(1, non_missing) < 0.8:
        raise ValidationFailure(
            f"Covariate {column!r} has {unparsable_count} value(s) that parse neither as "
            "numbers nor as missing, so it was not treated as numeric.",
            details={
                "column": column,
                "unparsable_count": unparsable_count,
                "fix": "Clean the column, or remove it from the adjustment set.",
            },
        )

    text = raw.astype("string").fillna("").str.strip()
    levels = sorted({value for value, is_missing in zip(text, missing, strict=True) if not is_missing})
    if len(levels) < 2:
        raise ValidationFailure(
            f"Covariate {column!r} has fewer than two observed levels in the analysis cohort.",
            details={"column": column, "levels": levels},
        )
    if len(levels) > EstimationLimits.MAX_CATEGORICAL_LEVELS:
        raise ValidationFailure(
            f"Covariate '{column}' has {len(levels)} distinct values, above the categorical "
            f"bound of {EstimationLimits.MAX_CATEGORICAL_LEVELS}; a column this "
            "high-cardinality is unlikely to be a confounder and would dominate the encoded "
            "design.",
            details={
                "column": column,
                "distinct_values": len(levels),
                "max_categorical_levels": EstimationLimits.MAX_CATEGORICAL_LEVELS,
            },
        )
    spec = CovariateSpec(column=column, kind=CATEGORICAL_KIND, levels=levels)
    spec.missing_in_cohort = int(missing.sum())
    parsed = text.where(~pd.Series(missing, index=frame.index), other=None).astype(object)
    parsed[missing] = None
    return spec, parsed


def prepare_cohort(
    dataset: Dataset,
    request: EstimationRequest,
    *,
    treatment_column: str,
    outcome_column: str,
    covariate_columns: list[str],
) -> PreparedData:
    """Build the analysis cohort with explicit treatment, outcome and covariates."""
    limits = EstimationLimits
    exclusions: list[ExclusionReason] = []

    partition_mask, split_exclusion = _partition_mask(dataset, request)
    if split_exclusion is not None:
        exclusions.append(split_exclusion)

    frame = dataset.frame.iloc[np.flatnonzero(partition_mask)].reset_index(drop=True)
    row_ids = [rid for rid, keep in zip(dataset.row_ids, partition_mask, strict=True) if keep]
    rows_cohort_frame = len(frame)
    if rows_cohort_frame < limits.MIN_ROWS_TOTAL:
        raise ValidationFailure(
            f"The analysis cohort has {rows_cohort_frame} rows, below the minimum of "
            f"{limits.MIN_ROWS_TOTAL} required for effect estimation.",
            details={"rows": rows_cohort_frame, "minimum": limits.MIN_ROWS_TOTAL},
        )
    if rows_cohort_frame > limits.MAX_ROWS:
        raise LimitExceededError(
            f"The analysis cohort has {rows_cohort_frame} rows, above the estimation bound of "
            f"{limits.MAX_ROWS}. Nothing was estimated.",
            details={"rows": rows_cohort_frame, "max_rows": limits.MAX_ROWS},
        )
    if len(covariate_columns) > limits.MAX_COVARIATES:
        raise ValidationFailure(
            f"{len(covariate_columns)} adjustment covariates were resolved, above the bound of "
            f"{limits.MAX_COVARIATES}.",
            details={"max_covariates": limits.MAX_COVARIATES},
        )

    # -- treatment ------------------------------------------------------------ #
    raw_treatment = frame[treatment_column]
    treat_missing = _missing_mask(raw_treatment)
    mapped = pd.Series(np.nan, index=frame.index, dtype="Float64")
    unmatched_values: dict[str, int] = {}
    for position, (value, is_missing) in enumerate(zip(raw_treatment, treat_missing, strict=True)):
        if is_missing:
            continue
        if _value_matches(value, request.treatment_mapping.treated):
            mapped.iloc[position] = 1
        elif _value_matches(value, request.treatment_mapping.control):
            mapped.iloc[position] = 0
        else:
            key = str(value).strip()
            unmatched_values[key] = unmatched_values.get(key, 0) + 1
    if unmatched_values:
        listed = sorted(unmatched_values)[:5]
        raise ValidationFailure(
            "The treatment column contains values that match neither requested treatment "
            "value, so the encoding is ambiguous and was refused.",
            details={
                "column": treatment_column,
                "requested_treated": request.treatment_mapping.treated,
                "requested_control": request.treatment_mapping.control,
                "unmatched_values_with_counts": {value: unmatched_values[value] for value in listed},
                "fix": "Map both remaining values explicitly, or restrict the cohort first. "
                "SplitScope does not guess treatment encodings.",
            },
        )
    treatment = mapped.to_numpy(dtype="float64", na_value=np.nan)
    if treat_missing.any():
        exclusions.append(
            ExclusionReason(
                reason="missing_treatment_value",
                detail="Rows with a missing treatment value cannot receive a treatment state.",
                count=int(treat_missing.sum()),
                sample_row_ids=_sample(row_ids, treat_missing),
            )
        )

    # -- outcome --------------------------------------------------------------- #
    raw_outcome = frame[outcome_column]
    raw_outcome_missing = _missing_mask(raw_outcome)
    outcome, unparsed_outcome = _numeric_parse(raw_outcome, raw_outcome_missing)
    outcome_missing = raw_outcome_missing | np.isnan(outcome)
    if raw_outcome_missing.any():
        exclusions.append(
            ExclusionReason(
                reason="missing_outcome_value",
                detail="Rows with a missing outcome value cannot contribute to the estimand.",
                count=int(raw_outcome_missing.sum()),
                sample_row_ids=_sample(row_ids, raw_outcome_missing),
            )
        )
    if unparsed_outcome.any():
        exclusions.append(
            ExclusionReason(
                reason="invalid_outcome_value",
                detail="Rows whose outcome is not a finite number (unparsable or infinite).",
                count=int(unparsed_outcome.sum()),
                sample_row_ids=_sample(row_ids, unparsed_outcome),
            )
        )

    # -- covariates ------------------------------------------------------------- #
    parsed_columns: dict[str, pd.Series] = {}
    covariates: list[CovariateSpec] = []
    for column in covariate_columns:
        if column in (treatment_column, outcome_column):
            raise ValidationFailure(
                f"Covariate '{column}' resolves to the treatment or outcome column.",
                details={"column": column},
            )
        spec, parsed = _covariate_parse(frame, column)
        covariates.append(spec)
        parsed_columns[column] = parsed

    keep = ~(treat_missing | outcome_missing)

    if request.missing_data_policy == "complete_case":
        per_column: dict[str, int] = {}
        for spec in covariates:
            column_missing = parsed_columns[spec.column].isna().to_numpy()
            if column_missing.any():
                newly = column_missing & keep
                if newly.any():
                    per_column[spec.column] = int(newly.sum())
                keep = keep & ~column_missing
        if per_column:
            exclusions.append(
                ExclusionReason(
                    reason="missing_covariate_complete_case",
                    detail="Complete-case policy: rows missing any adjustment covariate are "
                    "excluded. Per-column newly-excluded counts: "
                    + ", ".join(f"{col}={count}" for col, count in sorted(per_column.items()))
                    + ". Substantial complete-case exclusion can itself bias the analysis; the "
                    "per-covariate missingness summary is reported so it can be judged.",
                    count=int((~keep & ~(treat_missing | outcome_missing)).sum()),
                )
            )

    kept_positions = np.flatnonzero(keep)
    final_treatment = treatment[kept_positions]
    final_outcome = outcome[kept_positions]
    treated_count = int((final_treatment == 1).sum())
    control_count = int((final_treatment == 0).sum())
    if treated_count < limits.MIN_ROWS_PER_ARM or control_count < limits.MIN_ROWS_PER_ARM:
        raise ValidationFailure(
            "A treatment arm is too small for estimation.",
            details={
                "treated_rows": treated_count,
                "control_rows": control_count,
                "minimum_per_arm": limits.MIN_ROWS_PER_ARM,
                "fix": "Check the treatment mapping and cohort; a degenerate arm cannot "
                "support an average treatment effect.",
            },
        )

    final_frame = frame.iloc[kept_positions].reset_index(drop=True)
    for spec in covariates:
        parsed = parsed_columns[spec.column].iloc[kept_positions].reset_index(drop=True)
        if spec.kind == CATEGORICAL_KIND:
            parsed = parsed.where(parsed.notna(), other=None)
        final_frame[spec.column] = parsed
    final_frame[TREATMENT_COLUMN] = final_treatment.astype(int)
    final_frame[OUTCOME_COLUMN] = final_outcome
    final_row_ids = [row_ids[i] for i in kept_positions]

    outcome_task, outcome_coding = _outcome_task(final_outcome)
    if outcome_task == "logistic":
        # Explicit recoding to 0/1 per the recorded coding; the raw values are
        # reported in outcome_coding so the probability difference is always
        # interpretable.
        coded_one = outcome_coding["coded_one"]
        final_outcome = (final_outcome == coded_one).astype(float)
        outcome_coding["recoded_to_zero_one"] = True
    final_frame[OUTCOME_COLUMN] = final_outcome

    return PreparedData(
        frame=final_frame,
        row_ids=final_row_ids,
        treatment=final_treatment.astype(int),
        outcome=final_outcome,
        covariates=covariates,
        outcome_task=outcome_task,
        outcome_coding=outcome_coding,
        rows_dataset=dataset.row_count,
        rows_cohort_frame=rows_cohort_frame,
        rows_final=len(final_row_ids),
        treated_count=treated_count,
        control_count=control_count,
        exclusions=exclusions,
        missing_policy=request.missing_data_policy,
    )


def _sample(row_ids: list[str], mask: np.ndarray) -> list[str]:
    positions = np.flatnonzero(np.asarray(mask, dtype=bool))
    return [row_ids[i] for i in positions[:_EXCLUSION_SAMPLE]]


def _outcome_task(outcome: np.ndarray) -> tuple[str, dict[str, Any]]:
    values = outcome[~np.isnan(outcome)]
    distinct = np.unique(values)
    if len(distinct) == 2:
        low, high = sorted(float(v) for v in distinct)
        return "logistic", {
            "kind": "binary",
            "coded_one": high,
            "coded_zero": low,
            "interpretation": (
                "The estimate is a difference in probabilities for the outcome value "
                f"{high} (coded 1) versus {low} (coded 0)."
            ),
        }
    return "linear", {
        "kind": "continuous",
        "interpretation": "The estimate is in the outcome's own units.",
    }


__all__ = [
    "CATEGORICAL_KIND",
    "MISSING_TOKENS",
    "NUMERIC_KIND",
    "OUTCOME_COLUMN",
    "TREATMENT_COLUMN",
    "CovariateSpec",
    "ExclusionReason",
    "PreparedData",
    "prepare_cohort",
]
