"""Reports: structure, escaping, determinism and CSV export hardening."""

from __future__ import annotations

import json
from html.parser import HTMLParser

from app.audit.types import SplitAssignment, SplitSummary
from app.reports.csv_export import DANGEROUS_PREFIXES, build_assignment_csv, sanitize_csv_cell
from app.reports.html_report import render_audit_html
from app.reports.json_report import build_audit_report, report_filename

from .conftest import make_dataset, make_roles, run_audit_for

HOSTILE_COLUMN = "<script>alert('x')</script>"
HOSTILE_VALUE = '=HYPERLINK("http://example.invalid","click")'
HOSTILE_NAME = 'orders"><img src=x onerror=alert(1)>.csv'


def _hostile_dataset():
    rows = []
    for index in range(12):
        rows.append(
            {
                "customer": "C1" if index < 6 else "C2",
                "grp": "wide" if index % 2 else "narrow",
                HOSTILE_COLUMN: str(index % 3),
                "label": "1" if index % 2 else "0",
                "split": "train" if index % 4 else "test",
                "note": HOSTILE_VALUE if index == 0 else f"n{index}",
            }
        )
    return make_dataset(rows, name=HOSTILE_NAME)


def _hostile_result():
    dataset = _hostile_dataset()
    roles = make_roles(
        features=["grp", HOSTILE_COLUMN],
        target="label",
        entity="customer",
        split="split",
        metadata_excluded=["note"],
    )
    return run_audit_for(dataset, roles)


def test_json_report_contains_the_required_identity_and_settings_blocks():
    result = _hostile_result()
    report = build_audit_report(result, run_id="run-abc")

    for key in (
        "report_kind",
        "app",
        "schema",
        "run_id",
        "input",
        "roles",
        "resolved_roles",
        "settings",
        "split",
        "evaluation",
        "findings",
        "rule_outcomes",
        "not_evaluated",
        "diagnostics",
        "limitations",
        "assumptions",
        "reproducibility",
        "data_note",
    ):
        assert key in report, key

    assert report["app"]["version"] == result.app_version
    assert report["schema"]["audit_schema_version"] == result.schema_version
    assert report["app"]["generated_at_utc"].endswith("+00:00")
    assert len(report["input"]["sha256"]) == 64
    assert "not anonymisation" in report["input"]["sha256_note"]
    assert report["input"]["row_count"] == result.dataset.row_count
    assert report["settings"]["audit_config"]["strip_whitespace"] is True
    assert report["settings"]["audit_config"]["max_examples"] == result.audit_config.max_examples
    assert report["split"]["train_rows"] == result.split.train_rows
    assert report["split"]["achieved_test_fraction"] == result.split.achieved_test_fraction
    assert "missing_definition" in report["settings"]["limits"]["canonicalization"]
    assert report["reproducibility"]["run_dependent_fields"]
    assert "not included" in report["data_note"]


def test_json_report_does_not_embed_the_full_dataset():
    result = _hostile_result()
    report = build_audit_report(result)
    body = json.dumps(report)
    assert "diagnostics" in report
    # The metadata column values in this fixture are n1, n2, ... and must not appear.
    assert '"n7"' not in body
    assert len(body) < 200_000


def test_json_report_round_trips_through_json():
    report = build_audit_report(_hostile_result())
    reparsed = json.loads(json.dumps(report))
    assert reparsed["report_kind"] == "audit"


def test_html_report_escapes_user_supplied_names_and_values():
    result = _hostile_result()
    html = render_audit_html(result, run_id="run-abc")

    assert "<script>alert('x')</script>" not in html.replace("&lt;script&gt;", "")
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<img src=x onerror=" not in html
    assert "<script" not in html.lower()


