#!/usr/bin/env python3
"""Conjugate heat transfer study pipeline: STEP assembly -> multi-region mesh ->
chtMultiRegion case -> solve -> heat-exchanger KPIs.

Outputs are organised project-wise; the study slug may contain "/" to scope the
study under its project (preferred), e.g. --study acme-hx/baseline:

    outputs/<project>/<study-slug>/
        assembly/manifest.json   components, materials, BCs (step_assembly.py)
        assembly/surfaces.json   surface listing to help patch selection
        mesh/assembly.msh        conformal multi-component Gmsh mesh (v2.2)
        case/                    multi-region OpenFOAM case (runs inside WSL)
        cht_kpis.json            heat duty, effectiveness, LMTD, UA, balances
"""
from __future__ import annotations

import json
import math
import re
import shutil
import time
from pathlib import Path

from cht_case import (write_skeleton, write_regions, merged_solver, region_map,
                      patches_for)
from foam_case import parse_checkmesh
from step_assembly import inspect_step, mesh_assembly, validate_manifest
from study_pipeline import flat_slug
from wsl_bridge import run_foam, run_wsl, win_to_wsl

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = REPO_ROOT / "outputs"


def study_dir(slug: str) -> Path:
    d = OUTPUTS / slug          # slug may be "project/study" (nested is preferred)
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifest_path(slug: str) -> Path:
    return study_dir(slug) / "assembly" / "manifest.json"


def load_manifest(slug: str) -> dict:
    f = manifest_path(slug)
    if not f.exists():
        raise FileNotFoundError(
            f"No assembly manifest for study '{slug}'. Run the step_assembly "
            f"inspect script on the STEP file first.")
    return json.loads(f.read_text(encoding="utf-8"))


def save_manifest(slug: str, manifest: dict) -> None:
    f = manifest_path(slug)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def inspect(slug: str, step_file: str | Path) -> dict:
    return inspect_step(step_file, study_dir(slug) / "assembly")


# ─────────────────────────────── prepare ─────────────────────────────────────

