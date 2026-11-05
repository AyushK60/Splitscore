# S8B visual verification

The Causal Lab was judged against the S7 visual identity and the S8B brief's
acceptance criteria: readable nodes, unobscured labels, clear directional
arrows, immediately understandable selection, effective use of canvas space,
predictable inspectors, and membership in the established paper/ink/teal/copper
design language — a scientific product, not a default React Flow prototype.

## Screenshots

All captured by the automated journey `frontend/e2e/s8-causal-lab.spec.ts`
(`animations: 'disabled'`), so every image is reproducible:

| File | Content | Viewport |
|---|---|---|
| `docs/screenshots/s8/s8_empty_lab.png` | Empty Causal Lab: toolbar, rail, teaching-example empty state | 1440 × 900 |
| `docs/screenshots/s8/s8_populated_dag.png` | Three-node DAG, two directed edges, graph-settings inspector with assumption registry | 1440 × 900 |
| `docs/screenshots/s8/s8_validation_pass.png` | "Structurally valid DAG · 3 warnings" chip and warnings panel | 1440 × 900 |
| `docs/screenshots/s8/s8_node_inspector.png` | Node inspector with structure-derived facts note | 1440 × 900 |
| `docs/screenshots/s8/s8_validation_rejected.png` | Backend-rejected cycle: alert, blocking error named, draft intact | 1440 × 900 |
| `docs/screenshots/s8/s8_tablet_768.png` | Three-node DAG fitted, rail retained | 768 × 1024 |
| `docs/screenshots/s8/s8_tablet_inspector.png` | Inspector overlays the canvas at tablet width | 768 × 1024 |
| `docs/screenshots/s8/s8_mobile_390.png` | Toolbar wraps, rail overlays as a drawer, no horizontal overflow | 390 × 844 |

## Findings from the inspection pass

Each item below was **observed in a screenshot, fixed, and re-verified with a
fresh capture** (details in `S8B_IMPLEMENTATION.md` §5):

1. Render loop (React #185) crashed the workspace after the first node — fixed
   by moving selection out of React Flow.
2. Edges did not render at all (missing handles) — fixed.
3. Canvas measured 0 px tall, making the graph invisible — fixed.
4. Nodes were stranded off-canvas after incremental adds (premature fitView,
   then a maxZoom fit) — fixed with a debounced, zoom-capped refit; verified in
   the populated, validation and tablet captures where all three nodes fit.
5. Edges rendered as thick error-red ribbons (warnings marked as errors; a CSS
   selector also hit the invisible 22 px interaction path) — fixed; edges are
   now thin ink strokes with copper selection, visible in every capture.
6. **Pre-existing, all views:** at phone widths the context band consumed
   ~860 px of height, pushing every workspace below the fold (visible as the
   blank first screen in the first mobile capture) — fixed in `app.css`;
   the final mobile capture shows the toolbar, rail and canvas within one
   screen.

## Remaining accepted limitations

* The auto-fit zoom floor (`minZoom: 0.55`) means a wide graph at tablet width
  may extend slightly past the right edge until the user pans — deliberate, so
  node text never shrinks to unreadable sizes.
* The minimap appears only above 10 nodes, so the teaching examples show
  none — by design.
* Screenshot evidence covers Chromium (the project's supported browser).
