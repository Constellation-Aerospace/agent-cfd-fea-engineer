#!/usr/bin/env python3
"""Parametric sweep: run each operating point through the full CFD pipeline, compare KPIs.

Example:
    python run_sweep.py --study baseline --matrix sweep.json --sim-time 2.0 --np 6
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from study_pipeline import (prepare, solve, extract_kpis, load_params,  # noqa: E402
                            save_params, study_dir)

KPI_COLS = ["back_pressure_gauge_Pa", "back_pressure_above_hydrostatic_Pa",
            "T_max_axis_K", "thermal_decay_length_10pct_m"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True, help="Base study (physics defaults)")
    ap.add_argument("--matrix", required=True, help="JSON list (inline or file path)")
    ap.add_argument("--sim-time", type=float, default=2.0, help="Physical end time per point [s]")
    ap.add_argument("--np", type=int, default=6)
    ap.add_argument("--mesh-factor", type=float, default=1.0)
    ap.add_argument("--time-limit", type=int, default=14400, help="Wall clock per point [s]")
    args = ap.parse_args()

    p = Path(args.matrix)
    matrix = json.loads(p.read_text(encoding="utf-8")) if p.exists() else json.loads(args.matrix)
    if not isinstance(matrix, list) or not matrix:
        print("ERROR: matrix must be a non-empty JSON list of config dicts")
        return 1

    base_cfg = load_params(args.study)
    rows = []
    for i, point in enumerate(matrix, 1):
        label = point.pop("label", f"p{i:02d}")
        slug = f"{args.study}-{label}"
        print(f"\n=== Point {i}/{len(matrix)}: {label} -> {slug} ===")
        print(f"  overrides: {json.dumps(point)}")
        save_params(slug, base_cfg)
        try:
            prep = prepare(slug, {**point, "end_time_s": args.sim_time, "n_procs": args.np},
                           mesh_size_factor=args.mesh_factor)
            run = solve(slug, n_procs=args.np, time_limit_s=args.time_limit)
            kpis = extract_kpis(slug)
            rows.append({"label": label, "study": slug,
                         "cells": prep["checkMesh"].get("cells"),
                         "final_time_s": run["final_time_s"],
                         "wall_clock_s": run["wall_clock_s"],
                         **{k: kpis.get(k) for k in KPI_COLS},
                         **{f"cfg_{k}": v for k, v in point.items() if not isinstance(v, dict)}})
            print(f"  KPIs: {json.dumps({k: kpis.get(k) for k in KPI_COLS})}")
        except Exception as exc:  # noqa: BLE001 — one failed point must not kill the sweep
            print(f"  POINT FAILED: {exc}")
            rows.append({"label": label, "study": slug, "error": str(exc)[:300]})

    d = study_dir(args.study)
    (d / "parametric_results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    fields = sorted({k for r in rows for k in r}, key=lambda k: (k != "label", k))
    with open(d / "parametric_results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # trend plot: KPIs vs point label
    ok_rows = [r for r in rows if "error" not in r]
    if len(ok_rows) >= 2:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        labels = [r["label"] for r in ok_rows]
        for ax, key in zip(axes.flat, KPI_COLS):
            vals = [r.get(key) for r in ok_rows]
            if any(v is not None for v in vals):
                ax.plot(labels, vals, "o-")
            ax.set_title(key, fontsize=9)
            ax.tick_params(axis="x", rotation=30, labelsize=8)
            ax.grid(alpha=0.3)
        fig.suptitle(f"Parametric trends — {args.study}")
        fig.tight_layout()
        fig_dir = d / "figures"
        fig_dir.mkdir(exist_ok=True)
        fig.savefig(fig_dir / "parametric_trends.png", dpi=150)

    print(f"\nSweep complete: {len(ok_rows)}/{len(rows)} points succeeded.")
    print(f"Results: {d / 'parametric_results.csv'}")
    return 0 if len(ok_rows) == len(rows) else 2


if __name__ == "__main__":
    sys.exit(main())
