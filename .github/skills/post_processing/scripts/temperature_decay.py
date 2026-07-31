#!/usr/bin/env python3
"""Temperature decay along the jet axis and plume-rise line, across written times.

Example:
    python temperature_decay.py --study baseline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from study_pipeline import study_dir, load_params, read_line_sample  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True)
    ap.add_argument("--n-times", type=int, default=5, help="Number of time snapshots to overlay")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = study_dir(args.study)
    cfg = load_params(args.study)
    T_amb = cfg.get("T_water_C", 15.0) + 273.15
    T_exh = cfg.get("T_exhaust_C", 400.0) + 273.15
    fig_dir = d / "figures"
    fig_dir.mkdir(exist_ok=True)

    latest = read_line_sample(args.study, "jetAxis")
    if not latest:
        print("ERROR: no jetAxis samples found — has the case been run?")
        return 1
    all_times = latest["_available_times"]
    pick = all_times[:: max(1, len(all_times) // args.n_times)][-args.n_times:] or all_times

    metrics = {}
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for t in pick:
        data = read_line_sample(args.study, "jetAxis", time_dir=f"{t:g}")
        if not data or "x" not in data or "T" not in data:
            continue
        xs, Ts = data["x"], data["T"]
        x0 = xs[0]
        ax.plot([x - x0 for x in xs], Ts, label=f"t = {t:g} s")
        theta = [(T - T_amb) / (T_exh - T_amb) for T in Ts]
        d10 = next((x - x0 for x, th in zip(xs, theta) if th <= 0.10), None)
        metrics[f"t={t:g}"] = {"T_max_K": round(max(Ts), 2),
                               "decay_length_10pct_m": round(d10, 3) if d10 else None}
    ax.axhline(T_amb, color="grey", ls="--", lw=0.8, label="ambient water")
    ax.set_xlabel("Distance from pipe exit along jet axis [m]")
    ax.set_ylabel("Temperature [K]")
    ax.set_title(f"Jet-axis temperature decay — {args.study}")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "temperature_decay.png", dpi=150)
    plt.close(fig)

    rise = read_line_sample(args.study, "plumeRise")
    if rise and "z" in rise and "T" in rise:
        fig, ax = plt.subplots(figsize=(6, 6.5))
        ax.plot(rise["T"], rise["z"])
        ax.axhline(0, color="steelblue", ls="--", lw=0.8, label="free surface")
        ax.set_xlabel("Temperature [K]")
        ax.set_ylabel("z [m] (0 = free surface)")
        ax.set_title(f"Plume-rise temperature profile (t = {rise['_time'][0]:g} s)")
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(fig_dir / "plume_rise.png", dpi=150)
        plt.close(fig)

    (fig_dir / "decay_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"Figures: {fig_dir / 'temperature_decay.png'}, {fig_dir / 'plume_rise.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
