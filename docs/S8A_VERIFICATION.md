# S8A verification

**Date:** 2026-11-05 · **Branch:** `v2-premium-visual-foundation` · **Python:** project venv (`E:\Splitscore V2\.venv`) · **OS:** Windows 10, Git Bash

Every result below is from an actual executed command; nothing is projected.

## Commands and results

Run from the repository root. The backend suite:

```bash
cd backend
../.venv/Scripts/python.exe -m pytest -q
# 406 passed, 3 warnings in 12.96s
```

The new S8A suite alone:

```bash
../.venv/Scripts/python.exe -m pytest -q tests/test_causal_graphs.py
# 33 passed, 1 warning in 1.84s
```

Synthetic oracle evaluation:

```bash
../.venv/Scripts/python.exe scripts/evaluate_synthetic.py
# 41 case(s), 41 passed, 0 failed, 0 error(s) | 61 check(s), 0 failed
# exit 0: all expectations matched
```

### Warnings (all pre-existing)

The backend run's three warnings are the S7 baseline's three: two numpy
divide warnings from the singular-design refusal test and one
Starlette/httpx `TestClient` deprecation warning emitted at import. No new
warning was introduced by S8A.

### Ledger

| Suite | S7 baseline `e100d53` | After S8A |
|---|---:|---:|
| Backend | 373 | **406** (+33) |
| Synthetic oracle | 41 cases / 61 checks | **41 / 61** |

## Frontend, TypeScript, ESLint, Playwright

**Not run — out of scope for the changed file set.** S8A modified no file under
`frontend/`; the only integration changes outside `backend/app/causal/` are
`backend/app/api/deps.py`, `backend/app/api/routes_causal.py`,
`backend/app/main.py` (router include + CORS `PUT`/`DELETE` methods). The S7
frontend suites exercise the same REST behaviour through the built app and are
unaffected by a purely additive router. This is a documented scope decision,
not a skipped gate; the next frontend-touching stage (S8B) must run all of them.

## Scientific test fixtures

Highlights from `backend/tests/test_causal_graphs.py` (expected outcomes are
hand-written in each test):

| Fixture | Expectation under test |
|---|---|
| Four-node confounded retention DAG (`age→tenure, age→churn, plan→tenure, plan→churn, tenure→churn`) | `201`; `validation.ok`; tenure's derived ancestors are `{age, plan}`; treatment→outcome path exists. |
| Chain `a→b→c→d` | `is_dag`; b's ancestors `[a]`, descendants `[c, d]`. |
| Fork `a←b→c` treatment b outcome c | No directed path (warning, not error); shared ancestor. |
| Collider `a→c←b` | `is_collider` true for c only. |
| Self-loop, directed cycle, duplicate node, duplicate edge, dangling endpoint | Each a blocking `422` with the specific issue code. |
| Treatment = outcome; treatment = undefined node | Blocking `analysis_same_node` / `analysis_node_missing`. |
| Node anchored to a non-existent column | Blocking `unknown_column` naming the node. |
| Schema version `9.9.9` | Blocking `unsupported_schema_version`. |
| Missing edge rationale, unselected scope, unobserved node | `201` with `edge_missing_rationale`, `analysis_incomplete`, `unobserved_variable_present` warnings; `ok` stays true. |
| Declared mediator off any treatment→outcome path | Warning `declared_role_unsupported`; the node's `kind` is **not** rewritten. |
| Missing target population | Warning `no_target_population`. |
| Duplicate assumption id | Blocking `duplicate_assumption_id`. |
| Graph on evicted dataset (store overfilled) | `410` on graph routes; the orphaned graph is pruned from the registry. |
| Valid graph fetched under a different dataset | `404 not_found`. |
| Invalid `PUT` (cycle introduced) | `422`; stored revision and fingerprint unchanged; edges unchanged. |
| Export → import roundtrip | New `graph_id`, revision 0, identical `spec_fingerprint_sha256`. |
| Import of a foreign JSON object / schema `0.9.0` file | `422` with explanatory messages. |
| Export from dataset A imported into dataset B (different columns) | `422` with `unknown_column`. |
| Fingerprint invariance | Same hash with reordered nodes and with/without layout coordinates; different hash after an edge rationale changes. |
| Existing endpoints after wiring | `/api/health`, `/api/datasets/{id}`, `/api/datasets/{id}/study` all `200` with unchanged shapes. |

## Environmental notes

* Port 8123 remains occupied by an unrelated process (recorded in S7); S8A ran
  no server, so this did not arise.
* No system-level dependency is missing; the project venv provided everything.
  No dependency was added — the validation engine is dependency-free Python.
