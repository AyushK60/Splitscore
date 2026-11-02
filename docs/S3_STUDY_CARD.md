# Study Card (F01)

A Study Card is the researcher's declaration of what a dataset is for. It is
attached to one loaded dataset, lives in the server's memory for the same TTL as
the data, and can be exported and re-imported as metadata only.

## Model

`backend/app/research/schema.py` — `StudyCardDraft`, a Pydantic model with
`extra="forbid"`. Missing values are `None`; blank strings are normalised to
`None` before validation, so "empty" and "not declared" are the same thing.

| Section | Fields |
| --- | --- |
| Purpose | `title`*, `objective`*, `domain`, `target_task`*, `primary_outcome` |
| Design | `design`*, `unit_of_analysis`*, `population`, `sampling`, `collection_period`, `inclusion_rules`, `exclusion_rules`, `predictor_availability` |
| Measurement | `missing_data_convention` |
| Rights | `data_owner`, `rights_note`, `consent_status`, `limitations` |

`*` = required for the completion indicator.

Enumerations are closed: `design` (cross-sectional, longitudinal, experimental,
quasi-experimental, observational, other, unknown), `target_task` (prediction,
descriptive, causal, exploration, unknown), `consent_status` (obtained, waiver,
not required, refused, unknown), `predictor_availability` (at prediction time,
after outcome, mixed, not applicable, unknown). An unknown design is a valid
answer; a missing design is not silently turned into one.

`privacy_flags` accepts `contains_direct_identifiers`,
`contains_sensitive_attributes`, `restricted_use` — the user asserts them, and
their absence is not a claim that none apply.

## Completion — a count, not a score

```json
{
  "required": 5,
  "declared": 3,
  "ratio": 0.6,
  "missing": ["design", "unit_of_analysis"],
  "note": "Counts only fields this product requires to describe a study. It is not a measure of scientific quality or ethical approval."
}
```

The UI shows `3/5 required fields declared` plus the missing field names. There
is no numerical "study quality" anywhere in the product.

## Provenance

Every field is returned with `provenance: "user_declared" | "missing"`. The
response separates:

- `declared` — fields the user supplied,
- `missing` — fields left blank,
- `computed` — dataset facts (`row_count`, `column_count`, `fingerprint_sha256`,
  profile columns, schema fingerprint),
- `inferred` — always empty today, with a note that the product does not fill in
  study fields.

Consent is never inferred. If a `rights_note` exists but `consent_status` is
blank, the card reports `consent_not_stated` as an informational issue rather
than assuming permission.

## API

| Method | Path | Behaviour |
| --- | --- | --- |
| `GET` | `/api/datasets/{id}/study` | creates the record on first read; returns card, completion, fields, provenance, roles |
| `PUT` | `/api/datasets/{id}/study` | validates and replaces the card; increments `revision` |
| `GET` | `/api/datasets/{id}/study/export` | JSON download: card, roles, declarations, provenance, dataset identity — **no rows** |
| `POST` | `/api/datasets/{id}/manifest/validate` | with `apply: true`, imports study metadata from a matching manifest |

Import validates `manifest_schema_version`, the dataset SHA-256 and the schema
fingerprint first; a mismatch is reported and nothing is applied.

## Storage and honesty

`StudyRegistry` is a bounded (32 entries) in-memory map keyed by dataset id,
inside the same `AppContext` as the store. Consequences, stated in every payload
via `storage_note`:

- a restart loses the card;
- the card expires with the dataset, so it cannot outlive its data;
- a saved card does **not** mean the raw dataset was saved — raw data is never
  written to disk.

## Verified behaviour

`backend/tests/test_research.py` covers creation-once, dataset scoping, required
field completion, no invented values, edits and revisions, invalid enum rejection
(422), export without cell values, and the completion note not being a quality
score. The browser suite fills and saves a card, exports a manifest and re-imports
it, then checks the title survived.
