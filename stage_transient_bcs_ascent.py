#!/usr/bin/env python3
"""Retarget the radiator `convection` boundary conditions of the balloon-ttp
0-10 km / 40-minute ascent CHT case to a given mission time, in a named time
directory, so chtMultiRegionFoam can be restarted for the next segment.

Unlike stage_transient_bcs.py (which drives the altitude_environment BC type
via atmosphere.py's high-altitude sky-sink model), this script implements the
forced-convection ascent profile given directly in
`Jetson_Transient_Analysis_0_10km.md` Section 6 for the 0-10 km / 2400 s climb:

  T_amb(t) = 15.0 - 0.02708*t                       [degC]   (ISA lapse, doc Sec.6B)
  h(t)     = piecewise-linear 15 -> 11 -> 8 W/m2K    (doc Sec.6C, breakpoint at 1200 s)

`radiator_plate` is treated as the sun-facing panel: its ambient is bumped by
q_solar/h(t) where q_solar = 1360 * 0.2 = 272 W/m2 (doc Sec.6D, optional solar
term), folding the absorbed flux into an equivalent ambient temperature for the
single-Ta `externalWallHeatFluxTemperature` BC (mode=coefficient computes both
the convective AND the grey-radiative flux to this same Ta, since `emissivity`
is also set on the patch). `radiator_plate_2` (shaded) uses T_amb(t) directly.

Usage:
    python stage_transient_bcs_ascent.py --study balloon-ttp/transient-0-10km \
        --time 300 --t 300
    python stage_transient_bcs_ascent.py --study <slug> --time 0 --t 150 --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

Q_SOLAR_W_M2 = 1360.0 * 0.2


def t_amb_c(t: float) -> float:
    return 15.0 - 0.02708 * t


def h_ascent(t: float) -> float:
    if t <= 1200.0:
        return 15.0 - (15.0 - 11.0) / 1200.0 * t
    return 11.0 - (11.0 - 8.0) / 1200.0 * (t - 1200.0)


def patch_block(text: str, patch: str) -> tuple[int, int] | None:
    m = re.search(rf"^\s*{re.escape(patch)}\s*$", text, re.M)
    if not m:
        return None
    open_idx = text.find("{", m.end())
    if open_idx < 0:
        return None
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return open_idx, i
    return None


def set_entry(body: str, key: str, value: str) -> tuple[str, bool]:
    new, n = re.subn(rf"(\b{key}\s+)[^;]*;", rf"\g<1>{value};", body, count=1)
    return new, bool(n)


def patch_region_T(f: Path, patch: str, Ta_K: float, h: float, dry_run: bool) -> None:
    text = f.read_text(encoding="utf-8", errors="replace")
    if "format" in text[:400] and "binary" in text[:400]:
        raise SystemExit(f"{f} is binary — set writeFormat ascii in controlDict.")
    span = patch_block(text, patch)
    if span is None:
        raise SystemExit(f"Patch '{patch}' not found in {f}")
    a, b = span
    body = text[a:b + 1]
    body, ok_ta = set_entry(body, "Ta", f"uniform {Ta_K:.3f}")
    body, ok_h = set_entry(body, "h", f"uniform {h:.5g}")
    if not (ok_ta and ok_h):
        raise SystemExit(f"Patch '{patch}' in {f} has no Ta/h entries.")
    if not dry_run:
        f.write_text(text[:a] + body + text[b + 1:], encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True)
    ap.add_argument("--time", required=True, help="Time directory to patch (e.g. '0', '300')")
    ap.add_argument("--t", type=float, required=True,
                    help="Mission time [s] the new BCs represent (segment midpoint)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    case = REPO_ROOT / "outputs" / args.study / "case"
    tdir = case / args.time
    if not tdir.is_dir():
        raise SystemExit(f"Time directory not found: {tdir}")

    Ta_shaded_K = t_amb_c(args.t) + 273.15
    h_val = h_ascent(args.t)
    Ta_sun_K = Ta_shaded_K + Q_SOLAR_W_M2 / h_val

    targets = [
        ("radiator_plate", "radiator_plate_outer", Ta_sun_K, h_val),
        ("radiator_plate_2", "radiator_plate_2_outer", Ta_shaded_K, h_val),
    ]
    report = {"study": args.study, "time_dir": tdir.name, "t_s": args.t,
              "T_amb_C": round(t_amb_c(args.t), 3), "h_W_m2K": round(h_val, 4),
              "patches": {}}
    for region, patch, Ta_K, h in targets:
        f = tdir / region / "T"
        if not f.exists():
            raise SystemExit(f"Missing field file: {f}")
        patch_region_T(f, patch, Ta_K, h, args.dry_run)
        report["patches"][f"{region}/{patch}"] = {"Ta_K": round(Ta_K, 3), "h_W_m2K": round(h, 4)}

    print(json.dumps(report, indent=2))
    if args.dry_run:
        print("\n(dry run — no files written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
