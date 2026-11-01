"""SS-NEAR-001: near-duplicate candidates across the split (opt-in, bounded).

Method, stated in full because the number it produces is only meaningful with its
definitions attached:

1. **Columns.** Only selected feature columns that parse as numeric for at least
   ``min_numeric_ratio`` of their non-missing values take part. Non-numeric
   feature columns are listed as excluded, not silently skipped.
2. **Rows.** Rows missing more than ``max_missing_fraction_per_row`` of the
   included columns are excluded and counted.
3. **Imputation.** Remaining gaps are filled with the column median computed over
   the analysed rows of *both* splits together, so the imputation does not depend
   on which split a row landed in.
4. **Scaling.** With ``scaling='robust'`` each column is centred on its median and
   divided by its interquartile range; with ``scaling='none'`` raw values are
   used. Constant columns are excluded because they contribute zero difference by
   definition, in either scaling mode.
5. **Distance.** Normalised Chebyshev (L-infinity) distance: the maximum absolute
   scaled difference over the included columns. One number per row pair, directly
   readable as "no included feature differs by more than this".
6. **Pairs.** Only cross-split pairs are compared, in chunks, so peak memory stays
   bounded regardless of the row bound.

The scaler is diagnostic. It is never serialised, never returned as a fitted
pipeline, and must not be reused for modelling.

Severity is capped at ``medium``: similar rows are candidates, not proof.
"""

from __future__ import annotations

import heapq

import numpy as np
import pandas as pd

from app.audit.rules.base import RuleContext, RuleOutput, format_value
from app.audit.tokens import column_missing_mask
from app.audit.types import Count, EvidenceExample, Finding, RuleMetric

RULE_ID = "SS-NEAR-001"
TITLE = "Near-duplicate candidates across the split"

#: Test-row chunk size for the pairwise distance sweep.
PAIR_CHUNK_SIZE = 64
MEDIUM_CANDIDATE_PAIRS = 10
MEDIUM_CANDIDATE_TEST_SHARE = 0.05
TOP_DIFFERING_COLUMNS = 4

LIMITATIONS = [
    "Similarity is not leakage. Rows that are close in the scaled feature space may be genuinely "
    "distinct records; this rule reports candidates for inspection, never conclusions.",
    "Only numeric feature columns participate. Text, categorical and timestamp features are "
    "excluded from the distance and are listed explicitly in the finding's metrics.",
    "Distances are measured after diagnostic scaling. The scaler is a diagnostic device, not an "
    "exported fitted pipeline; reusing it as one would change its purpose.",
    "Counts taken over a sample describe that sample. They are reported with their scope and are "
    "not estimates for the whole dataset.",
    "Missing values are median-imputed, which pulls rows with gaps toward the centre of the "
    "distribution and can make such rows appear closer to each other than they are.",
    "Pairs are compared across the split only. Within-split near-duplicates are not reported here.",
    "Successive-threshold search, blocking and locality-sensitive hashing are not implemented; the "
    "sweep is exhaustive over the analysed sample, which is why the sample is bounded.",
]


def _fmt_raw(value: float) -> str:
    return "(missing)" if value != value else format_value(f"{value:g}", limit=32)


def _proportional_sample(
    seed: int, train_positions: list[int], test_positions: list[int], cap: int
) -> tuple[list[int], list[int]]:
    """Seeded, proportional sample that keeps both sides non-empty."""
    total = len(train_positions) + len(test_positions)
    effective = max(2, min(cap, total))
    rng = np.random.default_rng(seed)

    n_train = int(round(effective * len(train_positions) / total))
    n_train = max(1, min(n_train, len(train_positions)))
    n_test = max(1, min(effective - n_train, len(test_positions)))
    # Give back to train if the test side could not absorb its share.
    n_train = max(1, min(effective - n_test, len(train_positions)))

    train_sample = sorted(
        rng.choice(np.asarray(train_positions, dtype=np.int64), size=n_train, replace=False).tolist()
    )
    test_sample = sorted(
        rng.choice(np.asarray(test_positions, dtype=np.int64), size=n_test, replace=False).tolist()
    )
    return train_sample, test_sample


