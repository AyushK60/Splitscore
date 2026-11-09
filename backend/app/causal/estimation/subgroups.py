"""Subgroup and heterogeneous treatment-effect analysis.

Subgroup average treatment effects are computed from the **cross-fitted AIPW
estimating equation**: the pseudo-outcome

    psi_i = m1_hat(X_i) - m0_hat(X_i)
            + T_i (Y_i - m1_hat(X_i)) / e_hat(X_i)
            - (1 - T_i) (Y_i - m0_hat(X_i)) / (1 - e_hat(X_i))

is formed once on the whole analysis cohort with out-of-fold nuisance
predictions, and the subgroup ATE for group g is the average of psi within
that group. This is the group-specific estimating equation - doubly robust
under the identification assumptions plus within-group positivity - not a
filtered overall model prediction re-labelled as heterogeneity. Because the
pseudo-outcome is a per-row estimating quantity, each subgroup's uncertainty
comes from its own influence values:

    SE(ATE_g) = sd(psi | g) / sqrt(n_g),

and a between-group contrast ATE_a - ATE_b has the exact influence-function
variance  var(psi|a)/n_a + var(psi|b)/n_b (the groups are disjoint).

The nuisances are cross-fitted on the full cohort, so every subgroup summary
explicitly discloses that provenance; a subgroup result is reported only when
both arms inside the subgroup carry enough rows, and within-group propensity
extremes are surfaced as overlap warnings. A variable that is a descendant of
the treatment on the stored graph is refused outright: conditioning on a
post-treatment variable does not identify causal heterogeneity.
"""

from __future__ import annotations

import secrets
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats

from app.audit.dataset import Dataset
from app.causal.estimation.contracts import (
    ESTIMATION_SCHEMA_VERSION,
    EstimationLimits,
    EstimationRequest,
)
from app.causal.estimation.estimators import EstimationFailure, estimate_aipw
from app.causal.estimation.preparation import _covariate_parse, prepare_cohort
from app.causal.estimation.service import (
    ESTIMATION_VERSION,
    _reproducibility,
    _resolved_column,
    run_identification_gate,
)
from app.causal.identification import build_dag
from app.causal.registry import CausalGraphRecord
from app.core.errors import ValidationFailure

#: Version of the subgroup contract, echoed in every payload.
SUBGROUP_SCHEMA_VERSION = "1.0.0"

#: Hard bound on reported groups: a categorical variable with more observed
#: levels than this must be binned, level-selected or refused.
MAX_GROUPS = 8

#: Fitted-propensity values outside this window are surfaced as within-group
#: overlap warnings. They do not invalidate anything by themselves.
OVERLAP_CAUTION_LOW = 0.05
OVERLAP_CAUTION_HIGH = 0.95

NUMERIC_BINNINGS: dict[str, dict[str, Any]] = {
    "median": {"bins": 2, "quantiles": [0.0, 0.5, 1.0]},
    "tercile": {"bins": 3, "quantiles": [0.0, 1 / 3, 2 / 3, 1.0]},
    "quartile": {"bins": 4, "quantiles": [0.0, 0.25, 0.5, 0.75, 1.0]},
}

SUBGROUP_SCOPE_NOTE = (
    "Each subgroup estimate is an average treatment effect computed from the cross-fitted "
    "AIPW estimating equation on that subgroup's rows, under the same assumed graph, "
    "adjustment set and cohort as the overall analysis. Heterogeneity described here is "
    "exploratory evidence about this sample under those assumptions - not a verified "
    "mechanism and not a prediction about any individual."
)

MULTIPLE_COMPARISONS_NOTE = (
    "Several subgroup estimates and contrasts are inspected at once, so the largest "
    "observed difference is partly a selection effect. Interval overlap (or its absence) "
    "is not a test of a difference: two intervals can both contain zero while the "
    "between-group contrast is precisely non-zero, and vice versa. Read the reported "
    "contrasts, which carry their own uncertainty, instead of comparing intervals."
)


