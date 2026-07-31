#!/usr/bin/env python3
"""Assign materials, component types, and boundary conditions in the assembly manifest.

Examples:
    # list library materials and current assignments
    python assign_materials.py --study hx --list

    # component typing + material
    python assign_materials.py --study hx --component tube_fluid --type fluid --material water
    python assign_materials.py --study hx --component shell --type solid --material stainless_316

    # boundary patches (selector + BC on a component's external surfaces)
    python assign_materials.py --study hx --patch hot_inlet --component gas_fluid \\
        --select xmin --bc '{"type": "velocity_inlet", "U_m_s": 5.0, "T_C": 400}'
    python assign_materials.py --study hx --patch hot_outlet --component gas_fluid \\
        --select xmax --bc '{"type": "pressure_outlet", "p_Pa": 101325}'
    python assign_materials.py --study hx --patch casing_outer --component shell \\
        --select remaining --bc '{"type": "convection", "h_W_m2K": 12, "T_amb_C": 25, "emissivity": 0.35}'

    # radiation model / solver settings / validation
    python assign_materials.py --study hx --radiation P1
    python assign_materials.py --study hx --solver '{"mode": "steady", "iterations": 2000}'
    python assign_materials.py --study hx --validate
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from cht_pipeline import load_manifest, save_manifest  # noqa: E402
from materials import list_materials  # noqa: E402
from step_assembly import validate_manifest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True)
    ap.add_argument("--list", action="store_true", help="Show materials + assignments")
    ap.add_argument("--component", help="Component to modify")
    ap.add_argument("--type", choices=["solid", "fluid"], help="Component type")
    ap.add_argument("--material", help="Material name from the library")
    ap.add_argument("--t-init", type=float, default=None, help="Initial temperature [C]")
    ap.add_argument("--overrides", help="JSON dict of property overrides for the component")
    ap.add_argument("--patch", help="Boundary patch name to create/update")
    ap.add_argument("--select", help="Selector: xmin|xmax|ymin|ymax|zmin|zmax|remaining "
                                     "or JSON ({'box': ...}, {'plane': ...}, {'surfaces': ...})")
    ap.add_argument("--bc", help="JSON boundary condition dict for --patch")
    ap.add_argument("--radiation", choices=["none", "P1", "fvDOM"], help="Radiation model")
    ap.add_argument("--emissivity-default", type=float, default=None)
    ap.add_argument("--solver", help="JSON dict merged into the solver block")
    ap.add_argument("--validate", action="store_true", help="Validate the manifest")
    args = ap.parse_args()

    manifest = load_manifest(args.study)

    if args.list:
        print(json.dumps({"library": list_materials(),
                          "components": {n: {k: c[k] for k in ("type", "material", "T_init_C")}
                                         for n, c in manifest["components"].items()},
                          "patches": manifest.get("patches", {}),
                          "radiation": manifest.get("radiation", {}),
                          "solver": manifest.get("solver", {})}, indent=2))
        return 0

    changed = False
    if args.component:
        comp = manifest["components"].get(args.component)
        if comp is None:
            print(f"Unknown component '{args.component}'. "
                  f"Have: {', '.join(manifest['components'])}")
            return 1
        if args.type:
            comp["type"] = args.type
        if args.material:
            comp["material"] = args.material
        if args.t_init is not None:
            comp["T_init_C"] = args.t_init
        if args.overrides:
            comp.setdefault("overrides", {}).update(json.loads(args.overrides))
        changed = True

    if args.patch:
        if not (args.select and args.bc):
            print("--patch needs both --select and --bc")
            return 1
        select = args.select
        if select.strip().startswith("{"):
            select = json.loads(select)
        manifest.setdefault("patches", {})[args.patch] = {
            "component": args.component or manifest.get("patches", {}).get(
                args.patch, {}).get("component"),
            "select": select,
            "bc": json.loads(args.bc),
        }
        if not manifest["patches"][args.patch]["component"]:
            print("--patch needs --component")
            return 1
        changed = True

    if args.radiation:
        manifest.setdefault("radiation", {})["model"] = args.radiation
        changed = True
    if args.emissivity_default is not None:
        manifest.setdefault("radiation", {})["emissivity_default"] = args.emissivity_default
        changed = True
    if args.solver:
        manifest.setdefault("solver", {}).update(json.loads(args.solver))
        changed = True

    if changed:
        save_manifest(args.study, manifest)
        print("Manifest updated.")

    if args.validate or changed:
        problems = validate_manifest(manifest)
        if problems:
            print("Validation problems:")
            for p in problems:
                print(f"  - {p}")
            return 2 if args.validate else 0
        print("Manifest is ready for meshing/case setup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
