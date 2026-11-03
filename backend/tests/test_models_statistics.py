"""Numerical oracles for the S6 statistical engine.

Expectations here are computed independently of the production implementation:

* OLS coefficients are solved from the normal equations with numpy, and the
  standard errors, intervals and p-values are computed from the textbook
  formula with scipy's t distribution — not read back from statsmodels.
* Logistic coefficients and standard errors are compared with a direct
  statsmodels ``Logit`` fit written in the test, which is the trusted
  reference implementation for maximum likelihood.
* Categorical coding is checked against a hand-built dummy matrix and a numpy
  least-squares solve.
* Guardrail tests assert refusals, not silently altered specifications.
"""

from __future__ import annotations

import numpy as np
import pytest
import statsmodels.api as sm
from scipy import stats as sps

from app.core.errors import ValidationFailure
from app.models.contracts import StatisticsConfig
from app.models.statistics import fit_statistics

TOL_COEF = 1e-8
TOL_SE = 1e-8


def _terms(result: dict) -> dict[str, dict]:
    return {entry["term"]: entry for entry in result["coefficients"]}


def _ols_data(seed: int = 11, n: int = 60) -> tuple[list[dict], np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x1 = rng.normal(0, 1, n)
    x2 = rng.uniform(-2, 2, n)
    y = 1.25 + 2.0 * x1 - 1.5 * x2 + rng.normal(0, 0.35, n)
    rows = [
        {"x1": float(a), "x2": float(b), "y": float(c)}
        for a, b, c in zip(x1, x2, y, strict=True)
    ]
    return rows, x1, x2, y


def test_ols_matches_independent_normal_equations(dataset_factory):
    rows, x1, x2, y = _ols_data()
    dataset = dataset_factory(rows)
    result = fit_statistics(
        dataset, StatisticsConfig(task="ols", outcome="y", predictors=("x1", "x2"))
    )

    design = np.column_stack([np.ones_like(x1), x1, x2])
    beta = np.linalg.solve(design.T @ design, design.T @ y)
    residual = y - design @ beta
    dof = len(y) - design.shape[1]
    sigma2 = float(residual @ residual / dof)
    covariance = sigma2 * np.linalg.inv(design.T @ design)
    standard_errors = np.sqrt(np.diag(covariance))
    statistics = beta / standard_errors
    p_values = 2 * sps.t.sf(np.abs(statistics), dof)
    critical = sps.t.ppf(0.975, dof)

    terms = _terms(result)
    for index, name in enumerate(["const", "x1", "x2"]):
        entry = terms[name]
        assert entry["estimate"] == pytest.approx(beta[index], abs=TOL_COEF)
        assert entry["std_error"] == pytest.approx(standard_errors[index], abs=TOL_SE)
        assert entry["statistic"] == pytest.approx(statistics[index], abs=1e-7)
        assert entry["p_value"] == pytest.approx(p_values[index], abs=1e-9)
        assert entry["ci_low"] == pytest.approx(
            beta[index] - critical * standard_errors[index], abs=1e-7
        )
        assert entry["ci_high"] == pytest.approx(
            beta[index] + critical * standard_errors[index], abs=1e-7
        )
        assert entry["ci_low"] < entry["estimate"] < entry["ci_high"]
    assert "odds_ratio" not in terms["x1"]

    r_squared = 1.0 - float(residual @ residual) / float(((y - y.mean()) ** 2).sum())
    assert result["fit"]["r_squared"] == pytest.approx(r_squared, abs=1e-10)
    assert result["fit"]["df_resid"] == dof
    assert result["population"]["analyzed"] == len(y)
    assert result["population"]["excluded"] == 0
    assert result["specification"]["formula"] == "y ~ x1 + x2"
    assert set(result["versions"]) >= {"python", "numpy", "pandas", "statsmodels", "scipy"}

    # Diagnostics are the fitted object's own numbers, not placeholders.
    for row in result["diagnostics"]["sample"]["rows"]:
        assert row["residual"] == pytest.approx(row["observed"] - row["fitted"], abs=1e-9)


def test_ols_without_intercept_is_a_different_model(dataset_factory):
    rows, x1, x2, y = _ols_data(seed=19)
    dataset = dataset_factory(rows)
    with_intercept = fit_statistics(
        dataset, StatisticsConfig(task="ols", outcome="y", predictors=("x1", "x2"))
    )
    without = fit_statistics(
        dataset,
        StatisticsConfig(task="ols", outcome="y", predictors=("x1", "x2"), intercept=False),
    )
    assert "const" not in _terms(without)
    assert _terms(without)["x1"]["estimate"] != pytest.approx(
        _terms(with_intercept)["x1"]["estimate"], abs=1e-6
    )
    design = np.column_stack([x1, x2])
    beta = np.linalg.solve(design.T @ design, design.T @ y)
    assert _terms(without)["x1"]["estimate"] == pytest.approx(beta[0], abs=TOL_COEF)
    assert _terms(without)["x2"]["estimate"] == pytest.approx(beta[1], abs=TOL_COEF)


def test_logistic_matches_reference_implementation_and_orientation(dataset_factory):
    rng = np.random.default_rng(5)
    n = 400
    x1 = rng.normal(0, 1, n)
    x2 = rng.integers(0, 2, n).astype(float)
    latent = -0.4 + 1.3 * x1 + 0.9 * x2
    probability = 1.0 / (1.0 + np.exp(-latent))
    y = rng.binomial(1, probability)
    rows = [
        {"x1": float(a), "x2": float(b), "group": "yes" if outcome else "no"}
        for a, b, outcome in zip(x1, x2, y, strict=True)
    ]
    dataset = dataset_factory(rows)
    result = fit_statistics(
        dataset,
        StatisticsConfig(
            task="logistic",
            outcome="group",
            predictors=("x1", "x2"),
            positive_level="yes",
        ),
    )

    design = np.column_stack([np.ones_like(x1), x1, x2])
    reference = sm.Logit(y, design).fit(disp=0)
    terms = _terms(result)
    for index, name in enumerate(["const", "x1", "x2"]):
        assert terms[name]["estimate"] == pytest.approx(reference.params[index], abs=1e-6)
        assert terms[name]["std_error"] == pytest.approx(reference.bse[index], abs=1e-5)
        assert terms[name]["odds_ratio"] == pytest.approx(
            np.exp(reference.params[index]), rel=1e-9
        )

    # Orientation: larger x1 raises the probability of the positive class.
    assert terms["x1"]["estimate"] > 0
    assert terms["x1"]["odds_ratio"] > 1
    assert result["fit"]["mcfadden_pseudo_r_squared"] == pytest.approx(
        float(reference.prsquared), abs=1e-9
    )
    assert result["fit"]["log_likelihood"] == pytest.approx(float(reference.llf), abs=1e-8)
    assert "r_squared" not in result["fit"], "OLS R² must not be shown for a classifier"
    assert result["specification"]["outcome_coding"]["positive_level"] == "yes"
    assert result["specification"]["outcome_coding"]["negative_level"] == "no"
    assert result["specification"]["outcome_coding"]["positive_count"] == int(y.sum())


def test_categorical_predictor_uses_the_declared_reference(dataset_factory):
    rng = np.random.default_rng(23)
    x = rng.uniform(0, 5, 90)
    categories = np.array(["a", "b", "c"] * 30)
    offsets = {"a": 3.0, "b": 0.0, "c": -1.0}
    y = 1.0 + 2.0 * x + np.array([offsets[value] for value in categories]) + rng.normal(0, 0.1, 90)
    rows = [
        {"x": float(a), "cat": value, "y": float(outcome)}
        for a, value, outcome in zip(x, categories, y, strict=True)
    ]
    dataset = dataset_factory(rows)
    result = fit_statistics(
        dataset,
        StatisticsConfig(
            task="ols",
            outcome="y",
            predictors=("x", "cat"),
            categorical_references={"cat": "b"},
        ),
    )

    terms = _terms(result)
    assert "cat[b]" not in terms, "the reference level is the omitted category"
    assert "cat[a]" in terms and "cat[c]" in terms
    coding = next(entry for entry in result["specification"]["coding"] if entry["column"] == "cat")
    assert coding["kind"] == "categorical"
    assert coding["reference"] == "b"
    assert coding["levels"] == ["a", "b", "c"]
    assert result["specification"]["formula"] == "y ~ x + C(cat, Treatment('b'))"

    design = np.column_stack(
        [np.ones_like(x), x, (categories == "a").astype(float), (categories == "c").astype(float)]
    )
    beta = np.linalg.solve(design.T @ design, design.T @ y)
    assert terms["cat[a]"]["estimate"] == pytest.approx(beta[2], abs=TOL_COEF)
    assert terms["cat[c]"]["estimate"] == pytest.approx(beta[3], abs=TOL_COEF)
    # The reference level's offset is the baseline, so its coefficient is omitted.
    assert abs(terms["cat[a]"]["estimate"] - 3.0) < 0.15


def test_complete_case_population_is_counted_and_fail_refuses(dataset_factory):
    rows, _, _, _ = _ols_data(n=24)
    rows[3]["x1"] = ""  # missing predictor
    rows[7]["y"] = ""  # missing outcome
    rows[9]["x1"] = ""  # missing predictor
    dataset = dataset_factory(rows)
    result = fit_statistics(
        dataset, StatisticsConfig(task="ols", outcome="y", predictors=("x1", "x2"))
    )
    assert result["population"]["rows_total"] == 24
    assert result["population"]["analyzed"] == 21
    assert result["population"]["excluded"] == 3
    assert result["population"]["excluded_missing_by_column"] == {"y": 1, "x1": 2}
    assert any(warning["code"] == "complete_case_population" for warning in result["warnings"])

    with pytest.raises(ValidationFailure) as failure:
        fit_statistics(
            dataset,
            StatisticsConfig(
                task="ols",
                outcome="y",
                predictors=("x1", "x2"),
                missing_policy="fail",
            ),
        )
    assert failure.value.details["excluded_rows"] == 3


def test_single_class_and_uncoded_binary_outcomes_are_refused(dataset_factory):
    rows = [{"x": float(i), "group": "yes"} for i in range(30)]
    dataset = dataset_factory(rows)
    with pytest.raises(ValidationFailure) as single:
        fit_statistics(
            dataset,
            StatisticsConfig(
                task="logistic",
                outcome="group",
                predictors=("x",),
                positive_level="yes",
            ),
        )
    assert "exactly two observed levels" in single.value.message

    mixed = [{"x": float(i), "group": "yes" if i % 2 else "no"} for i in range(40)]
    dataset = dataset_factory(mixed)
    with pytest.raises(ValidationFailure) as uncoded:
        fit_statistics(
            dataset,
            StatisticsConfig(task="logistic", outcome="group", predictors=("x",)),
        )
    assert "positive class" in uncoded.value.message
    assert uncoded.value.details["levels"] == ["no", "yes"]


def test_constant_outcome_and_constant_predictor_are_refused(dataset_factory):
    rows = [{"x": float(i), "y": 5.0} for i in range(30)]
    dataset = dataset_factory(rows)
    with pytest.raises(ValidationFailure) as constant_outcome:
        fit_statistics(dataset, StatisticsConfig(task="ols", outcome="y", predictors=("x",)))
    assert "constant" in constant_outcome.value.message.lower()

    varying = [{"x": 1.0, "z": float(i), "y": float(i % 7)} for i in range(30)]
    dataset = dataset_factory(varying)
    with pytest.raises(ValidationFailure) as constant_predictor:
        fit_statistics(dataset, StatisticsConfig(task="ols", outcome="y", predictors=("x",)))
    assert "constant" in constant_predictor.value.message.lower()


def test_singular_design_is_refused_with_the_offending_terms(dataset_factory):
    rows = [
        {"x1": float(i), "x3": float(2 * i), "y": float(3 + 0.5 * i)}
        for i in range(30)
    ]
    dataset = dataset_factory(rows)
    with pytest.raises(ValidationFailure) as failure:
        fit_statistics(
            dataset, StatisticsConfig(task="ols", outcome="y", predictors=("x1", "x3"))
        )
    assert "rank deficient" in failure.value.message
    assert failure.value.details["rank"] < failure.value.details["parameters"]
    assert failure.value.details["duplicated_terms"]


def test_duplicate_predictor_unknown_column_and_small_population_are_refused(dataset_factory):
    rows, _, _, _ = _ols_data(n=30)
    dataset = dataset_factory(rows)
    with pytest.raises(ValidationFailure):
        fit_statistics(
            dataset, StatisticsConfig(task="ols", outcome="y", predictors=("x1", "x1"))
        )
    with pytest.raises(ValidationFailure):
        fit_statistics(
            dataset, StatisticsConfig(task="ols", outcome="nope", predictors=("x1",))
        )
    with pytest.raises(ValidationFailure) as small:
        fit_statistics(
            dataset_factory(rows[:9]),
            StatisticsConfig(task="ols", outcome="y", predictors=("x1", "x2")),
        )
    assert "below the minimum" in small.value.message


def test_high_cardinality_categories_are_refused(dataset_factory):
    rows = [
        {"x": float(i), "cat": f"level-{i}", "y": float(i % 5)}
        for i in range(30)
    ]
    dataset = dataset_factory(rows)
    with pytest.raises(ValidationFailure) as failure:
        fit_statistics(
            dataset, StatisticsConfig(task="ols", outcome="y", predictors=("x", "cat"))
        )
    assert "levels" in failure.value.message
    assert failure.value.details["limit"] == 12


def test_repeated_fits_are_identical(dataset_factory):
    rows, _, _, _ = _ols_data(seed=31)
    dataset = dataset_factory(rows)
    config = StatisticsConfig(task="ols", outcome="y", predictors=("x1", "x2"))
    first = fit_statistics(dataset, config)
    second = fit_statistics(dataset, config)
    assert [entry["estimate"] for entry in first["coefficients"]] == [
        entry["estimate"] for entry in second["coefficients"]
    ]
    assert first["diagnostics"]["sample"] == second["diagnostics"]["sample"]
