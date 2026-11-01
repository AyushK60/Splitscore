"""The leakage-check rule registry.

Order here is the order findings appear in results, reports and the UI. It is
fixed rather than discovered by scanning, so the engine's behaviour cannot change
because a module was imported in a different order.
"""

from __future__ import annotations

from app.audit.rules import (
    chronology,
    entity_overlap,
    exact_duplicates,
    near_duplicates,
    target_copy,
)
from app.audit.rules.base import Rule, RuleContext, RuleOutput

RULES: tuple[Rule, ...] = (
    exact_duplicates,
    entity_overlap,
    chronology,
    target_copy,
    near_duplicates,
)

RULE_TITLES: dict[str, str] = {rule.RULE_ID: rule.TITLE for rule in RULES}

CATEGORY_BY_RULE: dict[str, str] = {
    exact_duplicates.RULE_ID: "duplicate",
    entity_overlap.RULE_ID: "group",
    chronology.RULE_ID: "temporal",
    target_copy.RULE_ID: "target",
    near_duplicates.RULE_ID: "similarity",
}

__all__ = ["CATEGORY_BY_RULE", "RULES", "RULE_TITLES", "Rule", "RuleContext", "RuleOutput"]
