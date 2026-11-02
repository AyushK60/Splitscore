"""S4 Visual Explorer — numerical and API tests.

Independent oracles: scipy for correlation coefficients, hand-calculated
fixtures for histograms, quartiles, ranks and selection id sets. Expected
values are written here, never derived from the implementation under test.
"""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from scipy import stats as sps

from app.api.deps import reset_context
from app.explore.sampling import render_sample
from app.explore.selection import Predicate, evaluate_selection
from app.explore.stats import (
    box_stats,
    frequencies,
    histogram,
    parse_numeric,
    pearson,
    spearman,
    _average_ranks,
)

from .conftest import make_dataset


# --------------------------------------------------------------------------- #
# Pearson
# --------------------------------------------------------------------------- #


def _xy_fixture() -> tuple[list[dict[str, object]], list[float], list[float]]:
    """A fixed, mildly noisy relation with hand-checkable structure."""
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    y = [2.1, 3.9, 6.2, 8.1, 9.8, 12.3, 14.1, 15.9, 18.4, 19.7]
    rows: list[dict[str, object]] = [
        {"i": i, "x": xvalue, "y": yvalue} for i, (xvalue, yvalue) in enumerate(zip(x, y, strict=True))
    ]
    return rows, x, y


def test_pearson_matches_scipy():
    rows, x, y = _xy_fixture()
    dataset = make_dataset(rows, columns=["i", "x", "y"])
    parsed_x = parse_numeric(dataset, "x")
    parsed_y = parse_numeric(dataset, "y")
    result = pearson(parsed_x.values, parsed_y.values)
    expected, _ = sps.pearsonr(x, y)
    assert result.coefficient == pytest.approx(expected, abs=1e-12)
    assert result.n_valid == 10
    assert result.warning is None


def test_pearson_pairwise_complete_excludes_missing():
    rows, _x, _y = _xy_fixture()
    rows[2]["x"] = ""  # missing cell: excluded pairwise, never coerced to 0
    rows[5]["y"] = ""
    dataset = make_dataset(rows, columns=["i", "x", "y"])
    px, py = parse_numeric(dataset, "x"), parse_numeric(dataset, "y")
    result = pearson(px.values, py.values)

    complete_x = [row["x"] for i, row in enumerate(rows) if i not in (2, 5)]
    complete_y = [row["y"] for i, row in enumerate(rows) if i not in (2, 5)]
    expected, _ = sps.pearsonr(complete_x, complete_y)  # type: ignore[arg-type]
    assert result.coefficient == pytest.approx(expected, abs=1e-12)
    assert result.n_valid == 8


def test_pearson_constant_column_is_undefined_not_zero():
    rows, x, _y = _xy_fixture()
    for row in rows:
        row["c"] = 7.0
    dataset = make_dataset(rows, columns=["i", "x", "y", "c"])
    px, pc = parse_numeric(dataset, "x"), parse_numeric(dataset, "c")
    result = pearson(px.values, pc.values)
    assert result.coefficient is None
    assert result.warning == "constant_y"
    reverse = pearson(pc.values, px.values)
    assert reverse.coefficient is None
    assert reverse.warning == "constant_x"


def test_pearson_insufficient_pairs_is_undefined():
    dataset = make_dataset(
        [{"x": 1.0, "y": 2.0}, {"x": 2.0, "y": 4.0}], columns=["x", "y"]
    )
    px, py = parse_numeric(dataset, "x"), parse_numeric(dataset, "y")
    result = pearson(px.values, py.values)
    assert result.coefficient is None
    assert result.warning == "insufficient_pairs"
    assert result.n_valid == 2


def test_pearson_unparsed_cells_counted_not_coerced():
    rows = [{"x": value, "y": index} for index, value in enumerate(["1", "2", "oops", "4", "5", "6"], start=1)]
    dataset = make_dataset(rows, columns=["x", "y"])
    parsed = parse_numeric(dataset, "x")
    assert parsed.unparsed == 1
    assert parsed.missing == 0
    assert parsed.valid_count == 5


# --------------------------------------------------------------------------- #
# Spearman
# --------------------------------------------------------------------------- #


