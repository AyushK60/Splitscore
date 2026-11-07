# Common helpers for the SplitScope V2 desktop launcher.
#
# Dot-sourced by the launcher scripts in this directory. PowerShell 5.1
# compatible (Windows PowerShell, the default on Windows 10/11).

Set-StrictMode -Version 2.0

$script:APP_NAME = 'SplitScope'

# ---------------------------------------------------------------------------
# Output helpers (kept deliberately short and readable for a nontechnical user)
# ---------------------------------------------------------------------------

function Write-Info { param([string]$Message) Write-Host $Message }
function Write-Ok    { param([string]$Message) Write-Host $Message -ForegroundColor Green }
function Write-Warn2 { param([string]$Message) Write-Host $Message -ForegroundColor Yellow }
function Write-Fail  { param([string]$Message) Write-Host $Message -ForegroundColor Red }
function Write-Rule  { Write-Host ('-' * 62) -ForegroundColor DarkGray }

# ---------------------------------------------------------------------------
# Paths (always derived from the script location; no hardcoded project path)
# ---------------------------------------------------------------------------

function Get-ProjectRoot {
    # scripts/launcher/Common.ps1 -> scripts -> project root
    return (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
}

function Get-LauncherDir   { Join-Path (Get-ProjectRoot) '.launcher' }
function Get-LauncherLogDir { Join-Path (Get-LauncherDir) 'logs' }
function Get-LauncherStateDir { Join-Path (Get-LauncherDir) 'state' }
function Get-ServerStateFile { Join-Path (Get-LauncherStateDir) 'server.json' }

# Server host/port, honouring the same environment variables the app uses.
function Get-ServerHost {
    if ($env:SPLITSCOPE_HOST) { return $env:SPLITSCOPE_HOST }
    return '127.0.0.1'
}
function Get-ServerPort {
    if ($env:SPLITSCOPE_PORT) { return [int]$env:SPLITSCOPE_PORT }
    return 8000
}

# Address to use for health checks / the browser. A wildcard bind cannot be
# opened in a browser, so fall back to loopback.
function Get-LoopbackAddress {
    param([string]$ServerHost)
    if ($ServerHost -in @('0.0.0.0', '::', '[::]')) { return '127.0.0.1' }
    return $ServerHost
}

function Get-ServerUrl {
    $hostAddr = Get-LoopbackAddress (Get-ServerHost)
    return "http://${hostAddr}:$(Get-ServerPort)"
}

# ---------------------------------------------------------------------------
# Identity-aware health check
# ---------------------------------------------------------------------------

<#
.SYNOPSIS
    Probes <host>:<port>/api/health and verifies the responder identifies
    itself as SplitScope. Returns one of:
      'healthy'  - SplitScope responded with its health payload
      'occupied' - the port answers, but it is NOT SplitScope
      'down'     - nothing is listening / connection refused
#>
function Test-SplitScopeHealth {
    param(
        [string]$ServerHost,
        [int]$Port
    )
    if (-not $ServerHost) { $ServerHost = Get-ServerHost }
    if (-not $Port) { $Port = Get-ServerPort }
    $targetHost = Get-LoopbackAddress $ServerHost

    # 1. Is anything listening at all? (fast, no HTTP)
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $connectTask = $tcp.ConnectAsync($targetHost, $Port)
        if (-not $connectTask.Wait(600)) { return 'down' }
    } catch {
        return 'down'
    } finally {
        $tcp.Close()
    }

    # 2. Something is listening - confirm it is SplitScope, not another app.
    try {
        $response = Invoke-WebRequest -Uri "http://${targetHost}:$Port/api/health" `
            -UseBasicParsing -TimeoutSec 5
        $payload = $response.Content | ConvertFrom-Json
        if ($payload.app_name -eq $script:APP_NAME -and $payload.status -eq 'ok') {
            return 'healthy'
        }
        return 'occupied'
    } catch {
        # Port open but not a well-formed SplitScope health endpoint.
        return 'occupied'
    }
}

# ---------------------------------------------------------------------------
# Launcher-owned process record
# ---------------------------------------------------------------------------

function Read-ServerState {
    $stateFile = Get-ServerStateFile
    if (-not (Test-Path $stateFile)) { return $null }
    try {
        return Get-Content $stateFile -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Save-ServerState {
    param([hashtable]$State)
    $stateDir = Get-LauncherStateDir
    if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir -Force | Out-Null }
    $State | ConvertTo-Json | Set-Content -Path (Get-ServerStateFile) -Encoding ASCII
}

function Remove-ServerState {
    $stateFile = Get-ServerStateFile
    if (Test-Path $stateFile) { Remove-Item $stateFile -Force -ErrorAction SilentlyContinue }
}

<#
.SYNOPSIS
    Validates a saved launcher process record against the live process.

.DESCRIPTION
    A record may only be used to stop a server when ALL of the following
    match the live process: PID exists, executable path, process creation
    time, and the command line contains the expected backend entry marker.
    Anything else is treated as a stale/tampered record and never killed.

.RETURNS
    @{ Valid = bool; Reason = string; Process = Process or $null }
#>
function Test-ServerStateMatches {
    param($State)

    if ($null -eq $State -or -not $State.pid) {
        return @{ Valid = $false; Reason = 'No launcher process record.'; Process = $null }
    }

    $proc = $null
    try { $proc = Get-Process -Id ([int]$State.pid) -ErrorAction Stop } catch {}

    if ($null -eq $proc) {
        return @{ Valid = $false; Reason = "Recorded process (PID $($State.pid)) no longer exists (stale record)."; Process = $null }
    }

    # Executable identity: recorded python.exe must match the live one.
    $recordedExe = [string]$State.exe
    $liveExe = ''
    try { $liveExe = $proc.Path } catch {}
    if ($liveExe -and $recordedExe) {
        if (-not [string]::Equals($liveExe, $recordedExe, [StringComparison]::OrdinalIgnoreCase)) {
            return @{ Valid = $false; Reason = "PID $($State.pid) is now a different executable ($liveExe)."; Process = $proc }
        }
    } elseif (-not $liveExe) {
        # Path unreadable - fall through to stronger creation-time + cmdline checks.
    }

    # Creation-time check (guards against PID reuse).
    $recordedStart = $null
    try { $recordedStart = [datetime]::Parse($State.creation_time_utc).ToUniversalTime() } catch {}
    if ($recordedStart) {
        $liveStart = $null
        try { $liveStart = $proc.StartTimeUtc } catch { try { $liveStart = $proc.StartTime.ToUniversalTime() } catch {} }
        if ($liveStart -and ([Math]::Abs(($liveStart - $recordedStart).TotalSeconds) -gt 5)) {
            return @{ Valid = $false; Reason = "PID $($State.pid) was created at a different time than recorded (likely PID reuse)."; Process = $proc }
        }
    }

    # Command-line check: the recorded process must be the backend entry point.
    try {
        $cimProc = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $($State.pid)" -ErrorAction Stop
        if ($cimProc -and $cimProc.CommandLine) {
            if ($cimProc.CommandLine -notmatch 'app\.main') {
                return @{ Valid = $false; Reason = "PID $($State.pid) is not running the SplitScope backend (command line mismatch)."; Process = $proc }
            }
        }
    } catch {
        # CIM unavailable / access denied: exe + creation-time checks above still hold.
    }

    return @{ Valid = $true; Reason = 'Record matches the live process.'; Process = $proc }
}

function Get-StateProp {
    param($State, [string]$Name)
    $prop = $State.PSObject.Properties[$Name]
    if ($prop) { return $prop.Value }
    return $null
}

# ---------------------------------------------------------------------------
# Port listener resolution (used to record the real serving process)
# ---------------------------------------------------------------------------

function Get-ListenerPid {
    param([int]$Port)
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        try {
            # Note: uvicorn's listening socket can be reported in a state other
            # than 'Listen' by the CIM provider, so filter on the client side.
            $conns = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop)
            $conn = $conns | Where-Object { $_.State -eq 'Listen' } | Select-Object -First 1
            if (-not $conn) { $conn = $conns | Select-Object -First 1 }
            if ($conn -and $conn.OwningProcess) { return [int]$conn.OwningProcess }
        } catch {}
        Start-Sleep -Milliseconds 800
    }
    return $null
}

<#
.SYNOPSIS
    Identity gate for a process we are about to stop. A process is only
    accepted when the command line contains the backend entry marker and
    (when known) the executable and creation time match the recorded values.
#>
function Test-ProcessIdentity {
    param(
        [int]$ProcessId,
        [string]$ExpectedExe,
        [string]$ExpectedCreationUtc
    )
    try { $proc = Get-Process -Id $ProcessId -ErrorAction Stop } catch {
        return @{ Valid = $false; Reason = 'Process is gone.'; Process = $null }
    }
    try {
        $cim = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        if ($cim -and $cim.CommandLine -and ($cim.CommandLine -notmatch 'app\.main')) {
            return @{ Valid = $false; Reason = "PID $ProcessId is not running the SplitScope backend."; Process = $proc }
        }
        # An unreadable command line (process already terminating) falls
        # through to the executable and creation-time checks below.
    } catch {
        return @{ Valid = $false; Reason = "Could not verify the command line of PID $ProcessId."; Process = $proc }
    }
    $liveExe = ''
    try { $liveExe = $proc.Path } catch {}
    if ($ExpectedExe -and $liveExe -and
        -not [string]::Equals($liveExe, $ExpectedExe, [StringComparison]::OrdinalIgnoreCase)) {
        return @{ Valid = $false; Reason = "PID $ProcessId is a different executable ($liveExe)."; Process = $proc }
    }
    if ($ExpectedCreationUtc) {
        $recorded = $null
        try { $recorded = [datetime]::Parse($ExpectedCreationUtc).ToUniversalTime() } catch {}
        if ($recorded) {
            $liveStart = $null
            try { $liveStart = $proc.StartTimeUtc } catch { try { $liveStart = $proc.StartTime.ToUniversalTime() } catch {} }
            if ($liveStart -and ([Math]::Abs(($liveStart - $recorded).TotalSeconds) -gt 5)) {
                return @{ Valid = $false; Reason = "PID $ProcessId was created at a different time than recorded (likely PID reuse)."; Process = $proc }
            }
        }
    }
    return @{ Valid = $true; Reason = 'Identity confirmed.'; Process = $proc }
}

# ---------------------------------------------------------------------------
# Frontend production build staleness
# ---------------------------------------------------------------------------

function Test-FrontendBuildNeeded {
    param([string]$Root)
    $distIndex = Join-Path $Root 'frontend\dist\index.html'
    if (-not (Test-Path $distIndex)) {
        return @{ Needed = $true; Reason = 'the production build is missing (frontend/dist)' }
    }
    $distTime = (Get-Item $distIndex).LastWriteTimeUtc

    $inputs = @()
    $srcDir = Join-Path $Root 'frontend\src'
    if (Test-Path $srcDir) { $inputs += @(Get-ChildItem $srcDir -Recurse -File) }
    foreach ($rel in @('frontend\index.html', 'frontend\package.json', 'frontend\package-lock.json', 'frontend\vite.config.ts', 'frontend\tsconfig.json', 'frontend\tsconfig.app.json')) {
        $p = Join-Path $Root $rel
        if (Test-Path $p) { $inputs += (Get-Item $p) }
    }

    $newest = $inputs | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if ($newest -and $newest.LastWriteTimeUtc -gt $distTime) {
        return @{ Needed = $true; Reason = "frontend source changed after the last build ('$($newest.Name)')" }
    }
    return @{ Needed = $false; Reason = 'production build is up to date' }
}

# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------

function Find-NpmCommand {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npm) { return $npm.Source }
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) { return $npm.Source }
    return $null
}

function Find-PythonLauncher {
    <# Returns a hashtable @{ Exe; Args } for a suitable Python (3.11
       preferred, matching the pinned backend dependencies), or $null. #>
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $ver = (& py -3.11 --version 2>$null)
        if ($ver -match 'Python 3\.11') { return @{ Exe = $py.Source; Args = @('-3.11') } }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $ver = (& $python.Source --version 2>$null)
        if ($ver -match 'Python 3\.11') { return @{ Exe = $python.Source; Args = @() } }
    }
    return $null
}

# ---------------------------------------------------------------------------
# Desktop shortcut (standard Windows shell COM; no admin rights required)
# ---------------------------------------------------------------------------

function New-SplitScopeDesktopShortcut {
    param([string]$Root)
    $desktop = [Environment]::GetFolderPath('Desktop')
    if (-not $desktop) { throw 'Could not resolve the desktop folder.' }
    $linkPath = Join-Path $desktop 'SplitScope V2.lnk'

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($linkPath)
    $shortcut.TargetPath = Join-Path $Root 'Start-SplitScope.cmd'
    $shortcut.WorkingDirectory = $Root
    $shortcut.Description = 'Start SplitScope V2 (local data-leakage auditor)'
    # Standard Windows icon (no custom brand icon exists in the project).
    $shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,13"
    $shortcut.Save()
    return $linkPath
}

# ---------------------------------------------------------------------------
# Launcher log housekeeping (keep the newest N server log pairs)
# ---------------------------------------------------------------------------

function Invoke-LauncherLogRotation {
    param([int]$Keep = 20)
    $logDir = Get-LauncherLogDir
    if (-not (Test-Path $logDir)) { return }
    $logs = @(Get-ChildItem $logDir -Filter 'server-*.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTimeUtc -Descending)
    if ($logs.Count -le $Keep) { return }
    $logs | Select-Object -Skip $Keep | ForEach-Object {
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        $errSibling = $_.FullName -replace '\.log$', '.err.log'
        if (Test-Path $errSibling) { Remove-Item $errSibling -Force -ErrorAction SilentlyContinue }
    }
}

function Show-LogTail {
    param([string]$Path, [int]$Lines = 15)
    if (-not (Test-Path $Path)) { return }
    Write-Info ''
    Write-Warn2 ("Last lines of {0}:" -f (Split-Path -Leaf $Path))
    Get-Content $Path -Tail $Lines | ForEach-Object { Write-Host "  $_" }
}
