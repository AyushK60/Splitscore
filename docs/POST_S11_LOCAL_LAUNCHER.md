# Post-S11 Local Launcher — One-Click Desktop Launch for SplitScope V2

**Stage:** Post-S11 convenience layer (no application code touched)
**Scope:** Windows desktop launcher, safe server management, first-time setup
**Related commit:** see `git log` — committed separately from the S11 release line.

This stage adds a double-click launcher so SplitScope V2 can be started and
stopped without opening terminals. It changes **nothing** inside `backend/` or
`frontend/src/`; the S11 release behavior is untouched.

---

## Files

At the repository root (all are thin wrappers; all logic lives in
`scripts/launcher/*.ps1`):

| File | Purpose |
| --- | --- |
| `Setup-SplitScope.cmd` | One-time first install (see below). Safe to re-run. |
| `Start-SplitScope.cmd` | Start (or reuse) the app and open it in the browser. |
| `Stop-SplitScope.cmd` | Stop only the server this launcher started. |
| `Status-SplitScope.cmd` | Plain-language status report and next-step guidance. |
| `Install-Desktop-Shortcut.cmd` | Create the **SplitScope V2** desktop shortcut. |
| `scripts/launcher/Common.ps1` | Shared helpers (health check, identity gates, build staleness). |
| `scripts/launcher/Start-SplitScope.ps1` | Start logic. |
| `scripts/launcher/Stop-SplitScope.ps1` | Safe-stop logic. |
| `scripts/launcher/Status-SplitScope.ps1` | Status logic. |
| `scripts/launcher/Setup-SplitScope.ps1` | First-install logic. |
| `scripts/launcher/Install-DesktopShortcut.ps1` | Shortcut logic. |

Runtime state and server logs are written to `.launcher/` (gitignored):
`.launcher/state/server.json` (ownership record) and `.launcher/logs/`
(`server-<timestamp>.log` / `.err.log`, newest 20 kept).

---

## First-time setup (a new computer, straight from a clone)

1. Install **Python 3.11** and **Node.js ≥ 20.18** (nothing else is required;
   no admin rights, no Docker).
2. Double-click `Setup-SplitScope.cmd`. It:
   - checks Python 3.11 and Node/npm, with clear errors if missing;
   - creates `.venv` and installs the pinned `backend/requirements.txt`;
   - installs frontend dependencies from `package-lock.json` (`npm ci`);
   - builds the frontend (`npm run build` → `frontend/dist`);
   - creates the desktop shortcut.
3. From then on: double-click the **SplitScope V2** desktop shortcut.

Nothing is hardcoded to any install path — everything is derived from the
script location, so any clone location works (paths with spaces are fine).

## How starting works

1. Locates the project root from the script location.
2. Verifies `.venv\Scripts\python.exe` and `backend\app\main.py`.
3. Probes the configured port (default `127.0.0.1:8000`, honors
   `SPLITSCOPE_HOST` / `SPLITSCOPE_PORT`) with an **identity-aware** health
   check (`GET /api/health` must answer `app_name == "SplitScope"`):
   - SplitScope already healthy → reuse it, open the browser, start nothing.
   - Port held by a different application → refuse with a clear message;
     the other app is never stopped and its page is never opened.
4. Rebuilds the frontend only when `frontend/dist` is missing or older than
   the frontend sources.
5. Launches the backend detached (hidden window, logs redirected to
   `.launcher/logs/`), so closing the launcher window does not stop the app.
   Closing the browser does not stop the server either — that is what the
   Stop shortcut is for.
6. Waits for readiness with a **bounded** timeout (120 s, override with
   `SPLITSCOPE_STARTUP_TIMEOUT`), then opens the browser exactly once.
   On failure it explains what happened, shows the log tail, and cleans up
   the process it just started.

## How stopping works (safety rules)

`Stop-SplitScope.cmd` stops **only** processes this launcher started:

- It never kills by process name and never by port.
- The start writes an ownership record (`.launcher/state/server.json`) with
  the PID, executable path, and creation time of the venv `python.exe`
  redirector **and** of the actual listening server child it spawns.
- A process is stopped only when the live process matches its record on
  executable, creation time, and command line (`-m app.main`).
- Stale records (recorded process gone) are cleaned up, never acted on.
- If SplitScope is running but was **not** started by the launcher (e.g.
  `python -m app.main` in a terminal), Stop says so and leaves it running.
- A foreign application on port 8000 is never touched.

## Status

`Status-SplitScope.cmd` reports: running/stopped/foreign-port state, the local
URL, launcher-owned process status, frontend build freshness, log location,
and a suggested next step — in plain language.

## Desktop shortcut

`Install-Desktop-Shortcut.cmd` creates **SplitScope V2.lnk** on the desktop
(resolving OneDrive-redirected desktops correctly) pointing at
`Start-SplitScope.cmd`, working directory = project root, standard Windows
icon, no admin rights, no auto-start, and it never touches other shortcuts.

## Optional standalone window

`Start-SplitScope.cmd -AppWindow` opens SplitScope in a Microsoft Edge
"app-mode" window (no Electron/Tauri introduced). Without Edge — or without
the flag — the default browser is used, which always remains the primary
workflow.

## Verified on Windows 11 (real runs)

| # | Scenario | Result |
| --- | --- | --- |
| 1 | First start (server launched, readiness check, browser opened once) | PASS |
| 2 | Second start while running (reuse, no duplicate) | PASS |
| 3 | Stop (redirector + real server child terminated, health goes down) | PASS |
| 4 | Restart after stop | PASS |
| 5 | Start with an existing up-to-date production build (no rebuild) | PASS |
| 6 | Start with missing `frontend/dist` (automatic `npm run build`) | PASS |
| 7 | Missing Python venv (isolated clone without `.venv`) — clear setup guidance | PASS |
| 8 | Missing Node/npm while a rebuild is required — clear error, nothing started | PASS |
| 9 | Port 8000 held by unrelated software — Start refuses, Stop leaves it alone | PASS |
| 10 | Tampered/stale ownership record — Stop refuses, unrelated process untouched; Start reports "not launcher-managed" | PASS |
| 11 | Server that exits immediately (unbindable host) — clean failure, log tail, state cleaned up | PASS |
| 12 | Browser opens only after the identity-aware readiness check succeeds | PASS |
| 13 | Desktop shortcut created and verified (target, working dir, icon) | PASS |
| 14 | Project path with a space (`E:\Splitscore V2`) used throughout | PASS |
| 15 | Pre-existing unrelated Python/uvicorn processes (including a manually started SplitScope) survived all tests | PASS |
| — | Full backend test suite re-run after launcher changes | PASS (620 passed) |
| — | Setup re-run idempotency | PASS |

Not verified on real hardware in this environment: double-clicking the .lnk
itself under Explorer (functionally identical to running
`Start-SplitScope.cmd`, which was tested), and a full 120 s readiness timeout
(the bounded-loop and immediate-exit failure branches were exercised
directly; the timeout constant is configurable via
`SPLITSCOPE_STARTUP_TIMEOUT`).

## Limitations

- Windows-only (by design; the app itself remains cross-platform).
- The launcher manages one server instance per project (single-user local app).
- If the ownership record is deleted while the launcher's server runs, Stop
  will report the server as not launcher-managed rather than stop it.
- The optional app window uses Edge's app mode; other browsers' standalone
  modes were not scripted.
- Frontend-source staleness detection compares file timestamps; a source
  change with an unchanged mtime (e.g. `git checkout` of an older tree) can
  produce a false "up to date". Rebuild with `npm run build` to force.
