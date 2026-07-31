#!/usr/bin/env python3
"""End-to-end CFD study pipeline: geometry -> mesh -> case -> solve -> KPIs.

Shared by the multiphase_cfd, meshing (mesh independence), and parametric_study
skills. Outputs are organised project-wise: a "study" is one folder under its
project, and the study slug may contain "/" to scope it (preferred):

    outputs/<project>/<study-slug>/     e.g. --study marine-exhaust-cfd/baseline
        params.json            study configuration (solver cfg + geometry)
        mesh/exhaust.msh       Gmsh mesh (v2.2)
        case/                  OpenFOAM case (runs inside WSL)
        figures/               PNG plots
        report/                generated report
"""
from __future__ import annotations

import csv
import glob
import json
import shutil
import time
from pathlib import Path

from foam_case import write_case, fix_boundary_types, parse_checkmesh, merged_config
from marine_exhaust_geometry import generate_mesh
from wsl_bridge import run_foam, run_wsl

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = REPO_ROOT / "outputs"


def study_dir(slug: str) -> Path:
    d = OUTPUTS / slug          # slug may be "project/study" (nested is preferred)
    d.mkdir(parents=True, exist_ok=True)
    return d


def flat_slug(slug: str) -> str:
    """Filesystem-flat form of a possibly nested slug (WSL scratch dirs)."""
    return slug.strip("/").replace("/", "--").replace(" ", "_")


