"""SS-TGT-002: target proxy candidates (heuristic, bounded).

Label: this is a *candidate screen*, not a leakage verdict. It flags feature
columns that are almost perfectly predictive of the target on their own and
reports why, which columns were involved, what the evidence is, and what the
method cannot say. Candidate association is not proof of leakage — a feature
can be legitimately that good.

Method (both bounded to the configured example/feature limits):

* categorical feature against a class-like target: the maximum over feature
  values of the majority-class share (purity), weighted by the value's
  coverage. A value that determines the target almost always, over a real
  share of rows, is a proxy candidate;
* numeric feature against a binary target: the best single-threshold class
  separation (decision stump). A stump that separates the classes almost
  perfectly over a real share of rows is a proxy candidate.

A candidate is only flagged when the evidence covers a documented minimum share
of rows, so a quirk of three rows cannot dominate the screen. Severity is
always ``info``: the check has no authority to claim leakage.
"""

from __future__ import annotations

import pandas as pd

from app.audit.rules.base import RuleContext, RuleOutput, format_value
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-TGT-002"
TITLE = "Target proxy candidates (heuristic screen)"

MIN_COVERAGE = 0.02  # the dominant value / stump side must cover >= 2% of rows
MIN_ROWS_PER_SIDE = 3
PURITY_THRESHOLD = 0.98
TARGET_MAX_CLASSES = 12
MAX_CANDIDATES = 5

LIMITATIONS = [
    "A flagged column is a candidate, not a finding of leakage. A feature can be "
    "almost perfectly predictive because the business process genuinely works "
    "that way (a downstream fee that is a fixed percentage of the label, a "
    "post-eligibility flag that is definitionally equivalent to the outcome). "
    "Only the person who knows the process can decide.",
    "The screen only sees single columns. Interaction proxies (two columns that "
    "are innocuous alone) are out of scope for this version.",
    "Purity and stump separation are computed on the pooled split (train and "
    "test together) because the question — 'does this column carry the target?' "
    "— does not depend on the split.",
    "Categorical purity is only computed when the target behaves like a class "
    "variable (at most "
    f"{TARGET_MAX_CLASSES} distinct values). Continuous targets are screened "
    "with single-threshold separation on binary targets only.",
    "The screen is bounded: at most "
    f"{MAX_CANDIDATES} candidates are listed, ordered by purity then coverage.",
]


def run(ctx: RuleContext) -> RuleOutput:
    target = ctx.resolved.target_column
    features = list(ctx.resolved.feature_columns)
    if target is None:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No target column was selected, so proxy candidates cannot be screened.",
            target_column="(none)",
        )

    frame = ctx.dataset.frame
    target_values = frame[target]
    target_missing = int(target_values.isna().sum() + (target_values.astype(str) == "").sum())
    classes = sorted(set(target_values.dropna().astype(str)) - {""})
    metrics: list[RuleMetric] = [
        RuleMetric(key="target_column", label="Target column", value=target),
        RuleMetric(key="target_distinct_values", label="Target distinct values", value=len(classes)),
    ]
    if not classes or len(classes) > TARGET_MAX_CLASSES:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "unsupported",
            (
                f"The target has {len(classes)} distinct value(s); the proxy screen supports "
                f"class-like targets with at most {TARGET_MAX_CLASSES}. No candidate screen ran."
            ),
            target_column=target,
            distinct_values=str(len(classes)),
        )

    screened = 0
    candidates: list[dict[str, object]] = []
    for column in features:
        values = frame[column]
        is_numeric = pd.to_numeric(values, errors="coerce").notna().mean() >= 0.8
        candidate = _screen_column(
            values, target_values, is_numeric=is_numeric, classes=classes
        )
        if candidate is None:
            continue
        screened += 1
        candidates.append(candidate)

    candidates.sort(key=lambda item: (-float(item["purity"]), -float(item["coverage"])))
    kept = candidates[:MAX_CANDIDATES]

    metrics.extend(
        [
            RuleMetric(key="features_screened", label="Feature columns with evidence", value=screened),
            RuleMetric(key="candidates_found", label="Proxy candidates flagged", value=len(candidates)),
            RuleMetric(key="purity_threshold", label="Purity threshold", value=PURITY_THRESHOLD),
            RuleMetric(key="min_coverage", label="Minimum coverage", value=MIN_COVERAGE),
        ]
    )

    if not kept:
        return RuleOutput(status="evaluated", findings=[], metrics=metrics)

    examples = [
        EvidenceExample(
            label=(
                f"Candidate '{item['column']}' — purity {float(item['purity']):.3f}, "
                f"coverage {float(item['coverage']):.1%}"
            ),
            details={
                "column": str(item["column"]),
                "method": str(item["method"]),
                "dominant_value": str(item["dominant_value"]),
                "purity": f"{float(item['purity']):.4f}",
                "coverage": f"{float(item['coverage']):.4f}",
                "evidence": str(item["evidence"]),
            },
        )
        for item in kept
    ]

    findings = [
        Finding(
            rule_id=RULE_ID,
            title=TITLE,
            severity="info",
            severity_rationale=(
                f"{len(candidates)} feature column(s) behave almost like a copy of the target "
                "under a single-column screen. The screen cannot distinguish a leaked column "
                "from a legitimately near-deterministic one, so the result is an information "
                "flag with the evidence attached, never a claim of leakage."
            ),
            description=(
                "These feature columns are nearly determined by the target (or determine it) "
                "under the documented single-column screen: "
                + ", ".join(str(item["column"]) for item in kept)
                + ". Each candidate states the measured purity, the share of rows the evidence "
                "covers and the method used. Treat them as questions for the data owner, not "
                "as proven leakage."
            ),
            evidence_summary=(
                f"{len(candidates)} candidate column(s) at or above purity "
                f"{PURITY_THRESHOLD:.2f} with coverage at least {MIN_COVERAGE:.0%}; top "
                f"{len(kept)} listed."
            ),
            counts=[
                Count(
                    label="Proxy candidate columns flagged by the screen",
                    affected=len(candidates),
                    denominator=len(features),
                    unit="columns",
                    note="Denominator is the full feature set. Screening is single-column.",
                )
            ],
            examples=examples,
            example_total=len(candidates),
            examples_truncated=len(candidates) > MAX_CANDIDATES,
            recommended_action=(
                "For each candidate, ask the data owner whether the column is knowable at "
                "prediction time and whether it is definitionally tied to the target. Remove "
                "or transform columns that fail either test; keep and document the ones that "
                "pass."
            ),
            limitations=LIMITATIONS,
            assumptions=[
                f"Purity at or above {PURITY_THRESHOLD:.2f} with coverage at least "
                f"{MIN_COVERAGE:.0%} (and at least {MIN_ROWS_PER_SIDE} rows of evidence) is "
                "worth surfacing; anything weaker would drown the screen in noise.",
                "The target behaves as a class variable for this screen because it has at most "
                f"{TARGET_MAX_CLASSES} distinct observed values.",
            ],
        )
    ]
    return RuleOutput(status="evaluated", findings=findings, metrics=metrics)


