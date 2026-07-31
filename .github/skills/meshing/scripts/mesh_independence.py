#!/usr/bin/env python3
"""Mesh independence study: 3 refinement levels -> short solve -> KPI comparison + GCI.

Creates sibling studies <study>-mesh-coarse|medium|fine, each with identical physics
but scaled mesh, runs each for --sim-time seconds of physical time, then compares
KPIs and computes the Grid Convergence Index (Roache, safety factor 1.25).

Example:
    python mesh_independence.py --study baseline --sim-time 1.0 --np 6
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from study_pipeline import prepare, solve, extract_kpis, load_params, save_params, study_dir  # noqa: E402

LEVELS = [("coarse", 1.3), ("medium", 1.0), ("fine", 0.72)]
KPI_KEYS = ["back_pressure_gauge_Pa", "T_max_axis_K", "thermal_decay_length_10pct_m"]


def gci(f_coarse: float, f_medium: float, f_fine: float, r: float = 1.35) -> dict:
    """Grid Convergence Index for three solutions with (approx) constant ratio r."""
    e21 = f_medium - f_fine
    e32 = f_coarse - f_medium
    if abs(e21) < 1e-12 or e32 * e21 <= 0:
        return {"order_p": None, "gci_fine_pct": None,
                "note": "non-monotone or converged to machine tolerance"}
    p = math.log(abs(e32 / e21)) / math.log(r)
    gci_fine = 1.25 * abs(e21 / f_fine) / (r ** p - 1) * 100 if f_fine else None
    return {"order_p": round(p, 2), "gci_fine_pct": round(gci_fine, 2) if gci_fine else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True, help="Base study whose physics to use")
    ap.add_argument("--sim-time", type=float, default=1.0, help="Physical end time per level [s]")
    ap.add_argument("--np", type=int, default=6, help="MPI ranks per run")
    ap.add_argument("--time-limit", type=int, default=14400, help="Wall-clock limit per run [s]")
    args = ap.parse_args()

    base_cfg = load_params(args.study)
    results = []
    for level, factor in LEVELS:
        slug = f"{args.study}-mesh-{level}"
        print(f"\n=== Level '{level}' (factor {factor}) -> study {slug} ===")
        save_params(slug, base_cfg)
        prep = prepare(slug, {"end_time_s": args.sim_time, "n_procs": args.np},
                       mesh_size_factor=factor)
        print(f"  cells: {prep['checkMesh'].get('cells')}, "
              f"maxNonOrtho: {prep['checkMesh'].get('max_non_ortho')}")
        run = solve(slug, n_procs=args.np, time_limit_s=args.time_limit)
        print(f"  solved to t={run['final_time_s']} s in {run['wall_clock_s']} s wall")
        kpis = extract_kpis(slug)
        results.append({"level": level, "factor": factor,
                        "cells": prep["checkMesh"].get("cells"), **kpis})

    report: dict = {"levels": results, "gci": {}}
    for key in KPI_KEYS:
        vals = [r.get(key) for r in results]
        if all(isinstance(v, (int, float)) for v in vals):
            report["gci"][key] = gci(vals[0], vals[1], vals[2])
            f_med, f_fine = vals[1], vals[2]
            if f_fine:
                report["gci"][key]["medium_vs_fine_pct"] = round(
                    abs(f_med - f_fine) / abs(f_fine) * 100, 2)

    out_json = study_dir(args.study) / "mesh_independence.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    out_csv = study_dir(args.study) / "mesh_independence.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print("\n=== Mesh independence summary ===")
    print(json.dumps(report["gci"], indent=2))
    print(f"Full results: {out_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
