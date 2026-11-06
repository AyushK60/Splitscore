# S10-A — Research Run History & Reproducibility

**Status: COMPLETE.** Commit `28a6a7b`.

## The Research History interface

`GET /api/datasets/{dataset_id}/history` returns one typed entry per stored
run (newest first), covering every analysis kind the platform stores:

- `leakage_audit`, `split_comparison`, `statistical_model`,
  `prediction_model` (pre-S10 run kinds);
- `estimation`, `estimation_comparison`, `subgroups`, `robustness`,
  `what_if` (S9A/S9C run kinds).

Each entry records: run id, kind and analysis kind, label, wall-clock
timestamp when the payload carries one (`created_at_utc`/`generated_at_utc`)
plus the store's age, dataset identity with the **recorded** fingerprint,
graph identity and fingerprint for estimation runs, a parameters digest per
kind (estimators, adjustment set, subgroup definition, experiment
parameters, scenario profile, model formula…), staleness state with reasons,
and the reproducibility block (resolved seed, cross-fitting, uncertainty,
software versions) where the kind captures one.

## Honesty rules

1. **Never invented.** A field the run did not record is `"not_recorded"`
   (or `null` with a reason). Non-estimation manifests state explicitly that
   their kind predates structured reproducibility capture.
2. **Staleness re-check.** Dataset fingerprint mismatches, deleted graphs
   and structurally edited graphs mark the entry stale with spelled-out
   reasons. (Audit/comparison/model kinds record dataset fingerprints;
   the check applies to them too.)
3. **Expired = gone.** Runs evicted by the LRU or TTL simply do not appear;
   the storage note says so. History is a projection — it stores nothing.
4. **Study gap stated.** Studies are not linked to stored runs; every entry
   carries `study_id: null` with an explicit note that this is a current
   storage limitation, not a missing export.

## The portable reproducibility manifest

`GET /api/datasets/{id}/history/{run_id}/manifest` returns a versioned
(`manifest_schema_version: 1.0.0`), **metadata-only** JSON: run identity,
dataset identity (with `dataset_matches_run`), graph identity, analysis
definition, cohort accounting, reproducibility block (treatment mapping,
cohort request, cross-fitting, uncertainty, truncation, software versions,
limits), and an integrity block — `sha256` over the canonical JSON (sorted
keys, compact separators, no NaN) of the manifest without the integrity
block. The canonicalisation contract is verified in tests by recomputing the
hash independently.

The manifest states plainly: reproduction additionally requires the original
dataset (by fingerprint) and a compatible software environment. No results
and no dataset content are embedded. The frontend History stage downloads it
as `splitscope_manifest_<kind>_<run>.json`.

## Privacy posture

Unchanged from the platform's local-first rules: nothing leaves the process
except explicit user downloads; manifests contain no rows, no results and no
raw bytes — only fingerprints and configuration.
