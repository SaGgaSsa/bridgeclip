# BridgeClip Windows source setup (Windows 10/11 x64).
#
# Creates/reuses engine/.venv with Python 3.12, installs the hashed lock file,
# runs `npm ci`, and verifies FFmpeg/FFprobe (libass `ass` filter), Node 22,
# and the OpenCode CLI. It never stores API keys and never pre-downloads
# Whisper model weights (faster-whisper downloads them on first local use).
#
# Usage (PowerShell 5.1+):
#   powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
# or:
#   npm run setup:windows

[CmdletBinding()]
param(
  [switch]$SkipPython,
  [switch]$SkipNode
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $RepoRoot 'engine\.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$LockFile = Join-Path $RepoRoot 'engine\requirements.lock'

function Write-Step([string]$Message) {
  Write-Host ''
  Write-Host "==> $Message"
}

function Write-Info([string]$Message) {
  Write-Host "    $Message"
}

function Fail([string]$Message) {
  Write-Host ''
  Write-Host "ERROR: $Message" -ForegroundColor Red
  exit 1
}

function Test-AppCommand([string]$Name) {
  return ($null -ne (Get-Command $Name -ErrorAction SilentlyContinue))
}

# 0. Sanity: repo layout and architecture.
if (-not (Test-Path -LiteralPath $LockFile)) {
  Fail "engine\requirements.lock was not found at: $LockFile. Run this script from the BridgeClip checkout."
}
if (-not [Environment]::Is64BitOperatingSystem) {
  Write-Host 'WARNING: BridgeClip source builds target Windows 10/11 x64; this machine does not report a 64-bit OS.' -ForegroundColor Yellow
}

# 1. Python 3.12 (launcher `py -3.12` preferred on Windows).
$SystemPython = $null
if (-not $SkipPython) {
  Write-Step 'Checking Python 3.12'
  $pythonCandidates = @()
  if (Test-AppCommand 'py') { $pythonCandidates += @{ Exe = 'py'; Args = @('-3.12') } }
  if (Test-AppCommand 'python') { $pythonCandidates += @{ Exe = 'python'; Args = @() } }
  if (Test-AppCommand 'python3') { $pythonCandidates += @{ Exe = 'python3'; Args = @() } }
  foreach ($candidate in $pythonCandidates) {
    $exe = $candidate.Exe
    $extraArgs = @($candidate.Args)
    try {
      $versionOutput = (& $exe @extraArgs '--version' 2>&1 | Out-String)
    } catch {
      continue
    }
    if ($versionOutput -match 'Python\s+3\.12\.(\d+)') {
      $SystemPython = @{ Exe = $exe; ExtraArgs = $extraArgs }
      Write-Info "Found $($versionOutput.Trim()) via: $exe $($extraArgs -join ' ')"
      break
    } elseif ($versionOutput -match 'Python\s+(\d+\.\d+\.\d+)') {
      Write-Info "Ignoring $($Matches[1]) via ${exe} (need 3.12.x)."
    }
  }
  if ($null -eq $SystemPython) {
    Fail 'Python 3.12 was not found. Install Python 3.12 x64 from https://www.python.org/downloads/ (check "Add python.exe to PATH" or use the `py` launcher), then rerun this script.'
  }
}

# 2. Node 22 + npm.
if (-not $SkipNode) {
  Write-Step 'Checking Node.js 22 and npm'
  if (-not (Test-AppCommand 'node')) {
    Fail 'node was not found on PATH. Install Node.js 22 LTS from https://nodejs.org/ and reopen the terminal.'
  }
  $nodeVersion = (& node --version 2>&1 | Out-String).Trim()
  if ($nodeVersion -notmatch '^v22\.') {
    Fail "Found node $nodeVersion, but BridgeClip development requires Node.js 22.x. Install Node 22 and rerun."
  }
  Write-Info "Found node $nodeVersion."
  if (-not (Test-AppCommand 'npm')) {
    Fail 'npm was not found on PATH. Repair your Node.js 22 installation, then rerun.'
  }
  Write-Info "Found npm $((& npm --version 2>&1 | Out-String).Trim())."
}

# 3. FFmpeg / FFprobe with the libass-backed `ass` filter (used for captions).
Write-Step 'Checking FFmpeg and FFprobe'
foreach ($tool in @('ffmpeg', 'ffprobe')) {
  if (-not (Test-AppCommand $tool)) {
    Fail "$tool was not found on PATH. Install an FFmpeg build with libass (for example https://www.gyan.dev/ffmpeg/builds/ or https://github.com/BtbN/FFmpeg-Builds), add its bin folder to PATH, then rerun."
  }
  Write-Info "Found ${tool}: $((Get-Command $tool | Select-Object -ExpandProperty Source))"
}
try {
  $filters = (& ffmpeg -hide_banner -filters 2>&1 | Out-String)
} catch {
  Fail 'Could not run `ffmpeg -hide_banner -filters`. Reinstall FFmpeg and make sure `ffmpeg` is on PATH.'
}
if ($filters -notmatch '(?m)^\s*[A-Z.]{2,}\s+ass\s') {
  Fail 'Your FFmpeg build does not expose the `ass` filter (libass). Captioned renders need it. Install a full Windows build (gyan.dev or BtbN) and rerun this script.'
}
Write-Info 'FFmpeg exposes the `ass` caption filter.'
try {
  Write-Info "ffprobe: $((& ffprobe -version 2>&1 | Out-String).Split([Environment]::NewLine)[0].Trim())"
} catch {
  Fail 'Could not run `ffprobe -version`. Reinstall FFmpeg and make sure `ffprobe` is on PATH.'
}

# 4. OpenCode CLI (default local planner). Warn only: OpenRouter remains an option.
Write-Step 'Checking OpenCode CLI'
if (Test-AppCommand 'opencode') {
  try {
    Write-Info "Found opencode: $((& opencode --version 2>&1 | Out-String).Trim())"
  } catch {
    Write-Info 'Found `opencode` on PATH (version check failed, continuing).'
  }
  Write-Info 'Sign in and make sure your model is available before running local planning jobs.'
} else {
  Write-Host 'WARNING: `opencode` was not found on PATH. Local clip planning (the default) needs the OpenCode CLI signed in with an available model. OpenRouter planning remains an option in Settings.' -ForegroundColor Yellow
  Write-Host '    Install it from https://opencode.ai/ and rerun this script to verify.' -ForegroundColor Yellow
}

# 5. engine/.venv (create or reuse; reuse must be Python 3.12).
if (-not $SkipPython) {
  Write-Step 'Setting up engine\.venv'
  if (Test-Path -LiteralPath $VenvPython) {
    Write-Info "Reusing existing venv at: $VenvDir"
    try {
      $venvVersion = (& "$VenvPython" -c "import sys; print('%s.%s.%s' % sys.version_info[:3])" 2>&1 | Out-String).Trim()
    } catch {
      Fail "The existing venv Python failed to run: $VenvPython. Delete the engine\.venv folder and rerun this script."
    }
    if ($venvVersion -notmatch '^3\.12\.') {
      Fail "The existing engine\.venv uses Python $venvVersion, but 3.12.x is required. Delete the engine\.venv folder and rerun this script."
    }
    Write-Info "Venv Python is $venvVersion."
  } else {
    Write-Info "Creating venv at: $VenvDir"
    $exe = $SystemPython.Exe
    $venvArgs = @($SystemPython.ExtraArgs) + @('-m', 'venv', "$VenvDir")
    try {
      & $exe @venvArgs
    } catch {
      Fail "Could not create engine\.venv with $exe. Error: $($_.Exception.Message)"
    }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
      Fail "venv creation finished but $VenvPython is missing. Delete engine\.venv and rerun."
    }
  }

  Write-Step 'Installing locked Python dependencies (hash-checked)'
  Write-Info 'Source: engine\requirements.lock (never requirements.txt directly).'
  try {
    & "$VenvPython" -m pip install --require-hashes -r "$LockFile"
  } catch {
    Fail "pip install failed. Rerun this script; if it persists, delete engine\.venv and rerun. Error: $($_.Exception.Message)"
  }
  if (-not $?) {
    Fail 'pip install reported an error. Rerun this script; if it persists, delete engine\.venv and rerun.'
  }
}

