"""Independent numerical tests for the S9B overlap-histogram extension.

The S9B overlap figure needs an aggregated per-arm propensity distribution. The
only backend change S9B makes is this bounded addition to the S9A overlap
payload; it is verified here against hand-computed bin assignments, not against
the implementation's own output.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.causal.estimation.diagnostics import (
    HISTOGRAM_BINS,
    overlap_payload,
    propensity_histogram,
)


def _payload(propensity: np.ndarray, treatment: np.ndarray) -> dict:
    return propensity_histogram(propensity, treatment)


def test_edges_are_the_fixed_unit_interval_grid():
    histogram = _payload(np.array([0.2, 0.8]), np.array([1, 0]))
    assert histogram["bin_count"] == HISTOGRAM_BINS == 20
    assert len(histogram["bin_edges"]) == HISTOGRAM_BINS + 1
    assert histogram["bin_edges"][0] == 0.0
    assert histogram["bin_edges"][-1] == 1.0
    # Width 0.05 exactly, uniformly spaced.
    assert np.allclose(np.diff(histogram["bin_edges"]), 0.05)


def test_counts_match_hand_computed_bin_assignment():
    # Bins are [0, .05), [.05, .10), ..., [.95, 1].
    propensity = np.array([0.001, 0.049, 0.05, 0.074, 0.999])
    treatment = np.array([1, 1, 0, 0, 0])
    histogram = _payload(propensity, treatment)

    treated = histogram["treated_counts"]
    control = histogram["control_counts"]
    # Treated: 0.001 and 0.049 both fall in the first bin.
    assert treated[0] == 2
    assert sum(treated) == 2
    # Control: 0.05 and 0.074 in bin 1, 0.999 in the last bin.
    assert control[1] == 2
    assert control[-1] == 1
    assert sum(control) == 3


def test_counts_sum_to_arm_sizes_and_shares_sum_to_one():
    rng = np.random.default_rng(20240901)
    propensity = rng.uniform(0.02, 0.98, size=1200)
    treatment = (rng.random(1200) < propensity).astype(int)

    histogram = _payload(propensity, treatment)
    assert sum(histogram["treated_counts"]) == int(treatment.sum())
    assert sum(histogram["control_counts"]) == int((treatment == 0).sum())
    assert pytest.approx(sum(histogram["treated_share"]), abs=1e-6) == 1.0
    assert pytest.approx(sum(histogram["control_share"]), abs=1e-6) == 1.0

    # Shares are within-arm relative frequencies, not shares of the pooled rows.
    first_treated = histogram["treated_counts"][0] / treatment.sum()
    assert histogram["treated_share"][0] == pytest.approx(first_treated, abs=1e-7)


def test_histogram_never_exposes_individual_scores():
    histogram = _payload(np.array([0.31, 0.32, 0.77]), np.array([1, 1, 0]))
    assert set(histogram) == {
        "bin_edges",
        "bin_count",
        "treated_counts",
        "control_counts",
        "treated_share",
        "control_share",
        "definition",
    }
    # Only bounded aggregates leave the server: no per-row array can be read
    # out of a payload whose every list is at most one value longer than the
    # fixed bin count.
    for value in histogram.values():
        if isinstance(value, list):
            assert len(value) <= HISTOGRAM_BINS + 1


def test_overlap_payload_carries_the_histogram_next_to_the_quantiles():
    rng = np.random.default_rng(7)
    propensity = rng.uniform(0.05, 0.95, size=200)
    treatment = (rng.random(200) < 0.5).astype(int)
    outcome = rng.normal(size=200)

    payload = overlap_payload(propensity, treatment, outcome)
    histogram = payload["propensity_histogram"]
    assert sum(histogram["treated_counts"]) + sum(histogram["control_counts"]) == 200
    # The existing S9A summary is unchanged and still present.
    assert payload["propensity_summary"]["min"] == pytest.approx(propensity.min())
    assert "effective_sample_sizes" in payload
