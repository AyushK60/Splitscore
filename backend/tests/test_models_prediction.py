"""Independent oracles for the S6 predictive engine (F10).

The expectations are recomputed here from the stored test predictions:

* confusion matrices, per-class precision/recall/F1 and balanced accuracy are
  rebuilt by hand from the row-level predictions;
* regression MAE/RMSE/R² are recomputed with numpy from the same rows;
* the learned numeric median is compared with the median of the *training*
  rows, on a fixture where a global median would be visibly different;
* the sealed-test contract is asserted structurally: candidates carry only
  validation scores and the test partition is evaluated once.

These tests do not import or reuse the production metric helpers.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core.errors import ValidationFailure
from app.models.prediction import PredictionConfig, fit_prediction

TRAIN_VALUE = "train"
TEST_VALUE = "test"


def _classification_rows(n_train: int = 120, n_test: int = 120, seed: int = 7) -> list[dict]:
    """Binary outcome with a test-only feature shift and 20% missing predictors."""
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for index in range(n_train + n_test):
        is_test = index >= n_train
        latent = float(rng.normal())
        label = "yes" if latent > 0 else "no"
        value = float(rng.normal(0, 1))
        if is_test:
            value = 1000.0 + float(rng.normal(0, 5))
        if rng.random() < 0.2:
            numeric: float | None = None
        else:
            numeric = value
        rows.append(
            {
                "x": numeric,
                "segment": ["a", "a", "a", "a", "a", "a", "b", "c", None][index % 9],
                "split": TEST_VALUE if is_test else TRAIN_VALUE,
                "outcome": label,
            }
        )
    return rows


def _classification_config(**overrides) -> PredictionConfig:
    values = {
        "task": "classification",
        "outcome": "outcome",
        "predictors": ("x",),
        "positive_level": "yes",
        "split_source": "existing",
        "seed": 99,
        "models": ("baseline", "logistic"),
    }
    values.update(overrides)
    return PredictionConfig(**values)


def _roles() -> dict[str, list[str]]:
    return {
        "x": ["feature"],
        "segment": ["feature"],
        "split": ["split"],
        "outcome": ["target"],
    }


def test_classification_metrics_match_hand_computed_confusion_matrix(dataset_factory):
    dataset = dataset_factory(_classification_rows())
    result = fit_prediction(
        dataset,
        _classification_config(),
        roles=_roles(),
        split_labels=(TRAIN_VALUE, TEST_VALUE),
    )

    rows = result["evaluation"]["predictions"]["rows"]
    labels = result["outcome"]["labels"]
    assert len(rows) == result["evaluation"]["n"] == 120
    assert {row["row_id"] for row in rows} == {
        row_id for row_id, row in zip(dataset.row_ids, dataset.frame.itertuples(), strict=True)
        if row.split == TEST_VALUE
    }

    index = {label: position for position, label in enumerate(labels)}
    matrix = np.zeros((len(labels), len(labels)), dtype=int)
    for row in rows:
        matrix[index[row["observed"]], index[row["predicted"]]] += 1
    metrics = result["evaluation"]["metrics"]
    assert matrix.tolist() == metrics["confusion_matrix"]
    assert int(matrix.sum()) == metrics["n"] == 120

    accuracy = float(np.trace(matrix) / matrix.sum())
    assert metrics["accuracy"] == pytest.approx(accuracy, abs=1e-12)

    recalls: list[float] = []
    for position, entry in enumerate(metrics["per_class"]):
        support = int(matrix[position].sum())
        predicted = int(matrix[:, position].sum())
        true_positive = int(matrix[position, position])
        assert entry["support"] == support
        assert entry["predicted"] == predicted
        assert entry["precision"] == pytest.approx(
            true_positive / predicted if predicted else None, abs=1e-12
        )
        assert entry["recall"] == pytest.approx(
            true_positive / support if support else None, abs=1e-12
        )
        if support and predicted:
            f1 = 2 * true_positive / (support + predicted)
            assert entry["f1"] == pytest.approx(f1, abs=1e-12)
        if support:
            recalls.append(true_positive / support)
    assert metrics["balanced_accuracy"] == pytest.approx(float(np.mean(recalls)), abs=1e-12)

    if metrics["roc_auc"] is not None:
        assert 0.0 <= metrics["roc_auc"] <= 1.0
        curve = metrics["roc_curve"]
        # JSON has no infinity: every published threshold must be finite, while
        # the curve itself still ends at the (1, 1) corner.
        assert all(math.isfinite(value) for value in curve["thresholds"])
        assert curve["fpr"][-1] == 1.0 and curve["tpr"][-1] == 1.0
        assert all(0.0 <= value <= 1.0 for value in curve["fpr"] + curve["tpr"])


def test_preprocessing_is_fitted_on_training_rows_only(dataset_factory):
    rows = _classification_rows()
    dataset = dataset_factory(rows)
    result = fit_prediction(
        dataset,
        _classification_config(),
        roles=_roles(),
        split_labels=(TRAIN_VALUE, TEST_VALUE),
    )

    train_values = [
        row["x"] for row in rows if row["split"] == TRAIN_VALUE and row["x"] is not None
    ]
    all_values = [row["x"] for row in rows if row["x"] is not None]
    train_median = float(np.median(train_values))
    global_median = float(np.median(all_values))

    learned = result["design"]["preprocessing"]["learned"]["numeric_medians"]["x"]
    assert learned == pytest.approx(train_median, abs=1e-12)
    # The test partition sits two orders of magnitude away, so an imputer fitted
    # on the concatenated frame would report a different median. This is the
    # concrete leakage signature the test is guarding against.
    assert global_median != pytest.approx(train_median, abs=1e-6)
    assert learned != pytest.approx(global_median, abs=1e-6)
    assert result["design"]["preprocessing"]["fit_partition"].startswith("fit")


def test_test_partition_is_evaluated_once_and_never_used_for_selection(dataset_factory):
    dataset = dataset_factory(_classification_rows())
    result = fit_prediction(
        dataset,
        _classification_config(models=("baseline", "logistic", "random_forest")),
        roles=_roles(),
        split_labels=(TRAIN_VALUE, TEST_VALUE),
    )

    assert result["specification"]["test_evaluations"] == 1
    assert result["specification"]["selection_rule"].startswith("highest balanced accuracy")
    assert result["evaluation"]["partition"] == "test"
    assert result["selected"]["validation"]["metric"] == "balanced_accuracy"

    candidates = result["candidates"]
    assert len(candidates) == 3
    for candidate in candidates:
        assert candidate["status"] == "fitted"
        assert "test" not in candidate
        assert "validation" in candidate
    scores = {candidate["family"]: candidate["selection_score"] for candidate in candidates}
    assert result["selected"]["family"] == max(scores, key=scores.get)
    assert result["selected"]["validation"]["score"] == pytest.approx(
        max(scores.values()), abs=1e-12
    )
    partitions = result["split"]["partitions"]
    assert partitions["fit"] + partitions["validation"] + partitions["test"] == 240
    assert result["selected"]["refit_rows"] == partitions["fit"] + partitions["validation"]


def test_repeated_run_is_reproducible(dataset_factory):
    dataset = dataset_factory(_classification_rows())
    config = _classification_config(models=("logistic", "random_forest"))
    first = fit_prediction(dataset, config, roles=_roles(), split_labels=(TRAIN_VALUE, TEST_VALUE))
    second = fit_prediction(dataset, config, roles=_roles(), split_labels=(TRAIN_VALUE, TEST_VALUE))

    assert first["evaluation"]["metrics"] == second["evaluation"]["metrics"]
    assert first["evaluation"]["predictions"] == second["evaluation"]["predictions"]
    assert first["design"]["preprocessing"]["learned"] == second["design"]["preprocessing"]["learned"]
    assert first["split"] == second["split"]


def test_regression_metrics_match_independent_recomputation(dataset_factory):
    rng = np.random.default_rng(21)
    rows = []
    for index in range(180):
        x1 = float(rng.normal())
        x2 = float(rng.uniform(0, 4))
        y = 4.0 + 2.5 * x1 - 0.75 * x2 + float(rng.normal(0, 0.4))
        rows.append(
            {
                "x1": x1,
                "x2": x2,
                "y": y,
                "split": TEST_VALUE if index >= 140 else TRAIN_VALUE,
            }
        )
    dataset = dataset_factory(rows)
    result = fit_prediction(
        dataset,
        PredictionConfig(
            task="regression",
            outcome="y",
            predictors=("x1", "x2"),
            split_source="existing",
            models=("baseline", "linear"),
        ),
        roles={"x1": ["feature"], "x2": ["feature"], "y": ["target"], "split": ["split"]},
        split_labels=(TRAIN_VALUE, TEST_VALUE),
    )

    predictions = result["evaluation"]["predictions"]["rows"]
    observed = np.array([row["observed"] for row in predictions])
    predicted = np.array([row["predicted"] for row in predictions])
    residual = observed - predicted
    metrics = result["evaluation"]["metrics"]

    assert len(predictions) == 40
    assert metrics["mae"] == pytest.approx(float(np.mean(np.abs(residual))), abs=1e-12)
    assert metrics["rmse"] == pytest.approx(float(math.sqrt(np.mean(residual**2))), abs=1e-12)
    assert metrics["r2"] == pytest.approx(
        float(1 - np.sum(residual**2) / np.sum((observed - observed.mean()) ** 2)), abs=1e-12
    )
    assert metrics["n"] == 40
    assert result["selected"]["family"] == "linear"

    residual_summary = result["evaluation"]["diagnostics"]["residual_summary"]
    assert residual_summary["mean"] == pytest.approx(float(np.mean(residual)), abs=1e-12)
    assert residual_summary["min"] == pytest.approx(float(np.min(residual)), abs=1e-12)
    sample = result["evaluation"]["diagnostics"]["sample"]
    assert sample["drawn_rows"] == len(sample["rows"])
    assert all(row["row_id"] for row in sample["rows"])


def test_subgroup_table_has_exact_denominators_and_small_group_warning(dataset_factory):
    dataset = dataset_factory(_classification_rows())
    result = fit_prediction(
        dataset,
        _classification_config(subgroup_column="segment"),
        roles=_roles(),
        split_labels=(TRAIN_VALUE, TEST_VALUE),
    )

    subgroup = result["subgroups"]
    assert subgroup is not None
    assert subgroup["partition"] == "test"
    assert subgroup["test_rows"] == 120
    assert subgroup["grouped_rows"] == 120
    assert subgroup["outside_bins"] == 0
    assert [row["group"] for row in subgroup["rows"]] == ["a", "b", "c", "(missing)"]
    assert sum(row["n"] for row in subgroup["rows"]) == 120
    tests = [row for row in subgroup["rows"] if row["n"] > 0]
    assert len(tests) == 4
    assert sum(row["n"] for row in tests) == 120
    by_group = {row["group"]: row for row in tests}
    assert by_group["a"]["n"] > 20
    assert by_group["a"]["warning"] is None
    for group in ("b", "c", "(missing)"):
        assert by_group[group]["n"] < 20
    for row in tests:
        assert row["share"] == pytest.approx(row["n"] / 120, abs=1e-6)
        assert row["metric_name"] == "accuracy"
        assert 0.0 <= row["metric"] <= 1.0
        if row["n"] < 20:
            assert row["warning"] is not None
            assert "small subgroup" in row["warning"]


def test_guarded_refusals(dataset_factory):
    dataset = dataset_factory(_classification_rows())

    with pytest.raises(ValidationFailure, match="positive class"):
        fit_prediction(
            dataset,
            _classification_config(positive_level=None),
            roles=_roles(),
            split_labels=(TRAIN_VALUE, TEST_VALUE),
        )
    with pytest.raises(ValidationFailure, match="positive class|positive level"):
        fit_prediction(
            dataset,
            _classification_config(positive_level="maybe"),
            roles=_roles(),
            split_labels=(TRAIN_VALUE, TEST_VALUE),
        )
    with pytest.raises(ValidationFailure, match="outcome cannot also be a predictor"):
        fit_prediction(
            dataset,
            _classification_config(predictors=("x", "outcome")),
            roles=_roles(),
            split_labels=(TRAIN_VALUE, TEST_VALUE),
        )
    with pytest.raises(ValidationFailure, match="no confirmed split"):
        fit_prediction(
            dataset,
            _classification_config(),
            roles=_roles(),
            split_labels=(None, None),
        )
    with pytest.raises(ValidationFailure, match="non-numeric"):
        fit_prediction(
            dataset,
            PredictionConfig(
                task="regression",
                outcome="segment",
                predictors=("x",),
                split_source="existing",
            ),
            roles=_roles(),
            split_labels=(TRAIN_VALUE, TEST_VALUE),
        )


def test_generated_group_split_keeps_entities_disjoint(dataset_factory):
    rng = np.random.default_rng(3)
    rows = []
    for index in range(160):
        entity = f"entity-{index // 10}"
        x = float(rng.normal())
        rows.append(
            {
                "x": x,
                "y": float(2 * x + rng.normal(0, 0.2)),
                "entity": entity,
            }
        )
    dataset = dataset_factory(rows)
    result = fit_prediction(
        dataset,
        PredictionConfig(
            task="regression",
            outcome="y",
            predictors=("x",),
            split_source="generated",
            split_strategy="group",
            test_fraction=0.3,
            seed=5,
            models=("linear",),
        ),
        roles={"x": ["feature"], "y": ["target"], "entity": ["entity"]},
        split_labels=(None, None),
    )

    summary = result["split"]["summary"]
    assert summary["kind"] == "group"
    assert result["split"]["strategy"] == "group"
    assert summary["train_rows"] + summary["test_rows"] == 160
    assert result["split"]["partitions"]["test"] >= 5

    # Reproduce the published split and check the group constraint directly.
    from app.audit.canonical import ValueCanonicalizer
    from app.splits.strategies import group_holdout

    reproduced = group_holdout(
        dataset.frame,
        entity_column="entity",
        test_fraction=0.3,
        seed=5,
        canonicalizer=ValueCanonicalizer(),
    )
    frame = dataset.frame
    train_entities = set(frame.loc[reproduced.masks.train, "entity"])
    test_entities = set(frame.loc[reproduced.masks.test, "entity"])
    assert train_entities.isdisjoint(test_entities)
    assert len(test_entities) == 4
    fit_entities = set(frame.loc[reproduced.masks.train, "entity"]) - test_entities
    assert fit_entities == train_entities
