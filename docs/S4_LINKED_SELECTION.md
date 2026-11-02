# S4 linked selection — one engine, immutable row ids

## The five distinct populations (never conflated)

| Term | Meaning | Where it lives |
| --- | --- | --- |
| **Dataset population** | every row of the loaded dataset (`row_count`) | store; shown in the header and every caption |
| **Applied global filters** | the active brush predicates (a *definition*, not an id list) | `ExploreState.selection.predicates` |
| **Rendered sample** | the rows a point-level chart draws (systematic grid of the *filtered* population) | backend `explore/series` response |
| **Active brushed selection** | rows passing the predicates — exact count + capped id list | backend `explore/selection` response |
| **Highlighted individual row** | one id under the cursor (inspector hover) | `ExploreState.highlightedId` |

Every view labels which of these it is showing. Counts shown to the user are
the exact selection count over the whole population; the id list used for
highlighting is capped at 20,000 and the UI states when truncation applies.

## How a brush becomes a selection

1. A drag on a parallel-coordinates axis (or a rectangle on the scatter)
   produces **predicates over real data units**: `{column, kind:'range',
   min, max}` (or `{column, kind:'values', values:[…]}` for categorical
   brushes).
2. `applyPredicates` debounces 220 ms, then `POST /explore/selection`.
3. The backend evaluates predicates **server-side over the full dataset**
   (`evaluate_selection` → numpy masks) and returns
   `{total_selected, row_ids (capped), ids_truncated}`.
4. `ExploreState.selection` is replaced atomically. Every chart re-renders
   from that single object; the row inspector fetches actual row text via
   `POST /explore/rows` by immutable id.

**Combination rule (documented in the backend and in export captions):**
predicates on the same column **union**; predicates on different columns
**intersect**. Two ranges on one axis = either range; a third brush on
another axis = AND.

## Coordination guarantees

- **One authoritative state.** Charts never keep private filters; brushing
  anywhere calls the same `applyPredicates`. The PC brush, the scatter box
  brush, the distribution overlay, the missingness percentages and the row
  inspector all read one object, so they cannot disagree.
- **Joins by immutable row id.** `row-000001…` ids are minted at load time
  and stable for the dataset's lifetime. No view joins on display indices.
- **Selection survives plot changes.** Switching tabs (PC → correlations →
  distributions → …) keeps the predicates and the highlighted cohort; the
  E2E journey asserts exactly this round trip.
- **Selection dies with the dataset.** When `dataset_id` changes, the
  provider resets schema, colour choice and selection before the new
  schema arrives — a brush computed for one dataset can never highlight
  rows of another.
- **Clearing is global.** "Clear selection" resets to the empty predicate
  list; the population readout, charts and inspector return to the full
  dataset. The underlying dataset is never modified by any selection.
- **Exact overlays, not client-side guesses.** The distribution and
  missingness endpoints accept the active predicates and return the
  selected cohort's counts on the same bins (`selection` /
  `population_counts`), computed server-side — the UI never approximates a
  statistic the backend can compute exactly.

## Exports retain selection information

Figure manifests and SVG caption blocks carry
`Active selection: <predicate description> (N of M rows)` plus the dataset
sha256, so an exported figure states exactly which cohort it depicts.
