#!/usr/bin/env python3
"""Build/validate the parametric exhaust-discharge domain and optionally export STEP.

Examples:
    python build_geometry.py --study baseline
    python build_geometry.py --study deep --set submergence=3.5 --set pipe_diameter=0.35 --export-step
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from marine_exhaust_geometry import DEFAULT_PARAMS, export_step  # noqa: E402
from study_pipeline import study_dir, load_params, save_params  # noqa: E402
from foam_case import merged_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True, help="Study slug under outputs/")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="Geometry parameter override (repeatable)")
    ap.add_argument("--export-step", action="store_true", help="Export domain.step")
    args = ap.parse_args()

    overrides = {}
    for spec in args.set:
        k, v = spec.split("=", 1)
        if k not in DEFAULT_PARAMS:
            print(f"ERROR: unknown geometry parameter '{k}'. Valid: {sorted(DEFAULT_PARAMS)}")
            return 1
        overrides[k] = float(v)

    cfg = merged_config(load_params(args.study))
    cfg["geometry"].update(overrides)

    # sanity checks (same rules build_model enforces)
    g = {**DEFAULT_PARAMS, **cfg["geometry"]}
    Ro = g["pipe_diameter"] / 2 + g["wall_thickness"]
    if not (Ro < g["submergence"] < g["water_depth"] - Ro):
        print(f"ERROR: pipe not fully submerged: need {Ro:.3f} < submergence < "
              f"{g['water_depth'] - Ro:.3f}, got {g['submergence']}")
        return 1

    save_params(args.study, cfg)
    print(f"Geometry parameters saved for study '{args.study}':")
    print(json.dumps(g, indent=2))

    if args.export_step:
        out = study_dir(args.study) / "geometry" / "domain.step"
        export_step(cfg["geometry"], out)
        print(f"STEP exported: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
