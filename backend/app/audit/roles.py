"""Column-role validation and resolution.

Role assignment is the user's declarative statement about what the data *means*.
The audit is only as meaningful as that statement, so validation is exhaustive
and every problem is returned as a typed issue rather than raised one at a time.

Errors block an audit. Warnings do not block it, but are carried into the report
because several of them (missing entity identifiers, degenerate groups, constant
features) change how a finding should be read.
"""

from __future__ import annotations

import numpy as np

from app.audit.canonical import ValueCanonicalizer
from app.audit.dataset import Dataset
from app.audit.io import to_datetime_series
from app.audit.types import ColumnRoles, ResolvedRoles, RoleIssue, RoleValidationResult

#: A column that never varies carries no information for feature comparison or
#: distance-based analysis.
CONSTANT_FEATURE_THRESHOLD = 1

#: Below this many distinct entity values, a group split cannot be meaningful.
MIN_GROUPS_FOR_GROUP_SPLIT = 2

#: Below this fraction of parsable timestamps, the chronology check cannot be
#: trusted and the role assignment is treated as an error rather than a warning.
MIN_VALID_TIMESTAMP_RATIO = 0.5

#: Maximum entities listed in a single issue payload.
MAX_LISTED = 20


def _cleaned_unique(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def validate_roles(dataset: Dataset, roles: ColumnRoles) -> RoleValidationResult:
    """Validate roles against a dataset and resolve them for the audit engine."""
    issues: list[RoleIssue] = []
    columns = set(dataset.columns)
    frame = dataset.frame

    # ---- structural validation -------------------------------------------------
    if not roles.features:
        issues.append(
            RoleIssue(
                code="empty_features",
                message="No feature columns were selected.",
                severity="warning",
                hint=(
                    "Feature-based checks (exact duplicates, near duplicates) will report themselves "
                    "as not evaluated. Group, chronology and target checks can still run."
                ),
            )
        )
    if len(roles.features) != len(set(roles.features)):
        issues.append(
            RoleIssue(
                code="duplicate_feature_entry",
                message="The feature list contains the same column more than once; "
                "duplicates were collapsed.",
                severity="warning",
            )
        )
    features = _cleaned_unique(roles.features)

    # An audit needs at least one role that some check can actually use.
    if (
        not features
        and roles.target is None
        and roles.entity is None
        and roles.timestamp is None
    ):
        issues.append(
            RoleIssue(
                code="no_analysis_roles",
                message=(
                    "No feature, target, entity or timestamp column was selected, so no check can "
                    "produce a result."
                ),
                hint="Select at least one column to analyse.",
            )
        )

    named_roles: dict[str, str] = {}
    for role_name, column in (
        ("target", roles.target),
        ("entity", roles.entity),
        ("timestamp", roles.timestamp),
        ("split", roles.split),
    ):
        if column is None:
            continue
        if column not in columns:
            issues.append(
                RoleIssue(
                    code="unknown_column",
                    message=f"The {role_name} column {column!r} is not present in the dataset.",
                    column=column,
                    hint=f"Available columns: {', '.join(sorted(columns)[:MAX_LISTED])}",
                )
            )
            continue
        named_roles[role_name] = column

    for name in features:
        if name not in columns:
            issues.append(
                RoleIssue(
                    code="unknown_column",
                    message=f"The feature column {name!r} is not present in the dataset.",
                    column=name,
                )
            )

    known_features = [f for f in features if f in columns]

    # ---- role overlap ----------------------------------------------------------
    role_by_field = [
        ("target", named_roles.get("target")),
        ("split", named_roles.get("split")),
        ("entity", named_roles.get("entity")),
        ("timestamp", named_roles.get("timestamp")),
    ]
    for role_name, column in role_by_field:
        if column is not None and column in known_features:
            issues.append(
                RoleIssue(
                    code="role_overlap",
                    message=(
                        f"Column {column!r} is assigned both as a feature and as the "
                        f"{role_name} column. These roles cannot overlap."
                    ),
                    column=column,
                    hint="Remove it from the feature list; the audit never compares target, "
                    "split, entity or timestamp columns as features.",
                )
            )

    metadata_excluded = _cleaned_unique(roles.metadata_excluded)
    for name in metadata_excluded:
        if name not in columns:
            issues.append(
                RoleIssue(
                    code="unknown_column",
                    message=f"The metadata column {name!r} is not present in the dataset.",
                    column=name,
                )
            )
        if name in known_features:
            issues.append(
                RoleIssue(
                    code="role_overlap",
                    message=(
                        f"Column {name!r} is marked as excluded metadata and also as a feature."
                    ),
                    column=name,
                )
            )

    used: dict[str, list[str]] = {}
    for role_name, column in role_by_field + [("feature", f) for f in known_features] + [
        ("metadata", name) for name in metadata_excluded if name in columns
    ]:
        if column is not None:
            used.setdefault(column, []).append(role_name)
    for column, role_names in used.items():
        if len(role_names) > 1:
            issues.append(
                RoleIssue(
                    code="column_multi_role",
                    message=f"Column {column!r} is assigned to multiple roles: {', '.join(role_names)}.",
                    column=column,
                )
            )

    # ---- split definition ------------------------------------------------------
    split_column = named_roles.get("split")
    if split_column is not None:
        if roles.split_train_value is None or roles.split_test_value is None:
            issues.append(
                RoleIssue(
                    code="missing_split_values",
                    message="A split column was selected but the train and test label values "
                    "were not both provided.",
                    column=split_column,
                    hint="Choose one observed value for train and a different one for test; both "
                    "labels are required before the split can be read.",
                )
            )
        elif roles.split_train_value == roles.split_test_value:
            issues.append(
                RoleIssue(
                    code="split_values_equal",
                    message="The train and test label values are identical, so the split "
                    "cannot be read.",
                    column=split_column,
                    hint="Choose two different values: one for the training side and one for the "
                    "testing side.",
                )
            )
        else:
            labels = dataset.values(split_column)
            train_value, test_value = roles.split_train_value, roles.split_test_value
            n_train = sum(1 for v in labels if v == train_value)
            n_test = sum(1 for v in labels if v == test_value)
            if n_train == 0:
                issues.append(
                    RoleIssue(
                        code="split_value_absent",
                        message=f"No rows carry the train label {train_value!r}.",
                        column=split_column,
                        hint="Choose a label that appears in the column; the observed values and "
                        "their row counts are listed next to the mapping controls.",
                    )
                )
            if n_test == 0:
                issues.append(
                    RoleIssue(
                        code="split_value_absent",
                        message=f"No rows carry the test label {test_value!r}.",
                        column=split_column,
                        hint="Choose a label that appears in the column; the observed values and "
                        "their row counts are listed next to the mapping controls.",
                    )
                )
            if 0 < n_train < 2 or 0 < n_test < 2:
                issues.append(
                    RoleIssue(
                        code="insufficient_split_size",
                        message=(
                            f"The split has {n_train} train and {n_test} test rows. A single row on "
                            "one side makes per-split rates meaningless even though the checks "
                            "still run."
                        ),
                        severity="warning",
                        column=split_column,
                    )
                )
            other = sorted({v for v in labels if v not in (train_value, test_value)})
            if other:
                shown = ", ".join(repr(v) for v in other[:MAX_LISTED])
                issues.append(
                    RoleIssue(
                        code="split_labels_unsupported",
                        message=(
                            f"{len(other)} label(s) other than {train_value!r} and "
                            f"{test_value!r} appear in {split_column!r}: {shown}."
                        ),
                        severity="warning",
                        column=split_column,
                        hint="Those rows are reported as unassigned and are excluded from the "
                        "audited split; they are never silently folded into either side.",
                    )
                )

    # ---- timestamp -------------------------------------------------------------
    timestamp_column = named_roles.get("timestamp")
    if timestamp_column is not None:
        parsed = to_datetime_series(dataset.series(timestamp_column))
        n_total = len(parsed)
        n_invalid = int(parsed.isna().sum())
        valid_ratio = (n_total - n_invalid) / n_total if n_total else 0.0
        if n_invalid > 0:
            issues.append(
                RoleIssue(
                    code="invalid_timestamp_values",
                    message=(
                        f"{n_invalid} of {n_total} values in {timestamp_column!r} "
                        f"({(1 - valid_ratio):.1%}) could not be parsed as timestamps."
                    ),
                    severity="warning" if valid_ratio >= MIN_VALID_TIMESTAMP_RATIO else "error",
                    column=timestamp_column,
                    hint="Unparsable rows are reported and excluded from ordering; the check "
                    "does not guess their position in time.",
                )
            )

    # ---- entity ----------------------------------------------------------------
    entity_column = named_roles.get("entity")
    if entity_column is not None:
        raw = dataset.values(entity_column)
        canonical = ValueCanonicalizer(
            strip_whitespace=True,
            normalize_numeric_strings=False,
            missing_tokens=(),
        )
        missing_flags = np.fromiter(
            (canonical.missing(v) for v in raw), dtype=bool, count=len(raw)
        )
        missing_count = int(missing_flags.sum())
        if missing_count > 0:
            issues.append(
                RoleIssue(
                    code="missing_entity_values",
                    message=(
                        f"{missing_count} of {len(raw)} values in {entity_column!r} are empty, "
                        "so those rows have no entity identifier."
                    ),
                    severity="warning",
                    column=entity_column,
                    hint="Rows without an entity identifier are counted separately and are never "
                    "merged into a single synthetic entity.",
                )
            )
        non_missing = [v for v, m in zip(raw, missing_flags.tolist(), strict=True) if not m]
        n_groups = len(set(non_missing))
        if n_groups < MIN_GROUPS_FOR_GROUP_SPLIT:
            issues.append(
                RoleIssue(
                    code="degenerate_groups",
                    message=(
                        f"Column {entity_column!r} has only {n_groups} distinct non-missing "
                        "value(s); a group split cannot be formed from it."
                    ),
                    severity="error",
                    column=entity_column,
                )
            )
        elif n_groups == len(non_missing):
            issues.append(
                RoleIssue(
                    code="degenerate_groups",
                    message=(
                        f"Every one of the {len(non_missing)} non-missing values in "
                        f"{entity_column!r} is unique, so it behaves like a row identifier."
                    ),
                    severity="warning",
                    column=entity_column,
                    hint="A group split will be equivalent to a random split in this case.",
                )
            )

    # ---- feature sanity --------------------------------------------------------
    constant_features: list[str] = []
    all_missing_features: list[str] = []
    for name in known_features:
        values = frame[name].tolist()
        non_empty = [v for v in values if v != ""]
        if not non_empty:
            all_missing_features.append(name)
        elif len(set(non_empty)) <= CONSTANT_FEATURE_THRESHOLD:
            constant_features.append(name)
    if constant_features:
        issues.append(
            RoleIssue(
                code="constant_feature",
                message=(
                    f"{len(constant_features)} selected feature column(s) never vary: "
                    f"{', '.join(constant_features[:MAX_LISTED])}."
                ),
                severity="warning",
                hint="Constant columns carry no information for duplicate or distance-based "
                "comparison, but they are still compared exactly.",
            )
        )
    if all_missing_features:
        issues.append(
            RoleIssue(
                code="all_missing_feature",
                message=(
                    f"{len(all_missing_features)} selected feature column(s) are empty for every "
                    f"row: {', '.join(all_missing_features[:MAX_LISTED])}."
                ),
                severity="warning",
                hint="An all-missing feature makes every row share one feature signature.",
            )
        )

    # ---- target ----------------------------------------------------------------
    target_column = named_roles.get("target")
    if target_column is not None:
        non_empty = [v for v in dataset.values(target_column) if v != ""]
        if len(set(non_empty)) <= 1 and non_empty:
            issues.append(
                RoleIssue(
                    code="constant_target",
                    message=(
                        f"The target column {target_column!r} has a single distinct value, so "
                        "target-based checks and stratification are not meaningful."
                    ),
                    severity="warning",
                    column=target_column,
                )
            )

    errors = [i for i in issues if i.severity == "error"]
    resolved: ResolvedRoles | None = None
    if not errors:
        resolved = ResolvedRoles(
            feature_columns=known_features,
            target_column=target_column,
            entity_column=entity_column,
            timestamp_column=timestamp_column,
            split_column=split_column,
            train_value=roles.split_train_value if split_column else None,
            test_value=roles.split_test_value if split_column else None,
            metadata_excluded=[n for n in metadata_excluded if n in columns],
            unused_columns=[
                c
                for c in dataset.columns
                if c not in set(known_features)
                and c
                not in {
                    target_column,
                    entity_column,
                    timestamp_column,
                    split_column,
                    *metadata_excluded,
                }
            ],
        )

    return RoleValidationResult(
        roles=roles,
        ok=not errors,
        issues=issues,
        resolved=resolved,
    )


__all__ = ["validate_roles"]