def load_params(slug: str) -> dict:
    f = study_dir(slug) / "params.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_params(slug: str, cfg: dict) -> None:
    (study_dir(slug) / "params.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def prepare(slug: str, cfg: dict | None = None, mesh_size_factor: float = 1.0,
            reuse_mesh: bool = False) -> dict:
    """Geometry + mesh + OpenFOAM case, converted and initialised. Returns summary."""
    d = study_dir(slug)
    cfg = merged_config({**load_params(slug), **(cfg or {})})
    save_params(slug, cfg)

    msh = d / "mesh" / "exhaust.msh"
    if not (reuse_mesh and msh.exists()):
        mesh_stats = generate_mesh(cfg["geometry"], msh, mesh_size_factor)
    else:
        mesh_stats = json.loads(msh.with_suffix(".stats.json").read_text(encoding="utf-8"))

    case = d / "case"
    if case.exists():
        shutil.rmtree(case)
    case.mkdir(parents=True)
    write_case(case, cfg)

    run_foam("gmshToFoam", case, "../mesh/exhaust.msh")
    fix_boundary_types(case)
    check_tail = run_foam("checkMesh", case)
    check = parse_checkmesh((case / "log.checkMesh").read_text(encoding="utf-8", errors="replace"))

    # initialise fields: 0.orig -> 0, then set water column + hot gas pipe
    if (case / "0").exists():
        shutil.rmtree(case / "0")
    shutil.copytree(case / "0.orig", case / "0")
    run_foam("setFields", case)

    summary = {"study": slug, "mesh": mesh_stats, "checkMesh": check,
               "case_dir": str(case)}
    (d / "prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if not check["ok"]:
        summary["warning"] = "checkMesh reported failures — inspect case/log.checkMesh"
    return summary


def solve(slug: str, n_procs: int | None = None, time_limit_s: int = 14400,
          end_time_s: float | None = None) -> dict:
    """Run compressibleInterFoam, reconstruct, export VTK.

    The case is copied to the WSL-native filesystem (~/foamruns/<slug>) for the run:
    OpenFOAM cannot tolerate spaces in /mnt/c paths under mpirun, and native ext4 I/O
    is far faster than drvfs for OpenFOAM's many small files. Results are copied back.
    """
    from wsl_bridge import win_to_wsl, run_wsl

    d = study_dir(slug)
    case = d / "case"
    cfg = load_params(slug)
    np_ = n_procs if n_procs is not None else int(cfg.get("n_procs", 6))

    if end_time_s is not None:
        cd = case / "system" / "controlDict"
        text = cd.read_text(encoding="utf-8")
        import re
        text = re.sub(r"endTime\s+[\d.eE+-]+;", f"endTime         {end_time_s};", text, count=1)
        cd.write_text(text, encoding="utf-8")

    wsl_case = win_to_wsl(case)
    work = f"/root/foamruns/{flat_slug(slug)}"
    if np_ > 1:
        solver = (f"decomposePar -force > log.decomposePar 2>&1 && "
                  f"mpirun --allow-run-as-root --use-hwthread-cpus -np {np_} compressibleInterFoam -parallel "
                  f"> log.compressibleInterFoam 2>&1 && "
                  f"reconstructPar > log.reconstructPar 2>&1")
    else:
        solver = "compressibleInterFoam > log.compressibleInterFoam 2>&1"

    script = (
        f"set -e; rm -rf {work}; mkdir -p /root/foamruns; "
        f"cp -r '{wsl_case}' {work}; cd {work}; rm -rf processor* VTK; "
        f"set +e; ( {solver} && foamToVTK -fields '(U T p p_rgh alpha.water)' "
        f"> log.foamToVTK 2>&1 ); rc=$?; set -e; "
        f"rm -rf processor*; cp -r {work}/. '{wsl_case}/'; "
        f"if [ $rc -eq 0 ]; then rm -rf {work}; fi; exit $rc"
    )
    t0 = time.time()
    run_wsl(script, openfoam=True, timeout=time_limit_s + 3600)
    elapsed = time.time() - t0

    log = (case / "log.compressibleInterFoam").read_text(encoding="utf-8", errors="replace")
    import re
    times = re.findall(r"^Time = ([\deE+.-]+)", log, re.M)
    courant = re.findall(r"Courant Number mean: ([\deE+.-]+) max: ([\deE+.-]+)", log)
    summary = {
        "study": slug,
        "completed": "End" in log.splitlines()[-1] or "Finalising" in log[-2000:] or bool(times),
        "final_time_s": float(times[-1]) if times else 0.0,
        "n_timesteps": len(times),
        "max_courant_final": float(courant[-1][1]) if courant else None,
        "wall_clock_s": round(elapsed, 1),
        "n_procs": np_,
    }
    (d / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


# ─────────────────────────────── KPI extraction ──────────────────────────────

def read_inlet_pressure(slug: str) -> tuple[list[float], list[float]]:
    """Time history of area-averaged inlet pressure [Pa]."""
    pattern = str(study_dir(slug) / "case" / "postProcessing" / "inletPressure" / "*" / "surfaceFieldValue*.dat")
    ts, ps = [], []
    for f in sorted(glob.glob(pattern)):
        for line in Path(f).read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                ts.append(float(parts[0]))
                ps.append(float(parts[1]))
    return ts, ps


def read_line_sample(slug: str, set_name: str, time_dir: str | None = None) -> dict:
    """Read a sampled line CSV (jetAxis / plumeRise) at a given (default latest) time."""
    base = study_dir(slug) / "case" / "postProcessing" / "jetSamples"
    if not base.exists():
        return {}
    times = sorted((p.name for p in base.iterdir() if p.is_dir()), key=float)
    if not times:
        return {}
    tsel = time_dir or times[-1]
    files = list((base / tsel).glob(f"{set_name}*.csv"))
    if not files:
        return {}
    with open(files[0], newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    cols: dict[str, list[float]] = {}
    for row in rows:
        for k, v in row.items():
            try:
                cols.setdefault(k, []).append(float(v))
            except (TypeError, ValueError):
                pass
    cols["_time"] = [float(tsel)]
    cols["_available_times"] = [float(t) for t in times]
    return cols


def extract_kpis(slug: str) -> dict:
    """Headline engineering KPIs for comparison across runs/meshes."""
    cfg = load_params(slug)
    p_atm = float(cfg.get("p_atm", 101325.0))
    rho_w = float(cfg.get("rho_water", 1025.0))
    geo = cfg.get("geometry", {})
    Hs = float(geo.get("submergence", 2.0))
    hydrostatic = rho_w * 9.81 * Hs

    kpis: dict = {"study": slug}
    ts, ps = read_inlet_pressure(slug)
    if ts:
        n_tail = max(1, len(ps) // 5)
        mean_tail = sum(ps[-n_tail:]) / n_tail
        kpis["back_pressure_abs_Pa"] = round(mean_tail, 1)
        kpis["back_pressure_gauge_Pa"] = round(mean_tail - p_atm, 1)
        kpis["back_pressure_above_hydrostatic_Pa"] = round(mean_tail - p_atm - hydrostatic, 1)
        kpis["hydrostatic_ref_Pa"] = round(hydrostatic, 1)

    axis = read_line_sample(slug, "jetAxis")
    if axis:
        xs = axis.get("x", [])
        Ts = axis.get("T", [])
        if xs and Ts:
            T_amb = float(cfg.get("T_water_C", 15.0)) + 273.15
            T_exh = float(cfg.get("T_exhaust_C", 400.0)) + 273.15
            kpis["T_max_axis_K"] = round(max(Ts), 2)
            # decay length: distance to 10% excess temperature
            target = T_amb + 0.10 * (T_exh - T_amb)
            decay_x = next((x for x, T in zip(xs, Ts) if T <= target), None)
            x0 = xs[0]
            kpis["thermal_decay_length_10pct_m"] = round(decay_x - x0, 3) if decay_x is not None else None
            kpis["kpi_sample_time_s"] = axis["_time"][0]
    return kpis
