#!/usr/bin/env python3
"""Set up the multi-region CHT case: assembly mesh -> gmshToFoam ->
splitMeshRegions -> per-region fields/properties from the manifest.

Examples:
    python setup_cht_case.py --study hx
    python setup_cht_case.py --study hx --mesh-factor 0.72   # finer mesh
    python setup_cht_case.py --study hx --reuse-mesh
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from cht_pipeline import prepare  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True, help="Study slug under outputs/")
    ap.add_argument("--mesh-factor", type=float, default=1.0,
                    help="Mesh size factor (1.0 medium, 0.72 fine, 1.3 coarse)")
    ap.add_argument("--reuse-mesh", action="store_true", help="Keep existing mesh")
    args = ap.parse_args()

    summary = prepare(args.study, mesh_size_factor=args.mesh_factor,
                      reuse_mesh=args.reuse_mesh)
    print(json.dumps(summary, indent=2))
    if summary.get("warning"):
        print(f"\nWARNING: {summary['warning']}")
        return 2
    print(f"\nCase ready: {summary['case_dir']}")
    print("Next: python .github/skills/conjugate_heat_transfer/scripts/run_cht_case.py "
          f"--study {args.study} --smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