# 6. Node dependencies (npm ci uses the Node lockfile).
if (-not $SkipNode) {
  Write-Step 'Installing Node dependencies (npm ci)'
  Push-Location -LiteralPath $RepoRoot
  try {
    & npm ci
    if (-not $?) {
      Fail '`npm ci` reported an error. Check the npm output above and rerun.'
    }
  } catch {
    Fail "`npm ci` failed. Error: $($_.Exception.Message)"
  } finally {
    Pop-Location
  }

  # 6b. Electron development runtime binary (required for `npm run dev`).
  # electron@44.x ships a JS wrapper without an npm postinstall hook, so a
  # fresh `npm ci` can finish without dist/electron.exe. Download it here.
  Write-Step 'Verifying Electron development runtime binary'
  $ElectronDir = Join-Path $RepoRoot 'node_modules\electron'
  $ElectronPathFile = Join-Path $ElectronDir 'path.txt'
  $ElectronInstallJs = Join-Path $ElectronDir 'install.js'
  $ElectronDistExe = Join-Path $ElectronDir 'dist\electron.exe'
  $ElectronReady = ((Test-Path -LiteralPath $ElectronPathFile) -and (Test-Path -LiteralPath $ElectronDistExe))
  if ($ElectronReady) {
    Write-Info "Found Electron runtime: $ElectronDistExe"
  } else {
    Write-Info 'Electron binary missing (node_modules\electron\path.txt and/or dist\electron.exe absent); downloading via node node_modules\electron\install.js ...'
    if (-not (Test-Path -LiteralPath $ElectronInstallJs)) {
      Fail 'Electron install script was not found at node_modules\electron\install.js after `npm ci`. Delete node_modules and rerun this script; if it persists, check the `electron` devDependency and npm output above.'
    }
    if (-not (Test-AppCommand 'node')) {
      Fail 'node was not found on PATH, so the Electron binary could not be downloaded. Install Node.js 22 and rerun this script.'
    }
    Push-Location -LiteralPath $RepoRoot
    try {
      & node "$ElectronInstallJs"
      if ((-not $?) -or ($LASTEXITCODE -ne 0)) {
        Fail "The Electron binary download failed (node node_modules\electron\install.js exited with code $LASTEXITCODE). Check your network/proxy, rerun this script, or run node node_modules\electron\install.js manually from the repo root."
      }
    } catch {
      Fail "Could not run the Electron installer (node node_modules\electron\install.js). Error: $($_.Exception.Message)"
    } finally {
      Pop-Location
    }
    if (-not (Test-Path -LiteralPath $ElectronPathFile)) {
      Fail 'Electron install finished but node_modules\electron\path.txt is still missing. Run `node node_modules\electron\install.js` manually from the repo root and rerun this script.'
    }
    if (-not (Test-Path -LiteralPath $ElectronDistExe)) {
      Fail 'Electron install finished but node_modules\electron\dist\electron.exe is still missing. Run `node node_modules\electron\install.js` manually from the repo root and rerun this script (check antivirus/quarantine if the exe disappears).'
    }
    Write-Info "Installed Electron runtime: $ElectronDistExe"
  }
}

Write-Host ''
Write-Host 'Windows source setup complete.' -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:'
Write-Host '  1. npm run dev                      # start BridgeClip with hot reload'
Write-Host '  2. Settings -> System check         # confirm Python, FFmpeg, and engine'
Write-Host '     Python path (dev): engine\.venv\Scripts\python.exe'
Write-Host '  3. Local planning: `opencode` must be signed in with an available model.'
Write-Host '     OpenRouter planning remains available in Settings.'
Write-Host '  Notes:'
Write-Host '  - Faster-Whisper downloads its model weights on first local use (nothing is pre-downloaded).'
Write-Host '  - Local transcription does not mean text stays on this PC: the default OpenCode planner may send transcript text to its configured service.'
Write-Host '  - Finished clips are vertical MP4 files, same as other BridgeClip builds.'
Write-Host '  - Windows distributable packaging (NSIS) is not verified; resource staging is currently macOS-only, so run from source via `npm run dev`.'
