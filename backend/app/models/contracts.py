"""Typed contracts and bounds for the S6 Model Lab.

The contracts are deliberately small and explicit. A statistical fit is defined
by: the task, the outcome, the predictors, the missing-data policy, whether an
intercept is included, the reference level for every categorical predictor, the
binary outcome coding, and the confidence level. Nothing else is inferred at fit
time; anything the user did not specify is reported back as a default that was
applied, with the value it took.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping

Task = Literal["ols", "logistic"]
MissingPolicy = Literal["complete_case", "fail"]

TASKS: tuple[Task, ...] = ("ols", "logistic")
MISSING_POLICIES: tuple[MissingPolicy, ...] = ("complete_case", "fail")

#: Hard bounds. They are enforced before a model is fitted, and the reason is
#: reported. A model is never silently fitted on a subsample: changing the
#: analysed population changes the estimand.
MAX_MODEL_ROWS = 10_000
MAX_PREDICTORS = 30
MAX_CATEGORICAL_LEVELS = 12
MIN_MODEL_ROWS = 12
MIN_ROWS_PER_PARAMETER = 5
SMALL_SAMPLE_PARAMETERS = 10
MAX_DIAGNOSTIC_POINTS = 1_200
VIF_WARNING = 10.0
CONDITION_WARNING = 1e6

TASK_LABELS = {
    "ols": "Ordinary least squares (numeric outcome)",
    "logistic": "Binary logistic regression (two-level outcome)",
}


@dataclass(frozen=True)
class StatisticsConfig:
    """A fully explicit statistical specification."""

    task: Task
    outcome: str
    predictors: tuple[str, ...]
    missing_policy: MissingPolicy = "complete_case"
    intercept: bool = True
    positive_level: str | None = None
    categorical_references: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    alpha: float = 0.05

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task,
            "outcome": self.outcome,
            "predictors": list(self.predictors),
            "missing_policy": self.missing_policy,
            "intercept": self.intercept,
            "positive_level": self.positive_level,
            "categorical_references": dict(self.categorical_references),
            "alpha": self.alpha,
        }


__all__ = [
    "CONDITION_WARNING",
    "MISSING_POLICIES",
    "MAX_CATEGORICAL_LEVELS",
    "MAX_DIAGNOSTIC_POINTS",
    "MAX_MODEL_ROWS",
    "MAX_PREDICTORS",
    "MIN_MODEL_ROWS",
    "MIN_ROWS_PER_PARAMETER",
    "MissingPolicy",
    "SMALL_SAMPLE_PARAMETERS",
    "StatisticsConfig",
    "TASK_LABELS",
    "TASKS",
    "Task",
    "VIF_WARNING",
]
