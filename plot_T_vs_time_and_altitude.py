#!/usr/bin/env python3
"""Per-component temperature vs. mission time AND vs. altitude, side by side.

Reads the study's `figures/transient_T_history.csv` (written by
`transient_history.py`) and plots each region's maximum temperature twice: once
against mission time, once against altitude (derived from a constant-rate ascent
to a capped altitude, then a flat dwell — the same assumption every transient
study in this project uses). Deliberately two panels sharing one y-axis rather
than a single dual-x-axis plot: altitude is a monotonic, non-injective function
of time (flat during the dwell), so overlaying both x-axes on one plot would
imply a false one-to-one mapping.

Usage:
    python plot_T_vs_time_and_altitude.py --study balloon-ttp/transient-shorter-strap-40km-3hr \
        --ascent-rate-m-s 5.5556 --alt-cap-m 40000 \
        --highlight jetson_module,interface_plate,strap_top,strap_bottom,radiator_plate_top,radiator_plate_bottom
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


def read_T_history(csv_path: Path) -> tuple[list[float], dict[str, list[float]]]:
    """-> (times_s, {region: [Tmax_C, ...]}) from transient_T_history.csv."""
    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        regions = [h[:-len("_Tmax_C")] for h in header if h.endswith("_Tmax_C")]
        idx = {r: header.index(f"{r}_Tmax_C") for r in regions}
        times, series = [], {r: [] for r in regions}
        for row in reader:
            if not row:
                continue
            times.append(float(row[0]))
            for r in regions:
                v = row[idx[r]]
                series[r].append(float(v) if v != "" else float("nan"))
    return times, series


def altitude_of(t: float, rate_m_s: float, alt_cap_m: float) -> float:
    return min(alt_cap_m, rate_m_s * t)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True)
    ap.add_argument("--ascent-rate-m-s", type=float, required=True,
                    help="Constant assumed ascent rate [m/s]")
    ap.add_argument("--alt-cap-m", type=float, required=True,
                    help="Altitude the ascent caps at (dwell altitude) [m]")
    ap.add_argument("--highlight", default="",
                    help="Comma-separated regions to emphasise (bold, opaque)")
    ap.add_argument("--out", default=None,
                    help="Output PNG (default: <study>/figures/T_vs_time_and_altitude.png)")
    args = ap.parse_args()

    study = REPO_ROOT / "outputs" / args.study
    csv_path = study / "figures" / "transient_T_history.csv"
    if not csv_path.exists():
        raise SystemExit(f"Not found: {csv_path} — run transient_history.py first.")

    times, series = read_T_history(csv_path)
    regions = sorted(series)
    alts = [altitude_of(t, args.ascent_rate_m_s, args.alt_cap_m) for t in times]
    alts_km = [a / 1000.0 for a in alts]

    hi = {s.strip() for s in args.highlight.split(",") if s.strip()}
    # Fixed categorical color per region (assigned once, identical on both panels).
    cmap = plt.get_cmap("tab10" if len(regions) <= 10 else "tab20")
    colors = {r: cmap(i % cmap.N) for i, r in enumerate(regions)}

    fig, (ax_t, ax_a) = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)

    for r in regions:
        lw = 2.2 if r in hi else 1.0
        alpha = 1.0 if (r in hi or not hi) else 0.45
        ax_t.plot(times, series[r], lw=lw, alpha=alpha, color=colors[r], label=r)
        ax_a.plot(alts_km, series[r], lw=lw, alpha=alpha, color=colors[r], label=r)

    ax_t.set_xlabel("mission time [s]")
    ax_t.set_ylabel("component maximum temperature [°C]")
    ax_t.set_title("vs. mission time")
    ax_t.grid(alpha=0.3)

    ax_a.set_xlabel("altitude [km]")
    ax_a.set_title("vs. altitude")
    ax_a.grid(alpha=0.3)
    # Altitude is non-injective (flat during the dwell) -- flag the dwell band so
    # the same altitude read on this axis is not mistaken for a single instant.
    dwell_alt_km = args.alt_cap_m / 1000.0
    if any(a >= args.alt_cap_m for a in alts):
        ax_a.axvline(dwell_alt_km, color="0.6", lw=1.0, ls="--", zorder=0)
        ax_a.text(dwell_alt_km, ax_a.get_ylim()[1] if ax_a.get_ylim()[1] else 0,
                  "  dwell\n  (const. alt.)", va="top", ha="left", fontsize=7, color="0.4")

    handles, labels = ax_t.get_legend_handles_labels()
    ncol = min(len(regions), 5)
    nrows = -(-len(regions) // ncol)  # ceil
    fig.legend(handles, labels, loc="lower center", ncol=ncol, fontsize=8,
              bbox_to_anchor=(0.5, 0.0), frameon=False)
    fig.suptitle(f"Per-component temperature — {args.study}")
    bottom_margin = 0.10 + 0.035 * nrows
    fig.tight_layout(rect=[0, bottom_margin, 1, 1])

    out = Path(args.out) if args.out else study / "figures" / "T_vs_time_and_altitude.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")
    print(f"regions: {len(regions)}   time samples: {len(times)}   "
          f"t_end: {times[-1] if times else 0}   alt_end_km: {alts_km[-1] if alts_km else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
