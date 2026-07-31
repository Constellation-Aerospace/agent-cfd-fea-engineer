#!/usr/bin/env python3
"""Generate the conformal multi-component mesh from the assembly manifest.

Examples:
    python mesh_assembly.py --study hx --level medium
    python mesh_assembly.py --study hx --factor 0.6   # custom refinement
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from cht_pipeline import load_manifest, study_dir  # noqa: E402
from step_assembly import mesh_assembly  # noqa: E402

LEVELS = {"coarse": 1.3, "medium": 1.0, "fine": 0.72}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True)
    ap.add_argument("--level", choices=sorted(LEVELS), default="medium")
    ap.add_argument("--factor", type=float, default=None,
                    help="Explicit mesh_size_factor (overrides --level)")
    ap.add_argument("--out", default=None, help="Output .msh (default mesh/assembly.msh)")
    args = ap.parse_args()

    factor = args.factor if args.factor is not None else LEVELS[args.level]
    manifest = load_manifest(args.study)
    out = Path(args.out) if args.out else study_dir(args.study) / "mesh" / "assembly.msh"

    print(f"Meshing assembly for study '{args.study}' (factor {factor}) ...")
    stats = mesh_assembly(manifest, out, factor)
    print(json.dumps(stats, indent=2))
    print("\nNext: python .github/skills/conjugate_heat_transfer/scripts/setup_cht_case.py "
          f"--study {args.study} --reuse-mesh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
