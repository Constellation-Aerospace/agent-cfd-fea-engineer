#!/usr/bin/env python3
"""Install the solver backend into WSL Ubuntu: OpenFOAM 2412, CalculiX ccx, Gmsh.

Idempotent — checks what is present and installs only what's missing (unless --force).
Uses the official openfoam.com apt repository. Requires WSL2 + Ubuntu.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from wsl_bridge import run_wsl, check_environment  # noqa: E402

INSTALL_CMD = (
    "export DEBIAN_FRONTEND=noninteractive && "
    "apt-get update -qq && apt-get install -y -qq curl ca-certificates && "
    "curl -s https://dl.openfoam.com/add-debian-repo.sh | bash && "
    "apt-get update -qq && "
    "apt-get install -y -qq openfoam2412-default calculix-ccx gmsh"
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Reinstall even if present")
    args = ap.parse_args()

    status = check_environment()
    if not status["wsl"]:
        print("ERROR: WSL Ubuntu not reachable. Install it first (admin PowerShell):")
        print("  wsl --install -d Ubuntu")
        return 1

    if not args.force and status["openfoam"] and status["calculix"] and status["gmsh_wsl"]:
        print("All solvers already installed:")
        print(f"  OpenFOAM {status['openfoam']}, CalculiX {status['calculix']}, Gmsh {status['gmsh_wsl']}")
        return 0

    print("Installing OpenFOAM 2412 + CalculiX + Gmsh into WSL (several minutes, ~2 GB)...")
    run_wsl(INSTALL_CMD, timeout=1800)

    status = check_environment()
    ok = status["openfoam"] and status["calculix"]
    print(f"OpenFOAM: {status['openfoam']}, CalculiX: {status['calculix']}, Gmsh: {status['gmsh_wsl']}")
    if not ok:
        print("ERROR: installation incomplete — inspect WSL apt logs.")
        return 1
    print("Solver backend ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
