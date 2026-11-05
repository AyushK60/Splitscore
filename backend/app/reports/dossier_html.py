"""Self-contained printable HTML for the S7 evidence dossier.

No external CSS, fonts, scripts or images. Every user-supplied value is escaped.
The print stylesheet is the PDF path: the browser's Print / Save as PDF action
renders this document without application chrome.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from html import escape
from typing import Any

from app.reports.dossier import SECTION_IDS

_CSS = """
:root {
  --ink: #18231d; --soft: #5c6b62; --line: #d8d1c2; --paper: #fbf8f1;
  --panel: #f5f1e7; --teal: #0a6d7d; --copper: #9a5b00; --high: #9d2b20;
  --medium: #8a5a0a; --low: #3a6186; --ok: #2a6a4b;
}
* { box-sizing: border-box; }
html { background: #e9e3d6; }
body {
  margin: 0 auto; max-width: 1080px; background: var(--paper); color: var(--ink);
  font: 14px/1.58 "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  padding: 0 0 56px;
}
.cover { background: #12190f; color: #f3ead9; padding: 38px 44px 30px; }
.eyebrow { font: 600 10px/1.4 Consolas, monospace; letter-spacing: .18em; text-transform: uppercase; color: #b4d0bd; }
h1 { font: 650 34px/1.12 "Iowan Old Style", "Palatino Linotype", Georgia, serif; margin: 10px 0 8px; letter-spacing: -.02em; }
.subtitle { color: #d8d1c2; max-width: 70ch; margin: 0; }
.cover-meta { display: flex; flex-wrap: wrap; gap: 8px 24px; margin-top: 22px; font: 11px/1.5 Consolas, monospace; color: #b4d0bd; }
.cover-meta span { overflow-wrap: anywhere; }
.body { padding: 0 44px; }
h2 { font: 650 22px/1.2 "Iowan Old Style", "Palatino Linotype", Georgia, serif; margin: 34px 0 6px; padding-bottom: 7px; border-bottom: 2px solid var(--ink); }
h3 { font-size: 15px; margin: 22px 0 7px; }
h4 { font-size: 13px; margin: 16px 0 5px; }
p { margin: 7px 0; max-width: 82ch; }
ul { margin: 6px 0; padding-left: 20px; }
li { margin: 3px 0; }
.mono, code { font-family: Consolas, "SF Mono", Menlo, monospace; font-size: 12px; }
.muted { color: var(--soft); }
.small { font-size: 12px; }
.lede { font-size: 15px; color: var(--soft); max-width: 82ch; }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 16px 0; }
.stat { border: 1px solid var(--line); background: #fff; padding: 11px 12px; }
.stat b { display: block; font: 650 24px/1.1 "Iowan Old Style", Georgia, serif; }
.stat span { font: 10px/1.4 Consolas, monospace; letter-spacing: .08em; text-transform: uppercase; color: var(--soft); }
.callout { border: 1px solid var(--line); border-left: 4px solid var(--teal); background: #fff; padding: 10px 13px; margin: 12px 0; }
.callout.warn { border-left-color: var(--copper); background: #fdf8ed; }
.callout.danger { border-left-color: var(--high); background: #fdf1ef; }
.callout p:first-child { margin-top: 0; }
.callout p:last-child { margin-bottom: 0; }
table { border-collapse: collapse; width: 100%; margin: 9px 0 14px; font-size: 12.5px; }
th, td { border: 1px solid var(--line); padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: var(--panel); font-weight: 650; }
tbody tr:nth-child(even) td { background: #fdfbf6; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
.badge { display: inline-block; padding: 1px 7px; border-radius: 999px; font: 700 10px/1.6 Consolas, monospace; text-transform: uppercase; letter-spacing: .04em; color: #fff; }
.badge.high { background: var(--high); } .badge.medium { background: var(--medium); }
.badge.low { background: var(--low); } .badge.info { background: #4d5563; }
.badge.ok { background: var(--ok); } .badge.neutral { background: #6b746d; }
.finding { border: 1px solid var(--line); border-left: 5px solid var(--low); background: #fff; padding: 13px 15px; margin: 14px 0; page-break-inside: avoid; }
.finding.high { border-left-color: var(--high); } .finding.medium { border-left-color: var(--medium); }
.finding.low { border-left-color: var(--low); } .finding.info { border-left-color: #4d5563; }
.finding h3 { margin-top: 0; }
.finding .meta { font: 11px/1.5 Consolas, monospace; color: var(--soft); }
.scorecard { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 12px 0; }
.score { border: 1px solid var(--line); background: #fff; padding: 11px 13px; }
.score h3 { margin: 0 0 4px; font-size: 14px; }
.score .status { font: 600 10px/1.5 Consolas, monospace; letter-spacing: .06em; text-transform: uppercase; color: var(--soft); }
.model { border: 1px solid var(--line); background: #fff; padding: 14px 16px; margin: 14px 0; page-break-inside: avoid; }
.model h3 { margin-top: 0; }
.kv { display: grid; grid-template-columns: minmax(150px, 220px) 1fr; gap: 0; border-top: 1px solid var(--line); margin: 8px 0 14px; }
.kv dt, .kv dd { margin: 0; padding: 5px 8px; border-bottom: 1px solid var(--line); }
.kv dt { color: var(--soft); font: 11px/1.5 Consolas, monospace; }
.kv dd { overflow-wrap: anywhere; }
.section-unavailable { border: 1px dashed var(--line); background: var(--panel); padding: 12px 14px; color: var(--soft); }
.toc { display: flex; flex-wrap: wrap; gap: 5px 14px; margin: 14px 0 0; font: 11px/1.5 Consolas, monospace; }
.toc a { color: var(--teal); text-decoration: none; }
.footer { margin: 40px 44px 0; padding-top: 12px; border-top: 1px solid var(--line); color: var(--soft); font-size: 11.5px; }
@media (max-width: 760px) {
  .cover, .body { padding-left: 20px; padding-right: 20px; }
  .summary-grid { grid-template-columns: repeat(2, 1fr); }
  .scorecard { grid-template-columns: 1fr; }
  .kv { grid-template-columns: 1fr; }
  .kv dt { border-bottom: 0; padding-bottom: 0; }
}
@media print {
  @page { margin: 16mm 13mm; }
  html, body { background: #fff; }
  body { max-width: none; padding: 0; font-size: 10.5px; }
  .cover { padding: 22px 24px 18px; print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  .body { padding: 0 24px; }
  h1 { font-size: 27px; }
  h2 { font-size: 18px; margin-top: 24px; page-break-after: avoid; }
  h3 { page-break-after: avoid; }
  .finding, .model, .score, table, .callout { page-break-inside: avoid; }
  .footer { margin-left: 24px; margin-right: 24px; }
  a { color: inherit; text-decoration: none; }
}
"""


def _esc(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        return ", ".join(_esc(item) for item in value) if value else "—"
    if isinstance(value, dict):
        return escape(json.dumps(value, ensure_ascii=False, sort_keys=True), quote=True)
    return escape(str(value), quote=True)


def _text(value: object) -> str:
    return _esc(value)


def _table(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    *,
    numeric: set[int] | None = None,
    raw: set[int] | None = None,
) -> str:
    """Render a table, escaping every cell except an explicit raw allowlist.

    `raw` is reserved for markup this module generated itself (severity badges).
    User-supplied values must continue through `_esc`.
    """
    numeric = numeric or set()
    raw = raw or set()
    head = "".join(f"<th>{_esc(header)}</th>" for header in headers)
    body = []
    for row in rows:
        cells = []
        for index, cell in enumerate(row):
            cls = ' class="num"' if index in numeric else ""
            rendered = str(cell) if index in raw else _esc(cell)
            cells.append(f"<td{cls}>{rendered}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _kv(pairs: Iterable[tuple[str, object]]) -> str:
    return (
        '<dl class="kv">'
        + "".join(f"<dt>{_esc(key)}</dt><dd>{_esc(value)}</dd>" for key, value in pairs)
        + "</dl>"
    )


def _list(items: Iterable[object]) -> str:
    values = [item for item in items if item not in (None, "")]
    if not values:
        return '<p class="muted">None recorded.</p>'
    return "<ul>" + "".join(f"<li>{_esc(item)}</li>" for item in values) + "</ul>"


def _badge(value: object, tone: str | None = None) -> str:
    text = str(value or "unknown")
    cls = tone or text.lower()
    if cls not in {"high", "medium", "low", "info", "ok", "neutral"}:
        cls = "neutral"
    return f'<span class="badge {cls}">{_esc(text)}</span>'


def _section_heading(section: dict[str, Any]) -> str:
    return (
        f'<section id="{_esc(section["id"])}">'
        f"<h2>{_esc(section['title'])}</h2>"
        f'<p class="lede">{_esc(section["description"])}</p>'
    )


def _summary(section: dict[str, Any]) -> str:
    data = section["data"]
    split = data.get("split") or {}
    stats = (
        f'<div class="summary-grid">'
        f'<div class="stat"><b>{_esc(data.get("findings_total"))}</b><span>findings</span></div>'
        f'<div class="stat"><b>{_esc(data.get("evaluated_rule_count"))}</b><span>checks evaluated</span></div>'
        f'<div class="stat"><b>{_esc(data.get("not_evaluated_count"))}</b><span>not evaluated</span></div>'
        f'<div class="stat"><b>{_esc(data.get("model_count"))}</b><span>model runs</span></div>'
        f"</div>"
    )
    analyses = _table(
        ["Analysis", "Run", "Status"],
        [
            [entry.get("label"), entry.get("run_id") or "—", entry.get("status")]
            for entry in data.get("analyses", [])
        ],
    )
    key_findings = data.get("key_findings", [])
    findings_html = (
        _table(
            ["Severity", "Rule", "Finding"],
            [[_badge(item.get("severity")), item.get("rule_id"), item.get("title")] for item in key_findings],
            raw={0},
        )
        if key_findings
        else '<p class="muted">No findings are present in the included audit run.</p>'
    )
    cautions = "".join(f"<li>{_esc(item)}</li>" for item in data.get("cautions", []))
    return (
        _section_heading(section)
        + f"<p><strong>Study:</strong> {_esc(data.get('study_title'))}"
        + (f" — {_esc(data.get('objective'))}" if data.get("objective") else "")
        + "</p>"
        + f"<p><strong>Audited split:</strong> {_esc(split.get('label'))} · "
        + f"{_esc(split.get('train_rows'))} train / {_esc(split.get('test_rows'))} test rows.</p>"
        + f"<p><strong>Audit headline:</strong> {_esc(data.get('audit_headline') or 'No audit run included.')}</p>"
        + stats
        + "<h3>Analyses in this dossier</h3>"
        + analyses
        + "<h3>Key findings</h3>"
        + findings_html
        + "<h3>Cautions for a reviewer</h3>"
        + f"<ul>{cautions}</ul>"
        + f'<p class="small muted">{_esc(data.get("note"))}</p>'
        + "</section>"
    )


def _provenance(section: dict[str, Any]) -> str:
    data = section["data"]
    dataset = data["dataset"]
    profile = data["profile"]
    columns = data.get("columns", [])
    rows = [
        [
            column.get("column"),
            column.get("detected_type"),
            column.get("declared_type"),
            ", ".join(column.get("roles", [])),
            column.get("missing_count"),
            column.get("distinct_count"),
            column.get("unit"),
        ]
        for column in columns
    ]
    return (
        _section_heading(section)
        + _kv(
            [
                ("Dataset", dataset.get("name")),
                ("Source", dataset.get("source")),
                ("Synthetic", dataset.get("is_synthetic")),
                ("Demo id", dataset.get("demo_id")),
                ("Rows × columns", f"{dataset.get('row_count')} × {dataset.get('column_count')}"),
                ("SHA-256", dataset.get("sha256")),
                ("Loaded at", dataset.get("created_at_utc")),
                (
                    "Numeric / datetime columns",
                    f"{profile.get('numeric_columns')} / {profile.get('datetime_columns')}",
                ),
                ("Exact duplicate rows", profile.get("duplicate_rows")),
            ]
        )
        + "<h3>Column dictionary</h3>"
        + _table(
            ["Column", "Detected", "Declared", "Roles", "Missing", "Distinct", "Unit"],
            rows,
            numeric={4, 5},
        )
        + "<h3>Profile warnings</h3>"
        + _list(profile.get("warnings", []))
        + f'<p class="small muted">{_esc(data.get("role_note"))}</p>'
        + "</section>"
    )


def _study(section: dict[str, Any]) -> str:
    data = section["data"]
    completion = data.get("completion") or {}
    fields = data.get("declared_fields", [])
    roles = (data.get("roles") or {}).get("assignments", {})
    role_rows = [[column, ", ".join(values)] for column, values in sorted(roles.items())]
    issues = data.get("issues", [])
    return (
        _section_heading(section)
        + _kv(
            [
                ("Study id", data.get("study_id")),
                ("Revision", data.get("revision")),
                ("Required fields declared", f"{completion.get('declared')} / {completion.get('required')}"),
                ("Missing required fields", completion.get("missing")),
                ("Updated", data.get("updated_at_utc")),
            ]
        )
        + "<h3>Declared study fields</h3>"
        + (
            _table(["Field", "Value"], [[field.get("label"), field.get("value")] for field in fields])
            if fields
            else '<p class="muted">No study fields were declared. Missing values are not filled in.</p>'
        )
        + "<h3>Role declarations</h3>"
        + (
            _table(["Column", "Research roles"], role_rows)
            if role_rows
            else '<p class="muted">No roles declared.</p>'
        )
        + "<h3>Study issues</h3>"
        + (
            _table(
                ["Severity", "Code", "Message"],
                [
                    [_badge(issue.get("severity")), issue.get("code"), issue.get("message")]
                    for issue in issues
                ],
                raw={0},
            )
            if issues
            else '<p class="muted">No study issues recorded.</p>'
        )
        + f'<p class="small muted">{_esc(data.get("note"))}</p>'
        + "</section>"
    )


def _audit(section: dict[str, Any]) -> str:
    data = section["data"]
    split = data.get("split") or {}
    evaluation = data.get("evaluation") or {}
    outcomes = data.get("rule_outcomes", [])
    not_evaluated = data.get("not_evaluated", [])
    return (
        _section_heading(section)
        + _kv(
            [
                ("Run id", data.get("run_id")),
                ("Generated", data.get("generated_at_utc")),
                ("Split", split.get("label")),
                ("Split kind", split.get("kind")),
                ("Train / test rows", f"{split.get('train_rows')} / {split.get('test_rows')}"),
                ("Achieved test fraction", split.get("achieved_test_fraction")),
                ("Seed", split.get("seed")),
                ("Headline", evaluation.get("headline")),
                ("Findings", evaluation.get("findings_total")),
            ]
        )
        + "<h3>Rule outcomes</h3>"
        + _table(
            ["Rule", "Title", "Status", "Findings", "Duration (ms)"],
            [
                [
                    outcome.get("rule_id"),
                    outcome.get("title"),
                    outcome.get("status"),
                    outcome.get("finding_count"),
                    outcome.get("duration_ms"),
                ]
                for outcome in outcomes
            ],
            numeric={3, 4},
        )
        + "<h3>Not evaluated</h3>"
        + (
            _table(
                ["Rule", "Status", "Reason"],
                [[item.get("rule_id"), item.get("status"), item.get("reason")] for item in not_evaluated],
            )
            if not_evaluated
            else '<p class="muted">Every enabled check was evaluated.</p>'
        )
        + "<h3>Audit limitations</h3>"
        + _list(data.get("limitations", []))
        + "</section>"
    )


def _scorecard(section: dict[str, Any]) -> str:
    data = section["data"]
    cards = []
    for category in data.get("categories", []):
        rules = category.get("rules", [])
        cards.append(
            '<div class="score">'
            f"<h3>{_esc(category.get('label'))}</h3>"
            f'<p class="status">{_esc(category.get("status"))} · {_esc(category.get("finding_count"))} finding(s)</p>'
            f'<p class="small">{_esc(category.get("affected_rows"))} affected row(s) where reported.</p>'
            + _table(
                ["Rule", "Status", "Findings"],
                [[rule.get("rule_id"), rule.get("status"), rule.get("finding_count")] for rule in rules],
                numeric={2},
            )
            + "</div>"
        )
    return (
        _section_heading(section)
        + f'<div class="scorecard">{"".join(cards)}</div>'
        + f'<p class="small muted">{_esc(data.get("note"))}</p>'
        + "</section>"
    )


def _findings(section: dict[str, Any]) -> str:
    data = section["data"]
    items = data.get("items", [])
    if not items:
        return (
            _section_heading(section)
            + '<div class="callout"><p><strong>No findings were produced by the included audit run.</strong> '
            "That is not evidence that the dataset or split is free of leakage; inspect the "
            "not-evaluated list and the audit limitations.</p></div></section>"
        )
    blocks = []
    for index, finding in enumerate(items, start=1):
        counts = _table(
            ["Count", "Affected", "Denominator", "Unit", "Scope", "Note"],
            [
                [
                    count.get("label"),
                    count.get("affected"),
                    count.get("denominator"),
                    count.get("unit"),
                    count.get("scope"),
                    count.get("note"),
                ]
                for count in finding.get("counts", [])
            ],
            numeric={1, 2},
        )
        examples = []
        for example in finding.get("examples", []):
            details = example.get("details") or {}
            examples.append(
                f"<h4>{_esc(example.get('label'))}</h4>"
                f'<p class="mono small">Row IDs: {_esc(example.get("row_ids"))}</p>'
                + (_table(["Field", "Value"], sorted(details.items())) if details else "")
            )
        if not examples:
            examples.append('<p class="muted">No examples were carried into this finding.</p>')
        truncated = (
            f'<p class="small muted">Evidence is bounded: {len(finding.get("examples", []))} of '
            f"{finding.get('example_total')} example group(s) are included.</p>"
            if finding.get("examples_truncated")
            else ""
        )
        blocks.append(
            f'<article class="finding {_esc(finding.get("severity"))}">'
            f"<h3>{index}. {_esc(finding.get('title'))}</h3>"
            f'<p class="meta">{_badge(finding.get("severity"))} · {_esc(finding.get("rule_id"))}</p>'
            f"<p><strong>Why this severity:</strong> {_esc(finding.get('severity_rationale'))}</p>"
            f"<p>{_esc(finding.get('description'))}</p>"
            f"<p><strong>Evidence summary:</strong> {_esc(finding.get('evidence_summary'))}</p>"
            f"{counts}<h4>Evidence</h4>{''.join(examples)}{truncated}"
            f"<p><strong>Recommended action:</strong> {_esc(finding.get('recommended_action'))}</p>"
            f"<h4>Limitations</h4>{_list(finding.get('limitations', []))}"
            f"<h4>Assumptions</h4>{_list(finding.get('assumptions', []))}"
            "</article>"
        )
    return _section_heading(section) + "".join(blocks) + "</section>"


def _comparison(section: dict[str, Any]) -> str:
    data = section["data"]
    rows = data.get("rows", [])
    table_rows = []
    for row in rows:
        findings = row.get("finding_counts") or {}
        table_rows.append(
            [
                row.get("label"),
                row.get("kind"),
                "yes" if row.get("supported") else "no",
                row.get("train_rows"),
                row.get("test_rows"),
                row.get("achieved_test_fraction"),
                row.get("exact_duplicate_test_share"),
                row.get("entity_overlap_test_share"),
                row.get("chronology_status"),
                sum(int(value) for value in findings.values()),
            ]
        )
    return (
        _section_heading(section)
        + _kv(
            [
                ("Run id", data.get("run_id")),
                ("Generated", data.get("generated_at_utc")),
                ("Candidates", len(rows)),
            ]
        )
        + _table(
            [
                "Strategy",
                "Kind",
                "Supported",
                "Train",
                "Test",
                "Achieved test",
                "Duplicate test share",
                "Entity overlap share",
                "Chronology",
                "Findings",
            ],
            table_rows,
            numeric={3, 4, 5, 6, 7, 9},
        )
        + f'<div class="callout warn"><p>{_esc(data.get("selection_note"))}</p></div>'
        + "<h3>Comparison limitations</h3>"
        + _list(data.get("limitations", []))
        + "</section>"
    )


def _metric_rows(metrics: dict[str, Any]) -> list[list[object]]:
    keys = (
        "accuracy",
        "balanced_accuracy",
        "roc_auc",
        "average_precision",
        "prevalence",
        "mae",
        "rmse",
        "r2",
    )
    return [[key, metrics.get(key)] for key in keys if key in metrics]


def _models(section: dict[str, Any]) -> str:
    data = section["data"]
    blocks = []
    for model in data.get("runs", []):
        if model.get("kind") == "statistical_model":
            spec = model.get("specification") or {}
            population = model.get("population") or {}
            fit = model.get("fit") or {}
            coefficients = model.get("coefficients", [])
            diagnostics = model.get("diagnostics") or {}
            blocks.append(
                '<article class="model">'
                f"<h3>{_esc(model.get('label') or model.get('run_id'))}</h3>"
                f'<p class="meta">{_esc(model.get("run_id"))} · statistical model · {_esc(model.get("task"))}</p>'
                + _kv(
                    [
                        ("Formula", spec.get("formula")),
                        ("Analysed rows", population.get("analyzed")),
                        ("Excluded rows", population.get("excluded")),
                        ("Missing policy", population.get("policy")),
                        ("Fit method", fit.get("method")),
                        ("R²", fit.get("r_squared")),
                        ("Adjusted R²", fit.get("adjusted_r_squared")),
                        ("AIC / BIC", f"{fit.get('aic')} / {fit.get('bic')}"),
                        ("Condition number", diagnostics.get("condition_number")),
                    ]
                )
                + "<h4>Coefficients</h4>"
                + _table(
                    ["Term", "Estimate", "Std. error", "95% low", "95% high", "p-value"],
                    [
                        [
                            coefficient.get("term"),
                            coefficient.get("estimate"),
                            coefficient.get("std_error"),
                            coefficient.get("ci_low"),
                            coefficient.get("ci_high"),
                            coefficient.get("p_value"),
                        ]
                        for coefficient in coefficients
                    ],
                    numeric={1, 2, 3, 4, 5},
                )
                + "<h4>Warnings</h4>"
                + _list([warning.get("message") for warning in model.get("warnings", [])])
                + f'<p class="small muted">{_esc(model.get("note"))}</p>'
                + "</article>"
            )
            continue
        if model.get("kind") == "prediction_model":
            spec = model.get("specification") or {}
            selected = model.get("selected") or {}
            evaluation = model.get("evaluation") or {}
            metrics = evaluation.get("metrics") or {}
            diagnostics = model.get("diagnostics") or {}
            split = model.get("split") or {}
            partitions = split.get("partitions") or {}
            subgroups = model.get("subgroups") or {}
            subgroup_rows = subgroups.get("rows", [])
            blocks.append(
                '<article class="model">'
                f"<h3>{_esc(model.get('label') or model.get('run_id'))}</h3>"
                f'<p class="meta">{_esc(model.get("run_id"))} · predictive model · {_esc(model.get("task"))}</p>'
                + _kv(
                    [
                        ("Outcome", model.get("outcome")),
                        ("Selected model", selected.get("label")),
                        ("Split source", split.get("source")),
                        (
                            "Fit / validation / test",
                            f"{partitions.get('fit')} / {partitions.get('validation')} / {partitions.get('test')}",
                        ),
                        ("Refit rows", selected.get("refit_rows")),
                        ("Test rows", evaluation.get("n")),
                    ]
                )
                + "<h4>Held-out metrics</h4>"
                + _table(["Metric", "Value"], _metric_rows(metrics), numeric={1})
                + "<h4>Diagnostics</h4>"
                + _kv(
                    [
                        (
                            "Calibration Brier",
                            (diagnostics.get("calibration_summary") or {}).get("brier_score"),
                        ),
                        (
                            "Calibration ECE",
                            (diagnostics.get("calibration_summary") or {}).get("expected_calibration_error"),
                        ),
                        ("Q–Q", (diagnostics.get("qq") or {}).get("applicable")),
                        ("Influence", (diagnostics.get("influence") or {}).get("applicable")),
                        (
                            "Permutation importance",
                            (diagnostics.get("permutation_importance") or {}).get("applicable"),
                        ),
                    ]
                )
                + (
                    "<h4>Subgroups</h4>"
                    + _table(
                        ["Group", "n", "Metric", "95% low", "95% high", "Warning"],
                        [
                            [
                                row.get("group"),
                                row.get("n"),
                                row.get("metric"),
                                row.get("ci_low"),
                                row.get("ci_high"),
                                row.get("warning"),
                            ]
                            for row in subgroup_rows
                        ],
                        numeric={1, 2, 3, 4},
                    )
                    + f'<p class="small muted">{_esc(subgroups.get("comparison_note"))}</p>'
                    if subgroup_rows
                    else ""
                )
                + "<h4>Warnings</h4>"
                + _list([warning.get("message") for warning in model.get("warnings", [])])
                + f'<p class="small muted">{_esc(model.get("note"))}</p>'
                + "</article>"
            )
            continue
        blocks.append(
            f'<article class="model"><h3>{_esc(model.get("label") or model.get("run_id"))}</h3>'
            f'<p class="muted">{_esc(model.get("note"))}</p></article>'
        )
    return _section_heading(section) + "".join(blocks) + "</section>"


def _limitations(section: dict[str, Any]) -> str:
    data = section["data"]
    not_evaluated = data.get("not_evaluated", [])
    model_warnings = data.get("model_warnings", [])
    return (
        _section_heading(section)
        + "<h3>Audit limitations</h3>"
        + _list(data.get("audit_limitations", []))
        + "<h3>Audit assumptions</h3>"
        + _list(data.get("audit_assumptions", []))
        + "<h3>Comparison limitations</h3>"
        + _list(data.get("comparison_limitations", []))
        + "<h3>Dataset and profile warnings</h3>"
        + _list([*data.get("dataset_warnings", []), *data.get("profile_warnings", [])])
        + "<h3>Model warnings</h3>"
        + (
            _table(
                ["Run", "Warnings"],
                [
                    [entry.get("run_id"), [warning.get("message") for warning in entry.get("warnings", [])]]
                    for entry in model_warnings
                ],
            )
            if model_warnings
            else '<p class="muted">No model warnings were recorded for the included runs.</p>'
        )
        + "<h3>Not evaluated</h3>"
        + (
            _table(
                ["Rule", "Status", "Reason"],
                [[item.get("rule_id"), item.get("status"), item.get("reason")] for item in not_evaluated],
            )
            if not_evaluated
            else '<p class="muted">No not-evaluated checks were recorded in the included audit.</p>'
        )
        + "<h3>General scope</h3>"
        + _list(data.get("general", []))
        + "</section>"
    )


def _reproducibility(section: dict[str, Any]) -> str:
    data = section["data"]
    return (
        _section_heading(section)
        + _kv(
            [
                ("Report schema", data.get("report_schema_version")),
                ("Application", f"{data.get('app', {}).get('name')} {data.get('app', {}).get('version')}"),
                ("Generated", data.get("generated_at_utc")),
                ("Dataset id", data.get("dataset_id")),
                ("Dataset SHA-256", data.get("dataset_sha256")),
                ("Rows × columns", f"{data.get('row_count')} × {data.get('column_count')}"),
                ("Audit run", data.get("audit_run_id")),
                ("Comparison run", data.get("comparison_run_id")),
                ("Model runs", data.get("model_run_ids")),
            ]
        )
        + f"<p>{_esc(data.get('deterministic_note'))}</p>"
        + f'<p class="small muted">{_esc(data.get("storage_note"))}</p>'
        + "</section>"
    )


_RENDERERS = {
    "summary": _summary,
    "provenance": _provenance,
    "study": _study,
    "audit": _audit,
    "scorecard": _scorecard,
    "findings": _findings,
    "comparison": _comparison,
    "models": _models,
    "limitations": _limitations,
    "reproducibility": _reproducibility,
}


def render_dossier_html(report: dict[str, Any]) -> str:
    sections = report.get("sections", {})
    included = report.get("included_sections", [])
    body_parts = []
    for section_id in SECTION_IDS:
        if section_id not in included:
            continue
        section = sections.get(section_id)
        if not section:
            continue
        if not section.get("available"):
            body_parts.append(
                _section_heading(section)
                + f'<div class="section-unavailable">{_esc(section.get("reason"))}</div></section>'
            )
            continue
        renderer = _RENDERERS.get(section_id)
        if renderer:
            body_parts.append(renderer(section))
    toc = "".join(
        f'<a href="#{_esc(section_id)}">{_esc(sections.get(section_id, {}).get("title", section_id))}</a>'
        for section_id in included
        if sections.get(section_id, {}).get("available")
    )
    summary = report.get("summary", {})
    dataset = report.get("dataset", {})
    integrity = report.get("integrity", {})
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(report.get("title"))}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="cover">
  <p class="eyebrow">SplitScope · evidence dossier · {_esc(report.get("schema_version"))}</p>
  <h1>{_esc(report.get("title"))}</h1>
  <p class="subtitle">{_esc(summary.get("objective") or "A structured review of the audited split, its evidence and the analyses that were actually run.")}</p>
  <div class="cover-meta">
    <span>{_esc(dataset.get("row_count"))} rows × {_esc(dataset.get("column_count"))} columns</span>
    <span>SHA-256 {_esc(dataset.get("sha256"))}</span>
    <span>Generated {_esc(report.get("generated_at_utc"))}</span>
    <span>{_esc("Synthetic demonstration data" if dataset.get("is_synthetic") else "Uploaded data")}</span>
  </div>
  <nav class="toc">{toc}</nav>
</header>
<main class="body">
{"".join(body_parts)}
</main>
<footer class="footer">
  <p><strong>Evidence integrity.</strong> {_esc(integrity.get("note"))}</p>
  <p>SplitScope audits splits, not models. Findings are evidence about the selected split, never a guarantee that data is safe or that a model will perform well. This dossier is not a causal analysis, an IRB approval or a consent record.</p>
</footer>
</body>
</html>
"""


__all__ = ["render_dossier_html"]