def test_average_ranks_handle_ties_by_averaging():
    ranks = _average_ranks(np.array([1.0, 2.0, 2.0, 3.0]))
    assert ranks.tolist() == [1.0, 2.5, 2.5, 4.0]


def test_spearman_matches_scipy_with_ties():
    x = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0, 5.0, 3.0]
    y = [7.0, 2.0, 8.0, 2.5, 5.0, 9.5, 1.0, 6.0, 5.0, 7.5]
    rows = [{"x": xv, "y": yv} for xv, yv in zip(x, y, strict=True)]
    dataset = make_dataset(rows, columns=["x", "y"])
    px, py = parse_numeric(dataset, "x"), parse_numeric(dataset, "y")
    result = spearman(px.values, py.values)
    expected, _ = sps.spearmanr(x, y)
    assert result.coefficient == pytest.approx(expected, abs=1e-12)
    assert result.n_valid == 10


def test_spearman_monotonic_is_one():
    dataset = make_dataset(
        [{"x": value, "y": value * value} for value in [1.0, 2.0, 3.0, 4.0, 5.0]],
        columns=["x", "y"],
    )
    px, py = parse_numeric(dataset, "x"), parse_numeric(dataset, "y")
    result = spearman(px.values, py.values)
    assert result.coefficient == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Histogram and box plot
# --------------------------------------------------------------------------- #


def test_histogram_counts_hand_fixture():
    dataset = make_dataset(
        [{"v": float(v)} for v in range(10)], columns=["v"]
    )
    parsed = parse_numeric(dataset, "v")
    hist = histogram(parsed, bins=5)
    assert hist.edges[0] == pytest.approx(0.0)
    assert hist.edges[-1] == pytest.approx(9.0)
    assert hist.counts == [2, 2, 2, 2, 2]  # 0,1 | 2,3 | 4,5 | 6,7 | 8,9
    assert hist.valid == 10
    assert hist.population == 10


def test_histogram_reports_missing_and_unparsed_denominators():
    dataset = make_dataset(
        [{"v": v} for v in ["1", "", "2", "n/a", "3", "4"]], columns=["v"]
    )
    parsed = parse_numeric(dataset, "v")
    hist = histogram(parsed, bins=4)
    assert hist.missing == 1
    assert hist.unparsed == 1
    assert hist.valid == 4
    assert sum(hist.counts) == 4


def test_histogram_single_distinct_value_has_one_bin():
    dataset = make_dataset([{"v": "5"} for _ in range(6)], columns=["v"])
    hist = histogram(parse_numeric(dataset, "v"), bins=10)
    assert hist.edges == [5.0, 5.0]
    assert hist.counts == [6]


def test_box_stats_hand_calculated():
    dataset = make_dataset([{"v": float(v)} for v in range(1, 10)], columns=["v"])
    box = box_stats(parse_numeric(dataset, "v"))
    assert box is not None
    assert box.n == 9
    assert box.q1 == pytest.approx(3.0)
    assert box.median == pytest.approx(5.0)
    assert box.q3 == pytest.approx(7.0)
    assert box.iqr == pytest.approx(4.0)
    # Fences: 3 - 6 = -3 and 7 + 6 = 13; every value is inside.
    assert box.whisker_low == pytest.approx(1.0)
    assert box.whisker_high == pytest.approx(9.0)
    assert box.outlier_count == 0


def test_box_stats_flag_outliers_beyond_fences():
    values = [float(v) for v in range(1, 10)] + [100.0]
    dataset = make_dataset([{"v": v} for v in values], columns=["v"])
    box = box_stats(parse_numeric(dataset, "v"))
    assert box is not None
    assert box.outlier_count == 1
    assert box.outlier_examples == [100.0]
    # Whisker stops at the largest value inside the fence, not at the outlier.
    assert box.whisker_high == pytest.approx(9.0)


def test_frequencies_cap_levels_with_other_bucket():
    rows = [{"c": f"level_{i:02d}"} for i in range(35)]
    rows += [{"c": "level_00"}] * 5
    dataset = make_dataset(rows, columns=["c"])
    from app.explore.stats import text_values

    values, missing = text_values(dataset, "c")
    freq = frequencies(values)
    assert missing == 0
    assert len(freq.levels) == 30
    assert freq.other_count == 5
    assert freq.distinct == 35
    assert sum(c for _, c in freq.levels) + freq.other_count == 40


