# Windows launcher

The `.cmd` files in the repository root are thin wrappers around
`scripts/launcher/*.ps1`. They need no admin rights and work from any clone
location, including paths with spaces.

| File | Purpose |
|------|---------|
| `Setup-SplitScope.cmd` | One-time setup: checks Python 3.11 and Node 20.18+, creates `.venv`, installs pinned dependencies, builds the frontend, adds a desktop shortcut. Safe to re-run. |
| `Start-SplitScope.cmd` | Starts the server (or reuses a running one) and opens the browser. |
| `Stop-SplitScope.cmd` | Stops only the server this launcher started. |
| `Status-SplitScope.cmd` | Reports whether the server is running, the URL, build freshness and log location. |
| `Install-Desktop-Shortcut.cmd` | Creates the desktop shortcut for `Start-SplitScope.cmd`. |

## Start

1. Checks that `.venv\Scripts\python.exe` and `backend\app\main.py` exist.
2. Probes the configured port (default `127.0.0.1:8000`, from `SPLITSCOPE_HOST`
   and `SPLITSCOPE_PORT`) with `GET /api/health`. If SplitScope answers, it is
   reused. If another program holds the port, the launcher stops with an error.
3. Rebuilds the frontend only if `frontend/dist` is missing or older than the sources.
4. Starts the backend detached, with logs in `.launcher/logs/`.
5. Waits up to 120 s (`SPLITSCOPE_STARTUP_TIMEOUT`) for the health check, then
   opens the browser once. On failure it prints the log tail and cleans up.

`Start-SplitScope.cmd -AppWindow` opens an Edge app-mode window instead of the
default browser.

## Stop

Start records the PID, executable and creation time of the processes it
launches in `.launcher/state/server.json`. Stop ends a process only if it still
matches that record and its command line is `-m app.main`. It never kills by
name or port, leaves manually started servers running, and discards stale records.

## Limitations

* Windows only.
* One server instance per project.
* Build staleness is judged by file timestamps, so a checkout of an older tree
  can look up to date. Run `npm run build` to force a rebuild.
