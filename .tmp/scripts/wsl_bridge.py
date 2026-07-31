#!/usr/bin/env python3
"""WSL bridge — run Linux solver commands (OpenFOAM, CalculiX, Gmsh) from Windows.

All CFD/FEA solvers live inside WSL Ubuntu. This module translates Windows paths
to /mnt/ form, wraps commands with the OpenFOAM environment when requested, and
streams solver logs back to the Windows side.

Usage (CLI):
    python wsl_bridge.py --check
    python wsl_bridge.py --run "checkMesh" --cwd "outputs/study-1/case" --openfoam
    python wsl_bridge.py --run "ccx_2.21 -i job" --cwd "outputs/fea-1"

Usage (import):
    from wsl_bridge import run_wsl, run_foam, win_to_wsl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

WSL_DISTRO = os.getenv("WSL_DISTRO", "Ubuntu")
WSL_USER = os.getenv("WSL_USER", "root")
OPENFOAM_BASHRC = os.getenv("OPENFOAM_BASHRC", "/usr/lib/openfoam/openfoam2412/etc/bashrc")

_LINK_ROOT = Path(os.getenv("LOCALAPPDATA", tempfile.gettempdir())) / "wsl_bridge_links"


def _space_safe(path: Path) -> Path:
    """OpenFOAM rejects paths containing spaces. If `path` has any, route it through
    an NTFS junction (no admin required; WSL resolves junctions transparently)."""
    p = Path(path).resolve()
    s = str(p)
    if " " not in s:
        return p
    parts = p.parts
    idx = max(i for i, part in enumerate(parts) if " " in part)
    anchor = Path(*parts[: idx + 1])          # deepest ancestor still containing a space
    suffix = parts[idx + 1:]
    link = _LINK_ROOT / hashlib.md5(str(anchor).lower().encode()).hexdigest()[:12]
    if " " in str(link):
        return p  # cannot help — LOCALAPPDATA itself has spaces
    if not link.exists():
        _LINK_ROOT.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(anchor)],
                           capture_output=True, text=True)
        if r.returncode != 0 and not link.exists():
            return p
    return link.joinpath(*suffix)


def win_to_wsl(path: str | Path) -> str:
    """Convert a Windows path (C:\\foo\\bar) to WSL form (/mnt/c/foo/bar),
    rerouting through a space-free junction when needed (OpenFOAM requirement)."""
    p = str(_space_safe(Path(path)))
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    if not m:
        return p.replace("\\", "/")
    drive, rest = m.groups()
    return f"/mnt/{drive.lower()}/" + rest.replace("\\", "/")


def run_wsl(
    command: str,
    cwd: str | Path | None = None,
    openfoam: bool = False,
    timeout: int | None = None,
    log_file: str | Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a shell command inside WSL. Raises RuntimeError on failure when check=True."""
    parts = []
    if openfoam:
        parts.append(f"source {OPENFOAM_BASHRC} 2>/dev/null || true")
    if cwd is not None:
        parts.append(f"cd '{win_to_wsl(cwd)}'")
    parts.append(command)
    full = " && ".join(parts) if cwd else "; ".join(parts)

    args = ["wsl", "-d", WSL_DISTRO, "-u", WSL_USER, "--", "bash", "-c", full]
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            encoding="utf-8", errors="replace")
    if log_file is not None:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        Path(log_file).write_text(
            (result.stdout or "") + "\n--- STDERR ---\n" + (result.stderr or ""),
            encoding="utf-8")
    if check and result.returncode != 0:
        tail = "\n".join(((result.stderr or "") + "\n" + (result.stdout or "")).splitlines()[-40:])
        raise RuntimeError(f"WSL command failed (exit {result.returncode}): {command}\n{tail}")
    return result


