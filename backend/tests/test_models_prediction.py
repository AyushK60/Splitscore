"""Independent oracles for the predictive engine (F10).

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

import json
import math

import numpy as np
import pytest
from scipy import stats as sps

from app.core.errors import ValidationFailure
from app.models.prediction import PredictionConfig, fit_prediction

TRAIN_VALUE = "train"
TEST_VALUE = "test"
Z_95 = 1.959963984540054


def _average_precision_by_hand(labels: np.ndarray, scores: np.ndarray) -> float:
    """Step-wise AP: sum of (recall_n - recall_n-1) * precision_n over score ties."""
    order = np.argsort(-scores, kind="stable")
    labels = labels[order]
    scores = scores[order]
    positives = int(labels.sum())
    true_positive = 0
    false_positive = 0
    previous_recall = 0.0
    area = 0.0
    index = 0
    while index < len(scores):
        score = scores[index]
        while index < len(scores) and scores[index] == score:
            if labels[index]:
                true_positive += 1
            else:
                false_positive += 1
            index += 1
        precision = true_positive / (true_positive + false_positive)
        recall = true_positive / positives
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return area


def _wilson_bounds(successes: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval, recomputed from the binomial counts."""
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total))
        / denominator
    )
    return max(0.0, centre - margin), min(1.0, centre + margin)


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
                    "bin": index % 3,
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


def test_pr_curve_and_calibration_reconcile_with_stored_probabilities(dataset_factory):
    dataset = dataset_factory(_classification_rows())
    result = fit_prediction(
        dataset,
        _classification_config(),
        roles=_roles(),
        split_labels=(TRAIN_VALUE, TEST_VALUE),
    )

    rows = result["evaluation"]["predictions"]["rows"]
    positive = result["outcome"]["positive_class"]
    observed = np.array([1 if row["observed"] == positive else 0 for row in rows])
    probabilities = np.array([row["probability_positive"] for row in rows], dtype=float)
    metrics = result["evaluation"]["metrics"]

    assert metrics["prevalence"] == pytest.approx(float(observed.mean()), abs=1e-12)
    assert metrics["positive_count"] == int(observed.sum())
    assert metrics["negative_count"] == int(len(observed) - observed.sum())
    expected_ap = _average_precision_by_hand(observed, probabilities)
    assert metrics["average_precision"] == pytest.approx(expected_ap, abs=1e-12)
    assert metrics["pr_auc"] == pytest.approx(expected_ap, abs=1e-12)
    assert "average precision" in metrics["pr_auc_definition"]

    curve = metrics["pr_curve"]
    assert curve is not None
    assert curve["average_precision"] == pytest.approx(expected_ap, abs=1e-12)
    assert curve["positive_count"] == int(observed.sum())
    assert curve["prevalence"] == pytest.approx(float(observed.mean()), abs=1e-12)
    assert len(curve["precision"]) == len(curve["recall"]) == curve["n_points"]
    assert all(0.0 <= value <= 1.0 for value in curve["precision"] + curve["recall"])

    calibration = result["evaluation"]["diagnostics"]["calibration"]
    summary = result["evaluation"]["diagnostics"]["calibration_summary"]
    assert calibration is not None and summary is not None
    edges = np.linspace(0.0, 1.0, 11)
    slots = np.clip(np.digitize(probabilities, edges[1:-1], right=True), 0, 9)
    total = 0
    weighted_gap = 0.0
    for index, entry in enumerate(calibration):
        mask = slots == index
        count = int(mask.sum())
        assert entry["count"] == count
        total += count
        if count:
            rate = float(observed[mask].mean())
            mean_predicted = float(probabilities[mask].mean())
            assert entry["observed_rate"] == pytest.approx(rate, abs=1e-12)
            assert entry["mean_predicted"] == pytest.approx(mean_predicted, abs=1e-12)
            assert entry["observed_rate_low"] <= rate <= entry["observed_rate_high"]
            weighted_gap += (count / len(observed)) * abs(rate - mean_predicted)
        else:
            assert entry["mean_predicted"] is None
            assert entry["observed_rate"] is None
    assert total == len(observed)
    assert summary["rows_in_bins"] == len(observed)
    assert summary["brier_score"] == pytest.approx(
        float(np.mean((probabilities - observed) ** 2)), abs=1e-12
    )
    assert summary["expected_calibration_error"] == pytest.approx(weighted_gap, abs=1e-12)
    assert summary["prevalence"] == pytest.approx(float(observed.mean()), abs=1e-12)


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
    json.dumps(result, allow_nan=False)

    residual_summary = result["evaluation"]["diagnostics"]["residual_summary"]
    assert residual_summary["mean"] == pytest.approx(float(np.mean(residual)), abs=1e-12)
    assert residual_summary["min"] == pytest.approx(float(np.min(residual)), abs=1e-12)
    sample = result["evaluation"]["diagnostics"]["sample"]
    assert sample["drawn_rows"] == len(sample["rows"])
    assert all(row["row_id"] for row in sample["rows"])

    diagnostics = result["evaluation"]["diagnostics"]
    qq = diagnostics["qq"]
    assert qq["applicable"] is True
    assert qq["n"] == 40
    ordered = np.sort(residual)
    theoretical = sps.norm.ppf((np.arange(1, 41) - 0.5) / 40)
    assert qq["sample"] == pytest.approx(ordered.tolist(), abs=1e-6)
    assert qq["theoretical"] == pytest.approx(theoretical.tolist(), abs=1e-6)
    assert qq["reference_slope"] == pytest.approx(float(np.std(residual, ddof=1)), abs=1e-6)
    assert qq["reference_intercept"] == pytest.approx(float(np.mean(residual)), abs=1e-6)

    train = rows[:140]
    x1_train = np.array([row["x1"] for row in train])
    x2_train = np.array([row["x2"] for row in train])
    y_train = np.array([row["y"] for row in train])
    design = np.column_stack([np.ones(len(train)), x1_train, x2_train])
    beta = np.linalg.solve(design.T @ design, design.T @ y_train)
    train_residual = y_train - design @ beta
    xtx_inv = np.linalg.inv(design.T @ design)
    leverage = np.einsum("ij,jk,ik->i", design, xtx_inv, design)
    parameters = design.shape[1]
    mse = float(train_residual @ train_residual / (len(train) - parameters))
    cooks = (train_residual**2 / (parameters * mse)) * (leverage / (1.0 - leverage) ** 2)

    influence = diagnostics["influence"]
    assert influence["applicable"] is True
    assert influence["n"] == 140
    assert influence["parameters"] == 3
    assert influence["residual_df"] == 137
    assert influence["max_leverage"] == pytest.approx(float(np.max(leverage)), abs=1e-12)
    assert influence["max_cooks"] == pytest.approx(float(np.max(cooks)), abs=1e-12)
    top = influence["top_influence"][0]
    top_index = dataset.row_ids.index(top["row_id"])
    assert top["leverage"] == pytest.approx(float(leverage[top_index]), abs=1e-12)
    assert top["cooks_distance"] == pytest.approx(float(cooks[top_index]), abs=1e-12)
    terms = [entry["term"] for entry in influence["coefficients"]]
    assert terms == ["const", "x1", "x2"]
    assert all(entry["ci_low"] <= entry["estimate"] <= entry["ci_high"] for entry in influence["coefficients"])

    importance = diagnostics["permutation_importance"]
    assert importance["applicable"] is True
    assert importance["partition"] == "test"
    assert importance["n"] == 40
    assert importance["rows"][0]["feature"] == "x1"
    assert importance["rows"][0]["importance_mean"] > 0
    assert all(math.isfinite(row["importance_mean"]) for row in importance["rows"])


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
    assert subgroup["interval_level"] == 0.95
    assert subgroup["outcome_measure"] == "positive-class rate"
    assert "multiplicity" in subgroup["comparison_note"]
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
        assert row["metric_denominator"] == row["n"]
        assert row["ci_low"] <= row["metric"] <= row["ci_high"]
        assert "Wilson" in row["ci_method"]
        low, high = _wilson_bounds(int(row["correct"]), row["n"])
        assert row["ci_low"] == pytest.approx(low, abs=1e-12)
        assert row["ci_high"] == pytest.approx(high, abs=1e-12)
        assert row["positive_count"] + row["negative_count"] == row["n"]
        assert row["outcome_mean"] == pytest.approx(row["positive_count"] / row["n"], abs=1e-12)
        if row["n"] < 20:
            assert row["warning"] is not None
            assert "small subgroup" in row["warning"]