class SubgroupSpec:
    """Which baseline variable defines the subgroups, and how it is partitioned."""

    def __init__(
        self,
        node_id: str,
        numeric_binning: Literal["median", "tercile", "quartile"] = "quartile",
        levels: list[str] | None = None,
        intent: Literal["exploratory", "prespecified"] = "exploratory",
    ) -> None:
        self.node_id = node_id
        self.numeric_binning = numeric_binning
        self.levels = levels
        self.intent = intent


def _require_pretreatment(
    record: CausalGraphRecord,
    request: EstimationRequest,
    subgroup_node: str,
) -> None:
    """Refuse treatment descendants (and the treatment/outcome themselves)."""
    if subgroup_node in (request.treatment_node, request.outcome_node):
        raise ValidationFailure(
            "The subgroup variable must be a baseline variable; it cannot be the treatment "
            "or the outcome node.",
            details={"subgroup_node": subgroup_node},
        )
    dag = build_dag(record.spec)
    descendants = dag.descendants_of(request.treatment_node)
    if subgroup_node in descendants:
        raise ValidationFailure(
            "The requested subgroup variable is a descendant of the treatment on the stored "
            "graph. Conditioning on a post-treatment variable does not identify causal "
            "heterogeneity, so subgroup analysis was refused.",
            details={
                "subgroup_node": subgroup_node,
                "treatment_node": request.treatment_node,
                "fix": "Choose a variable measured before treatment, or explicitly justify in "
                "the graph that this variable is unaffected by treatment.",
            },
        )


