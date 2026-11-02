# Data dictionary and research roles (F02, role mapping)

Each column carries two independent kinds of information:

- **computed** — detected type, missing count/ratio, distinct count, examples,
  numeric or timestamp summaries (see `S3_DATA_PROFILE.md`);
- **declared** — confirmed type, description, unit, measurement scale and one or
  more research roles.

Computed values never overwrite declarations. A confirmed type is shown next to
the detected one rather than replacing it.

## Roles

| Role | Meaning | Notes |
| --- | --- | --- |
| `entity` | entity/group identifier | one column only |
| `timestamp` | time of the record | one column only |
| `split` | train/test assignment | one column only; needs train and test labels |
| `target` | outcome | one column only |
| `predictor` | available as a feature | multiple columns |
| `treatment` | exposure | used by causal work in later stages |
| `confounder` | adjustment variable | may also be a predictor |
| `mediator` | post-treatment variable | may be a predictor, with tension warnings |
| `effect_modifier` | interaction variable | may also be a predictor |
| `instrument` | candidate instrument | may also be a predictor |
| `sensitive` | protected attribute | user-assigned only; never detected |
| `future_only` | value only known after the outcome | cannot be a predictor |
| `excluded` | excluded from analysis | cannot hold any other role |

Multiple compatible roles are allowed on purpose: a confounder *is* a predictor
used for adjustment, and forcing a single tag would make users misdescribe their
design.

## Conflict matrix

Hard errors (block saving; the previously saved map stays active):

- `target` with `predictor`, `confounder`, `treatment`, `mediator`, `instrument`
  or `effect_modifier`
- `split` with `predictor`, `confounder` or `treatment`
- `entity` with `predictor`, `confounder` or `treatment`
- `timestamp` with `predictor`
- `excluded` with any other role
- `future_only` with `predictor`, `confounder`, `treatment`, `instrument` or
  `mediator`

Warnings (saved, but reported and carried into the payload):

- `mediator` + `confounder` — adjusting would block part of the effect
- `instrument` + `confounder` — opposite roles
- `treatment` + `confounder` — same column in two roles
- `sensitive` + `predictor` — requires a recorded justification and a fairness plan

Structural errors: unknown column, unknown role, more than one `target`
(and the other singular roles), no roles at all, missing split labels.

## One authoritative mapping

`build_role_map` returns:

- `assignments` — the cleaned map (unknown roles dropped with an issue);
- `derived_roles` — V1 `ColumnRoles` (`features`, `target`, `entity`,
  `timestamp`, `split`, split values, `metadata_excluded`);
- `issues` — research conflicts **plus** the V1 validator's issues, prefixed
  `audit_`, so a map that is research-valid but audit-invalid cannot be saved;
- `ok`, `errors`, `warnings`.

The derived object is what the audit engine receives. The UI's "Use these roles in
the audit" button hands exactly that object to the workbench state, so the two
workspaces cannot disagree about what a column means.

Seeding: a bundled demo starts from its own manifest (`roles_seeded_from: "demo
manifest"`). An upload starts empty; the Study Card offers "Copy the workbench
roles" as an explicit action. Nothing is copied silently.

## V1 compatibility

`roles_from_column_roles` maps V1 roles into the research vocabulary exactly once
(features → predictor; target/entity/timestamp/split → the same names; excluded
metadata → excluded), and `test_derived_roles_are_accepted_by_the_v1_validator`
proves the derived map passes the original validator unchanged. The five leakage
checks, their definitions and their evidence are untouched.

## API

| Method | Path | Behaviour |
| --- | --- | --- |
| `GET` | `/api/datasets/{id}/dictionary` | computed columns + current roles + conventions |
| `PUT` | `/api/datasets/{id}/roles` | validates, stores only if valid, returns derived roles and issues |

## UI

`DataDictionary` renders a compact table (column, detected type, declared type,
missing, distinct, role chips). Selecting a row opens an inspector with all
thirteen role checkboxes, confirmed type, unit and description, plus the live
conflict messages. Conflicts turn the row red and leave the saved map untouched.
