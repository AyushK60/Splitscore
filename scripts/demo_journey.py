#!/usr/bin/env python3
"""Live HTTP journey verification for SplitScope.

Runs the documented user journey against a *running* SplitScope server over real
HTTP using only the Python standard library, then asserts the results.

Journey covered:
  1. Health check
  2. Demo catalogue + synthetic demo load
  3. Dataset preview (and a full row scan used by later invariant checks)
  4. Audit run -> findings that reference real evidence rows
  5. Split comparison: existing split vs generated group holdout
  6. Group-holdout CSV download: row correspondence, valid labels, and an
     independently recomputed "no shared nonmissing entities" invariant
  7. Existing-split CSV download: the same invariant, expected to show overlap
  8. JSON report download + parsing
  9. HTML report download

What this script deliberately does NOT do: it never re-implements an audit rule.
Fixtures come from the demo's own manifest (`expected_findings`, recommended
roles/config); everything else is a direct invariant over downloaded data.

Exit codes:
  0  every step passed
  1  a step executed and failed (HTTP error or failed assertion)
  2  the server could not be reached or did not answer (startup problem)

Usage:
  python scripts/demo_journey.py
  python scripts/demo_journey.py --base-url http://127.0.0.1:5177/api-proxy-check
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 20.0
DEMO_ID = "repeated_entity"

#: The documented missing-value rule: an empty cell is missing; "NA" is a value.
MISSING_VALUES = {""}

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNREACHABLE = 2


class ServerUnreachable(Exception):
    """The process did not answer HTTP at all (startup / proxy problem)."""


class CheckFailed(Exception):
    """An assertion about a successful response did not hold."""


class HttpError(Exception):
    """The server answered with a non-2xx status."""

    def __init__(self, method: str, url: str, status: int, raw: str, headers: dict):
        body = None
        try:
            body = json.loads(raw)
        except (ValueError, TypeError):
            body = None
        code = message = None
        details = {}
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            code = body["error"].get("code")
            message = body["error"].get("message")
            details = body["error"].get("details") or {}
        self.method = method
        self.url = url
        self.status = status
        self.raw = raw
        self.headers = headers
        self.code = code
        self.message = message
        self.details = details
        label = code or "unstructured error"
        super().__init__(f"{method} {url} -> HTTP {status} [{label}]: {message or raw[:300]}")

    @property
    def is_validation(self) -> bool:
        return self.status == 422 or self.code == "validation_error"


class Http:
    """Small JSON-over-HTTP client with finite timeouts and structured errors."""

    def __init__(self, base_url: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict, str]:
        url = self.base_url + path
        data: bytes | None = None
        headers: dict[str, str] = {"Accept": "application/json, text/csv, text/html"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)

        shown_body = "" if body is None else f" body={json.dumps(body, sort_keys=True)[:400]}"
        print(f"  -> {method} {path}{shown_body}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                raw = response.read().decode("utf-8", errors="replace")
                response_headers = {k.lower(): v for k, v in response.headers.items()}
        except urllib.error.HTTPError as exc:
            status = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
            response_headers = {k.lower(): v for k, v in exc.headers.items()}
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise ServerUnreachable(
                f"{method} {url} failed: {reason}\n"
                f"  The SplitScope backend is not answering on {self.base_url}.\n"
                "  Start it with:\n"
                "      cd backend && python -m app.main\n"
                "  then re-run this script (use --base-url if it listens elsewhere)."
            ) from exc
        except OSError as exc:
            raise ServerUnreachable(
                f"{method} {url} failed: {exc}\n"
                f"  The SplitScope backend is not answering on {self.base_url}.\n"
                "  Start it with:\n"
                "      cd backend && python -m app.main"
            ) from exc

        print(f"  <- {status} ({len(raw)} bytes)")
        if not 200 <= status < 300:
            raise HttpError(method, url, status, raw, response_headers)
        return status, response_headers, raw

    def json(self, method: str, path: str, body: dict | None = None) -> dict:
        _, headers, raw = self.request(method, path, body)
        content_type = headers.get("content-type", "")
        if "json" not in content_type:
            raise CheckFailed(
                f"{method} {path} returned content-type {content_type!r}, expected JSON."
            )
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise CheckFailed(f"{method} {path} returned a body that is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise CheckFailed(f"{method} {path} returned a JSON document of type {type(parsed).__name__}, expected an object.")
        return parsed


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def parse_assignment_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """Parse the exported split CSV, skipping the leading sanitisation note line."""
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if row and any(cell.strip() for cell in row)]
    # The export may be prefixed with a single-cell "# sanitisation note" row.
    if rows and len(rows[0]) == 1 and rows[0][0].lstrip().startswith("#"):
        rows = rows[1:]
    expect(len(rows) >= 2, "The split CSV has no data rows.")
    header = rows[0]
    records = [dict(zip(header, row)) for row in rows[1:]]
    return header, records


def shared_nonmissing_entities(
    assignments: list[dict[str, str]], entity_by_row: dict[str, str]
) -> tuple[set[str], set[str], set[str]]:
    """Recompute entity overlap directly from the downloaded assignment + data.

    Independent of anything the server reports: it only uses the CSV's row_id and
    split columns joined to the entity column read from the dataset preview.
    Missing entity cells (empty under the documented rule) are excluded.
    """
    train: set[str] = set()
    test: set[str] = set()
    for record in assignments:
        row_id = record["row_id"]
        entity = entity_by_row.get(row_id)
        if entity is None or entity.strip() in MISSING_VALUES:
            continue
        if record["split"] == "train":
            train.add(entity.strip())
        elif record["split"] == "test":
            test.add(entity.strip())
    return train, test, train & test


class Journey:
    def __init__(self, http: Http):
        self.http = http
        self.dataset_id: str | None = None
        self.row_count = 0
        self.columns: list[str] = []
        self.entity_column: str | None = None
        self.roles: dict = {}
        self.config: dict = {}
        self.row_map: dict[str, dict[str, str]] = {}
        self.audit_run_id: str | None = None
        self.audit_findings: list[dict] = []
        self.compare_run_id: str | None = None
        self.compare_rows: list[dict] = []
        self.assignments: dict[str, dict] = {}

    # -- steps ----------------------------------------------------------- #

    def step_health(self) -> None:
        health = self.http.json("GET", "/api/health")
        expect(health.get("status") == "ok", f"Health status is {health.get('status')!r}, expected 'ok'.")
        expect(health.get("app_name") == "SplitScope", f"Unexpected app_name {health.get('app_name')!r}.")
        expect("app_version" in health, "Health response has no app_version.")
        print(f"  SplitScope v{health['app_version']} on {self.http.base_url}")

    def step_load_demo(self) -> None:
        demos = self.http.json("GET", "/api/demos")
        demo_list = demos.get("demos") or []
        featured = (demos.get("featured_journey") or {}).get("demo_id")
        expect(bool(demo_list), "GET /api/demos returned no demos.")
        expect(
            any(d.get("demo_id") == DEMO_ID for d in demo_list),
            f"Featured demo {DEMO_ID!r} is missing from the catalogue.",
        )
        print(f"  {len(demo_list)} demos; featured journey: {featured}")

        loaded = self.http.json("POST", f"/api/demos/{DEMO_ID}/load")
        dataset = loaded.get("dataset") or {}
        self.dataset_id = dataset.get("dataset_id")
        expect(self.dataset_id, f"Demo load returned no dataset_id: {json.dumps(dataset)[:300]}")
        expect(dataset.get("is_synthetic") is True, "Loaded demo is not marked synthetic.")
        expect(dataset.get("source") == "demo", f"Demo source is {dataset.get('source')!r}, expected 'demo'.")
        self.row_count = int(dataset.get("row_count") or 0)
        self.columns = list(dataset.get("columns") or [])
        expect(self.row_count >= 20, f"Demo has only {self.row_count} rows (minimum is 20).")
        expect(len(self.columns) >= 2, "Demo has fewer than two columns.")

        roles = loaded.get("suggested_roles") or {}
        expect(bool(roles.get("features")), "Demo load suggested no feature columns.")
        expect(bool(roles.get("entity")), "Demo load suggested no entity column.")
        expect(roles.get("split"), "Demo load suggested no split column.")
        expect(roles.get("split_train_value") and roles.get("split_test_value"), "Demo load suggested no split train/test values.")
        self.roles = roles
        self.entity_column = roles.get("entity")
        config = loaded.get("recommended_audit_config")
        self.config = config if isinstance(config, dict) else {}
        print(f"  dataset_id={self.dataset_id} rows={self.row_count} cols={len(self.columns)}")
        print(f"  roles: entity={self.entity_column} target={roles.get('target')} features={len(roles['features'])}")

    def step_preview(self) -> None:
        preview = self.http.json("GET", f"/api/datasets/{self.dataset_id}/preview?limit=5")
        expect(preview.get("total_rows") == self.row_count, "Preview total_rows disagrees with the dataset summary.")
        expect(preview.get("columns") == self.columns, "Preview columns disagree with the dataset summary.")
        expect(len(preview.get("rows") or []) == 5, "Preview with limit=5 did not return 5 rows.")

        # Full scan: later invariant checks join assignments back to real data.
        offset = 0
        self.row_map = {}
        while offset < self.row_count:
            page = self.http.json(
                "GET", f"/api/datasets/{self.dataset_id}/preview?offset={offset}&limit=500"
            )
            page_columns = page.get("columns") or []
            for row_id, values in zip(page.get("row_ids") or [], page.get("rows") or []):
                expect(row_id not in self.row_map, f"Duplicate row_id {row_id!r} returned by preview.")
                self.row_map[row_id] = dict(zip(page_columns, values))
            offset += len(page.get("row_ids") or [])
            if not page.get("row_ids"):
                break
        expect(
            len(self.row_map) == self.row_count,
            f"Preview scan returned {len(self.row_map)} rows, expected {self.row_count}.",
        )
        print(f"  Scanned {len(self.row_map)} rows across all columns")

    def step_audit(self) -> None:
        payload = {"dataset_id": self.dataset_id, "roles": self.roles, "config": self.config}
        response = self.http.json("POST", "/api/audit", payload)
        self.audit_run_id = response.get("run_id")
        expect(self.audit_run_id, f"Audit returned no run_id: {json.dumps(response)[:300]}")
        result = response.get("result") or {}
        evaluation = result.get("evaluation") or {}
        self.audit_findings = result.get("findings") or []
        findings_total = evaluation.get("findings_total")
        expect(findings_total == len(self.audit_findings) or findings_total is None,
               "evaluation.findings_total disagrees with the findings list length.")

        rule_ids = [f.get("rule_id") for f in self.audit_findings]
        print(f"  run_id={self.audit_run_id} findings={len(self.audit_findings)}")
        for finding in self.audit_findings:
            examples = finding.get("examples") or []
            print(
                f"    [{finding.get('severity')}] {finding.get('rule_id')}: {finding.get('title')} "
                f"({len(examples)} evidence example(s))"
            )

        # Fixture expectations from the demo manifest (not a second audit impl).
        expect(len(self.audit_findings) >= 1, "The repeated-entity demo produced no findings; the manifest expects SS-ENT-001.")
        expect(
            "SS-ENT-001" in rule_ids,
            f"Expected finding SS-ENT-001 (manifest fixture) in {rule_ids}.",
        )
        ent = next(f for f in self.audit_findings if f.get("rule_id") == "SS-ENT-001")
        expect(ent.get("severity") == "high", f"SS-ENT-001 severity is {ent.get('severity')!r}, manifest expects 'high'.")
        expect(
            "SS-DUP-001" not in rule_ids,
            f"The manifest expects no exact-duplicate finding for this demo, got {rule_ids}.",
        )

        # Real evidence: every referenced evidence row must exist in the dataset.
        evidence_rows: list[str] = []
        for finding in self.audit_findings:
            examples = finding.get("examples") or []
            for example in examples:
                row_ids = example.get("row_ids") or []
                expect(bool(row_ids), f"Finding {finding.get('rule_id')} has an evidence example with no row_ids.")
                evidence_rows.extend(row_ids)
        missing = [row_id for row_id in evidence_rows if row_id not in self.row_map]
        expect(
            not missing,
            f"{len(missing)} evidence row_id(s) do not exist in the dataset, e.g. {missing[:5]}.",
        )
        expect(len(evidence_rows) >= 2, "Audit returned fewer than two evidence rows.")
        print(f"  Evidence rows resolve to real dataset rows: {len(evidence_rows)} referenced")

    def step_compare(self) -> None:
        payload = {
            "dataset_id": self.dataset_id,
            "roles": self.roles,
            "config": self.config,
            "strategies": [
                {
                    "kind": "group",
                    "label": f"Group holdout on {self.entity_column}",
                    "strategy_id": "group",
                    "test_fraction": 0.25,
                    "seed": 12345,
                }
            ],
            "include_existing_split": True,
        }
        response = self.http.json("POST", "/api/splits/compare", payload)
        self.compare_run_id = response.get("run_id")
        expect(self.compare_run_id, f"Compare returned no run_id: {json.dumps(response)[:300]}")
        self.compare_rows = (response.get("result") or {}).get("rows") or []
        self.assignments = {
            handle["strategy_id"]: handle for handle in (response.get("assignments") or [])
        }

        existing = next((r for r in self.compare_rows if r.get("kind") == "existing"), None)
        group = next((r for r in self.compare_rows if r.get("kind") == "group"), None)
        expect(existing is not None, "Comparison returned no 'existing' split row.")
        expect(group is not None, "Comparison returned no 'group' split row.")
        for row in (existing, group):
            expect(
                row.get("supported") is True,
                f"Strategy {row.get('strategy_id')!r} is unsupported: {row.get('unsupported_reason')!r}",
            )
            expect(
                int(row.get("train_rows") or 0) + int(row.get("test_rows") or 0) == self.row_count,
                f"Strategy {row.get('strategy_id')!r} does not cover all {self.row_count} rows.",
            )

        existing_overlap = existing.get("entity_shared_groups")
        group_overlap = group.get("entity_shared_groups")
        expect(
            isinstance(existing_overlap, int) and existing_overlap > 0,
            f"Existing split reports {existing_overlap!r} shared entity groups; the manifest expects overlap.",
        )
        expect(
            group_overlap == 0,
            f"Group holdout reports {group_overlap!r} shared entity groups; expected 0.",
        )
        expect(
            "group" in self.assignments and "existing" in self.assignments,
            f"Missing assignment handles; got {sorted(self.assignments)}.",
        )
        print(f"  run_id={self.compare_run_id} rows={len(self.compare_rows)}")
        print(f"  existing: shared groups={existing_overlap} findings={existing.get('finding_counts')}")
        print(f"  group:    shared groups={group_overlap} findings={group.get('finding_counts')}")

    def _download_assignment(self, strategy_id: str) -> list[dict[str, str]]:
        handle = self.assignments.get(strategy_id)
        expect(handle is not None, f"No assignment handle for strategy {strategy_id!r}.")
        assignment_id = handle["assignment_id"]
        path = handle.get("download_path") or f"/api/exports/split/{assignment_id}.csv"
        status, headers, raw = self.http.request("GET", path)
        content_type = headers.get("content-type", "")
        expect("text/csv" in content_type, f"Split export content-type is {content_type!r}, expected text/csv.")
        expect(
            "attachment" in headers.get("content-disposition", ""),
            "Split export has no Content-Disposition attachment header.",
        )
        header, records = parse_assignment_csv(raw)

        required = {"row_id", "split"}
        expect(
            required.issubset(set(header)),
            f"Split CSV header {header} is missing {sorted(required - set(header))}.",
        )
        # Row correspondence: same rows, same identifiers, same length.
        expect(
            len(records) == self.row_count,
            f"Split CSV has {len(records)} data rows, dataset has {self.row_count}.",
        )
        csv_row_ids = [r["row_id"] for r in records]
        expect(len(set(csv_row_ids)) == len(csv_row_ids), "Split CSV contains duplicate row_ids.")
        expected_ids = set(self.row_map)
        unexpected = [row_id for row_id in csv_row_ids if row_id not in expected_ids]
        expect(not unexpected, f"Split CSV contains {len(unexpected)} unknown row_id(s), e.g. {unexpected[:5]}.")
        missing_ids = expected_ids - set(csv_row_ids)
        expect(
            not missing_ids,
            f"Split CSV omits {len(missing_ids)} dataset row(s), e.g. {sorted(missing_ids)[:5]}.",
        )
        # Valid labels.
        labels = {r.get("split") for r in records}
        expect(labels <= {"train", "test"}, f"Split CSV contains invalid labels: {sorted(labels - {'train', 'test'})}.")
        expect(labels == {"train", "test"}, f"Split CSV labels are {sorted(labels)}, expected both train and test.")

        comparison = next(r for r in self.compare_rows if r.get("kind") == strategy_id or r.get("strategy_id") == strategy_id)
        trains = sum(1 for r in records if r["split"] == "train")
        tests = sum(1 for r in records if r["split"] == "test")
        expect(
            trains == int(comparison.get("train_rows") or -1),
            f"CSV has {trains} train rows, comparison reports {comparison.get('train_rows')}.",
        )
        expect(
            tests == int(comparison.get("test_rows") or -1),
            f"CSV has {tests} test rows, comparison reports {comparison.get('test_rows')}.",
        )
        print(f"  {assignment_id}: {len(records)} rows ({trains} train / {tests} test), labels valid")
        return records

    def step_group_assignment(self) -> None:
        entity_by_row = {
            row_id: (values.get(self.entity_column) or "") for row_id, values in self.row_map.items()
        }
        records = self._download_assignment("group")
        train, test, shared = shared_nonmissing_entities(records, entity_by_row)
        expect(
            len(train | test) > 0,
            "No nonmissing entity values were found; the overlap check would be vacuous.",
        )
        comparison = next(r for r in self.compare_rows if r.get("strategy_id") == "group")
        print(
            f"  independently recomputed: {len(train)} train entities, {len(test)} test entities, "
            f"{len(shared)} shared"
        )
        print(f"  server reported shared groups: {comparison.get('entity_shared_groups')}")
        expect(
            not shared,
            f"Group holdout shares {len(shared)} nonmissing entit(ies) between train and test: {sorted(shared)[:10]}",
        )

    def step_existing_assignment(self) -> None:
        entity_by_row = {
            row_id: (values.get(self.entity_column) or "") for row_id, values in self.row_map.items()
        }
        records = self._download_assignment("existing")
        train, test, shared = shared_nonmissing_entities(records, entity_by_row)
        expect(
            len(train | test) > 0,
            "No nonmissing entity values were found; the overlap check would be vacuous.",
        )
        print(f"  independently recomputed: {len(shared)} shared nonmissing entities in the existing split")
        expect(
            len(shared) > 0,
            "Fixture expectation failed: the demo's existing split should share entities between train and test.",
        )

    def step_json_report(self) -> None:
        status, headers, raw = self.http.request("POST", "/api/reports/json", {"run_id": self.audit_run_id})
        expect("application/json" in headers.get("content-type", ""),
               f"JSON report content-type is {headers.get('content-type')!r}.")
        expect("attachment" in headers.get("content-disposition", ""),
               "JSON report has no Content-Disposition attachment header.")
        report = json.loads(raw)
        expect(report.get("report_kind") == "audit", f"report_kind is {report.get('report_kind')!r}, expected 'audit'.")
        expect(report.get("run_id") == self.audit_run_id, "JSON report run_id does not match the audit run.")
        expect(report.get("input", {}).get("row_count") == self.row_count, "JSON report row_count does not match.")
        report_findings = report.get("findings") or []
        expect(
            len(report_findings) == len(self.audit_findings),
            f"JSON report has {len(report_findings)} findings, audit returned {len(self.audit_findings)}.",
        )
        expect(report.get("settings", {}).get("audit_config") is not None, "JSON report does not echo the audit settings.")
        expect(report.get("roles") is not None, "JSON report does not record the roles.")
        print(f"  JSON report: {len(raw)} bytes, {len(report_findings)} findings, run_id matches")

    def step_html_report(self) -> None:
        status, headers, raw = self.http.request("POST", "/api/reports/html", {"run_id": self.audit_run_id})
        expect("text/html" in headers.get("content-type", ""),
               f"HTML report content-type is {headers.get('content-type')!r}.")
        expect("attachment" in headers.get("content-disposition", ""),
               "HTML report has no Content-Disposition attachment header.")
        lowered = raw.lower()
        expect(lowered.lstrip().startswith("<!doctype html"), "HTML report does not start with a doctype.")
        expect("</html>" in lowered, "HTML report is not a closed document.")
        expect("SS-ENT-001" in raw, "HTML report does not render the entity-overlap finding.")
        expect("<script" not in lowered, "HTML report contains a <script> element; it must be self-contained.")
        print(f"  HTML report: {len(raw)} bytes, self-contained, renders SS-ENT-001")


STEPS: list[tuple[str, str]] = [
    ("Health check", "step_health"),
    (f"Load synthetic demo '{DEMO_ID}'", "step_load_demo"),
    ("Dataset preview + full row scan", "step_preview"),
    ("Audit run and finding evidence", "step_audit"),
    ("Split comparison (existing vs group holdout)", "step_compare"),
    ("Group-holdout CSV: rows, labels, independent overlap = 0", "step_group_assignment"),
    ("Existing-split CSV: independent overlap > 0", "step_existing_assignment"),
    ("JSON report download and parsing", "step_json_report"),
    ("HTML report download", "step_html_report"),
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the SplitScope API journey over live HTTP.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Server base URL (default {DEFAULT_BASE_URL})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds")
    args = parser.parse_args(argv)

    print("=" * 74)
    print("SPLITSCOPE LIVE API JOURNEY")
    print(f"target: {args.base_url}   timeout: {args.timeout:g}s")
    print("=" * 74)

    journey = Journey(Http(args.base_url, args.timeout))
    results: list[tuple[str, str, str]] = []
    exit_code = EXIT_OK

    for index, (title, method_name) in enumerate(STEPS):
        print()
        print(f"[{index + 1}/{len(STEPS)}] {title}")
        print("-" * 74)
        try:
            getattr(journey, method_name)()
        except ServerUnreachable as exc:
            print(f"  FAIL (server unreachable): {exc}")
            results.append((title, "FAIL", str(exc)))
            exit_code = EXIT_UNREACHABLE
            for skipped_title, _ in STEPS[index + 1:]:
                results.append((skipped_title, "NOT RUN", "server unreachable"))
            break
        except HttpError as exc:
            print(f"  FAIL (HTTP {exc.status}): {exc.method} {exc.url}")
            if exc.is_validation:
                print("  Structured validation response:")
                try:
                    print(json.dumps(json.loads(exc.raw), indent=2))
                except ValueError:
                    print(f"    {exc.raw}")
                print("  Compare this payload against GET /openapi.json for the endpoint schema.")
            else:
                print(f"    {json.dumps(json.loads(exc.raw) if exc.raw else {}, indent=2)[:1500] if exc.raw else '(empty body)'}")
            results.append((title, "FAIL", str(exc)))
            exit_code = EXIT_FAILED
            for skipped_title, _ in STEPS[index + 1:]:
                results.append((skipped_title, "NOT RUN", "earlier step failed"))
            break
        except CheckFailed as exc:
            print(f"  FAIL (assertion): {exc}")
            results.append((title, "FAIL", str(exc)))
            exit_code = EXIT_FAILED
            for skipped_title, _ in STEPS[index + 1:]:
                results.append((skipped_title, "NOT RUN", "earlier step failed"))
            break
        else:
            results.append((title, "PASS", ""))
    else:
        # All steps ran; report any that were recorded without reaching here.
        pass

    print()
    print("=" * 74)
    print("RESULTS")
    print("=" * 74)
    for title, status, detail in results:
        suffix = f"  -- {detail}" if detail and status != "PASS" else ""
        print(f"  {status:<8} {title}{suffix}")
    passed = sum(1 for _, status, _ in results if status == "PASS")
    failed = sum(1 for _, status, _ in results if status == "FAIL")
    not_run = sum(1 for _, status, _ in results if status == "NOT RUN")
    print()
    print(f"  passed={passed} failed={failed} not_run={not_run}")
    if exit_code == EXIT_UNREACHABLE:
        print("  EXIT 2: server unreachable -- start the backend and re-run.")
    elif exit_code == EXIT_FAILED:
        print("  EXIT 1: one or more journey steps failed.")
    else:
        print("  EXIT 0: full live API journey passed.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
