"""The shipped synthetic demos.

Expected numbers come from the committed manifest, which is produced by the
generators using independent pandas/NumPy operations — never by the audit engine
under test. The comparison is therefore a real check of the engine against
independently computed ground truth.
"""

from __future__ import annotations

import json

import pytest

from app.audit.engine import build_canonicalizer, run_audit
from app.audit.service import audit_existing_split, resolve_or_raise
from app.audit.types import AuditConfig, SplitConfig
from app.core.config import get_settings
from app.splits.strategies import generate_split, summarise
from app.synthetic.generators import DEMO_ORDER, DEMOS, build_demo
from app.synthetic.manifest import get_demo, load_manifest, recommended_audit_config, recommended_roles

from .conftest import findings_for, metric_for

DEMO_SETTINGS = get_settings()


@pytest.fixture(scope="module")
def manifest() -> dict:
    return load_manifest()


def _audit(demo_id: str):
    loaded = get_demo(demo_id)
    dataset = loaded.load(settings=DEMO_SETTINGS)
    result = audit_existing_split(
        dataset,
        roles=recommended_roles(demo_id),
        config=recommended_audit_config(demo_id, settings=DEMO_SETTINGS),
        settings=DEMO_SETTINGS,
    )
    return dataset, result, loaded.manifest_entry


def test_manifest_is_present_well_formed_and_synthetic_only(manifest):
    assert manifest["manifest_schema_version"]
    assert manifest["synthetic_only"] is True
    ids = [entry["demo_id"] for entry in manifest["datasets"]]
    assert ids == list(DEMO_ORDER)
    for entry in manifest["datasets"]:
        assert entry["synthetic"] is True
        assert entry["seed"] is not None
        assert entry["generation_method"]
        assert entry["teaching_point"]
        assert entry["expected_findings"]
        assert len(entry["sha256"]) == 64
        assert entry["row_count"] > 100


def test_committed_csvs_match_a_fresh_generation(manifest):
    import hashlib

    from app.synthetic.manifest import datasets_dir

    for entry in manifest["datasets"]:
        frame, _planted = build_demo(entry["demo_id"])
        from app.synthetic.generators import DEMOS

        path = datasets_dir() / DEMOS[entry["demo_id"]].filename
        expected = path.read_text(encoding="utf-8")
        regenerated = frame.to_csv(index=False, lineterminator="\n")
        assert regenerated == expected, entry["filename"]
        assert hashlib.sha256(expected.encode()).hexdigest() == entry["sha256"]


def test_every_demo_loads_with_the_documented_fingerprint():
    for demo_id in DEMO_ORDER:
        loaded = get_demo(demo_id)
        dataset = loaded.load(settings=DEMO_SETTINGS)
        assert dataset.fingerprint_sha256 == loaded.manifest_entry["sha256"]
        assert dataset.is_synthetic is True
        assert dataset.demo is not None and dataset.demo.synthetic is True
        assert dataset.demo.expected_findings
        assert len(dataset.columns) == loaded.manifest_entry["column_count"]


def test_exact_duplicates_demo_matches_its_planted_counts():
    _dataset, result, entry = _audit("exact_duplicates")
    counts = entry["summary_metrics"]

    finding = findings_for(result, "SS-DUP-001")[0]
    assert finding.severity == "high"
    assert metric_for(result, "SS-DUP-001", "exact_duplicate_test_rows") == counts[
        "cross_split_duplicate_test_rows"
    ]
    assert metric_for(result, "SS-DUP-001", "exact_duplicate_train_rows") == counts[
        "cross_split_duplicate_train_rows"
    ]
    assert metric_for(result, "SS-DUP-001", "exact_duplicate_shared_signatures") == counts[
        "cross_split_duplicate_groups"
    ]
    assert metric_for(result, "SS-DUP-001", "within_test_duplicate_rows") == 2 * counts[
        "intended_within_test_pairs"
    ]
    assert metric_for(result, "SS-DUP-001", "within_train_duplicate_rows") == 2 * counts[
        "intended_within_train_pairs"
    ]
    assert metric_for(result, "SS-DUP-001", "hash_bucket_collisions_rejected") == 0


