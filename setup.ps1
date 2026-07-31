# cfd-fea-engineer - First-Run Setup (thin wrapper)
# Full orchestration lives in first_run_setup.py: venv -> pip deps -> WSL check ->
# OpenFOAM/CalculiX/Gmsh install in WSL -> toolchain verification (incl. CHT) -> tests.
# Usage:
#   .\setup.ps1                 # full setup + verification (idempotent)
#   .\setup.ps1 -CheckOnly      # report status, change nothing
#   .\setup.ps1 -SkipSolvers    # venv/deps only (no WSL solver install)
param(
    [switch]$CheckOnly,
    [switch]$SkipSolvers,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Install Python 3.10+ from https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

$setupArgs = @()
if ($CheckOnly)   { $setupArgs += "--check-only" }
if ($SkipSolvers) { $setupArgs += "--skip-solvers" }
if ($SkipTests)   { $setupArgs += "--skip-tests" }

python first_run_setup.py @setupArgs
exit $LASTEXITCODE