def prepare(slug: str, mesh_size_factor: float = 1.0, reuse_mesh: bool = False) -> dict:
    """Mesh the assembly, build and initialise the multi-region case."""
    d = study_dir(slug)
    manifest = load_manifest(slug)
    problems = validate_manifest(manifest)
    if problems:
        raise RuntimeError("Manifest not ready:\n  - " + "\n  - ".join(problems))

    msh = d / "mesh" / "assembly.msh"
    if reuse_mesh and msh.exists():
        mesh_stats = json.loads(msh.with_suffix(".stats.json").read_text(encoding="utf-8"))
    else:
        mesh_stats = mesh_assembly(manifest, msh, mesh_size_factor)

    case = d / "case"
    if case.exists():
        shutil.rmtree(case)
    case.mkdir(parents=True)
    write_skeleton(case, manifest)

    run_foam("gmshToFoam", case, "../mesh/assembly.msh")
    check_tail = run_foam("checkMesh", case)
    check = parse_checkmesh((case / "log.checkMesh").read_text(encoding="utf-8",
                                                               errors="replace"))
    run_foam("splitMeshRegions", case, "-cellZones -overwrite")
    region_info = write_regions(case, manifest, patch_areas=mesh_stats.get("patches"))

    summary = {"study": slug, "mesh": mesh_stats, "checkMesh": check,
               **region_info, "case_dir": str(case)}
    (d / "prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if not check["ok"]:
        summary["warning"] = "checkMesh reported failures — inspect case/log.checkMesh"
    return summary


# ─────────────────────────────── solve ───────────────────────────────────────

def solve(slug: str, n_procs: int | None = None, time_limit_s: int = 14400,
          iterations: int | None = None, end_time_s: float | None = None) -> dict:
    """Run the chtMultiRegion solver inside WSL-native storage, copy results back."""
    d = study_dir(slug)
    case = d / "case"
    manifest = load_manifest(slug)
    slv = merged_solver(manifest)
    app = ("chtMultiRegionSimpleFoam" if slv["mode"] == "steady" else "chtMultiRegionFoam")
    np_ = n_procs if n_procs is not None else int(slv["n_procs"])

    stop_at = iterations if slv["mode"] == "steady" else end_time_s
    if stop_at is not None:
        cd = case / "system" / "controlDict"
        text = re.sub(r"endTime\s+[\d.eE+-]+;", f"endTime         {stop_at};",
                      cd.read_text(encoding="utf-8"), count=1)
        cd.write_text(text, encoding="utf-8")

    wsl_case = win_to_wsl(case)
    work = f"/root/foamruns/{flat_slug(slug)}"
    if np_ > 1:
        solver = (f"decomposePar -allRegions -force > log.decomposePar 2>&1 && "
                  f"mpirun --allow-run-as-root --use-hwthread-cpus -np {np_} {app} -parallel "
                  f"> log.{app} 2>&1 && "
                  f"reconstructPar -allRegions > log.reconstructPar 2>&1")
    else:
        solver = f"{app} > log.{app} 2>&1"
    script = (
        f"set -e; rm -rf {work}; mkdir -p /root/foamruns; "
        f"cp -r '{wsl_case}' {work}; cd {work}; rm -rf processor* VTK; "
        f"set +e; ( {solver} && foamToVTK -allRegions > log.foamToVTK 2>&1 ); rc=$?; set -e; "
        f"rm -rf processor*; cp -r {work}/. '{wsl_case}/'; "
        f"if [ $rc -eq 0 ]; then rm -rf {work}; fi; exit $rc"
    )
    t0 = time.time()
    run_wsl(script, openfoam=True, timeout=time_limit_s + 3600)
    elapsed = time.time() - t0

    log = (case / f"log.{app}").read_text(encoding="utf-8", errors="replace")
    times = re.findall(r"^Time = ([\deE+.-]+)", log, re.M)
    summary = {
        "study": slug, "application": app, "mode": slv["mode"],
        "completed": bool(times) and ("End" in log[-2000:] or "Finalising" in log[-2000:]),
        "final_time": float(times[-1]) if times else 0.0,
        "n_steps": len(times),
        "wall_clock_s": round(elapsed, 1),
        "n_procs": np_,
        "final_residuals": _final_residuals(log),
    }
    (d / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _final_residuals(log: str) -> dict:
    """Last initial residual per (region, field) — convergence at a glance."""
    region = None
    out: dict[str, float] = {}
    for line in log.splitlines():
        m = re.match(r"\s*Solving for (?:fluid|solid) region (\w+)", line)
        if m:
            region = m.group(1)
        m = re.search(r"Solving for (\w+), Initial residual = ([\deE+.-]+)", line)
        if m and region:
            out[f"{region}/{m.group(1)}"] = float(m.group(2))
    return out


# ─────────────────────────────── KPI extraction ──────────────────────────────

def _find_fo_files(case: Path, fo_name: str, file_glob: str) -> list[Path]:
    """Locate function-object output regardless of the region-nesting layout."""
    hits = []
    for base in case.glob("postProcessing/**/" + fo_name):
        if base.is_dir():
            hits.extend(base.glob("**/" + file_glob))
    return sorted(hits)


def _last_scalar(files: list[Path]) -> float | None:
    """Final 'time value' row across a series of .dat files."""
    val = None
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    val = float(parts[1])
                except ValueError:
                    pass
    return val


def _wall_heat_flux(files: list[Path]) -> dict[str, float]:
    """patch -> last integrated heat flux [W] from a wallHeatFlux .dat series."""
    out: dict[str, float] = {}
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 5:
                try:
                    out[parts[1]] = float(parts[4])
                except ValueError:
                    pass
    return out


def extract_cht_kpis(slug: str) -> dict:
    """Heat-exchanger KPIs: per-stream heat duty, effectiveness, LMTD, UA,
    energy balance, interface fluxes, per-region temperature extremes."""
    d = study_dir(slug)
    case = d / "case"
    manifest = load_manifest(slug)
    regions = region_map(manifest)
    kpis: dict = {"study": slug, "streams": {}, "regions": {}, "interfaces_W": {}}

    # per fluid stream: m_dot, T_in, T_out, Q = m_dot cp (T_out - T_in)
    for r, info in regions.items():
        if info["type"] != "fluid":
            continue
        bcs = patches_for(manifest, r)
        inlet = next((p for p, b in bcs.items() if b.get("type") == "velocity_inlet"), None)
        outlet = next((p for p, b in bcs.items() if b.get("type") == "pressure_outlet"), None)
        if not (inlet and outlet):
            continue
        m_in = _last_scalar(_find_fo_files(case, f"massFlow_{inlet}", "surfaceFieldValue*.dat"))
        T_in = _last_scalar(_find_fo_files(case, f"Tbulk_{inlet}", "surfaceFieldValue*.dat"))
        T_out = _last_scalar(_find_fo_files(case, f"Tbulk_{outlet}", "surfaceFieldValue*.dat"))
        if None in (m_in, T_in, T_out):
            continue
        cp = info["props"]["cp"]
        m_dot = abs(m_in)
        Q = m_dot * cp * (T_out - T_in)
        kpis["streams"][r] = {
            "inlet": inlet, "outlet": outlet,
            "m_dot_kg_s": round(m_dot, 6), "cp_J_kgK": cp,
            "T_in_C": round(T_in - 273.15, 3), "T_out_C": round(T_out - 273.15, 3),
            "Q_W": round(Q, 2),
        }

    streams = kpis["streams"]
    if len(streams) >= 2:
        hot = max(streams, key=lambda s: streams[s]["T_in_C"])
        cold = min(streams, key=lambda s: streams[s]["T_in_C"])
        sh, sc = streams[hot], streams[cold]
        Q_hot, Q_cold = -sh["Q_W"], sc["Q_W"]          # both positive if HX works
        Q_avg = 0.5 * (Q_hot + Q_cold)
        C_hot = sh["m_dot_kg_s"] * sh["cp_J_kgK"]
        C_cold = sc["m_dot_kg_s"] * sc["cp_J_kgK"]
        C_min = min(C_hot, C_cold)
        dT_max = sh["T_in_C"] - sc["T_in_C"]
        dT1 = sh["T_in_C"] - sc["T_out_C"]
        dT2 = sh["T_out_C"] - sc["T_in_C"]
        if dT1 > 0 and dT2 > 0:
            lmtd = (dT1 - dT2) / math.log(dT1 / dT2) if abs(dT1 - dT2) > 1e-9 else dT1
        else:
            lmtd = None
        kpis["heat_exchanger"] = {
            "hot_stream": hot, "cold_stream": cold,
            "Q_hot_W": round(Q_hot, 2), "Q_cold_W": round(Q_cold, 2),
            "Q_avg_W": round(Q_avg, 2),
            "energy_imbalance_pct": round(
                100 * abs(Q_hot - Q_cold) / max(abs(Q_avg), 1e-12), 2),
            "effectiveness": (round(Q_avg / (C_min * dT_max), 4)
                              if C_min * dT_max > 0 else None),
            "LMTD_K": round(lmtd, 3) if lmtd else None,
            "UA_W_K": round(Q_avg / lmtd, 2) if lmtd else None,
        }

    for r in regions:
        whf = _wall_heat_flux(_find_fo_files(case, f"wallHeatFlux_{r}", "wallHeatFlux*.dat"))
        for patch, q in whf.items():
            if "_to_" in patch:
                kpis["interfaces_W"][f"{r}:{patch}"] = round(q, 2)
        tmin = _last_scalar(_find_fo_files(case, f"minMaxT_{r}", "fieldMinMax*.dat"))
        entry: dict = {}
        if tmin is not None:
            entry["T_min_C"] = round(tmin - 273.15, 3)
        mx = _minmax_max(_find_fo_files(case, f"minMaxT_{r}", "fieldMinMax*.dat"))
        if mx is not None:
            entry["T_max_C"] = round(mx - 273.15, 3)
        if entry:
            kpis["regions"][r] = entry

    (d / "cht_kpis.json").write_text(json.dumps(kpis, indent=2), encoding="utf-8")
    return kpis


def _minmax_max(files: list[Path]) -> float | None:
    """fieldMinMax .dat rows: time field min [location...] max [location...] —
    with 'location no' the row is: time field min max."""
    val = None
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            nums = []
            for p in parts:
                try:
                    nums.append(float(p))
                except ValueError:
                    pass
            if len(nums) >= 3:
                val = nums[-1]
    return val
