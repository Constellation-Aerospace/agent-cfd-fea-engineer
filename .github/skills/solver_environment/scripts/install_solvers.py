#!/usr/bin/env python3
"""Install the solver backend into WSL Ubuntu: OpenFOAM 2412, CalculiX ccx, Gmsh, ElmerFEM.

Idempotent — checks what is present and installs only what's missing (unless --force).
Uses the official openfoam.com apt repository. Requires WSL2 + Ubuntu.

ElmerFEM has no apt/PPA package for Ubuntu 24.04 (noble) yet, so it is compiled from
source (serial, no GUI — see https://github.com/ElmerCSC/elmerfem/wiki/Packages). This
is skipped by default (adds ~10-20 min); pass --with-elmer to include it.
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

ELMER_DEPS_CMD = (
    "export DEBIAN_FRONTEND=noninteractive && apt-get update -qq && "
    "apt-get install -y -qq git cmake build-essential gfortran libblas-dev liblapack-dev"
)

# Serial (no MPI), no-GUI build — sufficient for single-part FEA decks run from this
# harness. mkdir -p / re-clone-if-missing keeps this idempotent across retries.
ELMER_BUILD_CMD = (
    "set -e; cd /opt; "
    "if [ ! -d elmerfem ]; then git clone --depth 1 https://github.com/ElmerCSC/elmerfem.git elmerfem; fi; "
    "cd elmerfem; mkdir -p build; cd build; "
    "cmake -DWITH_ELMERGUI:BOOL=FALSE -DWITH_MPI:BOOL=FALSE -DCMAKE_INSTALL_PREFIX=/usr/local .. "
    "> /opt/elmer_configure.log 2>&1; "
    "make -j$(nproc) > /opt/elmer_build.log 2>&1; "
    "make install >> /opt/elmer_build.log 2>&1"
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Reinstall even if present")
    ap.add_argument("--with-elmer", action="store_true",
                     help="Also build ElmerFEM from source (slow — no Ubuntu 24.04 package exists)")
    args = ap.parse_args()

    status = check_environment()
    if not status["wsl"]:
        print("ERROR: WSL Ubuntu not reachable. Install it first (admin PowerShell):")
        print("  wsl --install -d Ubuntu")
        return 1

    core_ready = status["openfoam"] and status["calculix"] and status["gmsh_wsl"]
    elmer_needed = args.with_elmer and not status["elmer"]
    if not args.force and core_ready and not elmer_needed:
        print("All requested solvers already installed:")
        print(f"  OpenFOAM {status['openfoam']}, CalculiX {status['calculix']}, "
              f"Gmsh {status['gmsh_wsl']}, Elmer {status['elmer']}")
        return 0

    if args.force or not core_ready:
        print("Installing OpenFOAM 2412 + CalculiX + Gmsh into WSL (several minutes, ~2 GB)...")
        run_wsl(INSTALL_CMD, timeout=None)  # no cap — OpenFOAM is ~1.5 GB and varies by connection

    if args.with_elmer and (args.force or not status["elmer"]):
        print("Building ElmerFEM from source into WSL (10-20 min, logs at /opt/elmer_build.log)...")
        run_wsl(ELMER_DEPS_CMD, timeout=300)
        run_wsl(ELMER_BUILD_CMD, timeout=3600)

    status = check_environment()
    ok = status["openfoam"] and status["calculix"]
    print(f"OpenFOAM: {status['openfoam']}, CalculiX: {status['calculix']}, "
          f"Gmsh: {status['gmsh_wsl']}, Elmer: {status['elmer']}")
    if not ok:
        print("ERROR: installation incomplete — inspect WSL apt logs.")
        return 1
    if args.with_elmer and not status["elmer"]:
        print("ERROR: ElmerFEM build did not complete — inspect /opt/elmer_build.log in WSL.")
        return 1
    print("Solver backend ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
