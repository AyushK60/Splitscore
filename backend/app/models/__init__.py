"""S6 Model Lab engines.

``contracts`` holds the typed specification and bounds; ``statistics`` holds the
statsmodels-backed OLS/logistic implementation. The predictive ML engine (F10)
is a later module in the same package.
"""

from app.models.contracts import StatisticsConfig
from app.models.statistics import fit_statistics

__all__ = ["StatisticsConfig", "fit_statistics"]
