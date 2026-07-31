#!/bin/bash
# cfd-fea-engineer - First-Run Setup (thin wrapper)
# Full orchestration lives in first_run_setup.py: venv -> pip deps -> WSL check ->
# OpenFOAM/CalculiX/Gmsh install in WSL -> toolchain verification (incl. CHT) -> tests.
# Note: the solver backend targets Windows+WSL; on plain Linux the WSL stage will
# report not-ready — install OpenFOAM 2412/CalculiX/gmsh natively and set the
# wsl_bridge env vars, or run with --skip-solvers for the Python-only stack.
# Usage: ./setup.sh [--check-only] [--skip-solvers] [--skip-tests]
set -e
cd "$(dirname "$0")"

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 is not installed (need 3.10+)"
    exit 1
fi

python3 first_run_setup.py "$@"
