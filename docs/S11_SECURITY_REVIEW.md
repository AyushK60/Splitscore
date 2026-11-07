# S11 — Security & Privacy Review

**Date:** 2026-11-07 · Scope: the documented **local/private research-demo**
threat model. Nothing here claims production/internet-facing hardening —
deployment, authentication and HTTPS are explicitly out of scope for this
product (unchanged from previous stages).

## Areas re-audited on the S11 tree

- **Upload validation**: backend CSV/TXT parsing with byte limits (25 MB),
  binary-sniffing refusal and structured parse errors (`app/audit/io.py`) —
  re-read, unchanged; error-recovery journey passes.
- **Dataset isolation & expiry**: in-memory session store, SHA-256 dataset
  fingerprints, TTL eviction; no on-disk persistence of uploads (verified by
  restart behaviour documented in S10 and re-confirmed by design reading).
- **HTML report escaping**: `dossier_html.py` escapes every user-supplied
  value via `html.escape(..., quote=True)`; no external CSS/JS/fonts/images in
  the printable document. No path found where dataset content, graph names or
  manifest metadata reach the HTML unescaped.
- **CSV formula-injection protection**: `csv_export.py` prefixes `=`, `+`, `-`,
  `@`, tab, CR with `'` and documents the transformation in the file header and
  API note — unchanged and covered by backend tests.
- **Figure SVG**: publication figures are rendered from stored specs
  server-side; dataset strings are escaped in the SVG path (S10-C contract).
- **Logs**: no raw research datasets are logged; server log output during the
  S11 sessions contains only HTTP access lines.
- **No telemetry**: no external analytics or network calls beyond localhost —
  verified by reviewing the frontend API client surface (unchanged).

## S11-specific security posture

S11 changed no API, no backend code, and no export path. The frontend changes
(provider hoisting, lazy routes, CSS) do not alter input handling, download
construction or URL parsing. The hash router continues to accept only known
view ids (`isViewId`) — no injection surface.

## Remaining assumptions (documented, unchanged)

- The server binds localhost for the demo; it offers **no authentication** and
  must not be exposed to a public network as-is.
- Uploaded data lives in server memory for the session; anyone with local
  machine access can read it — inherent to the local-first design.
- Exports are downloaded through the browser; integrity of the user's machine
  is assumed.
