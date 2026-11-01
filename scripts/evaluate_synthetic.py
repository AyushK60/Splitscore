#!/usr/bin/env python
"""Run the synthetic evaluation suite against the audit engine.

Usage
-----
    python scripts/evaluate_synthetic.py                          # summary to stdout
    python scripts/evaluate_synthetic.py --output-dir out/        # + JSON results
    python scripts/evaluate_synthetic.py --case dup_cross_split_multi
    python scripts/evaluate_synthetic.py --list                   # list case ids

What it does
------------
Runs every evaluation case in ``app.evaluation.cases`` (hand-built fixtures with
hand-written expectations, and the six committed demos with expectations from the
independent oracles in ``app.evaluation.oracles``) through the public audit
interface, then compares statuses, counts, metrics and evidence against the
expectations. Ground truth is never derived by running the detector being
evaluated.

Exit codes (mirrored in the JSON summary):
    0  every case passed
    1  at least one case failed an expectation (an evaluation failure)
    2  at least one case could not be evaluated (invalid/missing fixture,
       unexpected runtime error), or the invocation itself was wrong

This is an engineering check on deterministic synthetic fixtures. It does not
measure real-world detection accuracy.

Usage:
  python scripts/evaluate_synthetic.py --output-dir evaluation_output
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.evaluation.cases import build_cases  # noqa: E402
from app.evaluation.runner import run_suite  # noqa: E402

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_ERRORS = 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the SplitScope synthetic evaluation suite."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write evaluation_results.json into (created if absent).",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        default=None,
        metavar="CASE_ID",
        help="Run only this case id (repeatable).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the available case ids and exit without running anything.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()

    if args.list:
        for case in build_cases(settings):
            print(f"{case.case_id}  {case.description}")
        return EXIT_OK

    try:
        result = run_suite(settings, case_ids=args.cases)
    except ValueError as exc:
        # e.g. an unknown --case id: an invocation problem, not an evaluation
        # failure and not a runtime crash.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERRORS
    except Exception as exc:  # noqa: BLE001 - harness-level failure
        print(f"error: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ERRORS

    summary = result["summary"]

    # -- human-readable summary ----------------------------------------- #
    for case in result["results"]:
        line = f"[{case['status']:>5}] {case['case_id']}"
        if case["seed"] is not None:
            line += f"  (seed {case['seed']})"
        print(line)
        if case["error"]:
            print(f"        error: {case['error']}")
        for check in case["checks"]:
            if not check["passed"]:
                print(f"        {check['rule_id']} FAIL")
                for problem in check["problems"]:
                    print(f"          - {problem}")

    print(
        "\n{cases} case(s), {passed} passed, {failed} failed, {errored} error(s) | "
        "{checks_total} check(s), {checks_failed} failed".format(**summary)
    )
    exit_code = summary["exit_code"]
    meanings = {
        EXIT_OK: "all expectations matched",
        EXIT_FAILURES: "expectation mismatch(es): the engine disagrees with the "
        "specified ground truth",
        EXIT_ERRORS: "case(s) could not be evaluated: invalid fixture or runtime "
        "error",
    }
    print(f"exit {exit_code}: {meanings[exit_code]}")
    print(
        "Note: results describe deterministic synthetic fixtures only; they are "
        "not a measure of real-world detection accuracy."
    )

    # -- machine-readable results --------------------------------------- #
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        path = args.output_dir / "evaluation_results.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        print(f"wrote {path}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())