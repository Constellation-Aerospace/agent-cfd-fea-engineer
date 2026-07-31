#!/usr/bin/env python3
"""Exhaust back-pressure analysis: inlet pressure history, mean, hydrostatic split.

Example:
    python back_pressure.py --study baseline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from study_pipeline import study_dir, load_params, read_inlet_pressure, extract_kpis  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True)
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = study_dir(args.study)
    cfg = load_params(args.study)
    ts, ps = read_inlet_pressure(args.study)
    if not ts:
        print("ERROR: no inletPressure history — has the case been run?")
        return 1

    kpis = extract_kpis(args.study)
    p_atm = cfg.get("p_atm", 101325.0)
    hydro = kpis.get("hydrostatic_ref_Pa", 0.0)

    fig_dir = d / "figures"
    fig_dir.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(ts, [p / 1000 for p in ps], lw=1.0, label="inlet area-avg pressure")
    ax.axhline((p_atm + hydro) / 1000, color="grey", ls="--", lw=0.9,
               label=f"atm + hydrostatic ({(p_atm + hydro)/1000:.1f} kPa)")
    if "back_pressure_abs_Pa" in kpis:
        ax.axhline(kpis["back_pressure_abs_Pa"] / 1000, color="crimson", ls=":", lw=0.9,
                   label=f"tail mean ({kpis['back_pressure_abs_Pa']/1000:.1f} kPa)")
    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Pressure [kPa abs]")
    ax.set_title(f"Exhaust back-pressure — {args.study}")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(fig_dir / "back_pressure.png", dpi=150)
    plt.close(fig)

    (d / "kpis.json").write_text(json.dumps(kpis, indent=2), encoding="utf-8")
    print(json.dumps(kpis, indent=2))
    print(f"Figure: {fig_dir / 'back_pressure.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