class _MarkupAudit(HTMLParser):
    """Collects real tags and attributes from rendered markup."""

    DANGEROUS_TAGS = frozenset({"script", "iframe", "object", "embed", "form", "base", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.dangerous: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        if tag in self.DANGEROUS_TAGS:
            self.dangerous.append(tag)
        for name, value in attrs:
            lowered = name.lower()
            if lowered.startswith("on"):
                self.dangerous.append(f"{tag}[{name}]")
            if lowered == "http-equiv":
                self.dangerous.append(f"{tag}[http-equiv={value}]")
            if lowered in {"href", "src"} and value and value.lower().startswith("javascript:"):
                self.dangerous.append(f"{tag}[{name}=javascript:]")


ALLOWED_TAGS = {
    "html", "head", "meta", "title", "style", "body", "h1", "h2", "h3", "p", "ul", "li",
    "table", "thead", "tbody", "tr", "th", "td", "div", "span", "strong", "section", "em",
}


def test_html_report_contains_no_executable_markup_after_parsing():
    html = render_audit_html(_hostile_result())
    audit = _MarkupAudit()
    audit.feed(html)

    assert audit.dangerous == []
    assert set(audit.tags) <= ALLOWED_TAGS, set(audit.tags) - ALLOWED_TAGS
    # The hostile column name and dataset name are present as text, escaped.
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_html_report_includes_the_synthetic_banner_only_for_synthetic_data():
    result = _hostile_result()
    assert "Synthetic demonstration data" not in render_audit_html(result)

    synthetic = make_dataset(
        [{"x": str(index), "y": str(index * 2), "split": "train" if index % 2 else "test"} for index in range(8)],
        is_synthetic=True,
        source="demo",
    )
    html = render_audit_html(
        run_audit_for(synthetic, make_roles(features=["x", "y"], split="split"))
    )
    assert "Synthetic demonstration data" in html


def test_html_report_states_what_no_findings_means():
    clean = make_dataset(
        [{"x": str(index), "y": str(index * 2), "split": "train" if index % 2 else "test"} for index in range(8)]
    )
    result = run_audit_for(clean, make_roles(features=["x", "y"], split="split"))
    assert result.findings == []

    html = render_audit_html(result)
    assert "No findings were produced" in html
    assert "not evidence that the dataset or the split is free of leakage" in html
    assert "Not evaluated" in html


def test_report_filename_is_filesystem_safe_and_keeps_the_extension_out():
    name = report_filename("audit", HOSTILE_NAME)
    assert "<" not in name and ">" not in name and '"' not in name
    assert name.endswith("Z")
    assert name.startswith("splitscope-audit-")


def test_csv_cell_sanitization_prefixes_only_formula_triggers():
    for prefix in DANGEROUS_PREFIXES:
        assert sanitize_csv_cell(prefix + "cmd") == "'" + prefix + "cmd"
    assert sanitize_csv_cell("row-000123") == "row-000123"
    assert sanitize_csv_cell("-12.5") == "'-12.5"  # a leading minus is still a trigger
    assert sanitize_csv_cell("12.5") == "12.5"
    assert sanitize_csv_cell("") == ""


def test_assignment_csv_is_keyed_by_row_id_and_documents_sanitization():
    summary = SplitSummary(
        strategy_id="group-1",
        label="Group holdout",
        kind="group",
        requested_test_fraction=0.25,
        achieved_test_fraction=0.25,
        train_rows=2,
        test_rows=1,
        seed=12345,
        assignment_id="a-1",
    )
    assignment = SplitAssignment(
        assignment_id="a-1",
        summary=summary,
        train_row_ids=["row-000001", "row-000003"],
        test_row_ids=["row-000002"],
    )
    text = build_assignment_csv(assignment, include_header_note=True)
    lines = text.splitlines()

    assert "prevent spreadsheet formula injection" in lines[0]
    assert lines[1] == "row_id,split,strategy,strategy_kind,achieved_test_fraction,seed"
    assert lines[2].startswith("row-000001,train,")
    assert lines[4].startswith("row-000002,test,")
    assert "12345" in lines[2]
    assert len(lines) == 5


def test_audit_results_are_deterministic_apart_from_timestamps_and_timings():
    first = _hostile_result()
    second = _hostile_result()

    assert first.findings == second.findings
    assert first.rule_outcomes[0].rule_id == second.rule_outcomes[0].rule_id
    assert [outcome.metrics for outcome in first.rule_outcomes] == [
        outcome.metrics for outcome in second.rule_outcomes
    ]
    assert first.diagnostics == second.diagnostics
    assert first.evaluation.model_dump(
        exclude={"headline"}
    ) == second.evaluation.model_dump(exclude={"headline"})
    assert first.split == second.split
    # Timestamps and measured durations are explicitly excluded from determinism.
    assert first.generated_at_utc is not None
    assert first.duration_ms >= 0