# --------------------------------------------------------------------------- #
# Render sampling
# --------------------------------------------------------------------------- #


def test_render_sample_is_deterministic_and_bounded():
    first = render_sample(1000, 120)
    second = render_sample(1000, 120)
    assert first.indices == second.indices
    assert first.stride == 9  # ceil(1000 / 120)
    assert len(first.indices) == 112  # ceil(1000 / 9)
    assert first.indices[0] == 0
    assert first.indices[1] == 9
    assert first.population == 1000


def test_render_sample_draws_everything_below_cap():
    sample = render_sample(50, 120)
    assert sample.stride == 1
    assert sample.indices == list(range(50))


# --------------------------------------------------------------------------- #
# Selection predicates
# --------------------------------------------------------------------------- #


def test_selection_range_predicate_exact_ids():
    dataset = make_dataset(
        [{"v": float(v)} for v in range(10)], columns=["v"]
    )
    result = evaluate_selection(dataset, [Predicate(column="v", min=3.0, max=5.0)])
    assert result.total_selected == 3
    assert result.row_ids == [dataset.row_ids[i] for i in (3, 4, 5)]
    assert result.population == 10
    assert not result.ids_truncated


def test_selection_union_within_column_intersect_across_columns():
    dataset = make_dataset(
        [
            {"a": 1.0, "b": 1.0},
            {"a": 2.0, "b": 8.0},
            {"a": 8.0, "b": 2.0},
            {"a": 9.0, "b": 9.0},
        ],
        columns=["a", "b"],
    )
    # Two ranges on one axis union; the second column intersects.
    result = evaluate_selection(
        dataset,
        [
            Predicate(column="a", min=1.0, max=2.0),
            Predicate(column="a", min=8.0, max=9.0),
            Predicate(column="b", min=8.0, max=9.0),
        ],
    )
    # a in [1,2] or [8,9] -> rows 0,1,2,3; AND b >= 8 -> rows 1 and 3.
    assert result.row_ids == [dataset.row_ids[1], dataset.row_ids[3]]


def test_selection_categorical_values_predicate():
    dataset = make_dataset(
        [{"g": g, "v": float(i)} for i, g in enumerate(["alpha", "beta", "alpha", "gamma"])],
        columns=["g", "v"],
    )
    result = evaluate_selection(dataset, [Predicate(column="g", values=("alpha", "gamma"))])
    assert result.total_selected == 3
    assert result.row_ids == [dataset.row_ids[0], dataset.row_ids[2], dataset.row_ids[3]]


def test_selection_empty_predicates_selects_everything():
    dataset = make_dataset([{"v": float(v)} for v in range(5)], columns=["v"])
    result = evaluate_selection(dataset, [])
    assert result.total_selected == 5
    assert result.row_ids == dataset.row_ids


def test_selection_impossible_range_selects_nothing():
    dataset = make_dataset([{"v": float(v)} for v in range(5)], columns=["v"])
    result = evaluate_selection(dataset, [Predicate(column="v", min=10.0, max=20.0)])
    assert result.total_selected == 0
    assert result.row_ids == []


def test_selection_missing_cells_never_match_numeric_ranges():
    dataset = make_dataset(
        [{"v": v} for v in ["1", "", "3", "4"]], columns=["v"]
    )
    result = evaluate_selection(dataset, [Predicate(column="v", min=0.0, max=10.0)])
    # The missing cell is not a number, so brushing the full range excludes it.
    assert result.total_selected == 3


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


@pytest.fixture()
def client():
    from app.main import create_app

    reset_context()
    with TestClient(create_app()) as test_client:
        yield test_client


def _upload(client: TestClient, rows: list[dict[str, object]], columns: list[str]) -> dict:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ("" if row.get(k) is None else row.get(k, "")) for k in columns})
    response = client.post(
        "/api/datasets",
        files={"file": ("explore-fixture.csv", buffer.getvalue().encode("utf-8"), "text/csv")},
    )
    assert response.status_code in (200, 201), response.text
    return response.json()


