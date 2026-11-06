# S9C-A — Subgroup methodology

## Estimand and equation

For subgroup `g` defined by a pretreatment variable, the subgroup ATE is

    ATE_g = E[ ψ_i | i ∈ g ],      ψ_i = m̂1(X_i) − m̂0(X_i)
                                    + T_i (Y_i − m̂1(X_i))/ê(X_i)
                                    − (1 − T_i)(Y_i − m̂0(X_i))/(1 − ê(X_i)),

where `ψ` is the cross-fitted AIPW pseudo-outcome computed **once on the whole
analysis cohort** with out-of-fold nuisance predictions. This is the
group-specific estimating equation — the average of a per-row estimating
quantity over the subgroup's own rows — not a filtered overall model prediction
re-labelled as heterogeneity. It is doubly robust under the identification
assumptions (verified by the same S8C gate) plus within-group positivity.

Because `ψ` is a per-row quantity, each subgroup's uncertainty is its own
influence value:

    SE(ATE_g) = sd(ψ | g) / √n_g,        CI = ATE_g ± z_{level} · SE,

and a between-group contrast `ATE_a − ATE_b` (disjoint groups) has the exact
influence-function variance

    var(ψ|a)/n_a + var(ψ|b)/n_b.

Both formulas are pinned to 1e-12 against independent recomputation in
`test_s9c_subgroups.py`.

## Provenance disclosure

Nuisance models are cross-fitted on the full cohort, not re-fitted inside each
subgroup. This is the standard DR subgroup construction and is valid under the
identification assumptions with within-group positivity; every payload carries
a `pseudo_outcome_provenance` note saying exactly this, and per-group
propensity summaries (per-arm fitted ranges, extreme-score counts) expose where
the correction is fragile. Subgroups with any fitted score outside [0.01, 0.99]
carry a strong fragility warning; outside [0.05, 0.95], a weak-overlap warning.

## Eligibility and honest states

- The subgroup node must be **observed, anchored to a column, not the
  treatment or outcome node, and not a descendant of the treatment** on the
  stored graph (`dag.descendants_of`); refusal names the descendant rule.
  A subgroup column that *is* an adjustment covariate is welcome — a measured
  confounder is exactly what one stratifies on.
- Categorical columns: observed levels, capped at 8 groups (client may select
  specific levels). Numeric columns: quantile binning (median/tercile/quartile)
  with de-duplicated disclosed edges; ties collapse the binning with a note.
- Rows with missing subgroup values are excluded from every subgroup and
  counted in `rows_excluded_missing`; they remain in the overall estimate.
  Missingness is never treated as a group.
- A subgroup with fewer than `MIN_ROWS_PER_ARM` (10) rows in either arm is
  reported `status: "unavailable"` with the reason. No estimate is fabricated.

## Interpretation guardrails

- The overall ATE from the same pseudo-outcome is reported next to the
  subgroups; the exact identity `mean(ψ) = Σ_g (n_g/n)·ATE_g` is tested.
- Intent is recorded (`exploratory` default / `prespecified`) and echoed in the
  UI; exploratory findings are framed as hypotheses.
- A multiple-comparisons note accompanies every result, and the UI instructs
  reading the *contrasts* (which carry their own uncertainty) rather than
  comparing interval overlap — the classic "one CI excludes zero, the other
  does not" fallacy is named in the payload.
