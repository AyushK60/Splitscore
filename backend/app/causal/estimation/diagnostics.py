"""Covariate-balance and overlap/positivity diagnostics for estimation (estimation UI will render them).

Balance. Standardized mean differences (SMDs) per covariate, computed twice:
unweighted (pre-weighting) and, when propensity weights are supplied,
Hájek-weighted (post-weighting). Categorical covariates are compared through
binary level indicators - a well-defined category-level comparison, reported
per level. An SMD is a *descriptive* statistic: no threshold on it verifies
exchangeability, and this module never claims that it does.

Overlap. Real numerical summaries of the fitted propensity distribution:
arm-wise quantiles, extremes, weight summaries and Kish effective sample
sizes. Empirical overlap in this dataset is carefully distinguished from the
theoretical positivity assumption - a dataset cannot prove that every
covariate stratum had positive treatment probability in the population.

Every function returns structured numbers for estimation UI to render; nothing here
pre-renders graphs.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.causal.estimation.preparation import (
    NUMERIC_KIND,
    CovariateSpec,
)

EXTREME_LOW = 0.01
EXTREME_HIGH = 0.99

#: Fixed histogram geometry for the propensity-overlap figure. Twenty bins of
#: width 0.05 is the smallest resolution that shows the shape of both arms
#: without turning the payload into a row dump: 42 integers, no raw scores.
#: The bins are held constant so two runs are always directly comparable.
HISTOGRAM_BINS = 20

BALANCE_NOTE = (
    "Standardized mean differences are descriptive summaries of covariate balance in this "
    "sample. Denominator convention: the pooled term uses the population-form (non-debiased) "
    "variance, (squared treated SD + squared control SD) / 2, applied identically to the "
    "unweighted and weighted comparisons so pre/post values are mutually consistent. No SMD "
    "threshold (conventional or otherwise) constitutes a test of exchangeability or proof that "
    "confounding has been removed; balance can only be assessed relative to the adjustment set "
    "that graphical identification licensed."
)

POSITIVITY_NOTE = (
    "These are empirical overlap diagnostics for the fitted propensity distribution in this "
    "dataset. The theoretical positivity assumption - every analysed stratum having positive "
    "probability of both treatment states in the population - cannot be verified by any "
    "dataset, and these diagnostics neither establish nor refute it."
)


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    total = float(np.sum(weights))
    if total <= 0:
        return float("nan")
    return float(np.sum(weights * values) / total)


def _weighted_variance(values: np.ndarray, weights: np.ndarray) -> float:
    total = float(np.sum(weights))
    if total <= 0:
        return float("nan")
    mean = _weighted_mean(values, weights)
    return float(np.sum(weights * (values - mean) ** 2) / total)


def _smd(
    values: np.ndarray,
    treatment: np.ndarray,
    weights: np.ndarray | None,
) -> float | None:
    """Standardized mean difference (treated - control), optionally weighted.

    Returns None when the denominator is degenerate (both arms constant),
    which is reported as null rather than a fake zero.
    """
    t_mask = treatment == 1
    c_mask = treatment == 0
    t_values = values[t_mask]
    c_values = values[c_mask]
    if weights is None:
        t_w = np.ones(t_values.size)
        c_w = np.ones(c_values.size)
    else:
        t_w = weights[t_mask]
        c_w = weights[c_mask]
    if t_values.size == 0 or c_values.size == 0:
        return None
    var_t = _weighted_variance(t_values, t_w)
    var_c = _weighted_variance(c_values, c_w)
    pooled = (var_t + var_c) / 2.0
    if pooled <= 0 or not np.isfinite(pooled):
        return None
    return float(
        (_weighted_mean(t_values, t_w) - _weighted_mean(c_values, c_w)) / np.sqrt(pooled)
    )


def _covariate_values(frame: pd.DataFrame, spec: CovariateSpec) -> tuple[np.ndarray, list[dict[str, Any]] | None]:
    if spec.kind == NUMERIC_KIND:
        return frame[spec.column].to_numpy(dtype=float), None
    # Categorical: binary indicators per observed level; missing cells match
    # no level.
    raw = frame[spec.column].astype("string").fillna("")
    indicators = []
    for level in spec.levels or []:
        indicators.append({"level": level, "values": (raw.str.strip() == level).to_numpy(dtype=float)})
    return np.zeros(len(frame)), indicators


def balance_payload(
    frame: pd.DataFrame,
    treatment: np.ndarray,
    covariates: list[CovariateSpec],
    weights: np.ndarray | None = None,
) -> dict[str, Any]:
    """Pre-weighting SMDs for every covariate, plus post-weighting SMDs when weights exist."""
    covariate_payloads: list[dict[str, Any]] = []
    for spec in covariates:
        values, indicators = _covariate_values(frame, spec)
        if indicators is None:
            covariate_payloads.append(
                {
                    "column": spec.column,
                    "kind": spec.kind,
                    "level": None,
                    "smd_unweighted": _smd(values, treatment, None),
                    "smd_weighted": _smd(values, treatment, weights) if weights is not None else None,
                }
            )
        else:
            for indicator in indicators:
                covariate_payloads.append(
                    {
                        "column": spec.column,
                        "kind": spec.kind,
                        "level": indicator["level"],
                        "smd_unweighted": _smd(indicator["values"], treatment, None),
                        "smd_weighted": (
                            _smd(indicator["values"], treatment, weights)
                            if weights is not None
                            else None
                        ),
                    }
                )
    return {
        "covariates": covariate_payloads,
        "weighted": weights is not None,
        "interpretation_note": BALANCE_NOTE,
    }


def kish_ess(weights: np.ndarray) -> float:
    """Kish effective sample size: (Σw)² / Σw²."""
    total = float(np.sum(weights))
    if total <= 0:
        return 0.0
    return float(total**2 / np.sum(weights**2))


def _quantiles(values: np.ndarray, quantiles: list[float]) -> dict[str, float]:
    return {str(q): float(np.quantile(values, q)) for q in quantiles}


def _arm_shares(counts: np.ndarray) -> list[float]:
    total = float(np.sum(counts))
    if total <= 0:
        return [0.0 for _ in counts]
    return [float(value) / total for value in counts]


def propensity_histogram(propensity: np.ndarray, treatment: np.ndarray) -> dict[str, Any]:
    """Bounded, aggregated propensity distribution for the overlap figure.

    Fixed bins over the closed unit interval, counted separately per arm, plus
    each arm's within-arm relative frequency. This is the smallest payload that
    supports an honest overlaid histogram: counts and shares only, never scores
    or row identifiers, so no uploaded row can be reconstructed from it.
    """
    edges = np.linspace(0.0, 1.0, HISTOGRAM_BINS + 1)
    treated_counts, _ = np.histogram(propensity[treatment == 1], bins=edges)
    control_counts, _ = np.histogram(propensity[treatment == 0], bins=edges)
    return {
        "bin_edges": [round(float(edge), 6) for edge in edges],
        "bin_count": HISTOGRAM_BINS,
        "treated_counts": [int(value) for value in treated_counts],
        "control_counts": [int(value) for value in control_counts],
        "treated_share": [round(value, 8) for value in _arm_shares(treated_counts)],
        "control_share": [round(value, 8) for value in _arm_shares(control_counts)],
        "definition": (
            "Counts of fitted propensity scores in 20 fixed bins of width 0.05 over [0, 1]; "
            "shares are relative frequencies within each arm, so the two arms are comparable "
            "despite unequal group sizes. The scores are fitted estimates, not true treatment "
            "probabilities."
        ),
    }


def overlap_payload(
    propensity: np.ndarray,
    treatment: np.ndarray,
    outcome: np.ndarray,
    weights: np.ndarray | None = None,
    truncation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Empirical overlap/positivity diagnostics from the fitted propensities."""
    t_mask = treatment == 1
    c_mask = treatment == 0
    quantile_levels = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
    summary = {
        "min": float(np.min(propensity)),
        "max": float(np.max(propensity)),
        "quantiles_overall": _quantiles(propensity, quantile_levels),
        "quantiles_treated": _quantiles(propensity[t_mask], quantile_levels),
        "quantiles_control": _quantiles(propensity[c_mask], quantile_levels),
    }
    extreme_low = int((propensity < EXTREME_LOW).sum())
    extreme_high = int((propensity > EXTREME_HIGH).sum())
    extremes = {
        "below_0.01": extreme_low,
        "above_0.99": extreme_high,
        "count_definition": "fitted propensity strictly outside [0.01, 0.99]",
    }

    w1 = treatment / np.maximum(propensity, np.finfo(float).eps)
    w0 = (1.0 - treatment) / np.maximum(1.0 - propensity, np.finfo(float).eps)
    all_weights = w1 + w0
    ess = {
        "treated_rows_unweighted": int(t_mask.sum()),
        "control_rows_unweighted": int(c_mask.sum()),
        "treated_ess_weighted": kish_ess(w1),
        "control_ess_weighted": kish_ess(w0),
    }
    weight_summary = {
        "max_individual_weight": float(np.max(all_weights)),
        "quantiles_total_weight": _quantiles(all_weights, [0.5, 0.95, 0.99]),
    }

    warnings: list[str] = []
    if extreme_low or extreme_high:
        warnings.append(
            f"{extreme_low + extreme_high} fitted propensity score(s) fall outside "
            "[0.01, 0.99]; the weighted estimators lean on very few rows there and the "
            "effective sample size below reflects it."
        )
    if summary["quantiles_treated"]["0.01"] > summary["quantiles_control"]["0.99"]:
        warnings.append(
            "The treated arm's lowest propensity region lies above the control arm's highest: "
            "the two arms barely overlap empirically, and model-based extrapolation dominates "
            "the estimate in that region."
        )
    for arm in ("treated", "control"):
        arm_ess = ess[f"{arm}_ess_weighted"]
        arm_rows = ess[f"{arm}_rows_unweighted"]
        if arm_rows > 0 and arm_ess < 0.25 * arm_rows:
            warnings.append(
                f"The {arm} arm's effective sample size ({arm_ess:.1f}) is below a quarter of "
                f"its row count ({arm_rows}); the weights are highly variable."
            )
    if truncation is not None:
        warnings.append(
            "Propensity truncation was applied as explicitly requested; the diagnostics above "
            "describe the untruncated fitted scores, and the estimate describes the truncated "
            "estimand."
        )

    return {
        "propensity_summary": summary,
        "propensity_histogram": propensity_histogram(propensity, treatment),
        "extremes": extremes,
        "effective_sample_sizes": ess,
        "weight_summary": weight_summary,
        "warnings": warnings,
        "scope_note": POSITIVITY_NOTE,
        "truncation": truncation,
    }


__all__ = [
    "BALANCE_NOTE",
    "EXTREME_HIGH",
    "EXTREME_LOW",
    "POSITIVITY_NOTE",
    "balance_payload",
    "propensity_histogram",
    "kish_ess",
    "overlap_payload",
]