def _numeric_rows(n: int) -> tuple[list[dict[str, object]], list[str]]:
    rng = np.random.default_rng(42)
    a = np.round(rng.normal(10, 3, n), 4)
    b = np.round(a * 1.5 + rng.normal(0, 1, n), 4)
    rows = [
        {"a": float(a[i]), "b": float(b[i]), "g": "even" if i % 2 == 0 else "odd", "s": ("train" if i % 3 else "test")}
        for i in range(n)
    ]
    return rows, ["a", "b", "g", "s"]


def test_schema_reports_types_and_fingerprint(client):
    rows, columns = _numeric_rows(60)
    loaded = _upload(client, rows, columns)
    schema = client.get(f"/api/datasets/{loaded['dataset']['dataset_id']}/explore/schema").json()
    assert schema["dataset"]["fingerprint_sha256"] == loaded["dataset"]["fingerprint_sha256"]
    assert schema["row_count"] == 60
    types = {c["name"]: c["detected_type"] for c in schema["columns"]}
    assert types["a"] == "numeric"
    assert types["g"] == "categorical"
    assert "g" in schema["color_candidates"]
    assert set(schema["numeric_columns"]) == {"a", "b"}


def test_series_returns_immutable_ids_and_honest_sampling(client):
    rows, columns = _numeric_rows(500)
    loaded = _upload(client, rows, columns)
    dataset_id = loaded["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/explore/series",
        json={"columns": ["a", "b", "g"], "max_rows": 100},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["population"] == 500
    assert payload["drawn_rows"] == 100
    assert payload["sampling"]["method"] == "systematic_grid"
    assert payload["sampling"]["stride"] == 5
    ids = [row["id"] for row in payload["rows"]]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("row-") for i in ids)
    # Deterministic: the same request draws the same rows.
    repeat = client.post(
        f"/api/datasets/{dataset_id}/explore/series",
        json={"columns": ["a", "b", "g"], "max_rows": 100},
    ).json()
    assert [row["id"] for row in repeat["rows"]] == ids
    # Scale covers the full population, not the drawn sample.
    assert payload["scale"]["a"]["valid_count"] == 500


def test_series_with_filters_samples_from_filtered_population(client):
    rows, columns = _numeric_rows(500)
    loaded = _upload(client, rows, columns)
    dataset_id = loaded["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/explore/series",
        json={"columns": ["a", "g"], "max_rows": 100, "filters": [{"column": "g", "values": ["even"]}]},
    )
    payload = response.json()
    assert payload["filtered_population"] == 250
    # Systematic grid: stride ceil(250/100) = 3, so ceil(250/3) = 84 rows drawn.
    assert payload["sampling"]["stride"] == 3
    assert payload["drawn_rows"] == 84
    # Every drawn row satisfies the filter.
    assert all(row["values"]["g"] == "even" for row in payload["rows"])


def test_selection_endpoint_exact_count(client):
    rows, columns = _numeric_rows(60)
    loaded = _upload(client, rows, columns)
    dataset_id = loaded["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/explore/selection",
        json={"predicates": [{"column": "g", "values": ["even"]}]},
    )
    payload = response.json()
    assert payload["total_selected"] == 30
    assert payload["population"] == 60
    assert len(payload["row_ids"]) == 30
    assert payload["predicates"][0]["kind"] == "values"


def test_selection_endpoint_rejects_unknown_column(client):
    rows, columns = _numeric_rows(30)
    loaded = _upload(client, rows, columns)
    response = client.post(
        f"/api/datasets/{loaded['dataset']['dataset_id']}/explore/selection",
        json={"predicates": [{"column": "nope", "min": 0, "max": 1}]},
    )
    assert response.status_code == 422


def test_correlation_matches_scipy_through_the_api(client):
    rows, columns = _numeric_rows(200)
    loaded = _upload(client, rows, columns)
    dataset_id = loaded["dataset"]["dataset_id"]
    for method, oracle in (("pearson", sps.pearsonr), ("spearman", sps.spearmanr)):
        response = client.post(
            f"/api/datasets/{dataset_id}/explore/correlation",
            json={"columns": ["a", "b"], "method": method},
        )
        assert response.status_code == 200, response.text
        cell = response.json()["cells"][0]
        expected, _ = oracle([r["a"] for r in rows], [r["b"] for r in rows])
        assert cell["coefficient"] == pytest.approx(expected, abs=1e-12)
        assert cell["n_valid"] == 200
        assert cell["method"] == method


