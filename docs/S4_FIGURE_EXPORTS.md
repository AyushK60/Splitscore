# S4 figure exports (F22 preliminary)

## Formats

Every chart in the Visual Explorer carries an **Export** group with:

- **SVG** — a standalone serialization of the *live* figure: the geometry on
  screen at the moment of export (visible axes, committed brushes, current
  selection), never a cached or empty container. On export the builder:
  1. clones the live SVG and bakes computed styles into inline attributes —
     `var(--rs-*)` tokens resolve to literal colours, because a serialized
     SVG leaves the app's stylesheets behind (verified: the file decodes as
     an image outside the app);
  2. adds a print-safe paper background rect;
  3. appends a caption block: title, settings, counts, the active-selection
     sentence, dataset name + sha256 prefix + row count + app version +
     figure id + UTC timestamp, then any chart-specific notes (sampling
     description, policy statements).
- **PNG** — the same standalone SVG rasterised at 2× on a canvas
  (print-readable; the PC export measured 674 KB at 1440×~600 @2×).
- **JSON manifest** — full provenance:
  ```json
  {
    "figure_schema_version": "1.0.0",
    "figure_id": "parallel-coordinates",
    "generated_at_utc": "…",
    "application": { "name": "SplitScope", "version": "…" },
    "title": "…", "settings": "…", "counts": "…",
    "sampling": "Systematic grid sample: every 9th row of 10,000 …",
    "caption": ["…line per caption row…"],
    "dataset": { "dataset_id": "…", "name": "…", "sha256": "<64 hex>",
                 "row_count": 10000, "column_count": 7, "source": "upload" },
    "active_selection": { "predicates": […], "total_selected": 2622,
                          "population": 10000, "ids_truncated": false },
    "privacy": { "raw_rows_embedded": false,
                 "note": "The manifest references the in-memory dataset; it carries no cell values." }
  }
  ```

## Honesty rules enforced

- Exports reflect the **currently rendered state** — `getSvg()` returns the
  live DOM node; filters, brushes and selection are baked into both pixels
  and caption.
- Captions state the render sample ("N of M rows drawn (every k-th row)")
  and the exact active selection (predicate text + counts).
- No raw records are exported by default: charts contain aggregates or the
  already-rendered sample; manifests embed no cell values at all. Row-level
  values remain in the on-screen inspector (local-only, as ever).
- The scatter matrix is **JSON-only**: its panels are many small SVGs, and
  rather than compose a dubious mega-figure the UI says "open a pair in the
  focus scatter for SVG/PNG".

## Verification evidence

`frontend/scripts/capture-s4-exports.mjs` downloads the real files in a real
browser and inspects their content (15 checks, all passing): SVG contains
axis geometry, polylines of real data and the caption; PNG is a real raster
> 20 KB; the manifest carries the 64-hex fingerprint, the predicate list,
exact counts, and `raw_rows_embedded: false`; the SVG decodes standalone.
Sample outputs are committed at `docs/screenshots/s4/exports/`.

## Later F22 work (not claimed here)

Table exports (CSV/XLSX/TeX), DPI-controlled print dimensions, GraphML/DOT
for DAGs (S7), and dossier integration (S10) remain open.
