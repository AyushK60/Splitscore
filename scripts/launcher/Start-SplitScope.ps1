# Start-SplitScope.ps1 - one-click start for SplitScope V2.
#
# Behaviour:
#   1. Locate the project root relative to this script (no hardcoded paths).
#   2. Verify the Python virtual environment and backend entry point exist.
#   3. Probe the port with an identity-aware health check:
#        - SplitScope already healthy  -> reuse it (no duplicate processes)
#        - port held by another app    -> refuse, never open its page
#   4. Rebuild the frontend only when the production build is missing/stale.
#   5. Launch the backend detached from this window and record its identity
#      (PID, executable, creation time) so Stop can prove ownership later.
#   6. Poll /api/health with a bounded timeout, then open the browser once.
#   7. On any failure: explain it, point at the log, and clean up our child.

param(
    # Optional: open SplitScope in a standalone Edge app window instead of a
    # regular browser tab. Falls back to the default browser when Edge is
    # absent. The default-browser workflow always remains available.
    [switch]$AppWindow
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')

$Root = Get-ProjectRoot
$ServerHost = Get-ServerHost
$Port = Get-ServerPort
$ProbeHost = Get-LoopbackAddress $ServerHost
$Url = Get-ServerUrl

# Startup timeout (seconds). Bounded on purpose - never an infinite loop.
$TimeoutSeconds = 120
if ($env:SPLITSCOPE_STARTUP_TIMEOUT) {
    try { $TimeoutSeconds = [int]$env:SPLITSCOPE_STARTUP_TIMEOUT } catch {}
}

Write-Rule
Write-Info ' SplitScope V2 - starting'
Write-Rule

# --- 1. Virtual environment and backend entry point -------------------------

$venvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Fail 'SplitScope is not set up yet on this computer.'
    Write-Info ''
    Write-Info 'The Python environment was not found (.venv). Run:'
    Write-Info '    Setup-SplitScope.cmd'
    Write-Info 'once, and it will install everything needed.'
    exit 1
}

$backendMain = Join-Path $Root 'backend\app\main.py'
if (-not (Test-Path $backendMain)) {
    Write-Fail 'The backend entry point (backend\app\main.py) was not found.'
    Write-Info 'This installation appears incomplete - please re-clone or restore the repository.'
    exit 1
}

# --- 2. Is a server already there? (identity-aware, never guesses) ----------

$health = Test-SplitScopeHealth -ServerHost $ServerHost -Port $Port

if ($health -eq 'occupied') {
    Write-Fail "Port $Port is in use by a different application."
    Write-Info ''
    Write-Info 'SplitScope was NOT started, and nothing was changed or stopped.'
    Write-Info 'Free the port (or set SPLITSCOPE_HOST / SPLITSCOPE_PORT), then try again.'
    exit 1
}

$state = Read-ServerState
$reuseNote = ''

