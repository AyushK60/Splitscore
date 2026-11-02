# Dataset profile (F02, profiling)

`backend/app/research/profiling.py` computes the profile from the loaded frame.
Nothing is sampled, estimated or inferred from column names; every number has a
stated convention.

## Dataset level

| Figure | Definition |
| --- | --- |
| `row_count`, `column_count` | the parsed frame's shape |
| `duplicate_rows` | rows that exactly repeat an earlier row (`keep="first"`) |
| `duplicate_row_groups` | distinct duplicate signatures among those rows |
| `duplicate_example_row_ids` | up to five positional row ids |
| `numeric_columns`, `datetime_columns` | columns whose detected type is numeric/integer or datetime |
| `fingerprint_sha256` | SHA-256 of the uploaded bytes |

Duplicate rows are reported as a property of the file. The profile never says a
duplicate across a split is leakage; that is the audit's job, with its own
denominators.

## Column level

- `detected_type` plus `detected_type_reason` (the ratio that justified it).
- `missing_count` / `missing_ratio` — **an empty cell is missing**. `"NA"` is an
  ordinary value unless the Study Card declares otherwise.
- `distinct_count`, `distinct_ratio`.
- `examples` — first three non-missing values, truncated to 60 characters.
- `numeric` — count, min, max, mean, median, sample standard deviation
  (`ddof=1`), q1/q3 (linear interpolation), IQR outlier **candidates** and the
  rule used.
- `datetime` — parsed/unparsed counts, parse ratio, min/max UTC, span in days.
- `flags` — `identifier_like`, `constant`, `all_missing`, `unique_per_row`,
  `outlier_candidates`, `mixed_types`.
- `numeric_parse_ratio`, `datetime_parse_ratio`, `unparsed_numeric_cells` — how
  much of the column a numeric summary actually covers.

### Type detection order

1. no non-missing values → `empty`
2. two distinct values from a boolean vocabulary → `boolean`
3. ≥90 % parse as timestamps and <99 % as numbers → `datetime`
4. ≥99 % parse as numbers → `integer` (all whole) or `numeric`
5. every value unique with ≥10 rows → `identifier`
6. ≤20 distinct values → `categorical`
7. otherwise `text`

Between 50 % and 99 % numeric parsing the column is not summarised numerically;
it is flagged `mixed_types` and a warning names the ambiguity. This is the guard
against a mean computed over a silently coerced column.

## Conventions returned with the profile

The API returns them so the UI never has to paraphrase:

- a missing value is an empty cell; `"NA"`/`"NaN"` are values;
- numeric summaries ignore unparseable cells and report how many;
- detected types are advisory and never overwrite a confirmed type;
- outliers are IQR candidates, not data errors.

## Bounds

Profiling runs over the already-bounded in-memory frame (default limits: 10 000
rows, 100 columns, 256 MiB parsed). It allocates no persistent state, is not
cached, and does not modify the dataset. Re-opening the profile recomputes from
the same bytes.

## Tests

`backend/tests/test_research.py` asserts exact counts, missing ratios, type
detection, cardinality flags, duplicate row ids, a single-row dataset (std = 0),
text columns that must not receive a numeric summary, and numeric statistics
against an independent oracle (`statistics.stdev` and hand-computed quartiles).