def _screen_column(
    values: pd.Series, target_values: pd.Series, *, is_numeric: bool, classes: list[str]
) -> dict[str, object] | None:
    """Screen one feature column; return a candidate record or None."""
    if is_numeric:
        return _screen_numeric(values, target_values, classes)
    return _screen_categorical(values, target_values, classes)


def _screen_categorical(
    values: pd.Series, target_values: pd.Series, classes: list[str]
) -> dict[str, object] | None:
    non_missing = values.notna() & (values.astype(str) != "")
    if not non_missing.any():
        return None
    total = int(non_missing.sum())
    pairs = pd.DataFrame({"value": values[non_missing].astype(str), "target": target_values[non_missing].astype(str)})
    best: tuple[float, str, str, int] | None = None  # purity, value, dominant class, rows
    for value, group in pairs.groupby("value"):
        if len(group) < MIN_ROWS_PER_SIDE:
            continue
        counts = group["target"].value_counts()
        purity = float(counts.iloc[0]) / len(group)
        if best is None or purity > best[0]:
            best = (purity, str(value), str(counts.index[0]), len(group))
    if best is None:
        return None
    purity, value, dominant_class, rows = best
    coverage = rows / total
    if purity < PURITY_THRESHOLD or coverage < MIN_COVERAGE:
        return None
    return {
        "column": str(values.name),
        "method": "categorical purity (majority class share of one feature value)",
        "dominant_value": format_value(value),
        "purity": purity,
        "coverage": coverage,
        "evidence": (
            f"{rows} of {total} non-missing rows carry value '{format_value(value)}', and "
            f"{purity:.1%} of them have target class '{dominant_class}' — measured over the "
            "pooled split."
        ),
    }


def _screen_numeric(
    values: pd.Series, target_values: pd.Series, classes: list[str]
) -> dict[str, object] | None:
    if len(classes) != 2:
        return None  # stump separation is defined for binary targets only
    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.notna() & target_values.notna()
    if int(valid.sum()) < 2 * MIN_ROWS_PER_SIDE:
        return None
    frame = pd.DataFrame({"x": numeric[valid], "y": target_values[valid].astype(str)})
    # Group by distinct value: the stump splits between levels, so per-level
    # class counts keep the arithmetic exact even with heavy ties.
    levels = frame.groupby("x")["y"].agg(
        positives=lambda s: int((s == classes[0]).sum()), count="size"
    )
    n = int(levels["count"].sum())
    total_positive = int(levels["positives"].sum())
    left_positive = 0
    left = 0
    best: tuple[float, float] | None = None  # purity, threshold
    for x_value, row in levels.iterrows():
        left += int(row["count"])
        left_positive += int(row["positives"])
        right = n - left
        if left < MIN_ROWS_PER_SIDE or right < MIN_ROWS_PER_SIDE:
            continue
        right_positive = total_positive - left_positive
        purity = max(left_positive / left, (left - left_positive) / left) * (left / n) + max(
            right_positive / right, (right - right_positive) / right
        ) * (right / n)
        if best is None or purity > best[0]:
            best = (purity, float(x_value))
    if best is None:
        return None
    purity, threshold = best
    coverage = 1.0  # a stump covers every parsable row; reported for parity
    if purity < PURITY_THRESHOLD or coverage < MIN_COVERAGE:
        return None
    return {
        "column": str(values.name),
        "method": "single-threshold separation (best decision stump, binary target)",
        "dominant_value": f"threshold {threshold:.6g}",
        "purity": purity,
        "coverage": coverage,
        "evidence": (
            f"A single threshold on this column separates the two target classes with "
            f"{purity:.1%} weighted purity over all {n} parsable rows."
        ),
    }


__all__ = ["LIMITATIONS", "RULE_ID", "TITLE", "run"]
