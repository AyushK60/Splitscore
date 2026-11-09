"""Statistical uncertainty for the estimation estimators.

Two honest constructions, and nothing else:

* **Influence-function intervals.** For the cross-fitted AIPW, the per-row
  pseudo-outcomes are the estimator's influence function, so
  SE = std(ψ)/√n is valid once the nuisances are cross-fitted. For the Hájek
  IPW estimator the ratio-estimator influence function is used with the
  propensity treated as fixed - a documented, typically conservative choice
  when the propensity model is correctly specified.
* **Refitting bootstrap.** Every bootstrap replicate *refits the nuisance
  models* on the resampled rows (and re-runs cross-fitting for AIPW). A
  percentile interval is formed from the replicate estimates. Bootstrapping a
  fixed point estimate is explicitly not done anywhere here.

Failures are reported, not smoothed over: replicates that fail to produce a
finite estimate are counted; if too many fail the interval is returned in an
explicit ``unavailable`` state next to the surviving point estimate. No
p-values are produced anywhere in this module.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats as scipy_stats

from app.causal.estimation.estimators import EstimatorOutput

#: A bootstrap replicate set is usable when at least this fraction of
#: replicates produced finite estimates.
MIN_BOOTSTRAP_SUCCESS_FRACTION = 0.6


@dataclass
class UncertaintyResult:
    """The interval actually reported, or its explicit absence."""

    status: str  # "available" | "unavailable"
    method: str
    level: float
    standard_error: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    unavailable_reason: str | None = None
    bootstrap: dict[str, Any] | None = None
    assumptions: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "method": self.method,
            "level": self.level,
            "standard_error": self.standard_error,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "unavailable_reason": self.unavailable_reason,
            "bootstrap": self.bootstrap,
            "assumptions": list(self.assumptions),
        }


def _z_critical(level: float) -> float:
    return float(scipy_stats.norm.ppf(1.0 - (1.0 - level) / 2.0))


INDEPENDENCE_ASSUMPTION = (
    "The interval assumes independent observations. Clustered or repeated-measure "
    "data need cluster-aware inference this stage does not provide; the interval "
    "would then be anti-conservative."
)


def influence_function_interval(output: EstimatorOutput, level: float) -> UncertaintyResult:
    """Normal-approximation interval from the estimator's influence values."""
    if output.influence is None:
        return UncertaintyResult(
            status="unavailable",
            method="influence_function",
            level=level,
            unavailable_reason=(
                "This estimator has no closed-form influence function in this implementation; "
                "request the refitting bootstrap instead."
            ),
        )
    influence = np.asarray(output.influence, dtype=float)
    n = influence.size
    if n < 2 or not np.all(np.isfinite(influence)):
        return UncertaintyResult(
            status="unavailable",
            method="influence_function",
            level=level,
            unavailable_reason="Influence values are not finite or the cohort is too small.",
        )
    se = float(np.std(influence, ddof=1) / np.sqrt(n))
    z = _z_critical(level)
    return UncertaintyResult(
        status="available",
        method="influence_function_normal_approximation",
        level=level,
        standard_error=se,
        ci_lower=output.estimate - z * se,
        ci_upper=output.estimate + z * se,
        assumptions=[
            INDEPENDENCE_ASSUMPTION,
            "The influence-function form treats nuisance-model parameters as fixed for IPW; "
            "for cross-fitted AIPW the out-of-fold construction makes the interval valid "
            "under the stated regularity conditions.",
        ],
    )


def bootstrap_interval(
    resample_fn: Callable[[np.ndarray], float],
    n_rows: int,
    *,
    level: float,
    reps: int,
    seed: int,
) -> UncertaintyResult:
    """Percentile interval from a fully refitting bootstrap.

    ``resample_fn`` receives a bootstrap index array and must re-run the whole
    estimation procedure - nuisance fitting included - returning one finite
    estimate or raising.
    """
    rng = np.random.default_rng(seed)
    values: list[float] = []
    failures = 0
    failure_messages: list[str] = []
    for _ in range(reps):
        indices = rng.integers(0, n_rows, size=n_rows)
        try:
            value = float(resample_fn(indices))
            if not np.isfinite(value):
                raise ValueError("non-finite replicate estimate")
            values.append(value)
        except Exception as error:
            failures += 1
            if len(failure_messages) < 3:
                failure_messages.append(str(error))
    succeeded = len(values)
    usable = succeeded >= MIN_BOOTSTRAP_SUCCESS_FRACTION * reps
    payload = {
        "reps_requested": reps,
        "reps_succeeded": succeeded,
        "reps_failed": failures,
        "seed": seed,
        "interval_type": "percentile",
        "refit_nuisance_models": True,
        "sample_failure_messages": failure_messages,
    }
    if not usable or succeeded < 2:
        return UncertaintyResult(
            status="unavailable",
            method="bootstrap_percentile",
            level=level,
            unavailable_reason=(
                f"Only {succeeded} of {reps} bootstrap replicates produced a finite estimate; "
                "no interval is reported rather than an unreliable one."
            ),
            bootstrap=payload,
            assumptions=[INDEPENDENCE_ASSUMPTION],
        )
    alpha = 1.0 - level
    lower, upper = np.percentile(np.asarray(values), [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return UncertaintyResult(
        status="available",
        method="bootstrap_percentile",
        level=level,
        standard_error=float(np.std(np.asarray(values), ddof=1)),
        ci_lower=float(lower),
        ci_upper=float(upper),
        bootstrap=payload,
        assumptions=[
            INDEPENDENCE_ASSUMPTION,
            "Every replicate refits the nuisance models on the resampled rows.",
        ],
    )


__all__ = [
    "MIN_BOOTSTRAP_SUCCESS_FRACTION",
    "UncertaintyResult",
    "bootstrap_interval",
    "influence_function_interval",
]
