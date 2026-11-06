"""Seeded generators for the bundled synthetic demonstration datasets.

Every generator is a pure function of a seed: the same seed produces byte-identical
output, so the committed CSVs can be regenerated and verified. Each generator also
reports the *planted cases* it created, by row position, so the shipped manifest can
name the exact rows that carry each planted defect.

These are synthetic teaching datasets. They contain no real people, no real
transactions and no real measurements.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

SPLIT_TRAIN = "train"
SPLIT_TEST = "test"


@dataclass(frozen=True)
class DemoSpec:
    """Metadata plus the builder for one demonstration dataset."""

    demo_id: str
    title: str
    subtitle: str
    filename: str
    seed: int
    teaching_point: str
    generation_method: str
    expected_findings: list[dict[str, str]]
    recommended_audit: dict[str, Any]
    recommended_split: dict[str, Any] | None
    is_control: bool
    notes: list[str] = field(default_factory=list)
    build: Callable[[], tuple[pd.DataFrame, dict[str, Any]]] = field(repr=False, default=lambda: (pd.DataFrame(), {}))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _shuffle_with_seed(records: list[dict[str, Any]], seed: int) -> tuple[list[dict[str, Any]], np.ndarray]:
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(records))
    return [records[i] for i in order.tolist()], order


# --------------------------------------------------------------------------- #
# 1. Repeated-entity classification data
# --------------------------------------------------------------------------- #


def build_repeated_entity() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Customer-month panel with several rows per customer.

    Churn is a property of the customer, and the shipped split assigns those rows
    at random, so most customers end up on both sides of the boundary.
    """
    seed = 20240101
    rng = np.random.default_rng(seed)
    n_customers = 40
    rows_per_customer = 6

    records: list[dict[str, Any]] = []
    customer_split: dict[str, list[str]] = {}
    for index in range(n_customers):
        customer_id = f"C-{1000 + index}"
        base_tenure = float(rng.integers(2, 60))
        base_spend = float(np.round(rng.normal(62.0, 18.0), 2))
        base_tickets = int(rng.poisson(2.4))
        base_session = float(np.round(rng.normal(21.0, 5.5), 2))
        logit = 0.045 * (base_tickets - 2.4) - 0.03 * (base_spend - 62.0) / 10.0 - 0.01 * (base_tenure - 30)
        churn_probability = 1.0 / (1.0 + np.exp(-logit))
        churned = "yes" if rng.random() < churn_probability else "no"

        for month in range(rows_per_customer):
            records.append(
                {
                    "customer_id": customer_id,
                    "month_index": month,
                    "tenure_months": int(base_tenure + month),
                    "monthly_spend": round(base_spend + float(rng.normal(0.0, 3.5)), 2),
                    "support_tickets": max(0, base_tickets + int(rng.integers(-1, 2))),
                    "avg_session_minutes": round(base_session + float(rng.normal(0.0, 1.8)), 2),
                    "churned": churned,
                }
            )

    # Random split that ignores the entity, which is exactly the mistake the demo
    # is about.
    split_rng = np.random.default_rng(seed + 1)
    test_flags = split_rng.random(len(records)) < 0.25
    for record, is_test in zip(records, test_flags.tolist(), strict=True):
        record["split"] = SPLIT_TEST if is_test else SPLIT_TRAIN
        customer_split.setdefault(record["customer_id"], []).append(record["split"])

    frame = pd.DataFrame.from_records(records)
    shared_customers = sorted(
        customer for customer, labels in customer_split.items() if len(set(labels)) > 1
    )
    test_rows = int((frame["split"] == SPLIT_TEST).sum())

    planted = {
        "shared_entities": len(shared_customers),
        "shared_entity_examples": shared_customers[:5],
        "customers_total": n_customers,
        "rows_per_customer": rows_per_customer,
        "test_rows": test_rows,
        "train_rows": len(frame) - test_rows,
        "planted_cases": [
            {
                "kind": "shared_entity",
                "description": "Customer appears in both the train and the test split.",
                "entity_column": "customer_id",
                "entities": shared_customers[:5],
            }
        ],
    }
    return frame, planted


# --------------------------------------------------------------------------- #
# 2. Exact cross-split duplicates
# --------------------------------------------------------------------------- #