if ($health -eq 'healthy') {
    Write-Ok "SplitScope is already running at $Url - reusing it (no duplicate started)."
    $reuseNote = 'Reused the healthy server that was already running.'
    if ($state -and (Test-ServerStateMatches -State $state).Valid) {
        $reuseNote += " Launcher-managed process: PID $($state.pid)."
    } else {
        $reuseNote += ' (Not launcher-managed; Stop-SplitScope will not touch it.)'
    }
} else {
    # --- 3. Frontend production build (rebuild only when needed) ------------

    $build = Test-FrontendBuildNeeded -Root $Root
    if ($build.Needed) {
        Write-Info "Building the frontend because $($build.Reason)..."
        $npm = Find-NpmCommand
        if (-not $npm) {
            Write-Fail 'The frontend needs building, but Node.js/npm was not found on this computer.'
            Write-Info ''
            Write-Info 'Install Node.js 20.18 or newer (https://nodejs.org), then try again.'
            exit 1
        }
        Push-Location (Join-Path $Root 'frontend')
        try {
            & $npm run build 2>&1 | ForEach-Object { Write-Host "  $_" }
            if ($LASTEXITCODE -ne 0) {
                Write-Fail 'The frontend build failed. Fix the error above (or restore frontend\dist) and try again.'
                exit 1
            }
        } finally {
            Pop-Location
        }
        Write-Ok 'Frontend build complete.'
    } else {
        Write-Info "Frontend: $($build.Reason)."
    }

    # --- 4. Launch the backend (detached, so closing this window is safe) ---

    $logDir = Get-LauncherLogDir
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
    $outLog = Join-Path $logDir "server-$stamp.log"
    $errLog = Join-Path $logDir "server-$stamp.err.log"

    Write-Info "Starting the SplitScope server on http://${ProbeHost}:$Port ..."
    try {
        $proc = Start-Process -FilePath $venvPython `
            -ArgumentList @('-m', 'app.main') `
            -WorkingDirectory (Join-Path $Root 'backend') `
            -WindowStyle Hidden `
            -RedirectStandardOutput $outLog `
            -RedirectStandardError $errLog `
            -PassThru
    } catch {
        Write-Fail "Could not start the SplitScope server process: $($_.Exception.Message)"
        exit 1
    }

    # Record ownership evidence for Stop-SplitScope (validated at stop time).
    $liveStart = $null
    try { $liveStart = $proc.StartTimeUtc } catch { try { $liveStart = $proc.StartTime.ToUniversalTime() } catch {} }
    $record = @{
        pid               = $proc.Id
        exe               = $venvPython
        creation_time_utc = if ($liveStart) { $liveStart.ToString('o') } else { (Get-Date).ToUniversalTime().ToString('o') }
        command_marker    = 'app.main'
        host              = $ServerHost
        port              = $Port
        started_utc       = (Get-Date).ToUniversalTime().ToString('o')
        launcher_version  = 2
    }
    Save-ServerState -State $record
    Invoke-LauncherLogRotation

    # --- 5. Bounded readiness check ----------------------------------------

    Write-Info 'Waiting for SplitScope to become ready...'
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $ready = $false
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) { break }
        if ((Test-SplitScopeHealth -ServerHost $ServerHost -Port $Port) -eq 'healthy') { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }

    if (-not $ready) {
        if ($proc.HasExited) {
            $exitCode = 'unknown'
            try { if ($null -ne $proc.ExitCode) { $exitCode = $proc.ExitCode } } catch {}
            Write-Fail "SplitScope exited immediately after starting (exit code $exitCode)."
            Remove-ServerState
        } else {
            Write-Fail "SplitScope did not become ready within $TimeoutSeconds seconds."
            Write-Info 'It is still starting up or failed to bind the port; stopping the launcher-started process.'
            try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
            Remove-ServerState
        }
        Show-LogTail -Path $errLog
        Show-LogTail -Path $outLog
        Write-Info ''
        Write-Info "Full server logs: $logDir"
        exit 1
    }

    $state = Read-ServerState
    $reuseNote = "Launcher-managed process: PID $($proc.Id)."
    # The venv python.exe is a redirector: the real server is its child.
    # Record the actual listener (with identity evidence) so Stop can prove
    # ownership even if the redirector itself is gone. Best effort: a failure
    # here must never turn a healthy start into an error.
    try {
        # Primary: the backend child of the process we launched (command-line
        # matched). The venv python.exe redirector spawns the real interpreter
        # as its child. Socket-based lookup is only a fallback because the
        # CIM provider does not reliably report uvicorn's listening socket.
        $child = Get-CimInstance -ClassName Win32_Process -Filter "ParentProcessId = $($proc.Id)" -ErrorAction Stop |
            Where-Object { $_.CommandLine -match 'app\.main' } | Select-Object -First 1
        $listenerPid = if ($child) { [int]$child.ProcessId } else { $null }
        if (-not $listenerPid) { $listenerPid = Get-ListenerPid -Port $Port }
        if ($listenerPid) {
            $listenerProc = Get-Process -Id $listenerPid -ErrorAction SilentlyContinue
            if ($listenerProc) {
                $listenerStart = $null
                try { $listenerStart = $listenerProc.StartTimeUtc } catch { try { $listenerStart = $listenerProc.StartTime.ToUniversalTime() } catch {} }
                $record.server_pid = $listenerPid
                $record.server_exe = $listenerProc.Path
                $record.server_creation_time_utc = if ($listenerStart) { $listenerStart.ToString('o') } else { $null }
                Save-ServerState -State $record
                $reuseNote = "Launcher-managed processes: PID $($proc.Id) (server PID $listenerPid)."
            }
        }
    } catch {
        Write-Info 'Note: the server child process could not be recorded; Stop will still find it via its parent.'
    }
    Write-Ok "SplitScope is ready at $Url"
}

# --- 6. Open the browser exactly once, after readiness ----------------------

if ($AppWindow) {
    $edgeCandidates = @(
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($edgeCandidates) {
        Start-Process -FilePath $edgeCandidates -ArgumentList "--app=$Url"
    } else {
        Write-Warn2 'Microsoft Edge was not found; opening the default browser instead.'
        Start-Process $Url
    }
} else {
    Start-Process $Url
}

Write-Info ''
Write-Ok "SplitScope V2 is open in your browser: $Url"
Write-Info $reuseNote
Write-Info 'To shut it down later, double-click Stop-SplitScope.cmd.'
Write-Rule
exit 0
