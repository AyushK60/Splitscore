"""Self-contained, printable HTML report.

Constraints this file is written against:

* **Self-contained.** No external CSS, fonts, scripts or images. The file can be
  opened offline and printed to PDF.
* **Escaped.** Every piece of user-supplied text — dataset name, column names,
  cell values inside evidence, filename — passes through :func:`_esc`. A column
  header containing markup is rendered as text, never as markup. Values are only
  ever placed in element text or in escaped attribute values.
* **No dataset dump.** Only the bounded evidence samples already present in the
  result are rendered.
* **No embedded script.** There is no ``<script>`` element at all, so there is
  nothing for injected content to run inside.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from html import escape
from typing import Any

from app.audit.types import (
    AuditResult,
    ComparisonResult,
    DistributionSummary,
    Finding,
    NotEvaluatedCheck,
)
from app.core.version import APP_NAME

SEVERITY_ORDER = ("high", "medium", "low", "info")

_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --ink: #14181f;
  --muted: #5b6472;
  --line: #d6dbe3;
  --bg: #ffffff;
  --panel: #f7f8fa;
  --high: #a3231b;
  --medium: #9a5b00;
  --low: #3b5f8a;
  --info: #4b5563;
  --ok: #1d6b45;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0 auto; padding: 32px 28px 64px; max-width: 1040px; background: var(--bg);
  color: var(--ink); font: 15px/1.55 "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}
h1 {{ font-size: 26px; margin: 0 0 4px; letter-spacing: -0.01em; }}
h2 {{ font-size: 19px; margin: 34px 0 10px; padding-bottom: 6px; border-bottom: 2px solid var(--line); }}
h3 {{ font-size: 16px; margin: 22px 0 8px; }}
p {{ margin: 8px 0; }}
code, .mono {{ font-family: "Consolas", "SF Mono", Menlo, monospace; font-size: 13px; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0 14px; font-size: 13.5px; }}
th, td {{ border: 1px solid var(--line); padding: 6px 9px; text-align: left; vertical-align: top; }}
th {{ background: var(--panel); font-weight: 600; }}
tbody tr:nth-child(even) td {{ background: #fbfcfd; }}
.summary {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; margin: 16px 0; }}
.banner {{ background: #fdf6e3; border: 1px solid #e6d9a8; border-radius: 8px; padding: 10px 14px; margin: 14px 0; font-size: 14px; }}
.finding {{ border: 1px solid var(--line); border-left-width: 5px; border-radius: 8px; padding: 14px 16px; margin: 18px 0; }}
.finding.high {{ border-left-color: var(--high); }}
.finding.medium {{ border-left-color: var(--medium); }}
.finding.low {{ border-left-color: var(--low); }}
.finding.info {{ border-left-color: var(--info); }}
.badge {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: #fff; }}
.badge.high {{ background: var(--high); }}
.badge.medium {{ background: var(--medium); }}
.badge.low {{ background: var(--low); }}
.badge.info {{ background: var(--info); }}
.rule {{ color: var(--muted); font-size: 12.5px; letter-spacing: 0.03em; }}
.muted {{ color: var(--muted); }}
.limits {{ margin: 8px 0 0 0; padding-left: 22px; }}
.limits li {{ margin: 3px 0; }}
.counts-note {{ color: var(--muted); font-size: 12.5px; }}
.footer {{ margin-top: 46px; padding-top: 14px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }}
.bar-row {{ display: grid; grid-template-columns: 150px 1fr 60px; gap: 8px; align-items: center; margin: 3px 0; font-size: 13px; }}
.bar-track {{ background: var(--panel); border: 1px solid var(--line); height: 14px; border-radius: 3px; position: relative; overflow: hidden; }}
.bar-fill {{ height: 100%; background: #3b5f8a; }}
.bar-fill.test {{ background: #9a5b00; }}
.split-cell {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
@media print {{
  body {{ padding: 0 12px; max-width: none; font-size: 11.5px; }}
  h2 {{ page-break-after: avoid; }}
  .finding, table {{ page-break-inside: avoid; }}
}}
</style>
</head>
<body>
"""


def _esc(value: object) -> str:
    if value is None:
        return ""
    return escape(str(value), quote=True)


