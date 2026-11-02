"""The leakage-check rule registry.

Order here is the order findings appear in results, reports and the UI. It is
fixed rather than discovered by scanning, so the engine's behaviour cannot change
because a module was imported in a different order.

S5 additions (F04) are separate typed capabilities after the five original
checks, whose definitions, severities and denominators are unchanged.
"""

from __future__ import annotations

from app.audit.rules import (
    chronology,
    entity_memorization,
    entity_overlap,
    exact_duplicates,
    feature_availability,
    near_duplicates,
    preprocessing_fit,
    target_copy,
    target_proxy,
    temporal_horizon,
    validation_reuse,
)
from app.audit.rules.base import Rule, RuleContext, RuleOutput

RULES: tuple[Rule, ...] = (
    exact_duplicates,
    entity_overlap,
    chronology,
    target_copy,
    near_duplicates,
    # -- S5 integrity capabilities (F04) -- #
    feature_availability,
    target_proxy,
    entity_memorization,
    temporal_horizon,
    preprocessing_fit,
    validation_reuse,
)

RULE_TITLES: dict[str, str] = {rule.RULE_ID: rule.TITLE for rule in RULES}

CATEGORY_BY_RULE: dict[str, str] = {
    exact_duplicates.RULE_ID: "duplicate",
    entity_overlap.RULE_ID: "group",
    chronology.RULE_ID: "temporal",
    target_copy.RULE_ID: "target",
    near_duplicates.RULE_ID: "similarity",
    feature_availability.RULE_ID: "availability",
    target_proxy.RULE_ID: "target",
    entity_memorization.RULE_ID: "group",
    temporal_horizon.RULE_ID: "temporal",
    preprocessing_fit.RULE_ID: "pipeline",
    validation_reuse.RULE_ID: "reuse",
}

__all__ = ["CATEGORY_BY_RULE", "RULES", "RULE_TITLES", "Rule", "RuleContext", "RuleOutput"]