def build_exact_duplicates() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Order-level rows with copies deliberately placed on both sides.

    25 base rows are duplicated with one copy in train and one in test. A further
    10 train-only rows and 5 test-only rows are duplicated *within* their own
    split, so the report can show that within-split duplication is a different
    thing from cross-split duplication.
    """
    seed = 20240202
    rng = np.random.default_rng(seed)
    n_base = 80
    n_cross = 25
    n_within_train = 10
    n_within_test = 5

    base_rows = []
    for _ in range(n_base):
        base_rows.append(
            {
                "region": str(rng.choice(["north", "south", "east", "west"])),
                "channel": str(rng.choice(["web", "app", "partner"])),
                "units": int(rng.integers(1, 25)),
                "unit_price": round(float(rng.uniform(4.5, 220.0)), 2),
                "is_promo": int(rng.integers(0, 2)),
                "converted": int(rng.integers(0, 2)),
            }
        )

    cross_sources = base_rows[:n_cross]
    rest = base_rows[n_cross:]
    rest_order = rng.permutation(len(rest))
    rest_train = [rest[i] for i in rest_order[:40]]
    rest_test = [rest[i] for i in rest_order[40:]]

    records: list[dict[str, Any]] = []

    for row in cross_sources:
        records.append({**row, "split": SPLIT_TRAIN})
        records.append({**row, "split": SPLIT_TEST})

    for row in rest_train:
        records.append({**row, "split": SPLIT_TRAIN})
    for row in rest_test:
        records.append({**row, "split": SPLIT_TEST})

    # One further copy each: the original is already in the list from the bulk
    # loops above, so each of these groups ends up with exactly two members.
    for row in rest_train[:n_within_train]:
        records.append({**row, "split": SPLIT_TRAIN})
    for row in rest_test[:n_within_test]:
        records.append({**row, "split": SPLIT_TEST})

    records, _ = _shuffle_with_seed(records, seed + 1)
    frame = pd.DataFrame.from_records(records)

    # Positions changed with the shuffle, so recover them from the data itself:
    # a planted cross-split case is a feature signature present on both sides.
    feature_columns = ["region", "channel", "units", "unit_price", "is_promo"]
    signature = frame[feature_columns].astype(str).agg("|".join, axis=1)
    train_signatures = set(signature[frame["split"] == SPLIT_TRAIN])
    test_signatures = set(signature[frame["split"] == SPLIT_TEST])
    shared = sorted(train_signatures & test_signatures)
    duplicated_within_test = sorted(
        value for value in test_signatures if int((signature == value).sum()) > 1
    )

    planted_cases = [
        {
            "kind": "cross_split_duplicate_group",
            "description": "A feature signature appears in both splits.",
            "signature": value,
            "train_row_ids": [
                f"row-{index + 1:06d}"
                for index in frame.index[(signature == value) & (frame["split"] == SPLIT_TRAIN)].tolist()
            ],
            "test_row_ids": [
                f"row-{index + 1:06d}"
                for index in frame.index[(signature == value) & (frame["split"] == SPLIT_TEST)].tolist()
            ],
        }
        for value in shared[:5]
    ]
    planted_cases.append(
        {
            "kind": "within_split_duplicate_groups",
            "description": "Duplicated copies that both sit inside the test split, so they are not "
            "cross-split leakage.",
            "groups": len(duplicated_within_test),
            "rows": int(
                sum(int((signature == value).sum()) for value in duplicated_within_test)
            ),
        }
    )

    planted = {
        "feature_columns": feature_columns,
        "cross_split_duplicate_groups": len(shared),
        "cross_split_duplicate_test_rows": int(
            (signature.isin(shared) & (frame["split"] == SPLIT_TEST)).sum()
        ),
        "cross_split_duplicate_train_rows": int(
            (signature.isin(shared) & (frame["split"] == SPLIT_TRAIN)).sum()
        ),
        "within_test_duplicate_groups": len(duplicated_within_test),
        "within_train_duplicate_groups": int(
            sum(
                1
                for value in train_signatures
                if int((signature == value).sum()) > 1
                and int(((signature == value) & (frame["split"] == SPLIT_TEST)).sum()) == 0
            )
        ),
        "intended_cross_pairs": n_cross,
        "intended_within_train_pairs": n_within_train,
        "intended_within_test_pairs": n_within_test,
        "planted_cases": planted_cases,
    }
    return frame, planted


# --------------------------------------------------------------------------- #
# 3. Timestamped data with an inappropriate random split
# --------------------------------------------------------------------------- #


def build_chronology_violation() -> tuple[pd.DataFrame, dict[str, Any]]:
    """A drifting daily process, split at random instead of by time."""
    seed = 20240303
    rng = np.random.default_rng(seed)
    n_rows = 360

    timestamps = pd.date_range("2023-01-01", periods=n_rows, freq="D", tz="UTC")
    seconds = rng.integers(0, 86400, size=n_rows)
    observed = pd.to_datetime(timestamps) + pd.to_timedelta(seconds, unit="s")

    trend = np.linspace(0.0, 9.0, n_rows)
    season = 3.0 * np.sin(np.linspace(0.0, 6.0 * np.pi, n_rows))
    sensor_a = np.round(50.0 + trend + season + rng.normal(0.0, 1.4, size=n_rows), 3)
    sensor_b = np.round(12.0 + 0.4 * trend + rng.normal(0.0, 0.9, size=n_rows), 3)
    throughput = np.round(300.0 + 12.0 * trend + rng.normal(0.0, 18.0, size=n_rows), 2)
    defect_logit = -1.1 + 0.09 * (throughput - 340.0) / 10.0
    defect_probability = 1.0 / (1.0 + np.exp(-defect_logit))
    defect = (rng.random(n_rows) < defect_probability).astype(int)

    split_rng = np.random.default_rng(seed + 1)
    is_test = split_rng.random(n_rows) < 0.25

    frame = pd.DataFrame(
        {
            "event_ts": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "device_id": [f"D-{(index % 6) + 1:02d}" for index in range(n_rows)],
            "sensor_a": sensor_a,
            "sensor_b": sensor_b,
            "throughput": throughput,
            "defect": defect,
            "split": np.where(is_test, SPLIT_TEST, SPLIT_TRAIN),
        }
    )

    parsed = pd.to_datetime(frame["event_ts"], utc=True)
    train_max = parsed[frame["split"] == SPLIT_TRAIN].max()
    test_min = parsed[frame["split"] == SPLIT_TEST].min()
    affected = int(((frame["split"] == SPLIT_TRAIN) & (parsed > test_min)).sum())
    train_rows = int((frame["split"] == SPLIT_TRAIN).sum())

    plant = {
        "earliest_test_timestamp": test_min.isoformat(),
        "latest_train_timestamp": train_max.isoformat(),
        "train_rows_after_earliest_test": affected,
        "train_rows": train_rows,
        "test_rows": int((frame["split"] == SPLIT_TEST).sum()),
        "order_violation": bool(train_max > test_min),
        "planted_cases": [
            {
                "kind": "random_split_on_temporal_data",
                "description": "A random holdout puts training records later than the earliest test "
                "record, so the split cannot estimate future performance.",
                "earliest_test_timestamp": test_min.isoformat(),
                "train_rows_after_earliest_test": affected,
                "train_row_ids_example": [
                    f"row-{index + 1:06d}"
                    for index in frame.index[
                        (frame["split"] == SPLIT_TRAIN) & (parsed > test_min)
                    ].tolist()[:5]
                ],
            }
        ],
    }
    return frame, plant


# --------------------------------------------------------------------------- #
# 4. A feature that copies the target
# --------------------------------------------------------------------------- #


def build_target_copy() -> tuple[pd.DataFrame, dict[str, Any]]:
    """An account table where one feature *is* the label and another nearly is."""
    seed = 20240404
    rng = np.random.default_rng(seed)
    n_rows = 240

    account_age = np.round(rng.gamma(2.4, 240.0, size=n_rows), 2)
    logins_30d = np.round(rng.poisson(14.0, size=n_rows).astype(float), 0)
    avg_order_value = np.round(rng.normal(72.0, 21.0, size=n_rows), 2)

    risk_logit = -0.35 + 0.028 * (logins_30d - 14.0) - 0.006 * (avg_order_value - 72.0)
    churn_probability = 1.0 / (1.0 + np.exp(-risk_logit))
    churn_flag = (rng.random(n_rows) < churn_probability).astype(int)

    risk_score = churn_flag.copy()
    flip_mask = rng.random(n_rows) < 0.07
    risk_band = np.where(flip_mask, 1 - churn_flag, churn_flag)

    split_rng = np.random.default_rng(seed + 1)
    is_test = split_rng.random(n_rows) < 0.25

    frame = pd.DataFrame(
        {
            "account_ref": [f"A-{5000 + index}" for index in range(n_rows)],
            "account_age_days": account_age,
            "logins_30d": logins_30d,
            "avg_order_value": avg_order_value,
            "risk_score": risk_score,
            "risk_band": risk_band,
            "churn_flag": churn_flag,
            "split": np.where(is_test, SPLIT_TEST, SPLIT_TRAIN),
        }
    )

    exact_matches = int((frame["risk_score"] == frame["churn_flag"]).sum())
    near_matches = int((frame["risk_band"] == frame["churn_flag"]).sum())
    baseline = float(frame["churn_flag"].value_counts(normalize=True).max())

    plant = {
        "exact_copy_feature": "risk_score",
        "exact_copy_coverage": round(exact_matches / n_rows, 6),
        "near_copy_feature": "risk_band",
        "near_copy_coverage": round(near_matches / n_rows, 6),
        "target": "churn_flag",
        "target_majority_rate": round(baseline, 6),
        "planted_cases": [
            {
                "kind": "target_copy_feature",
                "description": "risk_score equals churn_flag on every row.",
                "feature": "risk_score",
                "coverage": round(exact_matches / n_rows, 6),
            },
            {
                "kind": "partial_target_copy_feature",
                "description": "risk_band equals churn_flag on all but the deliberately flipped rows.",
                "feature": "risk_band",
                "coverage": round(near_matches / n_rows, 6),
                "flipped_rows": int(flip_mask.sum()),
            },
        ],
    }
    return frame, plant


# --------------------------------------------------------------------------- #
# 5. Clean control
# --------------------------------------------------------------------------- #


def build_clean_control() -> tuple[pd.DataFrame, dict[str, Any]]:
    """A clean control for all four enabled checks, under a chronological split.

    Deliberately constructed so that the *shipped* split passes every enabled
    check: timestamps ascend with the split, entity identifiers are unique so no
    entity can straddle the boundary, features are continuous and distinct so no
    two rows share a feature signature, and no feature reproduces the target.
    """
    seed = 20240505
    rng = np.random.default_rng(seed)
    n_rows = 240

    x1 = np.round(rng.normal(0.0, 1.0, size=n_rows), 4)
    x2 = np.round(rng.normal(5.0, 2.0, size=n_rows), 4)
    x3 = np.round(rng.uniform(-3.0, 3.0, size=n_rows), 4)
    segment = rng.choice(["alpha", "beta", "gamma"], size=n_rows)
    label = (rng.random(n_rows) < 0.5).astype(int)

    timestamps = pd.date_range("2024-01-01", periods=n_rows, freq="6h", tz="UTC")
    split_index = int(round(n_rows * 0.75))
    split = np.where(np.arange(n_rows) < split_index, SPLIT_TRAIN, SPLIT_TEST)

    frame = pd.DataFrame(
        {
            "record_key": [f"R-{900000 + index}" for index in range(n_rows)],
            "entity_id": [f"E-{7000 + index}" for index in range(n_rows)],
            "created_at": timestamps.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "x1": x1,
            "x2": x2,
            "x3": x3,
            "segment": segment,
            "label": label,
            "split": split,
        }
    )

    parsed = pd.to_datetime(frame["created_at"], utc=True)
    train_max = parsed[frame["split"] == SPLIT_TRAIN].max()
    test_min = parsed[frame["split"] == SPLIT_TEST].min()

    plant = {
        "control": True,
        "train_rows": int((frame["split"] == SPLIT_TRAIN).sum()),
        "test_rows": int((frame["split"] == SPLIT_TEST).sum()),
        "latest_train_timestamp": train_max.isoformat(),
        "earliest_test_timestamp": test_min.isoformat(),
        "chronology_ordered": bool(train_max <= test_min),
        "distinct_entities": int(frame["entity_id"].nunique()),
        "planted_cases": [],
        "control_baseline": {
            "expected": "No findings from any of the four enabled checks with the shipped "
            "chronological split.",
            "check_expectations": {
                "SS-DUP-001": "no findings: every row has a distinct feature signature",
                "SS-ENT-001": "no findings: entity identifiers are unique, so no entity straddles the boundary",
                "SS-CHR-001": "no findings: the shipped split is chronological",
                "SS-TGT-001": "no findings: no feature reproduces the label",
            },
        },
    }
    return frame, plant


# --------------------------------------------------------------------------- #
# 6. Numeric near-duplicate example
# --------------------------------------------------------------------------- #


def build_near_duplicates() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Part measurements where some parts were measured twice with small jitter.

    The pairs are placed so that one copy is in train and one in test, which makes
    them cross-split near-duplicate candidates. They are *not* exact duplicates, so
    SS-DUP-001 should stay clean and the opt-in SS-NEAR-001 should find them.
    """
    seed = 20240606
    rng = np.random.default_rng(seed)
    n_unique = 240
    n_pairs = 20

    length = rng.normal(120.0, 14.0, size=n_unique)
    width = rng.normal(60.0, 8.0, size=n_unique)
    height = rng.normal(25.0, 4.0, size=n_unique)
    mass = rng.normal(340.0, 46.0, size=n_unique)
    grade = rng.choice(["A", "B", "C"], size=n_unique)

    iqr_scale = {"length_mm": 1.349 * 14.0, "width_mm": 1.349 * 8.0, "height_mm": 1.349 * 4.0, "mass_g": 1.349 * 46.0}
    jitter_fraction = 0.015

    records: list[dict[str, Any]] = []
    for index in range(n_unique):
        records.append(
            {
                "item_id": f"P-{3000 + index}",
                "length_mm": round(float(length[index]), 3),
                "width_mm": round(float(width[index]), 3),
                "height_mm": round(float(height[index]), 3),
                "mass_g": round(float(mass[index]), 3),
                "grade": str(grade[index]),
                "split": SPLIT_TEST if index < n_pairs else SPLIT_TRAIN,
            }
        )

    pair_positions: list[list[int]] = []
    for index in range(n_pairs):
        twin = {
            "item_id": f"P-{3000 + index}-R",
            "length_mm": round(float(length[index] + rng.uniform(-jitter_fraction, jitter_fraction) * iqr_scale["length_mm"]), 3),
            "width_mm": round(float(width[index] + rng.uniform(-jitter_fraction, jitter_fraction) * iqr_scale["width_mm"]), 3),
            "height_mm": round(float(height[index] + rng.uniform(-jitter_fraction, jitter_fraction) * iqr_scale["height_mm"]), 3),
            "mass_g": round(float(mass[index] + rng.uniform(-jitter_fraction, jitter_fraction) * iqr_scale["mass_g"]), 3),
            "grade": str(grade[index]),
            "split": SPLIT_TRAIN,
        }
        records.append(twin)
        pair_positions.append([index, len(records) - 1])

    # Remaining rows were already labelled train by the loop above; rebalance the
    # bulk rows so that the test side is not only the planted pairs.
    bulk_order = rng.permutation(n_unique - n_pairs)
    n_bulk_test = int(round((n_unique - n_pairs) * 0.25))
    test_bulk = {int(index) for index in bulk_order[:n_bulk_test].tolist()}
    for index in range(n_pairs, n_unique):
        records[index]["split"] = SPLIT_TEST if (index - n_pairs) in test_bulk else SPLIT_TRAIN

    frame = pd.DataFrame.from_records(records)

    feature_columns = ["length_mm", "width_mm", "height_mm", "mass_g"]
    planted = {
        "feature_columns": feature_columns,
        "near_duplicate_pairs": n_pairs,
        "jitter_fraction_of_iqr": jitter_fraction,
        "max_possible_scaled_distance": round(6 * jitter_fraction, 6),
        "recommended_threshold": 0.05,
        "test_rows": int((frame["split"] == SPLIT_TEST).sum()),
        "train_rows": int((frame["split"] == SPLIT_TRAIN).sum()),
        "planted_cases": [
            {
                "kind": "near_duplicate_pair",
                "description": "One part measured twice with small jitter, one copy in train and one "
                "in test.",
                "train_row_id": f"row-{train_position + 1:06d}",
                "test_row_id": f"row-{test_position + 1:06d}",
                "item_id": frame.loc[test_position, "item_id"] if test_position < len(frame) else None,
            }
            for test_position, train_position in pair_positions
        ],
    }
    return frame, planted


