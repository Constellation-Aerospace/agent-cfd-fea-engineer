#!/usr/bin/env python3
"""Assemble the transient histories of a staged CHT run into CSV + PNG.

Reads every function-object output written across all restart segments
(postProcessing/<region>/minMaxT_<region>/<startTime>/fieldMinMax*.dat and
.../wallHeatFlux_<region>/<startTime>/wallHeatFlux*.dat), de-duplicates
overlapping times, and writes:

    <study>/figures/transient_T_history.csv     time, per-region T_min/T_max [C]
    <study>/figures/transient_Q_history.csv     time, per-patch integral heat flux [W]
    <study>/figures/transient_temperatures.png  T_max(t) per region
    <study>/figures/transient_heat_balance.png  external patch heat flux vs time

Usage:
    python transient_history.py --study balloon-ttp/transient-0-20km
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent


def read_minmax(case: Path) -> dict[str, dict[float, tuple[float, float]]]:
    """region -> {time: (T_min_K, T_max_K)}"""
    out: dict[str, dict[float, tuple[float, float]]] = {}
    for f in sorted(case.glob("postProcessing/*/minMaxT_*/*/fieldMinMax*.dat")):
        region = f.parents[2].name
        series = out.setdefault(region, {})
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            if len(p) >= 3:
                try:
                    series[float(p[0])] = (float(p[1]), float(p[2]))
                except ValueError:
                    continue
    return out


def read_heatflux(case: Path) -> dict[str, dict[float, float]]:
    """'<region>:<patch>' -> {time: integral_W}"""
    out: dict[str, dict[float, float]] = {}
    for f in sorted(case.glob("postProcessing/*/wallHeatFlux_*/*/wallHeatFlux*.dat")):
        region = f.parents[2].name
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            if len(p) >= 5:
                try:
                    out.setdefault(f"{region}:{p[1]}", {})[float(p[0])] = float(p[4])
                except ValueError:
                    continue
    return out


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True)
    ap.add_argument("--highlight", default="",
                    help="Comma-separated regions to emphasise in the T plot")
    args = ap.parse_args()

    study = REPO_ROOT / "outputs" / args.study
    case = study / "case"
    figs = study / "figures"

    temps = read_minmax(case)
    fluxes = read_heatflux(case)
    if not temps:
        raise SystemExit(f"No fieldMinMax output under {case/'postProcessing'}")

    times = sorted({t for s in temps.values() for t in s})
    regions = sorted(temps)
    rows = []
    for t in times:
        row: list = [t]
        for r in regions:
            v = temps[r].get(t)
            row += ["" if v is None else round(v[0] - 273.15, 4),
                    "" if v is None else round(v[1] - 273.15, 4)]
        rows.append(row)
    header = ["time_s"] + [f"{r}_{k}_C" for r in regions for k in ("Tmin", "Tmax")]
    write_csv(figs / "transient_T_history.csv", header, rows)

    if fluxes:
        ftimes = sorted({t for s in fluxes.values() for t in s})
        patches = sorted(fluxes)
        frows = [[t] + [fluxes[p].get(t, "") for p in patches] for t in ftimes]
        write_csv(figs / "transient_Q_history.csv", ["time_s"] + patches, frows)

    hi = {s.strip() for s in args.highlight.split(",") if s.strip()}
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for r in regions:
        ts = sorted(temps[r])
        ys = [temps[r][t][1] - 273.15 for t in ts]
        ax.plot(ts, ys, lw=2.2 if r in hi else 1.0,
                alpha=1.0 if (r in hi or not hi) else 0.45, label=r)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("region maximum temperature [degC]")
    ax.set_title(f"Transient region temperatures — {args.study}")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(figs / "transient_temperatures.png", dpi=150)

    ext = {p: s for p, s in fluxes.items() if "_to_" not in p.split(":", 1)[1]}
    if ext:
        fig2, ax2 = plt.subplots(figsize=(9, 5))
        for p, s in sorted(ext.items()):
            ts = sorted(s)
            ax2.plot(ts, [s[t] for t in ts], lw=1.4, label=p)
        ax2.set_xlabel("time [s]")
        ax2.set_ylabel("integrated wall heat flux [W]")
        ax2.set_title(f"External heat exchange — {args.study}")
        ax2.grid(alpha=0.3)
        ax2.legend(fontsize=7)
        fig2.tight_layout()
        fig2.savefig(figs / "transient_heat_balance.png", dpi=150)

    print(f"regions: {len(regions)}   time samples: {len(times)}   "
          f"t_end: {times[-1] if times else 0}")
    print(f"wrote {figs/'transient_T_history.csv'}")
    if fluxes:
        print(f"wrote {figs/'transient_Q_history.csv'}")
    print(f"wrote {figs/'transient_temperatures.png'}")
    if ext:
        print(f"wrote {figs/'transient_heat_balance.png'}")
    for r in regions:
        last = max(temps[r])
        print(f"  {r:<20} T_max({last:g}s) = {temps[r][last][1]-273.15:8.3f} C")
    return 0


if __name__ == "__main__":
    sys.exit(main())