def _categorical_groups(
    series: pd.Series, requested_levels: list[str] | None
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Level groups over the *parsed* column (missing already NaN/None)."""
    non_missing = series.dropna()
    observed = sorted({str(value) for value in non_missing.unique()})
    if requested_levels is not None:
        unknown = [level for level in requested_levels if level not in observed]
        if unknown:
            raise ValidationFailure(
                "One or more requested subgroup levels are not present in this dataset's "
                "subgroup column.",
                details={"unknown_levels": unknown, "observed_levels": observed},
            )
        levels = list(requested_levels)
    else:
        levels = observed
    if not levels:
        raise ValidationFailure(
            "The subgroup column has no observed levels to analyse.",
            details={"column_non_missing_rows": int(len(non_missing))},
        )
    if len(observed) > MAX_GROUPS and requested_levels is None:
        raise ValidationFailure(
            f"The categorical subgroup column has {len(observed)} observed levels; more than "
            f"{MAX_GROUPS} groups is refused. Select specific levels, or bin a numeric "
            "baseline variable instead.",
            details={"observed_levels": len(observed), "max_groups": MAX_GROUPS},
        )
    groups = [{"label": level, "mask": series == level} for level in levels]
    excluded_missing = int(series.isna().sum())
    return groups, excluded_missing, []


def _numeric_groups(
    series: pd.Series, binning: str
) -> tuple[list[dict[str, Any]], int, list[str]]:
    """Quantile bins with disclosed, de-duplicated edges."""
    spec = NUMERIC_BINNINGS[binning]
    values = series.dropna().astype(float)
    if values.nunique() < spec["bins"]:
        raise ValidationFailure(
            f"The numeric subgroup column has fewer distinct values ({int(values.nunique())}) "
            f"than the requested {binning} binning produces.",
            details={"distinct_values": int(values.nunique()), "requested_bins": spec["bins"]},
        )
    edges = np.unique(np.quantile(values.to_numpy(), spec["quantiles"]))
    bins = len(edges) - 1
    notes: list[str] = []
    if bins < spec["bins"]:
        notes.append(
            f"Requested {binning} binning collapsed to {bins} bin(s) because of tied values "
            "at the quantile edges; the distinct edges are reported."
        )
    labels: list[str] = []
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        if index == bins - 1:
            labels.append(f"[{low:g}, {high:g}]")
        else:
            labels.append(f"[{low:g}, {high:g})")
    masks = []
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        if index == bins - 1:
            mask = series >= low
        else:
            mask = (series >= low) & (series < high)
        masks.append(mask)
    groups = [{"label": label, "mask": mask} for label, mask in zip(labels, masks)]
    excluded_missing = int(series.isna().sum())
    return groups, excluded_missing, notes


def _group_interval(
    psi: np.ndarray,
    mask: np.ndarray,
    level: float,
) -> dict[str, Any] | None:
    """The subgroup AIPW estimating equation with influence-function uncertainty."""
    values = psi[mask & np.isfinite(psi)]
    n_group = int(values.size)
    if n_group < 2:
        return None
    estimate = float(np.mean(values))
    se = float(np.std(values, ddof=1) / np.sqrt(n_group))
    if not np.isfinite(se) or se <= 0:
        return None
    z = float(stats.norm.ppf(1.0 - (1.0 - level) / 2.0))
    return {
        "estimate": estimate,
        "standard_error": se,
        "ci_lower": estimate - z * se,
        "ci_upper": estimate + z * se,
        "interval_level": level,
        "method": "aipw_pseudo_outcome_influence_function",
    }


def run_subgroup_estimation(
    dataset: Dataset,
    record: CausalGraphRecord,
    request: EstimationRequest,
    subgroup: SubgroupSpec,
) -> dict[str, Any]:
    """Run the identification gate, then subgroup ATEs on the shared cohort."""
    gate = run_identification_gate(dataset, record, request)
    treatment_column = _resolved_column(record, request.treatment_node, "treatment")
    outcome_column = _resolved_column(record, request.outcome_node, "outcome")
    adjustment_columns = [
        _resolved_column(record, node_id, "adjustment") for node_id in request.adjustment_nodes
    ]
    _require_pretreatment(record, request, subgroup.node_id)
    subgroup_column = _resolved_column(record, subgroup.node_id, "subgroup")
    if subgroup_column in (treatment_column, outcome_column):
        raise ValidationFailure(
            "The subgroup column is the treatment or outcome column; a subgroup variable "
            "must partition the cohort, not duplicate an analysis role.",
            details={"subgroup_column": subgroup_column},
        )
    # A subgroup variable that is also an adjustment covariate is welcome: a
    # measured confounder is exactly the kind of baseline variable worth
    # stratifying on, and the estimating equation handles it unchanged.
    if subgroup_column not in dataset.columns:
        raise ValidationFailure(
            "The subgroup node anchors to a column that is not present in the dataset.",
            details={"subgroup_column": subgroup_column},
        )

    prepared = prepare_cohort(
        dataset,
        request,
        treatment_column=treatment_column,
        outcome_column=outcome_column,
        covariate_columns=adjustment_columns,
    )

    # Resolve the seed exactly as run_estimation does, so cross-fitting folds
    # share one recorded source of randomness.
    seed = request.uncertainty.seed
    if seed is None:
        seed = secrets.randbits(31)
        request = request.model_copy(deep=True)
        request.uncertainty.seed = seed

    try:
        aipw = estimate_aipw(
            prepared.frame,
            prepared.treatment,
            prepared.outcome,
            prepared.covariates,
            prepared.missing_policy,
            prepared.outcome_task,
            request,
        )
    except EstimationFailure as error:
        raise ValidationFailure(
            f"The cross-fitted AIPW estimating equation could not be computed, so no subgroup "
            f"result exists: {error.message}",
            details=error.details,
        ) from error

    psi = aipw.pseudo_outcome
    e_hat = aipw.propensity
    assert psi is not None and e_hat is not None  # both are set by estimate_aipw
    level = request.uncertainty.level

    # Type and parse the subgroup column with the *same* value-based
    # conventions the cohort preparation uses (string frames, missing tokens),
    # so subgroup membership and cohort rows never disagree.
    parsed_spec, subgroup_series = _covariate_parse(prepared.frame, subgroup_column)
    kind = parsed_spec.kind
    if kind == "numeric":
        if subgroup.numeric_binning not in NUMERIC_BINNINGS:
            raise ValidationFailure(
                f"Unknown numeric binning '{subgroup.numeric_binning}'.",
                details={"supported": list(NUMERIC_BINNINGS)},
            )
        groups, excluded_missing, definition_notes = _numeric_groups(
            subgroup_series, subgroup.numeric_binning
        )
        definition = f"Quantile bins ({subgroup.numeric_binning}) of the baseline variable"
    else:
        groups, excluded_missing, definition_notes = _categorical_groups(
            subgroup_series, subgroup.levels
        )
        definition = "Observed levels of the categorical baseline variable"

    group_payloads: list[dict[str, Any]] = []
    for group in groups:
        mask = group["mask"].to_numpy()
        n_group = int(mask.sum())
        treated = int((prepared.treatment[mask] == 1).sum())
        control = int((prepared.treatment[mask] == 0).sum())
        entry: dict[str, Any] = {
            "label": group["label"],
            "rows": n_group,
            "treated_rows": treated,
            "control_rows": control,
            "status": "estimated",
            "estimate": None,
            "standard_error": None,
            "ci_lower": None,
            "ci_upper": None,
            "warnings": [],
        }
        if treated < EstimationLimits.MIN_ROWS_PER_ARM or control < EstimationLimits.MIN_ROWS_PER_ARM:
            entry["status"] = "unavailable"
            entry["unavailable_reason"] = (
                f"This subgroup has {treated} treated and {control} control rows; at least "
                f"{EstimationLimits.MIN_ROWS_PER_ARM} rows per arm are required before a "
                "subgroup effect is estimated. No estimate was fabricated."
            )
            group_payloads.append(entry)
            continue
        interval = _group_interval(psi, mask, level)
        if interval is None:
            entry["status"] = "unavailable"
            entry["unavailable_reason"] = (
                "The influence-function standard error is not defined for this subgroup "
                "(fewer than two usable rows, or a degenerate pseudo-outcome spread)."
            )
            group_payloads.append(entry)
            continue
        entry.update(
            estimate=interval["estimate"],
            standard_error=interval["standard_error"],
            ci_lower=interval["ci_lower"],
            ci_upper=interval["ci_upper"],
        )
        group_e = e_hat[mask]
        extremes = int(((group_e < 0.01) | (group_e > 0.99)).sum())
        entry["propensity_summary"] = {
            "treated_min": float(np.min(group_e[prepared.treatment[mask] == 1])),
            "treated_max": float(np.max(group_e[prepared.treatment[mask] == 1])),
            "control_min": float(np.min(group_e[prepared.treatment[mask] == 0])),
            "control_max": float(np.max(group_e[prepared.treatment[mask] == 0])),
            "extreme_rows": extremes,
        }
        if extremes > 0:
            entry["warnings"].append(
                f"{extremes} fitted propensity score(s) inside this subgroup fall outside "
                "[0.01, 0.99]; the pseudo-outcome correction for those rows is dominated by "
                "a near-deterministic score, so the estimate is fragile."
            )
        elif (
            np.min(group_e) < OVERLAP_CAUTION_LOW or np.max(group_e) > OVERLAP_CAUTION_HIGH
        ):
            entry["warnings"].append(
                "At least one fitted propensity score inside this subgroup lies outside "
                "[0.05, 0.95]; within-group overlap is weak at the tail and the estimate "
                "relies heavily on the outcome model there."
            )
        group_payloads.append(entry)

    estimated = [entry for entry in group_payloads if entry["status"] == "estimated"]
    contrasts: list[dict[str, Any]] | None = None
    if 2 <= len(estimated) <= 4:
        contrasts = []
        n_total = prepared.rows_final
        for i in range(len(estimated)):
            for j in range(i + 1, len(estimated)):
                a, b = estimated[i], estimated[j]
                mask_a = next(g["mask"].to_numpy() for g in groups if g["label"] == a["label"])
                mask_b = next(g["mask"].to_numpy() for g in groups if g["label"] == b["label"])
                var_a = float(np.var(psi[mask_a], ddof=1))
                var_b = float(np.var(psi[mask_b], ddof=1))
                n_a, n_b = a["rows"], b["rows"]
                se_contrast = float(np.sqrt(var_a / n_a + var_b / n_b))
                difference = a["estimate"] - b["estimate"]
                z = float(stats.norm.ppf(1.0 - (1.0 - level) / 2.0))
                contrasts.append(
                    {
                        "a": a["label"],
                        "b": b["label"],
                        "difference": difference,
                        "standard_error": se_contrast,
                        "ci_lower": difference - z * se_contrast,
                        "ci_upper": difference + z * se_contrast,
                    }
                )

    overall_estimate = float(np.mean(psi[np.isfinite(psi)]))
    overall_se = float(np.std(psi[np.isfinite(psi)], ddof=1) / np.sqrt(prepared.rows_final))
    z = float(stats.norm.ppf(1.0 - (1.0 - level) / 2.0))

    reproducibility = {
        **_reproducibility(dataset, record, request, seed, ["aipw"]),
        "subgroup": {
            "node_id": subgroup.node_id,
            "column": subgroup_column,
            "kind": kind,
            "definition": definition,
            "numeric_binning": subgroup.numeric_binning if kind == "numeric" else None,
            "requested_levels": subgroup.levels,
            "intent": subgroup.intent,
        },
        "analysis_kind": "subgroups",
    }

    notes = [
        {
            "code": "pseudo_outcome_provenance",
            "text": (
                "Subgroup effects are averages of the cross-fitted AIPW pseudo-outcome, whose "
                "nuisance models were fitted out-of-fold on the whole analysis cohort (not "
                "re-fitted inside each subgroup). The subgroup estimating equation remains "
                "valid under the identification assumptions with within-group positivity; the "
                "per-group overlap warnings describe where it is fragile."
            ),
        },
        {
            "code": "intent",
            "text": (
                "This analysis is marked as **prespecified**: the subgroup definition was "
                "fixed before looking at the estimated effects."
                if subgroup.intent == "prespecified"
                else "This analysis is marked as **exploratory** (the default). Subgroup "
                "findings selected after looking at the data overstate the extremes; treat "
                "them as hypotheses for a prespecified confirmation, not as confirmed effects."
            ),
        },
        {
            "code": "multiple_comparisons",
            "text": MULTIPLE_COMPARISONS_NOTE,
        },
        *definition_notes,
    ]
    if excluded_missing > 0:
        notes.append(
            {
                "code": "subgroup_missing_excluded",
                "text": (
                    f"{excluded_missing} cohort row(s) have a missing subgroup value and are "
                    "excluded from every subgroup (they remain in the overall estimate). "
                    "Missingness in the subgroup variable is not treated as a group."
                ),
            }
        )

    return {
        "analysis_kind": "subgroups",
        "estimation_version": ESTIMATION_VERSION,
        "subgroup_schema_version": SUBGROUP_SCHEMA_VERSION,
        "estimand": request.estimand,
        "gate": gate,
        "analysis": {
            **prepared.to_payload(),
            "treatment_column": treatment_column,
            "outcome_column": outcome_column,
            "adjustment_columns": adjustment_columns,
        },
        "subgroup": {
            "node_id": subgroup.node_id,
            "column": subgroup_column,
            "kind": kind,
            "definition": definition,
            "numeric_binning": subgroup.numeric_binning if kind == "numeric" else None,
            "requested_levels": subgroup.levels,
            "bin_edges": (
                [float(edge) for edge in _numeric_edges(subgroup_series, subgroup.numeric_binning)]
                if kind == "numeric"
                else None
            ),
            "intent": subgroup.intent,
            "rows_excluded_missing": excluded_missing,
        },
        "overall": {
            "estimator": "aipw",
            "estimate": overall_estimate,
            "standard_error": overall_se,
            "ci_lower": overall_estimate - z * overall_se,
            "ci_upper": overall_estimate + z * overall_se,
            "interval_level": level,
            "note": (
                "The overall ATE on the same cohort, from the same pseudo-outcome the "
                "subgroup estimates average. It is the cohort-average effect, not a "
                "summary of the subgroup effects."
            ),
        },
        "groups": group_payloads,
        "contrasts": contrasts,
        "notes": notes,
        "reproducibility": reproducibility,
        "scope_note": SUBGROUP_SCOPE_NOTE,
    }


def _numeric_edges(series: pd.Series, binning: str) -> np.ndarray:
    spec = NUMERIC_BINNINGS[binning]
    values = series.dropna().astype(float)
    return np.unique(np.quantile(values.to_numpy(), spec["quantiles"]))


__all__ = [
    "MAX_GROUPS",
    "SUBGROUP_SCHEMA_VERSION",
    "SubgroupSpec",
    "run_subgroup_estimation",
]