def run_foam(tool: str, case_dir: str | Path, args: str = "",
             timeout: int | None = None, parallel_np: int = 0) -> str:
    """Run an OpenFOAM tool in a case directory, writing log.<tool> inside the case.

    parallel_np > 0 runs the tool under mpirun with -parallel.
    Returns the last 30 lines of the log for quick inspection.
    """
    case_dir = Path(case_dir)
    log_name = f"log.{tool}"
    if parallel_np > 0:
        cmd = f"mpirun --allow-run-as-root -np {parallel_np} {tool} -parallel {args} > {log_name} 2>&1"
    else:
        cmd = f"{tool} {args} > {log_name} 2>&1"
    run_wsl(cmd, cwd=case_dir, openfoam=True, timeout=timeout)
    log_path = case_dir / log_name
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-30:])
    return "(no log produced)"


def check_environment() -> dict:
    """Verify the whole solver toolchain. Returns a status dict."""
    status: dict = {"wsl": False, "distro": WSL_DISTRO, "openfoam": None,
                    "openfoam_cht": None, "calculix": None, "gmsh_wsl": None,
                    "python_packages": {}}
    try:
        r = run_wsl("echo ok", check=False)
        status["wsl"] = r.returncode == 0 and "ok" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return status

    r = run_wsl("command -v compressibleInterFoam && foamVersion 2>/dev/null || echo -n", openfoam=True, check=False)
    if "compressibleInterFoam" in (r.stdout or ""):
        m = re.search(r"openfoam(\d{4})", r.stdout)
        status["openfoam"] = f"v{m.group(1)}" if m else "installed"

    # multi-region CHT toolchain (conjugate_heat_transfer skill)
    cht_tools = ("chtMultiRegionSimpleFoam", "chtMultiRegionFoam",
                 "splitMeshRegions", "gmshToFoam", "foamToVTK")
    r = run_wsl(" ; ".join(f"command -v {t}" for t in cht_tools), openfoam=True, check=False)
    found = r.stdout or ""
    missing_cht = [t for t in cht_tools if t not in found]
    status["openfoam_cht"] = "installed" if not missing_cht else None
    if missing_cht and status["openfoam"]:
        status["openfoam_cht_missing"] = missing_cht

    r = run_wsl("ccx_2.21 -v 2>/dev/null || ccx -v 2>/dev/null", check=False)
    m = re.search(r"[Vv]ersion\s*([\d.]+)", r.stdout or "")
    status["calculix"] = m.group(1) if m else (None if r.returncode else "installed")

    r = run_wsl("gmsh --version 2>&1", check=False)
    status["gmsh_wsl"] = (r.stdout or r.stderr or "").strip() or None

    for pkg in ("gmsh", "pyvista", "meshio", "numpy", "matplotlib", "fluidfoam"):
        try:
            __import__(pkg)
            status["python_packages"][pkg] = True
        except ImportError:
            status["python_packages"][pkg] = False
    return status


def ccx_binary() -> str:
    """Return the CalculiX executable name available in WSL."""
    r = run_wsl("command -v ccx_2.21 || command -v ccx", check=False)
    name = (r.stdout or "").strip().split("/")[-1]
    return name or "ccx"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="Verify solver toolchain, print JSON status")
    ap.add_argument("--run", type=str, help="Command to run inside WSL")
    ap.add_argument("--cwd", type=str, default=None, help="Windows working directory for --run")
    ap.add_argument("--openfoam", action="store_true", help="Source the OpenFOAM environment first")
    ap.add_argument("--timeout", type=int, default=None, help="Timeout in seconds")
    args = ap.parse_args()

    if args.check:
        status = check_environment()
        print(json.dumps(status, indent=2))
        ok = status["wsl"] and status["openfoam"] and status["calculix"]
        return 0 if ok else 1

    if args.run:
        r = run_wsl(args.run, cwd=args.cwd, openfoam=args.openfoam, timeout=args.timeout, check=False)
        sys.stdout.write(r.stdout or "")
        sys.stderr.write(r.stderr or "")
        return r.returncode

    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