# --------------------------------------------------------------------------- #
# 7. Confounded treatment-effect study (S9B demonstration)
# --------------------------------------------------------------------------- #


def build_causal_effect() -> tuple[pd.DataFrame, dict[str, Any]]:
    """A binary treatment with a known, constant average effect of 1.5 units.

    Two measured confounders (``age``, ``baseline_score``) and a categorical one
    (``region``) drive both the treatment assignment and the outcome, so the
    naive treated-minus-control difference is biased away from the true effect
    while an adjusted estimator recovers it in expectation. The data-generating
    process is fully documented in the demo spec, and the true effect is stored
    in the planted metadata so the studio can display it *next to* (never
    instead of) the finite-sample estimate the backend computes.

    No true propensity or potential-outcome column is shipped: those are not
    observable quantities in real data, and exposing them would let an
    estimator read the answer instead of estimating it.
    """
    seed = 20240901
    rng = np.random.default_rng(seed)
    n_rows = 1200

    age = np.clip(np.round(rng.normal(42.0, 11.0, size=n_rows), 0), 18, 80)
    baseline = np.round(rng.normal(50.0, 12.0, size=n_rows), 2)
    region = rng.choice(["north", "south", "east"], size=n_rows, p=[0.40, 0.35, 0.25])
    region_treatment = np.where(region == "south", 0.5, np.where(region == "east", -0.35, 0.0))
    region_outcome = np.where(region == "south", 0.8, np.where(region == "east", -0.6, 0.0))

    logit = -0.9 + 0.035 * (age - 42.0) + 0.02 * (baseline - 50.0) + region_treatment
    propensity = 1.0 / (1.0 + np.exp(-logit))
    treatment = (rng.random(n_rows) < propensity).astype(int)

    true_effect = 1.5
    outcome = np.round(
        10.0
        + true_effect * treatment
        + 0.25 * (age - 42.0)
        + 0.12 * (baseline - 50.0)
        + region_outcome
        + rng.normal(0.0, 2.0, size=n_rows),
        3,
    )

    # A random split exists only so the file is a normal audit input; the causal
    # analysis cohort is every row unless a researcher names a partition.
    split_rng = np.random.default_rng(seed + 1)
    split = np.where(split_rng.random(n_rows) < 0.25, SPLIT_TEST, SPLIT_TRAIN)

    frame = pd.DataFrame(
        {
            "unit_id": [f"U-{5000 + index}" for index in range(n_rows)],
            "age": age.astype(int),
            "baseline_score": baseline,
            "region": region,
            "treatment": treatment,
            "outcome": outcome,
            "split": split,
        }
    )

    treated = frame["treatment"] == 1
    naive_difference = float(
        frame.loc[treated, "outcome"].mean() - frame.loc[~treated, "outcome"].mean()
    )
    plant = {
        "true_ate": true_effect,
        "rows": int(len(frame)),
        "treated_rows": int(treated.sum()),
        "control_rows": int((~treated).sum()),
        "naive_difference_in_units": round(naive_difference, 4),
        "fitted_propensity_range": [round(float(propensity.min()), 4), round(float(propensity.max()), 4)],
        "split": {"train_rows": int((frame["split"] == SPLIT_TRAIN).sum()), "test_rows": int((frame["split"] == SPLIT_TEST).sum())},
        "planted_cases": [],
    }
    return frame, plant


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

