#!/usr/bin/env python3
"""Generate the study mesh at a chosen refinement level and report stats.

Examples:
    python generate_mesh.py --study baseline --level medium
    python generate_mesh.py --study baseline --factor 0.6   # custom refinement
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from marine_exhaust_geometry import generate_mesh  # noqa: E402
from study_pipeline import study_dir, load_params  # noqa: E402

LEVELS = {"coarse": 1.3, "medium": 1.0, "fine": 0.72}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True)
    ap.add_argument("--level", choices=sorted(LEVELS), default="medium")
    ap.add_argument("--factor", type=float, default=None,
                    help="Explicit mesh_size_factor (overrides --level)")
    ap.add_argument("--out", default=None, help="Output .msh path (default mesh/exhaust.msh)")
    args = ap.parse_args()

    factor = args.factor if args.factor is not None else LEVELS[args.level]
    cfg = load_params(args.study)
    out = Path(args.out) if args.out else study_dir(args.study) / "mesh" / "exhaust.msh"

    print(f"Meshing study '{args.study}' (factor {factor}) ...")
    stats = generate_mesh(cfg.get("geometry", {}), out, factor)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