def _list(items: Iterable[str]) -> str:
    rendered = "".join(f"<li>{_esc(item)}</li>" for item in items)
    return f'<ul class="limits">{rendered}</ul>'


def _table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    head = "".join(f"<th>{_esc(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _kv_table(pairs: Iterable[tuple[str, object]]) -> str:
    rows = [(key, "" if value is None else value) for key, value in pairs]
    return _table(["Field", "Value"], rows)


def _bar(label: str, value: float, maximum: float, serial: str, count: int) -> str:
    width = 0.0 if maximum <= 0 else max(0.0, min(100.0, value / maximum * 100.0))
    return (
        f'<div class="bar-row"><span class="mono">{_esc(label)}</span>'
        f'<span class="bar-track"><span class="bar-fill {serial}" style="width:{width:.2f}%"></span></span>'
        f'<span class="mono">{count}</span></div>'
    )


def _finding_html(finding: Finding, index: int) -> str:
    counts = _table(
        ["Count", "Affected", "Denominator", "Unit", "Scope", "Note"],
        [
            [
                count.label,
                count.affected,
                count.denominator,
                count.unit,
                count.scope,
                count.note or "",
            ]
            for count in finding.counts
        ],
    )
    examples = ""
    for example in finding.examples:
        details = _kv_table(sorted(example.details.items())) if example.details else ""
        row_ids = ", ".join(example.row_ids) if example.row_ids else "(none listed)"
        examples += (
            f"<h3>{_esc(example.label)}</h3>"
            f'<p class="mono muted">Row IDs: {_esc(row_ids)}</p>'
            f"{details}"
        )
    if not finding.examples:
        examples = '<p class="muted">No examples were carried into this finding.</p>'
    truncated = (
        f'<p class="counts-note">Evidence is bounded: {len(finding.examples)} of '
        f"{finding.example_total} example group(s) are included.</p>"
        if finding.examples_truncated
        else ""
    )

    return f"""
<section class="finding {_esc(finding.severity)}">
  <h3>{index}. {_esc(finding.title)}</h3>
  <p>
    <span class="badge {_esc(finding.severity)}">{_esc(finding.severity)}</span>
    <span class="rule">{_esc(finding.rule_id)}</span>
  </p>
  <p class="counts-note"><strong>Why this severity:</strong> {_esc(finding.severity_rationale)}</p>
  <p>{_esc(finding.description)}</p>
  <p><strong>Evidence summary:</strong> {_esc(finding.evidence_summary)}</p>
  {counts}
  <h3>Evidence</h3>
  {examples}
  {truncated}
  <h3>Recommended next action</h3>
  <p>{_esc(finding.recommended_action)}</p>
  <h3>Limitations of this finding</h3>
  {_list(finding.limitations)}
  <h3>Assumptions</h3>
  {_list(finding.assumptions)}
</section>
"""


def _not_evaluated_html(checks: Sequence[NotEvaluatedCheck]) -> str:
    if not checks:
        return '<p class="muted">Every enabled check ran.</p>'
    rows = []
    for check in checks:
        details = "; ".join(f"{key}: {value}" for key, value in sorted(check.details.items()))
        rows.append([check.rule_id, check.title, check.status, check.reason, details])
    return (
        '<p class="counts-note">These checks did <strong>not</strong> run. A check that did not run '
        "is not a check that passed.</p>"
        + _table(["Rule", "Title", "Status", "Reason", "Details"], rows)
    )


def _target_html(target: DistributionSummary | None) -> str:
    if target is None:
        return '<p class="muted">No target column was selected, so no target distribution is reported.</p>'
    if target.kind == "categorical":
        rows = [
            [
                category.category,
                category.train_count,
                f"{category.train_ratio:.1%}",
                category.test_count,
                f"{category.test_ratio:.1%}",
                f"{category.ratio_gap:.1%}",
            ]
            for category in target.categories
        ]
        maximum = max(
            [category.train_ratio for category in target.categories]
            + [category.test_ratio for category in target.categories]
            + [0.0]
        )
        bars = "".join(
            _bar(f"train {category.category}", category.train_ratio, maximum, "train", category.train_count)
            + _bar(f"test {category.category}", category.test_ratio, maximum, "test", category.test_count)
            for category in target.categories[:8]
        )
        return (
            f'<p class="counts-note">{_esc(target.note or "")}</p>'
            f"{bars}"
            + _table(
                ["Category", "Train n", "Train share", "Test n", "Test share", "Absolute gap"],
                rows,
            )
        )
    if target.kind == "continuous":
        stats_rows = [
            ["train", *[target.train_stats.get(key, "") for key in _STAT_KEYS]],
            ["test", *[target.test_stats.get(key, "") for key in _STAT_KEYS]],
        ]
        maximum = max(target.train_histogram + target.test_histogram + [0])
        labels = [
            f"{target.histogram_edges[index]:.3g}–{target.histogram_edges[index + 1]:.3g}"
            for index in range(len(target.histogram_edges) - 1)
        ]
        bars = "".join(
            _bar(f"train {labels[index]}", target.train_histogram[index], maximum, "train", target.train_histogram[index])
            + _bar(f"test {labels[index]}", target.test_histogram[index], maximum, "test", target.test_histogram[index])
            for index in range(len(labels))
        )
        return (
            f'<p class="counts-note">{_esc(target.note or "")}</p>'
            f"{bars}"
            + _table(["Split", *[key.upper() for key in _STAT_KEYS]], stats_rows)
        )
    return f'<p class="counts-note">{_esc(target.note or "No distribution available.")}</p>'


_STAT_KEYS = ("n", "mean", "std", "min", "p25", "median", "p75", "max")


def _header_html(
    *, title: str, subtitle: str, synthetic: bool, app_version: str, schema_version: str
) -> str:
    banner = (
        '<div class="banner"><strong>Synthetic demonstration data.</strong> This dataset was '
        "generated by SplitScope's seeded generators. It contains no real people, transactions or "
        "measurements.</div>"
        if synthetic
        else ""
    )
    return f"""
<h1>{_esc(title)}</h1>
<p class="muted">{_esc(subtitle)}</p>
{banner}
<div class="summary">
  <p><strong>What this report is.</strong> An evidence record of a deterministic audit: which of
  SplitScope's supported leakage risks were found in this specific train/test split, which rows
  support each conclusion, and which checks did not run.</p>
  <p><strong>What this report is not.</strong> It is not a detection of all data leakage, not proof
  that a model would be valid, and not a guarantee that the dataset is safe. "No findings" means
  only that the enabled checks found no supported issue in the inputs they examined.</p>
  <p class="mono muted">{_esc(APP_NAME)} {_esc(app_version)} · audit schema {_esc(schema_version)}</p>
</div>
"""


def _footer_html(result: Any, run_id: str | None) -> str:
    dataset = result.dataset
    return f"""
<div class="footer">
  <p>
    Input <span class="mono">{_esc(dataset.name)}</span> ·
    SHA-256 <span class="mono">{_esc(dataset.fingerprint_sha256)}</span> ·
    {dataset.row_count} rows × {dataset.column_count} columns ·
    source {_esc(dataset.source)} · demo {_esc(dataset.demo_id or "(none)")}
  </p>
  <p>
    The SHA-256 above is a reproducibility identifier for the audited bytes. It is not
    anonymisation: the data remains fully present in the original file.
  </p>
  <p>
    Generated {_esc(result.generated_at_utc)} (UTC) ·
    audit {result.duration_ms:.1f} ms ·
    run id <span class="mono">{_esc(run_id or "(not stored)")}</span>
  </p>
  <p>
    Row identifiers are positional: <span class="mono">row-000123</span> is the 123rd data row of the
    uploaded file. They are stable for a fixed file but change if the rows are reordered.
  </p>
  <p>
    Findings, counts and example ordering are deterministic for identical input bytes, roles and
    settings. Generated timestamp, duration and run id vary between runs.
  </p>
</div>
"""


def render_audit_html(result: AuditResult, *, run_id: str | None = None) -> str:
    title = f"{APP_NAME} audit report — {result.dataset.name}"
    parts = [
        _HEAD.format(title=_esc(title)),
        _header_html(
            title=f"SplitScope audit — {result.dataset.name}",
            subtitle=result.evaluation.headline,
            synthetic=result.dataset.is_synthetic,
            app_version=result.app_version,
            schema_version=result.schema_version,
        ),
        "<h2>Input</h2>",
        _kv_table(
            [
                ("File name", result.dataset.name),
                ("Source", result.dataset.source),
                ("Synthetic", "yes" if result.dataset.is_synthetic else "no"),
                ("Demo id", result.dataset.demo_id or "(none)"),
                ("SHA-256", result.dataset.fingerprint_sha256),
                ("Rows", result.dataset.row_count),
                ("Columns", result.dataset.column_count),
                ("Loaded at (UTC)", result.dataset.created_at_utc),
                ("Input warnings", "; ".join(result.dataset.warnings) or "(none)"),
            ]
        ),
        "<h2>Column roles</h2>",
        _kv_table(
            [
                ("Feature columns", ", ".join(result.roles.features)),
                ("Target", result.roles.target or "(none)"),
                ("Entity / group", result.roles.entity or "(none)"),
                ("Timestamp", result.roles.timestamp or "(none)"),
                ("Split column", result.roles.split or "(none)"),
                ("Train label", result.resolved_roles.train_value or "(none)"),
                ("Test label", result.resolved_roles.test_value or "(none)"),
                ("Excluded metadata", ", ".join(result.roles.metadata_excluded) or "(none)"),
                ("Unused columns", ", ".join(result.resolved_roles.unused_columns) or "(none)"),
            ]
        ),
        "<h2>Split</h2>",
        _kv_table(
            [
                ("Strategy", result.split.label),
                ("Kind", result.split.kind),
                ("Requested test fraction", _fraction(result.split.requested_test_fraction)),
                ("Achieved test fraction", f"{result.split.achieved_test_fraction:.4f}"),
                ("Train rows", result.split.train_rows),
                ("Test rows", result.split.test_rows),
                ("Seed", "" if result.split.seed is None else result.split.seed),
                ("Proportion note", result.split.proportion_note or ""),
                ("Notes", " ".join(result.split.notes)),
            ]
        ),
        "<h2>Audit settings</h2>",
        _kv_table(
            [
                ("Configuration", _json_block(result.audit_config.model_dump())),
                ("Limits and canonicalisation", _json_block(result.audit_limits)),
            ]
        ),
        "<h2>Evaluation summary</h2>",
        _kv_table(
            [
                ("Headline", result.evaluation.headline),
                ("Checks evaluated", ", ".join(result.evaluation.evaluated_rule_ids) or "(none)"),
                ("Findings", result.evaluation.findings_total),
                (
                    "Findings by severity",
                    ", ".join(
                        f"{severity}: {result.evaluation.findings_by_severity.get(severity, 0)}"
                        for severity in SEVERITY_ORDER
                    ),
                ),
                ("Total audit time", f"{result.duration_ms:.1f} ms"),
            ]
        ),
    ]

    if result.findings:
        parts.append("<h2>Findings</h2>")
        parts.extend(
            _finding_html(finding, index)
            for index, finding in enumerate(result.findings, start=1)
        )
    else:
        parts.append("<h2>Findings</h2>")
        parts.append(
            '<p>No findings were produced. This means only that the checks listed as evaluated found '
            "no supported issue in the inputs they examined; it is not evidence that the dataset or "
            "the split is free of leakage.</p>"
        )

    parts.extend(
        [
            "<h2>Not evaluated</h2>",
            _not_evaluated_html(result.evaluation.not_evaluated),
            "<h2>Supporting diagnostics</h2>",
            f'<p class="counts-note">{_esc(result.diagnostics.disclaimer)}</p>',
            _kv_table(
                [
                    ("Train rows", result.diagnostics.counts.train_rows),
                    ("Test rows", result.diagnostics.counts.test_rows),
                    ("Total rows", result.diagnostics.counts.total_rows),
                ]
            ),
            f'<p class="counts-note">{_esc(result.diagnostics.missingness_note)}</p>',
            _table(
                ["Column", "Train missing", "Train ratio", "Test missing", "Test ratio", "Gap"],
                [
                    [
                        row.column,
                        row.train_missing,
                        f"{row.train_missing_ratio:.1%}",
                        row.test_missing,
                        f"{row.test_missing_ratio:.1%}",
                        f"{row.missing_ratio_gap:.1%}",
                    ]
                    for row in result.diagnostics.missingness
                ],
            ),
            "<h3>Target distribution</h3>",
            _target_html(result.diagnostics.target),
            "<h2>Limitations</h2>",
            _list(result.limitations),
            "<h2>Assumptions</h2>",
            _list(result.assumptions),
            _footer_html(result, run_id),
        ]
    )
    parts.append("</body>\n</html>\n")
    return "\n".join(parts)


def render_comparison_html(result: ComparisonResult, *, run_id: str | None = None) -> str:
    title = f"{APP_NAME} split comparison — {result.dataset.name}"
    rows = []
    for row in result.rows:
        rows.append(
            [
                row.label,
                row.kind,
                "yes" if row.supported else "no",
                _fraction(row.requested_test_fraction),
                "" if row.achieved_test_fraction is None else f"{row.achieved_test_fraction:.4f}",
                row.train_rows,
                row.test_rows,
                _none(row.exact_duplicate_test_rows),
                _percent(row.exact_duplicate_test_share),
                _none(row.entity_shared_groups),
                _percent(row.entity_overlap_test_share),
                row.chronology_status or "",
                row.target_summary or "",
                row.unsupported_reason or "",
            ]
        )

    findings_sections = []
    for strategy_id, findings in result.per_strategy_findings.items():
        label = next(
            (row.label for row in result.rows if row.strategy_id == strategy_id), strategy_id
        )
        findings_sections.append(f"<h3>{_esc(label)}</h3>")
        if not findings:
            findings_sections.append(
                '<p class="muted">No findings from the checks that ran for this split.</p>'
            )
            continue
        findings_sections.append(
            _table(
                ["Rule", "Severity", "Title", "Evidence summary"],
                [
                    [finding.rule_id, finding.severity, finding.title, finding.evidence_summary]
                    for finding in findings
                ],
            )
        )

    not_evaluated_rows = sorted(
        {
            (check.rule_id, check.status, check.reason)
            for row in result.rows
            for check in row.not_evaluated
        }
    )

    parts = [
        _HEAD.format(title=_esc(title)),
        _header_html(
            title=f"SplitScope split comparison — {result.dataset.name}",
            subtitle="Candidate splits audited with the same checks and settings.",
            synthetic=result.dataset.is_synthetic,
            app_version=result.app_version,
            schema_version=result.schema_version,
        ),
        "<h2>Input</h2>",
        _kv_table(
            [
                ("File name", result.dataset.name),
                ("Synthetic", "yes" if result.dataset.is_synthetic else "no"),
                ("SHA-256", result.dataset.fingerprint_sha256),
                ("Rows", result.dataset.row_count),
                ("Columns", result.dataset.column_count),
            ]
        ),
        "<h2>Column roles</h2>",
        _kv_table(
            [
                ("Feature columns", ", ".join(result.roles.features)),
                ("Target", result.roles.target or "(none)"),
                ("Entity / group", result.roles.entity or "(none)"),
                ("Timestamp", result.roles.timestamp or "(none)"),
                ("Split column", result.roles.split or "(none)"),
            ]
        ),
        "<h2>Comparison</h2>",
        _table(
            [
                "Strategy",
                "Kind",
                "Supported",
                "Requested test fraction",
                "Achieved test fraction",
                "Train rows",
                "Test rows",
                "Exact-duplicate test rows",
                "Exact-duplicate test share",
                "Shared entities",
                "Entity-overlap test share",
                "Chronology",
                "Target distribution",
                "Unsupported reason",
            ],
            rows,
        ),
        "<h2>Findings by strategy</h2>",
        *findings_sections,
        "<h2>Not evaluated (union across strategies)</h2>",
        _not_evaluated_html(
            [
                NotEvaluatedCheck(
                    rule_id=rule_id, title=rule_id, status=status, reason=reason  # type: ignore[arg-type]
                )
                for rule_id, status, reason in not_evaluated_rows
            ]
        ),
        "<h2>Which split to use</h2>",
        f"<p>{_esc(result.selection_note)}</p>",
        "<h2>Limitations</h2>",
        _list(result.limitations),
        _footer_html(result, run_id),
        "</body>\n</html>\n",
    ]
    return "\n".join(parts)


def _fraction(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"


def _none(value: int | None) -> str:
    return "" if value is None else str(value)


def _percent(value: float | None) -> str:
    return "" if value is None else f"{value:.2%}"


def _json_block(payload: object) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=False, default=str)


__all__ = ["render_audit_html", "render_comparison_html"]