def test_repeated_entity_demo_matches_its_planted_overlap():
    dataset, result, entry = _audit("repeated_entity")
    counts = entry["summary_metrics"]

    finding = findings_for(result, "SS-ENT-001")[0]
    assert finding.severity == "high"
    assert metric_for(result, "SS-ENT-001", "shared_groups") == counts["shared_entities"]
    assert metric_for(result, "SS-ENT-001", "entity_overlap_test_rows") == counts["test_rows"]
    assert metric_for(result, "SS-ENT-001", "entity_overlap_test_share") == 1.0
    assert metric_for(result, "SS-DUP-001", "exact_duplicate_test_rows") == 0
    assert metric_for(result, "SS-ENT-001", "train_distinct_groups") == counts["customers_total"]
    assert dataset.demo is not None and dataset.demo.recommended_split["kind"] == "group"


def test_chronology_demo_matches_its_planted_violation():
    _dataset, result, entry = _audit("chronology_violation")
    counts = entry["summary_metrics"]

    assert counts["order_violation"] is True
    finding = findings_for(result, "SS-CHR-001")[0]
    assert finding.severity == "high"
    assert metric_for(result, "SS-CHR-001", "chronology_status") == "violation"
    assert metric_for(result, "SS-CHR-001", "train_rows_after_earliest_test") == counts[
        "train_rows_after_earliest_test"
    ]
    assert metric_for(result, "SS-CHR-001", "train_max_timestamp") == counts["latest_train_timestamp"]
    assert metric_for(result, "SS-CHR-001", "test_min_timestamp") == counts["earliest_test_timestamp"]


def test_target_copy_demo_reports_both_the_exact_and_the_partial_copy():
    _dataset, result, entry = _audit("target_copy")
    counts = entry["summary_metrics"]

    findings = findings_for(result, "SS-TGT-001")
    assert len(findings) == 2
    by_severity = {finding.severity: finding for finding in findings}
    assert set(by_severity) == {"high", "medium"}

    exact_coverage = counts["exact_copy_coverage"]
    near_coverage = counts["near_copy_coverage"]
    high_title = by_severity["high"].title
    medium_title = by_severity["medium"].title
    assert "risk_score" in high_title
    assert "risk_band" in medium_title
    assert f"{exact_coverage:.1%}" in high_title
    assert f"{near_coverage:.1%}" in medium_title

    medium_finding = by_severity["medium"]
    assert "majority-class" not in medium_finding.severity_rationale.lower() or "above the" in (
        medium_finding.severity_rationale
    )
    assert any("Counterexamples" in example.label for example in medium_finding.examples)


def test_near_duplicate_demo_matches_its_planted_pairs():
    _dataset, result, entry = _audit("near_duplicates")
    counts = entry["summary_metrics"]

    finding = findings_for(result, "SS-NEAR-001")[0]
    pairs = next(count for count in finding.counts if "Cross-split candidate pairs" in count.label)
    assert pairs.affected == counts["near_duplicate_pairs"]
    assert finding.severity == "medium"
    assert metric_for(result, "SS-DUP-001", "exact_duplicate_test_rows") == 0

    planted = {
        (case["train_row_id"], case["test_row_id"]) for case in entry["planted_cases"]
    }
    reported = {tuple(example.row_ids) for example in finding.examples}
    assert reported
    assert reported <= planted, reported - planted


def test_clean_control_produces_no_findings_and_evaluates_every_check():
    _dataset, result, entry = _audit("clean_control")

    assert entry["is_control"] is True
    assert result.findings == []
    assert set(result.evaluation.evaluated_rule_ids) == {
        "SS-DUP-001",
        "SS-ENT-001",
        "SS-CHR-001",
        "SS-TGT-001",
        "SS-TGT-002",
        "SS-ENT-002",
    }
    assert {check.rule_id for check in result.evaluation.not_evaluated} == {
        "SS-NEAR-001",
        "SS-AVL-001",
        "SS-CHR-002",
        "SS-PPF-001",
        "SS-VRU-001",
    }

    counts = entry["summary_metrics"]
    assert metric_for(result, "SS-CHR-001", "chronology_status") == "ordered"
    assert metric_for(result, "SS-ENT-001", "shared_groups") == 0
    assert metric_for(result, "SS-DUP-001", "exact_duplicate_test_rows") == 0
    assert metric_for(result, "SS-DUP-001", "distinct_feature_signatures") == counts["distinct_entities"]