def test_correlation_rejects_non_numeric_columns(client):
    rows, columns = _numeric_rows(30)
    loaded = _upload(client, rows, columns)
    response = client.post(
        f"/api/datasets/{loaded['dataset']['dataset_id']}/explore/correlation",
        json={"columns": ["a", "g"], "method": "pearson"},
    )
    assert response.status_code == 422


def test_correlation_via_demo_matches_independent_read(client):
    """The bundled clean_control demo against an independent pandas/scipy read."""
    loaded = client.post("/api/demos/clean_control/load").json()
    dataset_id = loaded["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/explore/correlation",
        json={"columns": ["x1", "x2", "x3"], "method": "spearman"},
    )
    assert response.status_code == 200
    cells = {(cell["x"], cell["y"]): cell for cell in response.json()["cells"]}

    import pandas as pd

    csv_path = Path(__file__).resolve().parents[2] / "datasets" / "clean_control.csv"
    frame = pd.read_csv(csv_path)
    for (x_name, y_name), cell in cells.items():
        expected, _ = sps.spearmanr(frame[x_name], frame[y_name])
        assert cell["coefficient"] == pytest.approx(expected, abs=1e-12), (x_name, y_name)
        assert cell["n_valid"] == len(frame)


def test_distribution_histogram_and_group_denominators(client):
    rows, columns = _numeric_rows(40)
    loaded = _upload(client, rows, columns)
    dataset_id = loaded["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/explore/distribution",
        json={"column": "a", "bins": 8, "group_by": "g"},
    )
    payload = response.json()
    assert payload["kind"] == "numeric"
    assert payload["population"] == 40
    assert sum(payload["counts"]) == 40
    groups = {g["group"]: g for g in payload["groups"]}
    assert set(groups) == {"even", "odd"}
    assert groups["even"]["rows"] == 20
    assert sum(groups["even"]["counts"]) == groups["even"]["valid_count"]
    assert groups["even"]["box"]["n"] == groups["even"]["valid_count"]


def test_distribution_categorical_frequencies(client):
    rows, columns = _numeric_rows(30)
    loaded = _upload(client, rows, columns)
    response = client.post(
        f"/api/datasets/{loaded['dataset']['dataset_id']}/explore/distribution",
        json={"column": "s"},
    )
    payload = response.json()
    assert payload["kind"] == "categorical"
    assert payload["population"] == 30
    levels = {level["value"]: level["count"] for level in payload["levels"]}
    assert levels == {"train": 20, "test": 10}


def test_missingness_exact_counts_and_group_breakdown(client):
    rows, columns = _numeric_rows(30)
    for i, row in enumerate(rows):
        if i % 5 == 0:
            row["a"] = ""
    loaded = _upload(client, rows, columns)
    dataset_id = loaded["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/explore/missingness",
        json={"columns": ["a", "b", "g"], "group_by": "g"},
    )
    payload = response.json()
    per_column = {c["column"]: c for c in payload["per_column"]}
    assert per_column["a"]["missing_count"] == 6
    assert per_column["a"]["missing_pct"] == pytest.approx(20.0)
    assert per_column["b"]["missing_count"] == 0
    groups = {g["group"]: g for g in payload["groups"]}
    even_missing = sum(c["missing_count"] for c in groups["even"]["per_column"] if c["column"] == "a")
    odd_missing = sum(c["missing_count"] for c in groups["odd"]["per_column"] if c["column"] == "a")
    assert even_missing + odd_missing == 6
    # The display matrix never pretends to be the full population.
    assert payload["matrix"]["row_count_drawn"] <= 30


def test_series_rejects_unknown_column(client):
    rows, columns = _numeric_rows(30)
    loaded = _upload(client, rows, columns)
    response = client.post(
        f"/api/datasets/{loaded['dataset']['dataset_id']}/explore/series",
        json={"columns": ["does_not_exist"]},
    )
    assert response.status_code == 422