DEMO_ORDER = (
    "repeated_entity",
    "exact_duplicates",
    "chronology_violation",
    "target_copy",
    "near_duplicates",
    "clean_control",
    "causal_effect",
)

DEMOS: dict[str, DemoSpec] = {
    "repeated_entity": DemoSpec(
        demo_id="repeated_entity",
        title="Repeated-entity subscription panel",
        subtitle="Several months per customer, split at random across the boundary",
        filename="repeated_entity.csv",
        seed=20240101,
        teaching_point=(
            "A random holdout on panel data puts most customers on both sides of the boundary. The "
            "test set then measures performance on customers the model has already seen, which is "
            "the wrong estimate if deployment must serve new customers. A group holdout on the same "
            "entity column removes the overlap."
        ),
        generation_method=(
            "Per-customer latent tenure, spend and ticket rate drawn from seeded NumPy "
            "distributions; six monthly rows per customer with per-row noise; churn drawn once per "
            "customer so the label is an entity-level property; split assigned by an independent "
            "seeded Bernoulli draw that ignores the customer."
        ),
        expected_findings=[
            {
                "rule_id": "SS-ENT-001",
                "severity": "high",
                "why": "Most customers have rows in both splits, so a large share of the test split "
                "belongs to an entity present in training.",
            },
            {
                "rule_id": "SS-DUP-001",
                "severity": "none",
                "why": "Feature values are continuous with per-row noise, so no two rows share an "
                "exact feature signature.",
            },
        ],
        recommended_audit={
            "features": ["tenure_months", "monthly_spend", "support_tickets", "avg_session_minutes"],
            "target": "churned",
            "entity": "customer_id",
            "timestamp": None,
            "split": "split",
            "split_train_value": SPLIT_TRAIN,
            "split_test_value": SPLIT_TEST,
            "metadata_excluded": ["month_index"],
            "near_duplicates": False,
        },
        recommended_split={"kind": "group", "test_fraction": 0.25, "seed": 12345},
        is_control=False,
        notes=[
            "The label is constant within a customer. Whether that is a defect depends on the "
            "prediction task: for an entity-level target, a group holdout is the honest split.",
        ],
        build=build_repeated_entity,
    ),
    "exact_duplicates": DemoSpec(
        demo_id="exact_duplicates",
        title="Order table with cross-split duplicate rows",
        subtitle="Copies of the same order placed deliberately on both sides of the boundary",
        filename="exact_duplicates.csv",
        seed=20240202,
        teaching_point=(
            "Exact duplicates that straddle the boundary make the test set partially remembered "
            "training data. The same file also contains duplicates that sit entirely inside one "
            "split; the report separates those two cases because only the first is cross-split "
            "leakage."
        ),
        generation_method=(
            "80 unique seeded order rows; 25 of them duplicated with one copy labelled train and the "
            "other test; 10 further rows duplicated inside train and 5 inside test; row order "
            "shuffled with a seeded permutation."
        ),
        expected_findings=[
            {
                "rule_id": "SS-DUP-001",
                "severity": "high",
                "why": "25 test rows share an exact feature signature with a training row, which is "
                "both above 10 rows and far above 5% of the test split.",
            },
            {
                "rule_id": "SS-ENT-001",
                "severity": "not_evaluated",
                "why": "No entity column is selected for this audit.",
            },
        ],
        recommended_audit={
            "features": ["region", "channel", "units", "unit_price", "is_promo"],
            "target": "converted",
            "entity": None,
            "timestamp": None,
            "split": "split",
            "split_train_value": SPLIT_TRAIN,
            "split_test_value": SPLIT_TEST,
            "metadata_excluded": [],
            "near_duplicates": False,
        },
        recommended_split={"kind": "random", "test_fraction": 0.25, "seed": 12345},
        is_control=False,
        build=build_exact_duplicates,
    ),
    "chronology_violation": DemoSpec(
        demo_id="chronology_violation",
        title="Drifting sensor stream split at random",
        subtitle="A temporal process whose train/test split ignores time",
        filename="chronology_violation.csv",
        seed=20240303,
        teaching_point=(
            "When the intended evaluation predicts forward in time, a random split trains on records "
            "from the future. The chronology check reports how far the training data extends past "
            "the earliest test record; a chronological holdout removes the violation."
        ),
        generation_method=(
            "360 daily observations with a linear drift, a six-cycle seasonal term and seeded noise; "
            "the defect rate rises with throughput; the split is an independent seeded Bernoulli "
            "draw that ignores the timestamp entirely."
        ),
        expected_findings=[
            {
                "rule_id": "SS-CHR-001",
                "severity": "high",
                "why": "A random split leaves the great majority of training rows newer than the "
                "earliest test timestamp, far above the 2% high-severity threshold.",
            },
            {
                "rule_id": "SS-DUP-001",
                "severity": "none",
                "why": "Sensor readings are continuous with noise, so no feature signature repeats.",
            },
        ],
        recommended_audit={
            "features": ["sensor_a", "sensor_b", "throughput"],
            "target": "defect",
            "entity": None,
            "timestamp": "event_ts",
            "split": "split",
            "split_train_value": SPLIT_TRAIN,
            "split_test_value": SPLIT_TEST,
            "metadata_excluded": ["device_id"],
            "near_duplicates": False,
        },
        recommended_split={"kind": "chronological", "test_fraction": 0.25, "seed": 12345},
        is_control=False,
        notes=[
            "device_id is present in the file but is not assigned the entity role, so SS-ENT-001 "
            "reports itself as not evaluated. Assign it to see the group check in action.",
        ],
        build=build_chronology_violation,
    ),
    "target_copy": DemoSpec(
        demo_id="target_copy",
        title="Account table with a target-copy feature",
        subtitle="One column is the label, another nearly is",
        filename="target_copy.csv",
        seed=20240404,
        teaching_point=(
            "A feature that reproduces the label turns the evaluation into a copy test. The check "
            "reports measured coverage rather than a verdict, and reports the counterexamples that "
            "bound the claim."
        ),
        generation_method=(
            "240 seeded accounts; churn drawn from a logistic function of logins and order value; "
            "risk_score set equal to the churn flag on every row; risk_band set equal to it on all "
            "but a seeded 7% of rows; split assigned by an independent seeded draw."
        ),
        expected_findings=[
            {
                "rule_id": "SS-TGT-001",
                "severity": "high",
                "why": "risk_score equals churn_flag on 100% of comparable rows, above the 99% "
                "high-severity threshold.",
            },
            {
                "rule_id": "SS-TGT-001",
                "severity": "medium",
                "why": "risk_band matches the target on roughly 93% of rows: above the 90% reporting "
                "threshold and above the majority-class rate, but below 99%.",
            },
        ],
        recommended_audit={
            "features": [
                "account_age_days",
                "logins_30d",
                "avg_order_value",
                "risk_score",
                "risk_band",
            ],
            "target": "churn_flag",
            "entity": None,
            "timestamp": None,
            "split": "split",
            "split_train_value": SPLIT_TRAIN,
            "split_test_value": SPLIT_TEST,
            "metadata_excluded": ["account_ref"],
            "near_duplicates": False,
        },
        recommended_split={"kind": "stratified", "test_fraction": 0.25, "seed": 12345},
        is_control=False,
        build=build_target_copy,
    ),
    "near_duplicates": DemoSpec(
        demo_id="near_duplicates",
        title="Part measurements with re-measured parts",
        subtitle="Some parts were measured twice with small jitter",
        filename="near_duplicates.csv",
        seed=20240606,
        teaching_point=(
            "Exact-duplicate detection misses near duplicates. The opt-in distance check finds them, "
            "but its output is a bounded list of candidates under a stated distance definition, not a "
            "finding of leakage: it is a screening step that needs a human decision."
        ),
        generation_method=(
            "280 unique seeded parts across four continuous measurements; 20 of them re-measured with "
            "uniform jitter of at most 1.5% of each column's interquartile range, with the original "
            "labelled test and the re-measurement labelled train; remaining rows split at random."
        ),
        expected_findings=[
            {
                "rule_id": "SS-NEAR-001",
                "severity": "medium",
                "why": "Around 20 cross-split pairs fall within the default 0.05 threshold in robustly "
                "scaled units, matching the planted re-measurements.",
            },
            {
                "rule_id": "SS-DUP-001",
                "severity": "none",
                "why": "The jittered copies are not exactly equal, so no feature signature is shared.",
            },
        ],
        recommended_audit={
            "features": ["length_mm", "width_mm", "height_mm", "mass_g"],
            "target": "grade",
            "entity": None,
            "timestamp": None,
            "split": "split",
            "split_train_value": SPLIT_TRAIN,
            "split_test_value": SPLIT_TEST,
            "metadata_excluded": ["item_id"],
            "near_duplicates": True,
        },
        recommended_split={"kind": "random", "test_fraction": 0.25, "seed": 12345},
        is_control=False,
        notes=[
            "SS-NEAR-001 is opt-in. The recommended audit configuration for this demo enables it.",
            "Near-duplicate output is candidate evidence. Raising the threshold widens the candidate "
            "list; it does not make the pairs more likely to be leakage.",
        ],
        build=build_near_duplicates,
    ),
    "clean_control": DemoSpec(
        demo_id="clean_control",
        title="Clean control dataset",
        subtitle="No planted leakage under the shipped chronological split",
        filename="clean_control.csv",
        seed=20240505,
        teaching_point=(
            "A control that should produce nothing. It shows the difference between 'no findings' and "
            "'not evaluated', and it shows that the checks fire when the same file is split "
            "inappropriately: a random holdout on this file raises the chronology check."
        ),
        generation_method=(
            "240 seeded rows with independent continuous features, a balanced label, unique record and "
            "entity identifiers, strictly increasing six-hourly timestamps, and a chronological 75/25 "
            "split."
        ),
        expected_findings=[
            {
                "rule_id": "SS-DUP-001",
                "severity": "none",
                "why": "Every row has a distinct feature signature.",
            },
            {
                "rule_id": "SS-ENT-001",
                "severity": "none",
                "why": "Entity identifiers are unique per row, so no entity value appears in both "
                "splits. The check runs and reports nothing.",
            },
            {
                "rule_id": "SS-CHR-001",
                "severity": "none",
                "why": "The shipped split is chronological, so no training row is newer than the "
                "earliest test row.",
            },
            {
                "rule_id": "SS-TGT-001",
                "severity": "none",
                "why": "No feature reproduces the label.",
            },
        ],
        recommended_audit={
            "features": ["x1", "x2", "x3", "segment"],
            "target": "label",
            "entity": "entity_id",
            "timestamp": "created_at",
            "split": "split",
            "split_train_value": SPLIT_TRAIN,
            "split_test_value": SPLIT_TEST,
            "metadata_excluded": ["record_key"],
            "near_duplicates": False,
        },
        recommended_split=None,
        is_control=True,
        notes=[
            "Entity identifiers are unique, so a group holdout on this file is equivalent to a random "
            "holdout. That is a property of the control, not of group splitting in general.",
        ],
        build=build_clean_control,
    ),
    "causal_effect": DemoSpec(
        demo_id="causal_effect",
        title="Confounded treatment-effect study",
        subtitle="A known average effect of 1.5 units behind measured confounding",
        filename="causal_effect.csv",
        seed=20240901,
        teaching_point=(
            "The treated and control groups differ in age, baseline score and region, and all "
            "three also shift the outcome, so the raw difference in means is not the causal "
            "effect. Adjusting for the measured confounders recovers an estimate close to the "
            "true 1.5-unit effect, while the demonstration's honest caveat remains: recovery "
            "here is a property of a known simulation with no unmeasured confounding."
        ),
        generation_method=(
            "1200 seeded rows. age ~ N(42, 11) clipped to [18, 80]; baseline_score ~ N(50, 12); "
            "region drawn from north/south/east with probabilities (0.40, 0.35, 0.25). Treatment "
            "is Bernoulli with logit = -0.9 + 0.035(age - 42) + 0.02(baseline_score - 50) + "
            "region shift (+0.5 south, -0.35 east). Outcome = 10 + 1.5*treatment + "
            "0.25(age - 42) + 0.12(baseline_score - 50) + region shift (+0.8 south, -0.6 east) + "
            "N(0, 2). A random 75/25 train/test column is included for the audit stages; the "
            "causal cohort is every row unless a partition is named. No true propensity or "
            "potential-outcome column is shipped."
        ),
        expected_findings=[
            {
                "rule_id": "SS-DUP-001",
                "severity": "none",
                "why": "Every row has a distinct measured signature, so no cross-split duplicate "
                "rows exist.",
            },
            {
                "rule_id": "SS-ENT-001",
                "severity": "none",
                "why": "unit_id is unique per row, so no entity straddles the split boundary.",
            },
        ],
        recommended_audit={
            "features": ["age", "baseline_score", "region"],
            "target": "outcome",
            "entity": "unit_id",
            "timestamp": None,
            "split": "split",
            "split_train_value": SPLIT_TRAIN,
            "split_test_value": SPLIT_TEST,
            "metadata_excluded": [],
            "near_duplicates": False,
        },
        recommended_split=None,
        is_control=False,
        notes=[
            "This dataset exists for the Effect Estimation Studio: it is the only bundled demo "
            "with a binary treatment and a continuous outcome.",
            "The true effect is a property of the simulation that generated the file. It is not "
            "available to SplitScope at estimation time and is never used to compute a result.",
        ],
        build=build_causal_effect,
    ),
}


def build_demo(demo_id: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    if demo_id not in DEMOS:
        raise KeyError(f"Unknown demo id: {demo_id}")
    return DEMOS[demo_id].build()


__all__ = [
    "DEMOS",
    "DEMO_ORDER",
    "DemoSpec",
    "build_chronology_violation",
    "build_clean_control",
    "build_causal_effect",
    "build_demo",
    "build_exact_duplicates",
    "build_near_duplicates",
    "build_repeated_entity",
    "build_target_copy",
]
