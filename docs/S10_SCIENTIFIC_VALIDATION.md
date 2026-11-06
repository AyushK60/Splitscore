# S10 Scientific Validation

**Status: COMPLETE.** Every S10 claim below is pinned by an executable test;
none is taken from the implementation on trust.

## Research history and manifests (S10-A)

| Claim | Test |
| --- | --- |
| History indexes runs across audit/model/estimation kinds with correct analysis kinds, graph identity, recorded seed and dataset fingerprint | `test_history_indexes_runs_across_kinds_with_metadata` |
| History is dataset-scoped; foreign datasets see nothing; unknown datasets 410 | `test_history_is_dataset_scoped_and_refuses_foreign_datasets` |
| A dataset-content change stales every run that recorded a fingerprint, with reasons | `test_history_marks_run_stale_when_dataset_content_changed` |
| Manifests are metadata-only and their canonical-JSON hash recomputes independently | `test_manifest_is_metadata_only_with_verifiable_integrity_hash` |
| Cross-dataset and unknown runs are refused | `test_manifest_refuses_cross_dataset_and_missing_runs` |
| Non-estimation manifests state the reproducibility gap explicitly | `test_non_estimation_manifest_states_reproducibility_gap_honestly` |
| The frontend renders kinds, staleness banners, filters, empty states and exports the manifest | `tests/HistoryView.test.tsx` (4 tests) |

## Integrated dossier (S10-B)

| Claim | Test |
| --- | --- |
| Schema 1.1.0 is additive: v1 section ids, order and semantics unchanged | `test_schema_is_additive_and_v1_sections_keep_their_ids` |
| Missing estimation runs render unavailable with reasons; the methodology says "Not evaluated" | `test_causal_sections_are_unavailable_without_estimation_runs` |
| The dossier estimate **equals** the stored run's estimate; identification verdicts and graph assumptions carry verbatim | `test_estimation_values_in_dossier_equal_the_stored_run` |
| Subgroup groups/estimates match the stored run; sensitivity "not a bound" and what-if counterfactual boundaries survive verbatim | `test_subgroup_and_robustness_and_what_if_sections_track_their_runs` |
| Technical presentation reports cross-fitting and the backdoor gate | `test_methodology_technical_level_reports_cross_fitting_details` |
| A run computed against changed dataset bytes is refused (422) | `test_dossier_refuses_a_stale_estimation_run` |
| Cross-dataset runs are refused (404) | `test_dossier_refuses_a_cross_dataset_estimation_run` |
| Mismatched analysis kinds are refused, never re-labelled | `test_mismatched_estimation_kind_is_refused_not_relabelled` |
| JSON is stable; HTML renders all new sections; `<assumption>` in user text is escaped, not injected | `test_dossier_json_and_html_exports_are_stable_and_escaped` |
| Preview renders new sections incl. failed estimators, unavailable subgroups, caveats | `tests/ReportPreview.test.tsx` S10-B block (5 tests) |

## Publication figures (S10-C)

| Claim | Test |
| --- | --- |
| The DAG figure is valid XML with every node/edge, role labels and the assumption caveat | `test_figure_is_valid_xml_with_all_nodes_and_edges` |
| It is deterministic; layout-only edits do not change the scientific fingerprint | `test_figure_is_deterministic_and_ignores_layout_for_fingerprint` |
| Missing graphs 404; unobserved nodes render dashed; layout-less graphs still render | remaining `test_s10_figure.py` tests |
| The complete workflow (audit → identification-gated estimation → three research experiments → integrated dossier → JSON download; history → manifest → figure) runs against the real backend | `e2e/s10-dossier.spec.ts` (2 journeys) |

## Cross-stage invariants

- No S10 path bypasses the S8C identification gate: dossier sources are
  stored runs, which were gated at computation time; the gate verdicts are
  reported, not re-derived.
- No dataset content leaves the process: dossier JSON/HTML embed bounded
  examples only (`raw_data_embedded: false`), manifests embed none.
- No cross-dataset mixing anywhere: history scoping, manifest ownership and
  dossier sources all refuse foreign or stale inputs.
