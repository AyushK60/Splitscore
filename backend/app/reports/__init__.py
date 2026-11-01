"""Report generation: machine-readable JSON, self-contained printable HTML, CSV exports."""

from app.reports.csv_export import build_assignment_csv, sanitize_csv_cell
from app.reports.html_report import render_audit_html, render_comparison_html
from app.reports.json_report import build_audit_report, build_comparison_report

__all__ = [
    "build_assignment_csv",
    "build_audit_report",
    "build_comparison_report",
    "render_audit_html",
    "render_comparison_html",
    "sanitize_csv_cell",
]
