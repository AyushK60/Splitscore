"""Independent ground-truth oracles for the synthetic evaluation.

Each oracle is written from the *documented definition* of the corresponding
rule (the definition text lives in the rule module's docstring and in the
assumptions the rule prints into its findings), using only pandas/numpy. No
oracle imports a rule, the engine, the canonicalisation helpers or any other
production counting code, so:

* agreement between oracle and detector is real evidence that the detector
  implements its stated definition, and
* a disagreement localises a bug to exactly one side.

Where a definition leaves a choice open (for example, the interpolation used
for quartiles in robust scaling), the oracle states which convention it uses
and hand-built fixtures are designed so that the choice cannot change the
answer (symmetric data with unambiguous quartiles).

These oracles compute *complete* expected outcomes - every detectable case,
not just the planted ones - because generated data can introduce additional
matches beyond what the generator planted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Shared, deliberately duplicated semantics (see module docstring for why).
# --------------------------------------------------------------------------- #

MISSING = ""


def _tokens(series: pd.Series, missing_tokens: frozenset[str] = frozenset()) -> list[str]:
    """Canonical comparison token per the documented missing/strip semantics."""
    out: list[str] = []
    for value in series.tolist():
        text = "" if value is None else str(value).strip()
        out.append(MISSING if text == "" or text in missing_tokens else text)
    return out


def _missing_mask(series: pd.Series, missing_tokens: frozenset[str] = frozenset()) -> np.ndarray:
    return np.array([token == MISSING for token in _tokens(series, missing_tokens)], dtype=bool)


def _parse_timestamps(series: pd.Series) -> pd.Series:
    """Parse timestamps per the chronology rule's stated policy.

    Naive timestamps are read as UTC, mixed offsets normalised to UTC, and
    unparsable values become NaT.
    """
    return pd.to_datetime(series, errors="coerce", utc=True, format="mixed")


def _severity_dup(affected_test_rows: int, test_rows: int) -> str:
    """SS-DUP-001 severity: high at >=10 affected test rows or >=5% share,
    medium at >=2 rows, else low (documented in the rule module)."""
    share = affected_test_rows / test_rows if test_rows else 0.0
    if affected_test_rows >= 10 or share >= 0.05:
        return "high"
    if affected_test_rows >= 2:
        return "medium"
    return "low"


def _severity_entity(test_share: float, threshold: float) -> str:
    return "high" if test_share >= threshold else "medium"


def _severity_chronology(affected_share: float, threshold: float) -> str:
    return "high" if affected_share >= threshold else "medium"


def _severity_target_copy(coverage: float, baseline: float | None, high: float, margin: float) -> str:
    if coverage >= high:
        return "high"
    if baseline is not None and coverage < baseline + margin:
        return "low"
    return "medium"


# --------------------------------------------------------------------------- #
# SS-DUP-001 - exact feature duplicates across the boundary
# --------------------------------------------------------------------------- #


@dataclass
class DuplicateTruth:
    shared_signatures: int
    affected_train_rows: int
    affected_test_rows: int
    test_signatures: int  # distinct signatures observed in the test split
    #: Test rows whose signature group contains >=2 *test* rows (within-test
    #: duplication only; a spanning group with a single test row is not counted).
    within_test_duplicate_rows: int
    #: Train rows whose signature group contains >=2 *train* rows, whether or
    #: not the group also spans the boundary. The rule's metric counts every
    #: group with >1 train row; its "within train only" label is looser than
    #: this. Both readings coincide on the bundled demo (every spanning group
    #: there has exactly one train row), and the hand-built fixture pins the
    #: behaviour explicitly.
    within_train_duplicate_rows: int
    severity: str | None  # None when no finding is expected

    def as_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items()}


def duplicate_truth(
    frame: pd.DataFrame,
    feature_columns: list[str],
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    *,
    missing_tokens: frozenset[str] = frozenset(),
) -> DuplicateTruth:
    """Complete expected outcome of SS-DUP-001 from its documented definition.

    Definition: canonicalise the selected feature columns (strip whitespace;
    missing is empty-after-strip, plus configured tokens), group rows by the
    full tuple, and report groups containing at least one train and one test
    row. Only selected features are compared; target, split and unselected
    columns are ignored.
    """
    per_column = [_tokens(frame[column], missing_tokens) for column in feature_columns]
    signatures = list(zip(*per_column, strict=True))

    train_signatures: dict[tuple[str, ...], int] = {}
    test_signatures: dict[tuple[str, ...], int] = {}
    for signature, is_train, is_test in zip(signatures, train_mask, test_mask, strict=True):
        if is_train:
            train_signatures[signature] = train_signatures.get(signature, 0) + 1
        if is_test:
            test_signatures[signature] = test_signatures.get(signature, 0) + 1

    shared = set(train_signatures) & set(test_signatures)
    affected_train = sum(train_signatures[sig] for sig in shared)
    affected_test = sum(test_signatures[sig] for sig in shared)
    within_test = sum(count for count in test_signatures.values() if count > 1)
    within_train = sum(count for count in train_signatures.values() if count > 1)

    test_rows = int(test_mask.sum())
    return DuplicateTruth(
        shared_signatures=len(shared),
        affected_train_rows=affected_train,
        affected_test_rows=affected_test,
        test_signatures=len(test_signatures),
        within_test_duplicate_rows=within_test,
        within_train_duplicate_rows=within_train,
        severity=_severity_dup(affected_test, test_rows) if shared else None,
    )


# --------------------------------------------------------------------------- #
# SS-ENT-001 - entity overlap
# --------------------------------------------------------------------------- #


@dataclass
class EntityTruth:
    shared_groups: int
    affected_train_rows: int
    affected_test_rows: int
    train_distinct_groups: int
    test_distinct_groups: int
    unlabelled_train_rows: int
    unlabelled_test_rows: int
    severity: str | None

    def as_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items()}


def entity_truth(
    frame: pd.DataFrame,
    entity_column: str,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    *,
    high_share_threshold: float = 0.10,
    missing_tokens: frozenset[str] = frozenset(),
) -> EntityTruth:
    """Complete expected outcome of SS-ENT-001.

    Definition: entity values are compared as literal strings after stripping.
    Rows with an empty entity value are counted separately and never merged
    into one synthetic entity. Severity is high when the share of test rows
    belonging to a shared entity reaches the configured threshold.
    """
    tokens = _tokens(frame[entity_column], missing_tokens)
    missing = np.array([token == MISSING for token in tokens], dtype=bool)

    train_groups: dict[str, int] = {}
    test_groups: dict[str, int] = {}
    for token, is_train, is_test, is_missing in zip(
        tokens, train_mask, test_mask, missing, strict=True
    ):
        if is_missing:
            continue
        if is_train:
            train_groups[token] = train_groups.get(token, 0) + 1
        if is_test:
            test_groups[token] = test_groups.get(token, 0) + 1

    shared = set(train_groups) & set(test_groups)
    affected_train = sum(train_groups[t] for t in shared)
    affected_test = sum(test_groups[t] for t in shared)
    test_rows = int(test_mask.sum())
    share = affected_test / test_rows if test_rows else 0.0

    return EntityTruth(
        shared_groups=len(shared),
        affected_train_rows=affected_train,
        affected_test_rows=affected_test,
        train_distinct_groups=len(train_groups),
        test_distinct_groups=len(test_groups),
        unlabelled_train_rows=int((missing & train_mask).sum()),
        unlabelled_test_rows=int((missing & test_mask).sum()),
        severity=_severity_entity(share, high_share_threshold) if shared else None,
    )


# --------------------------------------------------------------------------- #
# SS-CHR-001 - chronology violation
# --------------------------------------------------------------------------- #


@dataclass
class ChronologyTruth:
    status: str  # 'ordered' | 'violation' | 'insufficient_data'
    affected_train_rows: int
    boundary_tie_rows: int
    unparsable_train_rows: int
    unparsable_test_rows: int
    train_valid_rows: int
    test_valid_rows: int
    severity: str | None

    def as_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items()}


def chronology_truth(
    frame: pd.DataFrame,
    timestamp_column: str,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    *,
    high_share_threshold: float = 0.02,
) -> ChronologyTruth:
    """Complete expected outcome of SS-CHR-001.

    Definition: a violation is at least one *strictly later* training
    timestamp than the earliest valid test timestamp. Train rows exactly equal
    to the earliest test timestamp are boundary ties and are not violations.
    Unparsable timestamps are excluded from ordering and counted. If either
    side has no parsable timestamp the check reports insufficient data.
    """
    parsed = _parse_timestamps(frame[timestamp_column])
    valid = parsed.notna().to_numpy()

    train_positions = np.nonzero(train_mask & valid)[0].tolist()
    test_positions = np.nonzero(test_mask & valid)[0].tolist()

    unparsable_train = int((train_mask & ~valid).sum())
    unparsable_test = int((test_mask & ~valid).sum())

    if not train_positions or not test_positions:
        return ChronologyTruth(
            status="insufficient_data",
            affected_train_rows=0,
            boundary_tie_rows=0,
            unparsable_train_rows=unparsable_train,
            unparsable_test_rows=unparsable_test,
            train_valid_rows=len(train_positions),
            test_valid_rows=len(test_positions),
            severity=None,
        )

    train_values = parsed.iloc[train_positions]
    test_min = parsed.iloc[test_positions].min()
    affected = int((train_values > test_min).sum())
    ties = int((train_values == test_min).sum())

    if affected == 0:
        status, severity = "ordered", None
    else:
        status = "violation"
        severity = _severity_chronology(affected / len(train_positions), high_share_threshold)

    return ChronologyTruth(
        status=status,
        affected_train_rows=affected,
        boundary_tie_rows=ties,
        unparsable_train_rows=unparsable_train,
        unparsable_test_rows=unparsable_test,
        train_valid_rows=len(train_positions),
        test_valid_rows=len(test_positions),
        severity=severity,
    )


# --------------------------------------------------------------------------- #
# SS-TGT-001 - feature exactly matching the target
# --------------------------------------------------------------------------- #


@dataclass
class TargetCopyMatch:
    feature: str
    comparable_rows: int
    matching_rows: int
    coverage: float
    severity: str


@dataclass
class TargetCopyTruth:
    status: str  # 'evaluated' | 'insufficient_data'
    distinct_target_values: int
    matches: list[TargetCopyMatch] = field(default_factory=list)
    skipped_constant: list[str] = field(default_factory=list)
    skipped_small: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "distinct_target_values": self.distinct_target_values,
            "matches": [match.__dict__ for match in self.matches],
            "skipped_constant": list(self.skipped_constant),
            "skipped_small": list(self.skipped_small),
        }


def _decimal_equal(left: str, right: str) -> bool:
    """Numeric equivalence for numeric-looking values ('1' == '1.0')."""
    from decimal import Decimal, InvalidOperation

    if left == right:
        return True
    if "_" in left or "_" in right:
        return False
    try:
        left_num, right_num = Decimal(left), Decimal(right)
    except (InvalidOperation, ValueError):
        return False
    return left_num.is_finite() and right_num.is_finite() and left_num == right_num


def target_copy_truth(
    frame: pd.DataFrame,
    feature_columns: list[str],
    target_column: str,
    *,
    min_coverage: float = 0.90,
    high_coverage: float = 0.99,
    baseline_margin: float = 0.05,
    min_comparable_rows: int = 10,
    categorical_max_unique: int = 20,
    missing_tokens: frozenset[str] = frozenset(),
) -> TargetCopyTruth:
    """Complete expected outcome of SS-TGT-001.

    Definition: over rows where both the feature and target are non-missing,
    does the feature equal the target (string equality after stripping, with
    decimal equivalence for numeric-looking values)? A constant feature cannot
    copy a varying target and is skipped; a feature with fewer than the
    minimum comparable rows is skipped. Coverage below the reporting threshold
    produces no finding. Severity: high at >= the high-coverage threshold;
    low when coverage fails to exceed the target's majority-class rate (over
    comparable rows) by the baseline margin; otherwise medium. A target with
    at most one distinct non-missing value makes the whole check insufficient.
    """
    target_tokens = _tokens(frame[target_column], missing_tokens)
    target_missing = _missing_mask(frame[target_column], missing_tokens)
    distinct_targets = {t for t, m in zip(target_tokens, target_missing, strict=True) if not m}

    if len(distinct_targets) <= 1:
        return TargetCopyTruth(status="insufficient_data", distinct_target_values=len(distinct_targets))

    truth = TargetCopyTruth(status="evaluated", distinct_target_values=len(distinct_targets))

    for column in feature_columns:
        feature_tokens = _tokens(frame[column], missing_tokens)
        feature_missing = _missing_mask(frame[column], missing_tokens)

        non_missing = {t for t, m in zip(feature_tokens, feature_missing, strict=True) if not m}
        if len(non_missing) <= 1:
            truth.skipped_constant.append(column)
            continue

        comparable_idx = [
            i for i in range(len(frame)) if not feature_missing[i] and not target_missing[i]
        ]
        if len(comparable_idx) < min_comparable_rows:
            truth.skipped_small.append(column)
            continue

        matches = sum(
            1 for i in comparable_idx if _decimal_equal(feature_tokens[i], target_tokens[i])
        )
        coverage = matches / len(comparable_idx)

        # Majority-class baseline over the comparable rows.
        counts: dict[str, int] = {}
        for i in comparable_idx:
            counts[target_tokens[i]] = counts.get(target_tokens[i], 0) + 1
        baseline = (
            max(counts.values()) / len(comparable_idx) if len(counts) <= categorical_max_unique else None
        )

        if coverage >= min_coverage:
            truth.matches.append(
                TargetCopyMatch(
                    feature=column,
                    comparable_rows=len(comparable_idx),
                    matching_rows=matches,
                    coverage=round(coverage, 6),
                    severity=_severity_target_copy(coverage, baseline, high_coverage, baseline_margin),
                )
            )

    return truth


# --------------------------------------------------------------------------- #
# SS-NEAR-001 - near-duplicate candidates (Chebyshev distance, opt-in)
# --------------------------------------------------------------------------- #


@dataclass
class NearDuplicateTruth:
    status: str  # 'evaluated' | 'unsupported' | 'insufficient_data'
    candidate_pairs: int
    implicated_train_rows: int
    implicated_test_rows: int
    analysed_train_rows: int
    analysed_test_rows: int
    excluded_constant: list[str] = field(default_factory=list)
    excluded_zero_iqr: list[str] = field(default_factory=list)
    dropped_rows: int = 0
    severity: str | None = None

    def as_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items()}


def near_duplicate_truth(
    frame: pd.DataFrame,
    feature_columns: list[str],
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    *,
    threshold: float = 0.05,
    scaling: str = "robust",
    min_numeric_ratio: float = 0.8,
    max_missing_fraction_per_row: float = 0.5,
    medium_pairs: int = 10,
    medium_test_share: float = 0.05,
) -> NearDuplicateTruth:
    """Complete expected outcome of SS-NEAR-001 (unsampled path).

    Definition, per the rule's module docstring: numeric feature columns only
    (>= min_numeric_ratio of non-missing values parse as numbers); rows
    missing more than max_missing_fraction_per_row of the included columns are
    dropped; remaining gaps are filled with the column median over the
    analysed rows of both splits; 'robust' scaling centres on the median and
    divides by the interquartile range (numpy's linear interpolation), with
    constant and zero-IQR columns excluded; the distance between a train and a
    test row is the maximum absolute scaled difference (Chebyshev); pairs at
    or below the threshold are candidates. Severity is capped at medium.
    """
    numeric_columns: list[str] = []
    excluded_non_numeric: list[str] = []
    for column in feature_columns:
        series = frame[column]
        non_missing = int((~_missing_mask(series)).sum())
        if non_missing == 0:
            excluded_non_numeric.append(column)
            continue
        parsed = pd.to_numeric(series, errors="coerce")
        ratio = float(parsed.notna().sum()) / float(non_missing)
        if ratio >= min_numeric_ratio:
            numeric_columns.append(column)
        else:
            excluded_non_numeric.append(column)

    if not numeric_columns:
        return NearDuplicateTruth(
            status="unsupported",
            candidate_pairs=0,
            implicated_train_rows=0,
            implicated_test_rows=0,
            analysed_train_rows=0,
            analysed_test_rows=0,
        )

    raw = np.column_stack(
        [pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float) for column in numeric_columns]
    )
    train_positions = np.nonzero(train_mask)[0]
    test_positions = np.nonzero(test_mask)[0]

    missing_fraction = np.isnan(raw).sum(axis=1) / raw.shape[1]
    retained = missing_fraction <= max_missing_fraction_per_row
    dropped = int((~retained).sum())

    train_kept = train_positions[retained[train_positions]]
    test_kept = test_positions[retained[test_positions]]

    if len(train_kept) == 0 or len(test_kept) == 0:
        return NearDuplicateTruth(
            status="insufficient_data",
            candidate_pairs=0,
            implicated_train_rows=0,
            implicated_test_rows=0,
            analysed_train_rows=len(train_kept),
            analysed_test_rows=len(test_kept),
            dropped_rows=dropped,
        )

    combined = raw[np.concatenate([train_kept, test_kept])]
    with np.errstate(all="ignore"):
        column_min = np.nanmin(combined, axis=0)
        column_max = np.nanmax(combined, axis=0)
    constant = column_min == column_max
    medians = np.nanmedian(combined, axis=0)
    q25 = np.nanpercentile(combined, 25, axis=0)
    q75 = np.nanpercentile(combined, 75, axis=0)
    iqr = q75 - q25

    excluded_constant = [numeric_columns[i] for i in np.nonzero(constant)[0].tolist()]
    zero_iqr = (~constant) & (iqr == 0)
    excluded_zero_iqr = (
        [numeric_columns[i] for i in np.nonzero(zero_iqr)[0].tolist()] if scaling == "robust" else []
    )
    drop = constant | (zero_iqr if scaling == "robust" else np.zeros_like(constant))

    if bool(drop.all()):
        return NearDuplicateTruth(
            status="insufficient_data",
            candidate_pairs=0,
            implicated_train_rows=0,
            implicated_test_rows=0,
            analysed_train_rows=len(train_kept),
            analysed_test_rows=len(test_kept),
            excluded_constant=excluded_constant,
            excluded_zero_iqr=excluded_zero_iqr,
            dropped_rows=dropped,
        )

    keep = np.nonzero(~drop)[0]

    def prepared(positions: np.ndarray) -> np.ndarray:
        matrix = raw[positions][:, keep].copy()
        missing = np.isnan(matrix)
        matrix[missing] = np.take(medians[keep], np.nonzero(missing)[1])
        if scaling == "robust":
            matrix = (matrix - medians[keep]) / iqr[keep]
        return matrix

    train_scaled = prepared(train_kept)
    test_scaled = prepared(test_kept)

    distance = np.abs(train_scaled[:, None, :] - test_scaled[None, :, :]).max(axis=2)
    hits = distance <= threshold
    train_hit = hits.any(axis=1)
    test_hit = hits.any(axis=0)

    pairs = int(hits.sum())
    analysed_pairs = int(train_scaled.shape[0] * test_scaled.shape[0])
    implicated_train = int(train_hit.sum())
    implicated_test = int(test_hit.sum())
    test_share = implicated_test / test_scaled.shape[0]

    severity = None
    if pairs > 0:
        severity = (
            "medium"
            if pairs >= medium_pairs or test_share >= medium_test_share
            else "low"
        )

    return NearDuplicateTruth(
        status="evaluated",
        candidate_pairs=pairs,
        implicated_train_rows=implicated_train,
        implicated_test_rows=implicated_test,
        analysed_train_rows=int(train_scaled.shape[0]),
        analysed_test_rows=int(test_scaled.shape[0]),
        excluded_constant=excluded_constant,
        excluded_zero_iqr=excluded_zero_iqr,
        dropped_rows=dropped,
        severity=severity,
    )


__all__ = [
    "ChronologyTruth",
    "DuplicateTruth",
    "EntityTruth",
    "NearDuplicateTruth",
    "TargetCopyMatch",
    "TargetCopyTruth",
    "chronology_truth",
    "duplicate_truth",
    "entity_truth",
    "near_duplicate_truth",
    "target_copy_truth",
]
