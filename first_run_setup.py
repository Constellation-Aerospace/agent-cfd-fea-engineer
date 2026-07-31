#!/usr/bin/env python3
"""First-run setup orchestrator for agent-cfd-fea-engineer.

One command stands up everything the agent needs — idempotent, safe to re-run:

    python first_run_setup.py              # full setup + verification
    python first_run_setup.py --check-only # report status, change nothing
    python first_run_setup.py --skip-solvers --skip-tests

Stages (each skippable, each reported in setup_report.json):
  1. host      Python >= 3.10 on Windows (or any OS for the venv part)
  2. venv      .venv created, pip upgraded, requirements.txt installed
  3. wsl       WSL2 + Ubuntu reachable (prints install instructions if not —
               `wsl --install -d Ubuntu` needs admin + reboot, so it is never
               attempted automatically)
  4. solvers   OpenFOAM v2412 + CalculiX + Gmsh installed inside WSL (apt,
               ~2 GB, several minutes on first run)
  5. verify    full toolchain check incl. CHT solvers (chtMultiRegion*Foam,
               splitMeshRegions, gmshToFoam, foamToVTK) and Python packages
  6. tests     pytest CI gate (tests/) with the venv interpreter

Run with any system Python — later stages re-invoke the venv interpreter.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / (
    "python.exe" if sys.platform == "win32" else "python")
REPORT = ROOT / "setup_report.json"

CHECKMARK, CROSS = "[ok]", "[!!]"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True,
                          encoding="utf-8", errors="replace", **kw)


def stage_host(report: dict) -> bool:
    ok = sys.version_info >= (3, 10)
    report["host"] = {"python": sys.version.split()[0], "ok": ok}
    print(f"{CHECKMARK if ok else CROSS} Python {sys.version.split()[0]}"
          + ("" if ok else " — need 3.10+ from https://www.python.org/downloads/"))
    return ok


def stage_venv(report: dict, check_only: bool) -> bool:
    if not VENV_PY.exists():
        if check_only:
            report["venv"] = {"ok": False, "note": "missing"}
            print(f"{CROSS} venv missing (.venv) — run without --check-only to create")
            return False
        print("Creating virtual environment ...")
        r = run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
        if r.returncode != 0:
            report["venv"] = {"ok": False, "note": r.stderr[-500:]}
            print(f"{CROSS} venv creation failed:\n{r.stderr[-500:]}")
            return False
    if not check_only:
        print("Installing Python dependencies (requirements.txt) ...")
        run([str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
        r = run([str(VENV_PY), "-m", "pip", "install", "-r",
                 str(ROOT / "requirements.txt"), "--quiet"])
        if r.returncode != 0:
            report["venv"] = {"ok": False, "note": r.stderr[-800:]}
            print(f"{CROSS} pip install failed:\n{r.stderr[-800:]}")
            return False
    report["venv"] = {"ok": True, "python": str(VENV_PY)}
    print(f"{CHECKMARK} venv ready: {VENV_PY}")
    return True


def stage_workspace(report: dict) -> bool:
    """Local folders, optional .env, memory DB — never blocks setup."""
    for d in (".tmp", "memory", "outputs"):
        (ROOT / d).mkdir(exist_ok=True)
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists() and example.exists():
        env.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"{CHECKMARK} .env created from .env.example (no API keys required)")
    mem = run([str(VENV_PY), str(ROOT / ".tmp/scripts/memory_db.py"), "status"],
              cwd=str(ROOT))
    report["workspace"] = {"ok": True, "memory_db": mem.returncode == 0}
    print(f"{CHECKMARK} workspace dirs ready"
          + ("" if mem.returncode == 0 else " (memory DB init deferred)"))
    return True


def stage_wsl(report: dict) -> bool:
    try:
        r = run(["wsl", "-l", "-q"])
        distros = [d.strip() for d in (r.stdout or "").replace("\x00", "").splitlines()
                   if d.strip()]
    except FileNotFoundError:
        distros = []
    ok = any(d.lower().startswith("ubuntu") for d in distros)
    report["wsl"] = {"ok": ok, "distros": distros}
    if ok:
        print(f"{CHECKMARK} WSL Ubuntu present ({', '.join(distros)})")
    else:
        print(f"{CROSS} WSL Ubuntu not found. Install it (admin PowerShell, then reboot):")
        print("      wsl --install -d Ubuntu")
        print("      ...then re-run: python first_run_setup.py")
    return ok


def stage_solvers(report: dict, check_only: bool) -> bool:
    script = ROOT / ".github/skills/solver_environment/scripts/install_solvers.py"
    if check_only:
        report["solvers"] = {"ok": None, "note": "skipped (check-only)"}
        return True
    print("Installing/verifying WSL solvers (OpenFOAM 2412 + CalculiX + Gmsh) ...")
    r = run([str(VENV_PY), str(script)], cwd=str(ROOT), timeout=2400)
    ok = r.returncode == 0
    report["solvers"] = {"ok": ok, "output": (r.stdout or "")[-800:]}
    print((r.stdout or "").strip()[-400:])
    if not ok:
        print(f"{CROSS} solver install failed — see output above")
    return ok


def stage_verify(report: dict) -> bool:
    script = ROOT / ".github/skills/solver_environment/scripts/check_environment.py"
    r = run([str(VENV_PY), str(script)], cwd=str(ROOT), timeout=600)
    ok = r.returncode == 0
    try:  # stdout = JSON status block followed by READY/NOT READY lines
        out = r.stdout or ""
        status = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except ValueError:
        status = {}
    report["verify"] = {"ok": ok, "status": status,
                        "detail": (r.stdout or "").strip().splitlines()[-6:]}
    print(f"{CHECKMARK if ok else CROSS} toolchain verification "
          + ("passed" if ok else "FAILED:"))
    if not ok:
        print(r.stdout)
    return ok


def stage_tests(report: dict) -> bool:
    print("Running test suite (tests/) ...")
    r = run([str(VENV_PY), "-m", "pytest", "tests", "-q"], cwd=str(ROOT), timeout=1200)
    tail = (r.stdout or "").strip().splitlines()[-3:]
    ok = r.returncode == 0
    report["tests"] = {"ok": ok, "tail": tail}
    print(f"{CHECKMARK if ok else CROSS} pytest: {' / '.join(tail)}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check-only", action="store_true",
                    help="Report status without installing anything")
    ap.add_argument("--skip-solvers", action="store_true",
                    help="Skip the WSL solver install stage")
    ap.add_argument("--skip-tests", action="store_true", help="Skip the pytest gate")
    args = ap.parse_args()

    report: dict = {}
    print("=== agent-cfd-fea-engineer first-run setup ===\n")

    ok = stage_host(report)
    ok = stage_venv(report, args.check_only) and ok
    if not args.check_only and report.get("venv", {}).get("ok"):
        stage_workspace(report)
    wsl_ok = stage_wsl(report)
    ok = ok and wsl_ok

    if wsl_ok and not args.skip_solvers:
        ok = stage_solvers(report, args.check_only) and ok
    elif args.skip_solvers:
        report["solvers"] = {"ok": None, "note": "skipped (--skip-solvers)"}

    if wsl_ok and report.get("venv", {}).get("ok"):
        ok = stage_verify(report) and ok

    if not args.skip_tests and not args.check_only and report.get("venv", {}).get("ok"):
        ok = stage_tests(report) and ok
    elif args.skip_tests:
        report["tests"] = {"ok": None, "note": "skipped (--skip-tests)"}

    report["ready"] = ok
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to {REPORT.name}")
    if ok:
        print("\nREADY. Suggested first commands:")
        print("  .venv\\Scripts\\python.exe .github/skills/solver_environment/scripts/check_environment.py")
        print("  .venv\\Scripts\\python.exe .github/skills/step_assembly/scripts/inspect_step.py --study demo --step <your.step>")
    else:
        print("\nNOT READY — fix the [!!] items above and re-run: python first_run_setup.py")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