def test_single_class_test_partition_marks_pr_and_roc_undefined(dataset_factory):
    rows = []
    for index in range(180):
        is_test = index >= 120
        rows.append(
            {
                "x": float(index % 13) + (index % 7) * 0.1,
                "outcome": "yes" if (not is_test and index % 2 == 0) else "no",
                "split": TEST_VALUE if is_test else TRAIN_VALUE,
            }
        )
    dataset = dataset_factory(rows)
    result = fit_prediction(
        dataset,
        _classification_config(),
        roles={"x": ["feature"], "split": ["split"], "outcome": ["target"]},
        split_labels=(TRAIN_VALUE, TEST_VALUE),
    )
    metrics = result["evaluation"]["metrics"]
    assert metrics["positive_count"] == 0
    assert metrics["prevalence"] == 0.0
    assert metrics["average_precision"] is None
    assert metrics["roc_auc"] is None
    assert metrics["pr_curve"] is None
    reasons = " ".join(entry["reason"] for entry in metrics["undefined"])
    assert "both classes" in reasons


def test_numeric_subgroup_bins_report_empty_and_outside_rows(dataset_factory):
    dataset = dataset_factory(_classification_rows())
    result = fit_prediction(
        dataset,
        _classification_config(subgroup_column="bin", subgroup_bins=(0.0, 1.0, 5.0, 10.0)),
        roles=_roles(),
        split_labels=(TRAIN_VALUE, TEST_VALUE),
    )

    subgroup = result["subgroups"]
    assert subgroup is not None
    assert subgroup["outside_bins"] == 0
    assert sum(row["n"] for row in subgroup["rows"]) == 120
    empty = [row for row in subgroup["rows"] if row["n"] == 0]
    assert empty
    for row in empty:
        assert row["metric"] is None
        assert row["ci_low"] is None and row["ci_high"] is None
        assert row["metric_denominator"] == 0
        assert row["warning"] == "empty subgroup"
    for row in subgroup["rows"]:
        if row["n"]:
            assert row["ci_low"] <= row["metric"] <= row["ci_high"]


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