def test_series_caps_columns(client):
    rows, columns = _numeric_rows(30)
    loaded = _upload(client, rows, columns)
    response = client.post(
        f"/api/datasets/{loaded['dataset']['dataset_id']}/explore/series",
        json={"columns": ["a"] * 33},
    )
    assert response.status_code == 422


def test_rows_endpoint_returns_exact_rows_by_immutable_id(client):
    rows, columns = _numeric_rows(30)
    for i, row in enumerate(rows):
        if i == 4:
            row["a"] = ""  # missing cell stays an empty string, not "nan"
    loaded = _upload(client, rows, columns)
    dataset_id = loaded["dataset"]["dataset_id"]
    schema = client.get(f"/api/datasets/{dataset_id}/explore/schema").json()
    first_id = "row-000001"
    fifth_id = "row-000005"
    assert first_id in [f"row-{i + 1:06d}" for i in range(schema["row_count"])]
    response = client.post(
        f"/api/datasets/{dataset_id}/explore/rows",
        json={"ids": [fifth_id, first_id, "row-999999"], "columns": ["a", "g"]},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    by_id = {row["id"]: row for row in payload["rows"]}
    assert set(by_id) == {first_id, fifth_id}
    assert payload["unknown_ids"] == ["row-999999"]
    assert by_id[first_id]["values"]["g"] in {"even", "odd"}
    assert by_id[fifth_id]["values"]["a"] == ""
    # File-order index travels with the row for provenance.
    assert by_id[first_id]["index"] == 0
    assert by_id[fifth_id]["index"] == 4


def test_distribution_with_selection_overlay_is_exact(client):
    rows, columns = _numeric_rows(40)
    loaded = _upload(client, rows, columns)
    dataset_id = loaded["dataset"]["dataset_id"]
    # Selection: the 20 "even" rows. Base layer must stay the full population.
    response = client.post(
        f"/api/datasets/{dataset_id}/explore/distribution",
        json={"column": "a", "bins": 10, "filters": [{"column": "g", "values": ["even"]}]},
    )
    payload = response.json()
    assert payload["population"] == 40
    assert sum(payload["counts"]) == 40
    selection = payload["selection"]
    assert selection["population"] == 20
    assert sum(selection["counts"]) == selection["valid_count"]
    assert selection["box"]["n"] == 20
    assert "active selection" in payload["filters_note"]


def test_missingness_with_selection_reports_both_populations(client):
    rows, columns = _numeric_rows(30)
    for i, row in enumerate(rows):
        if i % 5 == 0:  # rows 0,5,10,15,20,25 — three even, three odd
            row["a"] = ""
    loaded = _upload(client, rows, columns)
    dataset_id = loaded["dataset"]["dataset_id"]
    response = client.post(
        f"/api/datasets/{dataset_id}/explore/missingness",
        json={"columns": ["a"], "filters": [{"column": "g", "values": ["even"]}]},
    )
    payload = response.json()
    assert payload["population"] == 15
    # Of the six missing cells, exactly three fall on even rows.
    assert payload["per_column"][0]["missing_count"] == 3
    # population_counts keeps the whole-dataset numbers for comparison.
    assert payload["population_total"] == 30
    assert payload["population_counts"][0]["missing_count"] == 6


def test_population_mask_union_within_column(client):
    from app.explore.selection import Predicate, population_mask

    dataset = make_dataset(
        [{"v": float(v)} for v in range(6)], columns=["v"]
    )
    mask = population_mask(
        dataset,
        [Predicate(column="v", min=0.0, max=1.0), Predicate(column="v", min=4.0, max=5.0)],
    )
    assert mask.tolist() == [True, True, False, False, True, True]


def test_sampling_caption_uses_ordinals():
    from app.explore.sampling import _ordinal, render_sample

    assert _ordinal(1) == "1st"
    assert _ordinal(3) == "3rd"
    assert _ordinal(9) == "9th"
    assert _ordinal(12) == "12th"
    assert _ordinal(111) == "111th"
    sample = render_sample(3000, 1000)
    assert "every 3rd row" in sample.description
