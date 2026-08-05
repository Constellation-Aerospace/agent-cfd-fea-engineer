#!/usr/bin/env python3
"""Aerothermal environment calculator: altitude/orbit conditions -> ready-to-paste
boundary-condition JSON for the assembly manifest.

Examples:
    # stratospheric balloon payload at 30 km, white-painted enclosure
    python environment.py --altitude 30000 --emissivity 0.9 --alpha-solar 0.2 --L-char 0.5

    # satellite (vacuum), sunlit orbit average on a black-anodized radiator
    python environment.py --orbit --altitude 500000 --emissivity 0.88 --alpha-solar 0.86

    # eclipse case (no sun)
    python environment.py --orbit --altitude 500000 --emissivity 0.88 --no-sun
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from atmosphere import (atmosphere, sky_sink_temperature, earth_view_factor,  # noqa: E402
                        absorbed_environmental_flux, equivalent_sink_temperature,
                        natural_convection_h, SOLAR_CONSTANT)
from materials import air_at_altitude  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--altitude", type=float, required=True, help="Altitude [m]")
    ap.add_argument("--orbit", action="store_true",
                    help="Vacuum/orbit case (space_environment BC) — any altitude")
    ap.add_argument("--emissivity", type=float, required=True, help="IR emissivity")
    ap.add_argument("--alpha-solar", type=float, default=0.2, help="Solar absorptivity")
    ap.add_argument("--no-sun", action="store_true", help="Eclipse / night case")
    ap.add_argument("--solar-projection", type=float, default=0.25,
                    help="A_projected/A_total (0.25 sphere, up to 1 for tracking panel)")
    ap.add_argument("--L-char", type=float, default=1.0, help="Characteristic length [m]")
    ap.add_argument("--internal-power", type=float, default=None,
                    help="Optional payload dissipation [W] for a radiator-size hint")
    args = ap.parse_args()

    eps = args.emissivity
    loads = absorbed_environmental_flux(args.altitude, args.alpha_solar, eps,
                                        sun=not args.no_sun,
                                        solar_projection=args.solar_projection)
    out: dict = {"inputs": vars(args), "solar_constant_W_m2": SOLAR_CONSTANT,
                 "earth_view_factor": round(earth_view_factor(args.altitude), 4),
                 "absorbed_flux": {k: round(v, 2) for k, v in loads.items()}}

    if args.orbit:
        t_eq = equivalent_sink_temperature(eps, loads["q_total_W_m2"])
        out["equivalent_sink_C"] = round(t_eq - 273.15, 2)
        out["bc_json"] = {"type": "space_environment", "emissivity": eps,
                          "absorbed_flux_W_m2": round(loads["q_total_W_m2"], 2)}
        if args.internal_power:
            # radiator area so that eps*sigma*(T^4 - Teq^4) rejects P at 40 C surface
            from atmosphere import SIGMA
            t_s = 313.15
            a_req = args.internal_power / max(eps * SIGMA * (t_s ** 4 - t_eq ** 4), 1e-9)
            out["radiator_area_hint_m2_at_40C"] = round(a_req, 3)
    else:
        a = atmosphere(args.altitude)
        out["atmosphere"] = {k: (round(v, 6) if isinstance(v, float) else v)
                             for k, v in a.items()}
        out["sky_sink_C"] = round(sky_sink_temperature(args.altitude) - 273.15, 2)
        out["h_natural_est_W_m2K"] = round(
            natural_convection_h(args.altitude, args.L_char), 4)
        # sky_sink_temperature() already folds Earth's IR emission into the sink
        # temperature via T_EARTH_EFF (self-consistent with EARTH_IR: sigma*T_EARTH_EFF^4
        # ~= EARTH_IR, i.e. they are two encodings of the same ~240 W/m2 mean outgoing
        # longwave flux). Re-adding q_earth_ir here on top, as loads["q_total_W_m2"]
        # does, double-counts Earth's IR and can shift the effective sink temperature by
        # several tens of K (e.g. -60 C -> -20 C at 2500 m) -- only the solar + albedo
        # terms belong in this BC's absorbed_flux_W_m2. q_total_W_m2 (with q_earth_ir
        # included) is still correct for the --orbit/space_environment path above, where
        # base_sink_K is T_SPACE alone and there is no separate Earth-IR term to collide
        # with.
        q_abs_bc = loads["q_solar_W_m2"] + loads["q_albedo_W_m2"]
        out["absorbed_flux_bc_note"] = (
            "absorbed_flux_W_m2 below is q_solar + q_albedo only, excluding "
            "q_earth_ir_W_m2 -- that term is already represented by sky_sink_temperature() "
            "via T_EARTH_EFF; adding both would double-count Earth's IR emission")
        out["bc_json"] = {"type": "altitude_environment", "altitude_m": args.altitude,
                          "emissivity": eps,
                          "absorbed_flux_W_m2": round(q_abs_bc, 2),
                          "L_char_m": args.L_char}
        air = air_at_altitude(args.altitude)
        out["full_cfd_route"] = {
            "note": "to resolve rarefied natural convection explicitly, model the air "
                    "as a fluid component with these settings",
            "component_material": {"material": air["material"],
                                   "overrides": air["overrides"]},
            "solver": {"p_ref_Pa": air["p_ref_Pa"], "T_init_C": air["T_amb_C"]},
        }

    print(json.dumps(out, indent=2))
    print("\nPaste bc_json as the 'bc' of the exposed patches via assign_materials.py "
          "--patch <name> --select ... --bc '<json>'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
