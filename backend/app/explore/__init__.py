"""S4 Scientific Visual Explorer — bounded, deterministic data services for the
exploration workspace.

The explorer's contract with the rest of SplitScope:

* **Immutable row identity.** Every observation a chart renders is keyed by the
  dataset's ``row_ids`` (minted at load time, stable for the dataset's
  lifetime). Charts never join on display positions.
* **Population ≠ sample.** Aggregate statistics (correlations, histograms,
  missingness) are computed on the full requested population server-side. Only
  point-level *rendering* data is sampled, and every sampled payload states the
  method, the stride and both counts.
* **Undefined stays undefined.** A correlation of a constant column, a pair
  with too few complete observations, an all-missing histogram — all come back
  as ``null`` with a warning code, never as a fabricated zero.
* **Local only.** Nothing here writes to disk; inputs come from the store.
"""
