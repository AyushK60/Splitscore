# Install-DesktopShortcut.ps1 - create the "SplitScope V2" desktop shortcut.
#
# Uses standard Windows shell COM (no admin rights), targets the project's own
# Start-SplitScope.cmd, and never touches any other shortcut on the desktop.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')

$Root = Get-ProjectRoot

Write-Rule
Write-Info ' SplitScope V2 - desktop shortcut'
Write-Rule

# Sanity: the shortcut target must exist.
$startCmd = Join-Path $Root 'Start-SplitScope.cmd'
if (-not (Test-Path $startCmd)) {
    Write-Fail 'Start-SplitScope.cmd was not found next to this script.'
    Write-Info 'The launcher installation appears incomplete.'
    exit 1
}

try {
    $linkPath = New-SplitScopeDesktopShortcut -Root $Root
} catch {
    Write-Fail "Could not create the desktop shortcut: $($_.Exception.Message)"
    exit 1
}

Write-Ok 'Desktop shortcut created: "SplitScope V2"'
Write-Info ("  Location : {0}" -f $linkPath)
Write-Info ("  Starts   : {0}" -f $startCmd)
Write-Info ("  Runs in  : {0}" -f $Root)
Write-Info ''
Write-Info 'Double-click the shortcut to open SplitScope V2 in your browser.'
Write-Info 'No administrator rights were needed and nothing starts automatically at boot.'
Write-Rule
exit 0