def run(ctx: RuleContext) -> RuleOutput:
    settings = ctx.config.near_duplicates
    server_cap = ctx.settings.near_duplicate.max_combined_rows
    effective_cap = max(2, min(settings.max_combined_rows, server_cap))

    if not settings.enabled:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "disabled",
            "Near-duplicate analysis is opt-in and was not enabled for this audit.",
            effective_row_bound=str(effective_cap),
        )

    features = ctx.resolved.feature_columns
    if not features:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "not_evaluated",
            "No feature columns were selected, so no distance can be computed.",
            feature_columns="0",
        )

    frame = ctx.dataset.frame
    numeric_columns: list[str] = []
    excluded_columns: list[tuple[str, str]] = []
    for column in features:
        missing = column_missing_mask(frame, column, ctx.canonicalizer)
        non_missing = int((~missing).sum())
        if non_missing == 0:
            excluded_columns.append((column, "all values are missing"))
            continue
        parsed = pd.to_numeric(frame[column], errors="coerce")
        ratio = float(parsed.notna().sum()) / float(non_missing)
        if ratio >= settings.min_numeric_ratio:
            numeric_columns.append(column)
        else:
            excluded_columns.append((column, f"{ratio:.0%} of non-missing values parse as numbers"))

    if not numeric_columns:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "unsupported",
            "No selected feature column is numeric for at least "
            f"{settings.min_numeric_ratio:.0%} of its non-missing values; this version computes "
            "distances on numeric features only.",
            excluded_columns="; ".join(f"{c}: {r}" for c, r in excluded_columns[:10]),
        )

    train_positions = ctx.train_positions()
    test_positions = ctx.test_positions()
    combined = len(train_positions) + len(test_positions)
    unassigned = ctx.dataset.row_count - combined

    metrics = [
        RuleMetric(key="threshold", label="Distance threshold (scaled units)", value=settings.threshold),
        RuleMetric(key="scaling", label="Scaling", value=settings.scaling),
        RuleMetric(
            key="numeric_feature_columns_used",
            label="Numeric feature columns used in the distance",
            value=len(numeric_columns),
        ),
        RuleMetric(
            key="feature_columns_excluded",
            label="Feature columns excluded from the distance",
            value="; ".join(f"{c} ({r})" for c, r in excluded_columns[:10])
            if excluded_columns
            else "(none)",
        ),
        RuleMetric(key="combined_rows_before_bounding", label="Combined rows before bounding", value=combined),
        RuleMetric(key="effective_row_bound", label="Effective combined row bound", value=effective_cap),
    ]
    if unassigned:
        metrics.append(
            RuleMetric(
                key="unassigned_rows",
                label="Rows with no train/test label (excluded)",
                value=unassigned,
                unit="rows",
            )
        )

    sampling_note: str | None = None
    if combined > effective_cap:
        if settings.oversize_policy == "skip":
            return RuleOutput.not_run(
                RULE_ID,
                TITLE,
                "not_evaluated",
                f"The split has {combined} combined rows, above the effective bound of "
                f"{effective_cap}, and the oversize policy is 'skip'. Input is never truncated "
                "silently; reduce the dataset or raise the bound explicitly to run this check.",
                rows=str(combined),
                bound=str(effective_cap),
            )
        train_positions, test_positions = _proportional_sample(
            settings.sample_seed, train_positions, test_positions, effective_cap
        )
        sampling_note = (
            f"Seeded proportional sample: {len(train_positions)} train and {len(test_positions)} "
            f"test rows drawn from {combined} combined rows with seed {settings.sample_seed}. "
            "All counts below describe this sample, not the full split."
        )
        metrics.append(
            RuleMetric(
                key="sampled_rows",
                label="Rows in the analysed sample",
                value=len(train_positions) + len(test_positions),
                unit="rows",
            )
        )

    scope = "analysed sample (not a dataset-wide estimate)" if sampling_note else "full split"

    n_train = len(train_positions)
    selected_positions = train_positions + test_positions
    sub = frame.iloc[selected_positions][numeric_columns]

    raw_matrix = np.column_stack(
        [
            pd.to_numeric(sub[column], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
            for column in numeric_columns
        ]
    )

    missing_fraction = np.isnan(raw_matrix).sum(axis=1) / raw_matrix.shape[1]
    retained_rows = missing_fraction <= settings.max_missing_fraction_per_row
    dropped_rows = int((~retained_rows).sum())

    train_raw = raw_matrix[:n_train][retained_rows[:n_train]]
    test_raw = raw_matrix[n_train:][retained_rows[n_train:]]
    train_kept_positions = [p for p, keep in zip(train_positions, retained_rows[:n_train].tolist(), strict=True) if keep]
    test_kept_positions = [p for p, keep in zip(test_positions, retained_rows[n_train:].tolist(), strict=True) if keep]

    if train_raw.shape[0] == 0 or test_raw.shape[0] == 0:
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "insufficient_data",
            "After excluding rows with too many missing numeric values, one side of the split has no "
            "rows left to compare.",
            train_rows=str(train_raw.shape[0]),
            test_rows=str(test_raw.shape[0]),
            dropped_rows=str(dropped_rows),
        )

    combined_raw = np.vstack([train_raw, test_raw])
    all_missing = np.isnan(combined_raw).all(axis=0)
    with np.errstate(all="ignore"):
        column_min = np.nanmin(combined_raw, axis=0)
        column_max = np.nanmax(combined_raw, axis=0)
    constant = column_min == column_max
    medians = np.nanmedian(combined_raw, axis=0)
    q25 = np.nanpercentile(combined_raw, 25, axis=0)
    q75 = np.nanpercentile(combined_raw, 75, axis=0)
    iqr = q75 - q25

    excluded_constant = [numeric_columns[i] for i in np.nonzero(constant & ~all_missing)[0].tolist()]
    excluded_all_missing = [numeric_columns[i] for i in np.nonzero(all_missing)[0].tolist()]
    zero_iqr = (~constant) & (~all_missing) & (iqr == 0)
    excluded_zero_iqr = (
        [numeric_columns[i] for i in np.nonzero(zero_iqr)[0].tolist()]
        if settings.scaling == "robust"
        else []
    )

    drop = all_missing | constant | (zero_iqr if settings.scaling == "robust" else np.zeros_like(zero_iqr))
    if bool(drop.all()):
        return RuleOutput.not_run(
            RULE_ID,
            TITLE,
            "insufficient_data",
            "Every numeric feature column was excluded (all values missing, constant, or not robustly "
            "scalable), so no informative distance can be computed.",
            excluded_all_missing=str(len(excluded_all_missing)),
            excluded_constant=str(len(excluded_constant)),
            excluded_zero_iqr=str(len(excluded_zero_iqr)),
        )

    keep_cols = np.nonzero(~drop)[0]
    kept_medians = medians[keep_cols]
    used_columns = [numeric_columns[i] for i in keep_cols.tolist()]

    train_filled = train_raw[:, keep_cols].copy()
    test_filled = test_raw[:, keep_cols].copy()
    imputed_cells = int(np.isnan(train_filled).sum() + np.isnan(test_filled).sum())
    train_filled[np.isnan(train_filled)] = np.take(kept_medians, np.nonzero(np.isnan(train_filled))[1])
    test_filled[np.isnan(test_filled)] = np.take(kept_medians, np.nonzero(np.isnan(test_filled))[1])

    if settings.scaling == "robust":
        scale = iqr[keep_cols]
        train_scaled = (train_filled - kept_medians) / scale
        test_scaled = (test_filled - kept_medians) / scale
    else:
        train_scaled = train_filled
        test_scaled = test_filled

    metrics.extend(
        [
            RuleMetric(
                key="columns_used",
                label="Columns entering the distance",
                value=", ".join(used_columns[:12]) + (" …" if len(used_columns) > 12 else ""),
            ),
            RuleMetric(
                key="constant_columns_excluded",
                label="Constant columns excluded",
                value=", ".join(excluded_constant[:12]) if excluded_constant else "(none)",
            ),
            RuleMetric(
                key="zero_iqr_columns_excluded",
                label="Columns excluded: non-constant but zero interquartile range under robust scaling",
                value=", ".join(excluded_zero_iqr[:12]) if excluded_zero_iqr else "(none)",
            ),
            RuleMetric(
                key="rows_excluded_missingness",
                label="Rows excluded for too many missing values",
                value=dropped_rows,
                unit="rows",
            ),
            RuleMetric(
                key="imputed_cells",
                label="Cells median-imputed",
                value=imputed_cells,
                unit="values",
            ),
        ]
    )

    threshold = float(settings.threshold)
    keep_best = max(1, ctx.config.max_examples)
    best: list[tuple[float, int, int]] = []
    train_hit = np.zeros(train_scaled.shape[0], dtype=bool)
    test_hit = np.zeros(test_scaled.shape[0], dtype=bool)
    pairs_total = 0

    for start in range(0, test_scaled.shape[0], PAIR_CHUNK_SIZE):
        chunk = test_scaled[start : start + PAIR_CHUNK_SIZE]
        distance = np.abs(train_scaled[:, None, :] - chunk[None, :, :]).max(axis=2)
        rows, cols = np.nonzero(distance <= threshold)
        for row, col in zip(rows.tolist(), cols.tolist(), strict=True):
            pairs_total += 1
            train_hit[row] = True
            test_hit[start + col] = True
            value = float(distance[row, col])
            entry = (-value, row, start + col)
            if len(best) < keep_best:
                heapq.heappush(best, entry)
            elif value < -best[0][0]:
                heapq.heapreplace(best, entry)

    implicated_train = int(train_hit.sum())
    implicated_test = int(test_hit.sum())
    analysed_pairs = int(train_scaled.shape[0] * test_scaled.shape[0])

    metrics.extend(
        [
            RuleMetric(key="analysed_pairs", label="Cross-split pairs compared", value=analysed_pairs, unit="pairs"),
            RuleMetric(
                key="candidate_pairs",
                label="Candidate pairs at or below the threshold",
                value=pairs_total,
                unit="pairs",
            ),
            RuleMetric(
                key="implicated_test_rows",
                label="Test rows in at least one candidate pair",
                value=implicated_test,
                unit="rows",
            ),
        ]
    )

    if pairs_total == 0:
        return RuleOutput(status="evaluated", findings=[], metrics=metrics)

    test_share = implicated_test / test_scaled.shape[0]
    if pairs_total >= MEDIUM_CANDIDATE_PAIRS or test_share >= MEDIUM_CANDIDATE_TEST_SHARE:
        severity = "medium"
        rationale = (
            f"{pairs_total} cross-split pair(s) fall at or below the distance threshold of "
            f"{threshold:g}, involving {implicated_test} test rows ({test_share:.1%} of the analysed "
            "test rows), which is at or above the configured reporting level. Severity is capped at "
            "'medium' because near-identity is a screening signal: it identifies pairs to inspect, "
            "but similarity alone does not prove that leakage has occurred."
        )
    else:
        severity = "low"
        rationale = (
            f"{pairs_total} cross-split pair(s) fall at or below the distance threshold of "
            f"{threshold:g}, involving {implicated_test} test rows ({test_share:.1%} of the analysed "
            "test rows). Severity is 'low' and capped there by this rule's design, because near "
            "identity is a candidate signal rather than a proven defect."
        )

    ordered = sorted(best, key=lambda item: (item[0], item[1], item[2]))
    examples: list[EvidenceExample] = []
    for neg_distance, row, col in ordered:
        differences = np.abs(train_scaled[row] - test_scaled[col])
        top = np.argsort(-differences)[:TOP_DIFFERING_COLUMNS]
        detail_lines = []
        for index in top.tolist():
            column = used_columns[index]
            position = numeric_columns.index(column)
            detail_lines.append(
                f"{column}: train={_fmt_raw(train_raw[row, position])} "
                f"test={_fmt_raw(test_raw[col, position])} "
                f"scaled |diff|={differences[index]:.4f}"
            )
        examples.append(
            EvidenceExample(
                label=f"Candidate pair at distance {-neg_distance:.4f} (threshold {threshold:g})",
                row_ids=[ctx.row_id(train_kept_positions[row]), ctx.row_id(test_kept_positions[col])],
                details={
                    "distance": f"{-neg_distance:.6f}",
                    "threshold": f"{threshold:g}",
                    "train_row": ctx.row_id(train_kept_positions[row]),
                    "test_row": ctx.row_id(test_kept_positions[col]),
                    "top_feature_differences": " | ".join(detail_lines),
                },
            )
        )

    example_total = pairs_total
    examples_truncated = pairs_total > len(examples)

    if settings.scaling == "robust":
        measure = (
            f"a normalised Chebyshev distance of at most {threshold:g}, meaning that no included "
            f"numeric feature differs by more than {threshold:g} interquartile ranges between the "
            "two rows"
        )
    else:
        measure = (
            f"a maximum absolute difference of at most {threshold:g} in raw feature units, with no "
            "scaling applied"
        )

    finding = Finding(
        rule_id=RULE_ID,
        title=TITLE,
        severity=severity,
        severity_rationale=rationale,
        description=(
            f"{pairs_total} train/test row pair(s) out of {analysed_pairs} compared have {measure}, "
            "over the "
            f"{len(used_columns)} numeric feature column(s) that qualified. These pairs are "
            "candidates for near-duplication. Two records that are this close often share a cause: "
            "a repeated event recorded twice, a near-identical entity, or measurement noise around "
            "one underlying observation. Any of those, if it straddles the split boundary, means "
            "the test row is not an independent observation. Similarity alone does not establish "
            "that this has happened, which is why these are reported as candidates."
        ),
        evidence_summary=(
            f"{pairs_total} candidate pair(s) at or below distance {threshold:g}; "
            f"{implicated_test} of {test_scaled.shape[0]} analysed test row(s) "
            f"({test_share:.1%}) and {implicated_train} of {train_scaled.shape[0]} analysed train "
            f"row(s) are involved. Scope: {scope}."
        ),
        counts=[
            Count(
                label="Cross-split candidate pairs at or below the threshold",
                affected=pairs_total,
                denominator=analysed_pairs,
                unit="pairs",
                scope=scope,
            ),
            Count(
                label="Analysed test rows in at least one candidate pair",
                affected=implicated_test,
                denominator=int(test_scaled.shape[0]),
                unit="rows",
                scope=scope,
            ),
            Count(
                label="Analysed train rows in at least one candidate pair",
                affected=implicated_train,
                denominator=int(train_scaled.shape[0]),
                unit="rows",
                scope=scope,
            ),
            Count(
                label="Rows excluded for too many missing numeric values",
                affected=dropped_rows,
                denominator=int(combined),
                unit="rows",
                scope="selected rows before bounding" if not sampling_note else scope,
            ),
            Count(
                label="Feature columns excluded from the distance (non-numeric, constant or not scalable)",
                affected=len(excluded_columns) + len(excluded_constant) + len(excluded_zero_iqr),
                denominator=len(features),
                unit="columns",
                scope="all selected features",
            ),
        ],
        examples=examples,
        example_total=example_total,
        examples_truncated=examples_truncated,
        recommended_action=(
            "Inspect the listed pairs by their row IDs and decide whether they are the same "
            "underlying observation. If they are, remove or group them on one side of the boundary "
            "before training. If they are genuinely distinct records that happen to be close, "
            "record that judgement; raising the threshold is not a substitute for it."
        ),
        limitations=LIMITATIONS
        + ([sampling_note] if sampling_note else []),
        assumptions=[
            f"Distance is the maximum absolute difference over the included columns after "
            f"{'robust (median/IQR) scaling' if settings.scaling == 'robust' else 'no scaling'}.",
            "Scaling statistics are computed over the analysed rows of both splits combined, so the "
            "scale does not depend on the split.",
            "Missing values are filled with the column median of the analysed rows.",
            "A row is a candidate only against the other split; within-split similarity is out of scope.",
        ],
    )

    return RuleOutput(status="evaluated", findings=[finding], metrics=metrics)


__all__ = ["RULE_ID", "TITLE", "run"]
