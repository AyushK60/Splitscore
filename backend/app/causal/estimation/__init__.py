"""Scientific causal effect estimation.

This package turns a *verified graphical identification result* into a
numerically estimated average treatment effect computed from the uploaded
dataset. It is the first SplitScope stage allowed to produce a causal number,
so its contracts are correspondingly strict:

* estimation is gated on a classical backdoor adjustment set that identification itself
  verified against the stored graph - a client-supplied set is never trusted;
* treatment and outcome mappings are explicit; nothing is inferred from column
  labels;
* every payload carries row accounting, diagnostics, warnings and full
  reproducibility metadata, and never claims more than the estimator supports.

The estimators (regression adjustment, IPW, cross-fitted AIPW) live in
:mod:`app.causal.estimation.estimators`; uncertainty in
:mod:`app.causal.estimation.uncertainty`; balance/overlap diagnostics in
:mod:`app.causal.estimation.diagnostics`; and the identification gate plus
orchestration in :mod:`app.causal.estimation.service`.
"""

from app.causal.estimation.contracts import (
    ESTIMATION_SCHEMA_VERSION,
    ESTIMATOR_NAMES,
    EstimationLimits,
    EstimationRequest,
)

__all__ = [
    "ESTIMATION_SCHEMA_VERSION",
    "ESTIMATOR_NAMES",
    "EstimationLimits",
    "EstimationRequest",
]
