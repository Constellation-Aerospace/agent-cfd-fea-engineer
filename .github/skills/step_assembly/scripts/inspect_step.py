#!/usr/bin/env python3
"""Inspect a multi-part STEP assembly: enumerate components + contact interfaces,
write the assignment manifest template for a CHT study.

Examples:
    python inspect_step.py --study hx-proto --step "CAD/heat_exchanger.step"
    python inspect_step.py --study hx-proto --step CAD/hx.step --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from cht_pipeline import inspect, manifest_path  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True, help="Study slug under outputs/")
    ap.add_argument("--step", required=True, help="Path to the multi-part STEP file")
    ap.add_argument("--json", action="store_true", help="Print the full manifest JSON")
    args = ap.parse_args()

    manifest = inspect(args.study, args.step)
    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        comps = manifest["components"]
        print(f"Assembly: {manifest['step_file']}")
        print(f"Components ({len(comps)}):")
        print(f"  {'name':28s} {'type':6s} {'material':18s} {'volume [m3]':>13s}")
        for name, c in comps.items():
            print(f"  {name:28s} {c['type']:6s} {str(c['material']):18s} "
                  f"{c['volume_m3']:13.6g}")
        print(f"\nContact interfaces ({len(manifest['interfaces'])}):")
        for iface in manifest["interfaces"]:
            a, b = iface["components"]
            print(f"  {a} <-> {b}: {iface['area_m2']:.6g} m2 ({iface['n_surfaces']} faces)")
    print(f"\nManifest: {manifest_path(args.study)}")
    print("Next: assign materials/BCs with assign_materials.py (or edit the manifest), "
          "then mesh with mesh_assembly.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
