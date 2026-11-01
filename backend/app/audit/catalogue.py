"""Descriptive catalogue of the implemented checks.

Single source of truth for "what does this app actually check". The API serves it
and the documentation is generated from it, so the UI cannot advertise a check
that does not exist or describe one differently from how it behaves.
"""

from __future__ import annotations

from typing import Any

CHECKS: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "SS-DUP-001",
        "title": "Exact feature duplicates across the train/test split",
        "category": "duplicate",
        "default_enabled": True,
        "requires": [],
        "summary": (
            "Groups rows by the canonicalised tuple of selected feature columns and reports groups "
            "that contain at least one train row and at least one test row."
        ),
        "detects": [
            "Rows that are identical in every selected feature column and appear in both splits.",
            "Test rows that are exact duplicates of another test row (reported separately as "
            "within-split duplication, which is not cross-split leakage).",
        ],
        "does_not_detect": [
            "Rows that differ in a column that was not selected as a feature.",
            "Near-duplicate rows; see SS-NEAR-001.",
            "Preprocessing leakage, group leakage or temporal leakage.",
        ],
    },
    {
        "rule_id": "SS-ENT-001",
        "title": "Entity overlap between train and test splits",
        "category": "group",
        "default_enabled": True,
        "requires": ["entity"],
        "summary": (
            "Finds entity or group values that occur in both splits and reports the records those "
            "entities account for on each side."
        ),
        "detects": [
            "Entities present in both the training and the test split.",
            "Rows whose entity identifier is empty, counted separately rather than merged into one "
            "artificial entity.",
        ],
        "does_not_detect": [
            "Two identifiers for the same real entity under different spellings.",
            "Whether entity overlap is a defect for the intended task; the rule states the condition "
            "and the evaluation assumption it depends on.",
        ],
    },
    {
        "rule_id": "SS-CHR-001",
        "title": "Training records extend beyond the earliest test timestamp",
        "category": "temporal",
        "default_enabled": True,
        "requires": ["timestamp"],
        "summary": (
            "For a future-prediction evaluation, checks that no training record is timestamped "
            "strictly later than the earliest test record, and reports how far the training data "
            "extends past that boundary."
        ),
        "detects": [
            "A chronologically unordered train/test split.",
            "The magnitude of the overlap window and the number of affected training rows.",
        ],
        "does_not_detect": [
            "Temporal leakage from feature engineering: rolling windows, expanding aggregates, lag "
            "features computed before splitting, or labels that depend on later events.",
            "The intended prediction horizon; only ordering is checked.",
        ],
    },
    {
        "rule_id": "SS-TGT-001",
        "title": "Feature whose values exactly match the target",
        "category": "target",
        "default_enabled": True,
        "requires": ["target"],
        "summary": (
            "For each selected feature column, measures the fraction of rows where the feature value "
            "equals the target value over the rows where both are non-missing."
        ),
        "detects": [
            "A feature that reproduces the target value exactly or almost exactly.",
            "Reports measured coverage, the counterexamples, and the target's majority-class rate so "
            "the coverage can be judged.",
        ],
        "does_not_detect": [
            "Encoded, scaled, rounded, thresholded or one-hot transformed copies of the target.",
            "Features that correlate strongly with the target without copying it; correlation-based "
            "proxy detection is out of scope for this version.",
        ],
    },
    {
        "rule_id": "SS-NEAR-001",
        "title": "Near-duplicate candidates across the split",
        "category": "similarity",
        "default_enabled": False,
        "requires": ["features"],
        "summary": (
            "Opt-in and bounded. Compares numeric feature columns between splits with a normalised "
            "Chebyshev distance after documented diagnostic scaling, and lists the closest cross-split "
            "pairs as candidates."
        ),
        "detects": [
            "Cross-split row pairs whose largest scaled feature difference is at or below the "
            "configured threshold.",
            "Reports the distance, the top differing features with raw values, and the excluded "
            "non-numeric columns.",
        ],
        "does_not_detect": [
            "Leakage. Similarity is a screening signal, so this check never reports high severity.",
            "Near-duplicates in non-numeric columns.",
            "Dataset-wide rates when the analysis ran on a disclosed sample.",
        ],
    },
)

WHAT_THIS_APP_DOES_NOT_DO: tuple[str, ...] = (
    "It does not detect all data leakage. It implements five specific, enumerable checks.",
    "It does not prove that a model is valid, and it does not guarantee that a dataset is safe.",
    "It does not compute a combined trust score, because averaging unrelated defects hides which "
    "assumption was violated.",
    "It does not train or evaluate predictive models, so it reports no model performance.",
    "It does not inspect preprocessing pipelines; leakage introduced by a scaler, target encoder or "
    "imputer fitted on all data is outside its scope.",
    "It does not modify the uploaded dataset. Split assignments are stored separately.",
    "It supports comma-separated text files only, in this version.",
)

NO_FINDINGS_MEANS: str = (
    "'No findings' means only that the enabled checks found no supported issue in the inputs they "
    "examined. Checks listed under 'Not evaluated' did not run and must not be read as passing."
)


def catalogue_payload() -> dict[str, Any]:
    return {
        "checks": [dict(check) for check in CHECKS],
        "what_this_app_does_not_do": list(WHAT_THIS_APP_DOES_NOT_DO),
        "no_findings_means": NO_FINDINGS_MEANS,
    }


__all__ = ["CHECKS", "NO_FINDINGS_MEANS", "WHAT_THIS_APP_DOES_NOT_DO", "catalogue_payload"]
