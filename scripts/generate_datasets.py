#!/usr/bin/env python
"""Generate the bundled synthetic demonstration datasets and their manifest.

Usage
-----
    python scripts/generate_datasets.py            # write datasets/ in place
    python scripts/generate_datasets.py --check     # verify the committed files are reproducible

Every dataset is a pure function of its seed, so ``--check`` must produce byte-identical
files. CI runs ``--check`` so a drifted CSV cannot be committed unnoticed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.audit.io import read_csv_bytes  # noqa: E402
from app.core.version import APP_VERSION, MANIFEST_SCHEMA_VERSION  # noqa: E402
from app.synthetic.generators import DEMOS, DEMO_ORDER, build_demo  # noqa: E402

MANIFEST_FILENAME = "manifest.json"
DEFAULT_OUTPUT = REPO_ROOT / "datasets"


def _jsonable(value: object) -> object:
    """Convert NumPy scalars/arrays into JSON-safe values."""
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, pd.DataFrame):
        return f"<DataFrame shape={value.shape}>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def write_csv(frame: pd.DataFrame, path: Path) -> str:
    frame.to_csv(path, index=False, lineterminator="\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(output_dir: Path, *, write: bool) -> tuple[dict, list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    problems: list[str] = []

    for demo_id in DEMO_ORDER:
        spec = DEMOS[demo_id]
        frame, planted = build_demo(demo_id)
        path = output_dir / spec.filename

        if write:
            digest = write_csv(frame, path)
            payload = path.read_bytes()
        else:
            if not path.exists():
                problems.append(f"{spec.filename}: missing from {output_dir}")
                continue
            payload = path.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            tmp = output_dir / f"__check_{spec.filename}"
            write_csv(frame, tmp)
            regenerated = tmp.read_bytes()
            tmp.unlink()
            if regenerated != payload:
                problems.append(
                    f"{spec.filename}: committed file differs from a fresh generation "
                    f"(committed {len(payload)} bytes, regenerated {len(regenerated)} bytes)"
                )
            if digest != hashlib.sha256(regenerated).hexdigest():
                problems.append(f"{spec.filename}: checksum differs after regeneration")

        loaded = read_csv_bytes(
            payload,
            max_bytes=10**9,
            max_rows=10**7,
            max_columns=10**5,
            min_rows=1,
            min_columns=1,
            filename=spec.filename,
        )

        summary_metrics = {
            key: value
            for key, value in planted.items()
            if key
            not in {
                "planted_cases",
                "shared_entity_examples",
                "control_baseline",
                "feature_columns",
            }
            and not isinstance(value, (list, dict))
        }

        entries.append(
            {
                "demo_id": spec.demo_id,
                "title": spec.title,
                "subtitle": spec.subtitle,
                "filename": spec.filename,
                "synthetic": True,
                "is_control": spec.is_control,
                "seed": spec.seed,
                "row_count": loaded.row_count,
                "column_count": loaded.column_count,
                "columns": loaded.columns,
                "sha256": digest,
                "teaching_point": spec.teaching_point,
                "generation_method": spec.generation_method,
                "expected_findings": spec.expected_findings,
                "recommended_audit": spec.recommended_audit,
                "recommended_split": spec.recommended_split,
                "planted_cases": _jsonable(planted.get("planted_cases", [])),
                "summary_metrics": _jsonable(summary_metrics),
                "control_baseline": _jsonable(planted.get("control_baseline")),
                "intended_pair_counts": _jsonable(
                    {
                        "cross_split_duplicate_pairs": planted.get("intended_cross_pairs"),
                        "within_train_duplicate_pairs": planted.get("intended_within_train_pairs"),
                        "within_test_duplicate_pairs": planted.get("intended_within_test_pairs"),
                        "near_duplicate_pairs": planted.get("near_duplicate_pairs"),
                    }
                ),
                "notes": spec.notes,
            }
        )
        print(f"{spec.filename:28s} rows={loaded.row_count:5d} cols={loaded.column_count:3d} sha256={digest[:16]}")

    manifest = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "generated_by": "scripts/generate_datasets.py",
        "synthetic_only": True,
        "datasets": entries,
    }

    if write:
        (output_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {output_dir / MANIFEST_FILENAME}")

    return manifest, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify that the committed files are byte-identical to a fresh generation.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="Output directory.")
    args = parser.parse_args(argv)

    _, problems = build_manifest(args.out, write=not args.check)
    if problems:
        print("\nPROBLEMS:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    if args.check:
        print("\nAll committed datasets reproduce exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