def test_clean_control_is_not_vacuous_a_random_split_raises_the_chronology_check():
    """The control only looks clean because its split is chronological."""
    loaded = get_demo("clean_control")
    dataset = loaded.load(settings=DEMO_SETTINGS)
    roles = recommended_roles("clean_control")
    resolved, _ = resolve_or_raise(dataset, roles)
    config = recommended_audit_config("clean_control", settings=DEMO_SETTINGS)

    generated = generate_split(
        dataset,
        resolved_entity=resolved.entity_column,
        resolved_target=resolved.target_column,
        resolved_timestamp=resolved.timestamp_column,
        config=SplitConfig(kind="random", label="Random", test_fraction=0.25, seed=12345),
        canonicalizer=build_canonicalizer(config),
    )
    result = run_audit(
        dataset=dataset,
        roles=roles,
        resolved=resolved,
        config=config,
        masks=generated.masks,
        split_summary=summarise(
            strategy_id="random",
            label="Random",
            kind="random",
            generated=generated,
        ),
        settings=DEMO_SETTINGS,
    )
    assert metric_for(result, "SS-CHR-001", "chronology_status") == "violation"
    assert findings_for(result, "SS-CHR-001")


def test_every_evidence_row_id_exists_in_the_audited_dataset():
    for demo_id in DEMO_ORDER:
        dataset, result, _entry = _audit(demo_id)
        valid = set(dataset.row_ids)
        for finding in result.findings:
            for example in finding.examples:
                assert set(example.row_ids) <= valid, (demo_id, example.row_ids)
            for count in finding.counts:
                assert count.denominator >= count.affected >= 0


def test_demo_documentation_matches_the_shipped_configuration(manifest):
    for entry in manifest["datasets"]:
        spec = DEMOS[entry["demo_id"]]
        assert entry["generation_method"] == spec.generation_method
        assert entry["teaching_point"] == spec.teaching_point
        assert entry["expected_findings"] == spec.expected_findings
        assert entry["recommended_audit"] == spec.recommended_audit
        assert json.dumps(entry["planted_cases"]) == json.dumps(
            [json.loads(json.dumps(case)) for case in entry["planted_cases"]]
        )


def test_demo_expected_findings_name_only_registered_rules():
    from app.audit.rules import RULE_TITLES

    for demo_id in DEMO_ORDER:
        for expectation in DEMOS[demo_id].expected_findings:
            assert expectation["rule_id"] in RULE_TITLES, (demo_id, expectation["rule_id"])
            assert expectation["severity"] in {"high", "medium", "low", "info", "none", "not_evaluated"}


def test_audit_config_for_demos_only_enables_near_duplicates_where_documented():
    for demo_id in DEMO_ORDER:
        config = recommended_audit_config(demo_id, settings=DEMO_SETTINGS)
        expected = bool(DEMOS[demo_id].recommended_audit.get("near_duplicates", False))
        assert config.near_duplicates.enabled is expected, demo_id
        assert isinstance(config, AuditConfig)


def test_causal_effect_demo_has_a_binary_treatment_and_documented_true_effect():
    """The S9B demonstration must be estimable and must document its own DGP."""
    loaded = get_demo("causal_effect")
    dataset = loaded.load(settings=DEMO_SETTINGS)
    frame = dataset.frame

    assert sorted(frame["treatment"].unique().tolist()) == ["0", "1"]
    assert (frame["outcome"].astype(float).notna()).all()
    assert loaded.manifest_entry["summary_metrics"]["true_ate"] == 1.5
    # The point of the demo: measured confounding moves the raw contrast away
    # from the true effect, so the studio has something real to correct.
    naive = loaded.manifest_entry["summary_metrics"]["naive_difference_in_units"]
    assert naive > 2.0
    assert "No true propensity" in DEMOS["causal_effect"].generation_method
