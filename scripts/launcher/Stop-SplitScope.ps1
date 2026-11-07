# Stop-SplitScope.ps1 - stop only the server process(es) this launcher started.
#
# Safety rules enforced here:
#   * Never kill arbitrary Python processes or by process name.
#   * Never kill by port. A different app on port 8000 is left untouched.
#   * Every kill is gated on identity: the recorded PID must match the live
#     process on executable path, creation time, and command line.
#   * The launcher records the venv "python.exe" redirector AND the actual
#     listening server child; both are validated independently.
#   * Stale records are cleaned up, never acted on.
#   * A manually started SplitScope is reported, not stopped.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')

$Root = Get-ProjectRoot
$ServerHost = Get-ServerHost
$Port = Get-ServerPort
$Url = Get-ServerUrl

Write-Rule
Write-Info ' SplitScope V2 - stopping'
Write-Rule

$state = Read-ServerState

if ($state) {
    $recordedPid = [int](Get-StateProp $state 'pid')
    $check = Test-ServerStateMatches -State $state

    # A live process that does NOT match the record means PID reuse or a
    # tampered record - refuse to touch anything on that basis.
    if (-not $check.Valid -and $null -ne $check.Process) {
        Write-Fail 'The saved launcher record does not match the running process:'
        Write-Info ('  ' + $check.Reason)
        Write-Info 'Nothing was stopped (this guard prevents stopping the wrong program).'
        Write-Info "You can delete the stale record manually: $(Get-ServerStateFile)"
        exit 1
    }

    $killedAny = $false

    # 1. The recorded launcher process (venv python.exe redirector), if alive.
    if ($null -ne $check.Process) {
        Write-Info "Stopping launcher-managed server (PID $recordedPid, started $(Get-StateProp $state 'started_utc'))..."
        try { Stop-Process -Id $recordedPid -Force -ErrorAction Stop } catch {}
        $killedAny = $true
    }

    # 2. The recorded actual server process (the listening child), if alive,
    #    validated independently against its own identity evidence.
    $serverPid = Get-StateProp $state 'server_pid'
    if ($serverPid) {
        $sv = Test-ProcessIdentity -ProcessId ([int]$serverPid) `
            -ExpectedExe (Get-StateProp $state 'server_exe') `
            -ExpectedCreationUtc (Get-StateProp $state 'server_creation_time_utc')
        if ($sv.Valid) {
            Write-Info "Stopping the server process (PID $serverPid)..."
            try { Stop-Process -Id $serverPid -Force -ErrorAction SilentlyContinue } catch {}
            $killedAny = $true
        } elseif ($null -ne $sv.Process) {
            Write-Warn2 ("Recorded server PID $serverPid no longer matches its record - not stopping it:")
            Write-Info ('  ' + $sv.Reason)
        }
    }

    # 3. Defensive sweep: any direct child of the recorded launcher process
    #    that is provably still running the SplitScope backend (command-line
    #    check). This never reaches processes with a different parent.
    try {
        $children = Get-CimInstance -ClassName Win32_Process -Filter "ParentProcessId = $recordedPid" -ErrorAction Stop
        foreach ($child in $children) {
            if ($child.CommandLine -and $child.CommandLine -match 'app\.main') {
                Write-Info "Stopping remaining server child process (PID $($child.ProcessId))..."
                try { Stop-Process -Id ([int]$child.ProcessId) -Force -ErrorAction SilentlyContinue } catch {}
                $killedAny = $true
            }
        }
    } catch {}

    if (-not $killedAny) {
        Remove-ServerState
        Write-Info $check.Reason
        Write-Ok 'SplitScope is not running (stale launcher record cleaned up).'
        Write-Rule
        exit 0
    }

    # 4. Wait (bounded) until our processes are really gone.
    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-Date) -lt $deadline) {
        $remaining = $false
        foreach ($probeId in @($recordedPid) + @($serverPid)) {
            if (-not $probeId) { continue }
            try { $null = Get-Process -Id ([int]$probeId) -ErrorAction Stop; $remaining = $true } catch {}
        }
        if (-not $remaining) { break }
        Start-Sleep -Milliseconds 300
    }
    $stillAlive = @()
    foreach ($probeId in @($recordedPid) + @($serverPid)) {
        if (-not $probeId) { continue }
        try { $null = Get-Process -Id ([int]$probeId) -ErrorAction Stop; $stillAlive += $probeId } catch {}
    }

    Remove-ServerState

    if ($stillAlive.Count -gt 0) {
        Write-Warn2 ("Process(es) {0} have not exited within 15 seconds. They were asked to stop; please check Task Manager." -f ($stillAlive -join ', '))
        exit 1
    }

    $after = Test-SplitScopeHealth -ServerHost $ServerHost -Port $Port
    if ($after -eq 'healthy') {
        Write-Warn2 'The port still answers as SplitScope; another SplitScope instance may be running (not launcher-managed).'
        exit 1
    }

    Write-Ok 'SplitScope has been stopped.'
    Write-Info 'It can be started again any time with Start-SplitScope.cmd or the desktop shortcut.'
    Write-Rule
    exit 0
}

# No launcher record at all.
$health = Test-SplitScopeHealth -ServerHost $ServerHost -Port $Port

if ($health -eq 'healthy') {
    Write-Warn2 "SplitScope IS running at $Url, but it was not started by this launcher."
    Write-Info ''
    Write-Info 'Stop-SplitScope only manages servers it started itself, so nothing was stopped.'
    Write-Info 'If you started the server manually (e.g. "python -m app.main"), stop it in that'
    Write-Info 'terminal with Ctrl+C, or close that process in Task Manager.'
    exit 1
}

if ($health -eq 'occupied') {
    Write-Info "Port $Port is in use by a different application (not SplitScope)."
    Write-Info 'Nothing was stopped.'
    exit 0
}

Write-Ok 'SplitScope is not running. Nothing to stop.'
Write-Rule
exit 0
