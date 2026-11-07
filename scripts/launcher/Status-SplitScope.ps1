# Status-SplitScope.ps1 - nontechnical status report for SplitScope V2.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')

$Root = Get-ProjectRoot
$ServerHost = Get-ServerHost
$Port = Get-ServerPort
$Url = Get-ServerUrl
$probeHost = Get-LoopbackAddress $ServerHost

Write-Rule
Write-Info ' SplitScope V2 - status'
Write-Rule
Write-Info (" Project folder : {0}" -f $Root)
Write-Info (" Web address    : {0}" -f $Url)

# --- Server -----------------------------------------------------------------

$health = Test-SplitScopeHealth -ServerHost $ServerHost -Port $Port
$state = Read-ServerState
$stateCheck = if ($state) { Test-ServerStateMatches -State $state } else { $null }

Write-Info ''
switch ($health) {
    'healthy' {
        if ($state -and $stateCheck.Valid) {
            Write-Ok (" Server         : RUNNING and healthy (launcher-managed, PID {0})" -f $state.pid)
            Write-Info ("                  started {0}" -f $state.started_utc)
            $exitHint = 'Double-click Stop-SplitScope.cmd to shut it down.'
        } else {
            Write-Warn2 ' Server         : RUNNING and healthy, but NOT launcher-managed'
            Write-Info '                  (started manually, e.g. from a terminal).'
            Write-Info '                  Stop-SplitScope.cmd will not stop it - stop it where you started it.'
            $exitHint = 'To hand it over to the launcher, stop it manually, then start via the shortcut.'
        }
    }
    'occupied' {
        Write-Warn2 (" Server         : NOT running - port {0} is used by a different application" -f $Port)
        Write-Info '                  SplitScope cannot start until that program releases the port.'
        $exitHint = 'Close the other program (or set SPLITSCOPE_PORT) and start SplitScope again.'
    }
    default {
        Write-Info ' Server         : stopped'
        $exitHint = 'Double-click Start-SplitScope.cmd (or the desktop shortcut) to start it.'
    }
}

# --- Frontend production build ----------------------------------------------

$build = Test-FrontendBuildNeeded -Root $Root
$buildLabel = if ($build.Needed) { "needs a rebuild - $($build.Reason)" } else { 'production build is present and up to date' }
Write-Info (" Frontend build : {0}" -f $buildLabel)

if ($health -eq 'healthy' -and $build.Needed) {
    Write-Info '                  (The running server keeps using its loaded build;'
    Write-Info '                   stop and start again to pick up the new build.)'
}

# --- Launcher records and logs ----------------------------------------------

Write-Info (" Launcher state : {0}" -f $(if ($state) {
        if ($stateCheck.Valid) { "valid process record (PID $($state.pid))" }
        elseif ($null -eq $stateCheck.Process) { 'stale record (the recorded process is gone); cleaned up on next Stop/Start' }
        else { 'record does NOT match the running process - Stop will refuse to act' }
    } else { 'no server record (nothing launcher-managed)' }))

$logDir = Get-LauncherLogDir
$logCount = 0
if (Test-Path $logDir) {
    $logCount = @(Get-ChildItem $logDir -Filter 'server-*.log' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike '*.err.log' }).Count
}
Write-Info (" Server logs    : {0} kept in {1}" -f $logCount, $logDir)

# --- Guidance ---------------------------------------------------------------

Write-Info ''
Write-Info (" Next step      : {0}" -f $exitHint)
Write-Rule
exit 0
