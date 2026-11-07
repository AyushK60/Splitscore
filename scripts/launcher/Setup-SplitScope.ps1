# Setup-SplitScope.ps1 - one-time first install for SplitScope V2.
#
# Checks prerequisites (Python 3.11, Node.js >= 20.18), creates the Python
# virtual environment, installs the project's pinned backend dependencies,
# installs frontend dependencies from the lockfile, builds the frontend, and
# creates the desktop shortcut. Safe to re-run: completed steps are skipped.
#
# Everything is derived from this script's location - it never assumes any
# particular install path (e.g. E:\Splitscore V2) and needs no admin rights.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Common.ps1')

$Root = Get-ProjectRoot

Write-Rule
Write-Info ' SplitScope V2 - first-time setup'
Write-Rule
Write-Info (" Project folder: {0}" -f $Root)
Write-Info ''

# --- 1. Python ---------------------------------------------------------------

Write-Info '[1/5] Checking Python 3.11 ...'
$py = Find-PythonLauncher
if (-not $py) {
    Write-Fail 'Python 3.11 was not found on this computer.'
    Write-Info ''
    Write-Info 'SplitScope V2 is verified on Python 3.11 (its dependencies are pinned for 3.11).'
    Write-Info 'Install Python 3.11 from https://www.python.org/downloads/ (tick "Add to PATH"),'
    Write-Info 'then run Setup-SplitScope.cmd again.'
    exit 1
}
$pyVersion = (& $py.Exe @($py.Args) --version 2>$null)
Write-Ok ("  Found {0} ({1})." -f $pyVersion, $py.Exe)

# --- 2. Virtual environment + pinned backend dependencies --------------------

$venvDir = Join-Path $Root '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
Write-Info '[2/5] Checking the Python environment (.venv) ...'
if (Test-Path $venvPython) {
    Write-Ok '  .venv already exists - reusing it.'
} else {
    Write-Info '  Creating .venv (one-time, about 10 seconds) ...'
    & $py.Exe @($py.Args) -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Write-Fail 'Could not create the Python virtual environment. See the error above.'
        exit 1
    }
    Write-Ok '  .venv created.'
}

$req = Join-Path $Root 'backend\requirements.txt'
if (-not (Test-Path $req)) {
    Write-Fail 'backend\requirements.txt not found - the repository appears incomplete.'
    exit 1
}
Write-Info '  Installing the pinned backend dependencies (fastapi, uvicorn, ...) ...'
& $venvPython -m pip install --disable-pip-version-check -r $req
if ($LASTEXITCODE -ne 0) {
    Write-Fail 'Installing the backend dependencies failed (see above).'
    Write-Info 'Check your internet connection and run Setup-SplitScope.cmd again.'
    exit 1
}
Write-Ok '  Backend dependencies installed.'

# --- 3. Node.js / npm ---------------------------------------------------------

Write-Info '[3/5] Checking Node.js and npm ...'
$node = Get-Command node -ErrorAction SilentlyContinue
$npmCmd = Find-NpmCommand
if (-not $node -or -not $npmCmd) {
    Write-Fail 'Node.js / npm was not found on this computer.'
    Write-Info ''
    Write-Info 'SplitScope V2 needs Node.js 20.18 or newer (https://nodejs.org - the LTS works).'
    Write-Info 'Install it, then run Setup-SplitScope.cmd again.'
    exit 1
}
$nodeVersion = (& $node.Source --version) -replace '^v', ''
try {
    $nodeParts = $nodeVersion.Split('.')
    $nodeOk = ([int]$nodeParts[0] -gt 20) -or ([int]$nodeParts[0] -eq 20 -and [int]$nodeParts[1] -ge 18)
} catch { $nodeOk = $false }
if (-not $nodeOk) {
    Write-Fail ("Node.js {0} was found, but SplitScope V2 needs 20.18 or newer." -f $nodeVersion)
    Write-Info 'Install a current Node.js LTS from https://nodejs.org, then run Setup-SplitScope.cmd again.'
    exit 1
}
Write-Ok ("  Found Node.js v{0} and npm." -f $nodeVersion)

# --- 4. Frontend dependencies + production build ------------------------------

$frontendDir = Join-Path $Root 'frontend'
$lockfile = Join-Path $frontendDir 'package-lock.json'
Write-Info '[4/5] Preparing the frontend ...'
if (-not (Test-Path (Join-Path $frontendDir 'package.json'))) {
    Write-Fail 'frontend\package.json not found - the repository appears incomplete.'
    exit 1
}
if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
    Push-Location $frontendDir
    try {
        if (Test-Path $lockfile) {
            Write-Info '  Installing frontend dependencies from the lockfile (npm ci) ...'
            & $npmCmd ci
        } else {
            Write-Info '  Installing frontend dependencies (npm install; no lockfile found) ...'
            & $npmCmd install
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Fail 'Installing the frontend dependencies failed (see above).'
            Write-Info 'Check your internet connection and run Setup-SplitScope.cmd again.'
            exit 1
        }
    } finally {
        Pop-Location
    }
    Write-Ok '  Frontend dependencies installed.'
} else {
    Write-Ok '  Frontend dependencies already installed.'
}

$build = Test-FrontendBuildNeeded -Root $Root
if ($build.Needed) {
    Write-Info ("  Building the frontend ({0}) ..." -f $build.Reason)
    Push-Location $frontendDir
    try {
        & $npmCmd run build
        if ($LASTEXITCODE -ne 0) {
            Write-Fail 'The frontend build failed (see above).'
            exit 1
        }
    } finally {
        Pop-Location
    }
    Write-Ok '  Frontend built (frontend\dist).'
} else {
    Write-Ok ("  Frontend {0}." -f $build.Reason)
}

# --- 5. Desktop shortcut -------------------------------------------------------

Write-Info '[5/5] Creating the desktop shortcut ...'
$linkPath = New-SplitScopeDesktopShortcut -Root $Root
Write-Ok ("  Created: {0}" -f $linkPath)

# --- Done -----------------------------------------------------------------------

Write-Info ''
Write-Ok 'Setup is complete. SplitScope V2 is ready to use.'
Write-Info ''
Write-Info 'From now on, just double-click the "SplitScope V2" desktop shortcut:'
Write-Info '  1. It starts the app (first start takes a few seconds).'
Write-Info '  2. SplitScope opens in your browser at http://127.0.0.1:8000.'
Write-Info '  3. To shut it down, double-click Stop-SplitScope.cmd in the project folder.'
Write-Info ''
Write-Info 'You can re-run Setup-SplitScope.cmd any time - finished steps are skipped.'
Write-Rule
exit 0
