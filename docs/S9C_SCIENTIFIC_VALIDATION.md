# S9C — Scientific validation

**Rule of the house:** no expectation comes from the code under test. Known
answers come from the data-generating process written beside each test;
uncertainty arithmetic is pinned against independent closed-form formulas; the
what-if service is pinned against the already-verified S9A engine. Finite-sample
recovery tolerances are ~2 sampling standard errors, never exact equality.

## Subgroup effects (`backend/tests/test_s9c_subgroups.py`, 16 tests)

| # | Case | Verification |
|---|---|---|
| 1 | Constant effect across groups | Both subgroup ATEs ≈ 1.2 within tolerance |
| 2 | Heterogeneous effects (1.0 / 2.5) | Each subgroup recovers its own generating effect |
| 3 | No effect in either group | Both estimates ≈ 0 |
| 4 | Confounded assignment | Adjusted subgroup estimate recovers the truth; the naive within-group difference does not |
| 5 | Overall ↔ subgroup identity | `mean(ψ) = Σ (n_g/n)·ATE_g` exact to 1e-9 |
| 6 | Subgroup SE formula | Reported SE equals `sd(ψ|g)/√n_g` recomputed independently to 1e-12 |
| 7 | Contrast SE | Equals `√(var_a/n_a + var_b/n_b)` exactly; contrast equals the estimate difference |
| 8 | Post-treatment subgroup variable | Refused ("descendant of the treatment") |
| 9 | Insufficient treated rows in a subgroup | `unavailable` with reason; no estimate fabricated |
| 10 | Missing subgroup values | Excluded, counted, cohort accounting reconciles exactly |
| 11 | Unknown requested level | Refused |
| 12 | Numeric quartile binning | 4 groups, 5 disclosed edges, recovery within tolerance |
| 13 | Extreme within-group overlap | Fragility warning present |
| 14 | Reproducibility | Same seed → byte-identical groups and overall estimate |
| 15 | Interval coverage | CI brackets the true effect |
| 16 | Intent labelling | exploratory/prespecified echoed in the notes |

## Robustness (`backend/tests/test_s9c_robustness.py`, 12 tests)

1–4. **Subsampling:** reproducible from the recorded seed; original estimate
inside the subsample distribution's bulk; bounds enforced (reps, fraction);
failures recorded per repetition with the successful-repetition count
reconciling exactly (Hájek undefined when a subsample misses an arm).
5–7. **Placebo:** reproducible; placebo distribution centred near zero for a
randomised no-effect DGP; **original estimate equals the verified S9A engine's
estimate to 1e-12**.
8–12. **Sensitivity:** the (γ=0, κ=0) null cell sits within 0.15 of the
original; grid reproducible; the "hypothetical scenario, not a bound" caveat
ships verbatim; prevalence bounds enforced; unknown experiments refused.

## What-if (`backend/tests/test_s9c_whatif.py`, 10 tests)

1. Cohort contrast **equals the engine's regression-adjustment ATE to 1e-12**.
2. Linear-model profile contrast equals the cohort contrast (no interactions).
3. Deterministic.
4. Both arms and the contrast reported consistently.
5. No `ci_lower`/`ci_upper`/`standard_error` anywhere in a scenario payload.
6. Out-of-support numeric profile → named extrapolation warning.
7. Unobserved categorical level → refused.
8. Non-adjustment (incl. post-treatment) field → refused.
9. Unset fields disclosed as cohort median/mode, never silent.
10. Non-numeric value on a numeric field → refused.

## API integration (`backend/tests/test_s9c_research_api.py`, 7 tests)

Driven through the real FastAPI routes on the bundled `causal_effect` demo:
subgroups run/store/retrieve via the existing estimation-run history;
treatment-descendant refusal; backdoor-invalid adjustment refusal; all three
robustness experiments store; out-of-bounds reps → 422; what-if scenario stores,
is retrievable non-stale, and flips to **stale** after a structural graph edit;
runs belong to their dataset (cross-dataset fetch → 404).

## Totals

45 new backend tests; full suite **581 passed**; synthetic leakage oracle
**41/41 cases, 61/61 checks, exit 0** (no detector or audit behaviour changed).
Frontend: 31 new unit/component tests; **236 passing** in total. No existing
assertion was loosened; the only S9B-file touched was a behaviour-preserving
extraction of `describeError` into `src/estimation/estimationErrors.ts` (S9B
suite unchanged and passing).
