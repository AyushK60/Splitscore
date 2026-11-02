# Reproducibility foundation (F19, S3 portion)

A manifest answers three questions: which bytes were analysed, under which schema
and roles, and with which declared study. It is an identity document, not a data
export.

## Content

`backend/app/research/provenance.py` — `build_manifest`.

| Block | Contents |
| --- | --- |
| `manifest_schema_version`, `study_schema_version` | `1.0` / `1.0` |
| `application` | product name and version |
| `study` | the declared card fields (no defaults filled in) |
| `dataset` | name, source, synthetic flag, **SHA-256 of the uploaded bytes**, rows, columns, encoding, row-id scheme, **schema fingerprint** |
| `roles` | the declared assignment map, the derived V1 roles, and the role-validation counts |
| `analysis` | split description, seed (`null`), preprocessing (`none`), available checks, checks run (`[]`), run ids (`[]`) |
| `exclusions` | excluded columns; excluded row count is `null` because the audit applies none |
| `warnings` | declared-not-verified study data; fingerprints identify structure, not contents |
| `integrity` | `raw_data_embedded: false`, `cell_values_embedded: false` |

### Two fingerprints, deliberately different

- **Dataset SHA-256** — hash of the exact uploaded bytes, computed during
  ingestion. It identifies the file, not a schema.
- **Schema fingerprint** — SHA-256 of a canonical JSON document containing the
  column order and the full role mapping (including split labels). It identifies
  the *analysis configuration*: reordering columns or changing a role produces a
  different fingerprint, because that is a different analysis.

Neither fingerprint embeds a cell value, and the manifest never contains rows.

## Export

`GET /api/datasets/{id}/manifest/export` returns JSON with
`Content-Disposition: attachment` and an `X-SplitScope-Export-Note` header
stating that it contains metadata only. `GET /api/datasets/{id}/manifest`
returns the same body for display in the UI.

## Validation and import

`POST /api/datasets/{id}/manifest/validate` with `{ manifest, apply }`.

| Status | Meaning | What the UI does |
| --- | --- | --- |
| `match` | dataset hash and schema fingerprint both match | offers "Apply study metadata" |
| `dataset_mismatch` | the loaded bytes differ | explains that this manifest belongs to another file; applies nothing |
| `schema_mismatch` | same bytes, different columns or roles | reports the difference; does not apply |
| `unsupported_version` | unknown manifest schema | states which version this build reads |
| `malformed` | no derived roles or invalid role object | refuses |

`apply: true` is only honoured for `match`. It copies the study fields and the
role assignment map into the in-memory study record and returns the updated
study state. It never touches the dataset.

## What is not yet recorded

Deliberately deferred to later stages, and stated in `analysis` rather than
faked: audit run ids, check results, preprocessing graph, model specification,
DAG version, adjustment set, dependency versions beyond the application version,
figure ids, and timestamps per run. S3 records the *foundation* — identity,
schema, roles, declarations — so those stages can attach to it.

## Tests

`test_dataset_sha256_is_the_hash_of_the_uploaded_bytes` compares the manifest
against `hashlib.sha256` of the uploaded payload, independently of the app.
`test_manifest_contains_no_cell_values_and_no_rows` embeds a sentinel string in a
cell and asserts it never appears in the serialised manifest.
`test_schema_fingerprint_is_deterministic_and_role_sensitive` proves determinism
and sensitivity to a role change. Round-trip tests cover match, dataset mismatch
and unsupported version.
