#!/usr/bin/env python3
"""Toolchain health check: WSL, OpenFOAM, CalculiX, Gmsh, Python packages.

Exit 0 when the full CFD/FEA stack is ready; exit 1 with a remediation hint otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from wsl_bridge import check_environment  # noqa: E402


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    status = check_environment()
    print(json.dumps(status, indent=2))

    problems = []
    if not status["wsl"]:
        problems.append("WSL Ubuntu not reachable — install with: wsl --install -d Ubuntu")
    if not status["openfoam"]:
        problems.append("OpenFOAM missing — run install_solvers.py")
    elif not status.get("openfoam_cht"):
        problems.append(
            f"OpenFOAM CHT tools missing ({status.get('openfoam_cht_missing', '?')}) "
            "— run install_solvers.py --force (openfoam2412-default provides them)")
    if not status["calculix"]:
        problems.append("CalculiX missing — run install_solvers.py")
    missing_py = [k for k, v in status["python_packages"].items() if not v]
    if missing_py:
        problems.append(f"Python packages missing: {missing_py} — pip install -r requirements.txt")

    if problems:
        print("\nNOT READY:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nREADY: full CFD/FEA toolchain available.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
