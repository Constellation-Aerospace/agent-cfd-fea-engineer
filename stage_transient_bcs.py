#!/usr/bin/env python3
"""Retarget the altitude_environment boundary conditions of a CHT case to a new
flight altitude, in the latest time directory, so chtMultiRegionFoam can be
restarted for the next segment of an ascent profile.

chtMultiRegionFoam reads its boundary conditions from the start-time directory
(controlDict has `startFrom latestTime`). This script rewrites the `Ta` and `h`
entries of every `externalWallHeatFluxTemperature` patch that the manifest marks
as `altitude_environment`, using exactly the same physics the case factory uses
(atmosphere.combined_film): convection to the US76 air temperature plus grey
radiation to the sky sink, linearised into one (h, Ta) pair.

The linearisation reference temperature defaults to the CURRENT surface
temperature read back from the field file, which makes each segment exact at the
temperature the payload actually reached in the previous segment.

Usage:
    python stage_transient_bcs.py --study balloon-ttp/transient-0-20km \
        --altitude 1667 --h 13.0
    python stage_transient_bcs.py --study <slug> --altitude 11667 --h 1.910 --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / ".tmp" / "scripts"))

from atmosphere import (atmosphere, sky_sink_temperature,  # noqa: E402
                        equivalent_sink_temperature, natural_convection_h,
                        combined_film, ambient_T_blended)

AMBIENT_PROFILES = {
    "us76": None,  # atmosphere()'s own T_K, unchanged default behaviour
    "kolkata_12z_19may": ambient_T_blended,
}


def latest_time_dir(case: Path) -> Path:
    times = []
    for p in case.iterdir():
        if not p.is_dir():
            continue
        try:
            times.append((float(p.name), p))
        except ValueError:
            continue
    if not times:
        raise SystemExit(f"No time directories in {case}")
    return max(times, key=lambda t: t[0])[1]


def patch_block(text: str, patch: str) -> tuple[int, int] | None:
    """Return (start, end) char offsets of the { ... } body of a patch entry."""
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


def surface_T_from_block(body: str) -> float | None:
    """Mean of the patch `value` entry: 'uniform X' or 'nonuniform List<scalar> N (...)'."""
    m = re.search(r"\bvalue\s+uniform\s+([\d.eE+-]+)\s*;", body)
    if m:
        return float(m.group(1))
    m = re.search(r"\bvalue\s+nonuniform\s+List<scalar>\s*\d*\s*\((.*?)\)\s*;", body, re.S)
    if m:
        vals = [float(v) for v in m.group(1).split()]
        return sum(vals) / len(vals) if vals else None
    if re.search(r"\bvalue\s+nonuniform", body):
        return None      # binary payload — caller falls back
    return None


def set_entry(body: str, key: str, value: str) -> tuple[str, bool]:
    new, n = re.subn(rf"(\b{key}\s+)[^;]*;", rf"\g<1>{value};", body, count=1)
    return new, bool(n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True, help="Study slug under outputs/")
    ap.add_argument("--altitude", type=float, required=True, help="Segment altitude [m]")
    ap.add_argument("--h", type=float, default=None,
                    help="Convective film coefficient [W/m2K]; default = US76 "
                         "Churchill estimate from the manifest L_char_m")
    ap.add_argument("--t-surface-est-C", type=float, default=None,
                    help="Linearisation reference temperature [C]; default = the "
                         "surface temperature read back from the field file")
    ap.add_argument("--time", default=None,
                    help="Time directory to patch (default: latest)")
    ap.add_argument("--ambient-profile", choices=sorted(AMBIENT_PROFILES), default="us76",
                    help="Source for the ambient air temperature driving the film: "
                         "'us76' (default, unchanged) or 'kolkata_12z_19may' (digitized "
                         "12:00 UTC 19-May-2026 Kolkata sounding below 30 km, US76 at/"
                         "above it -- see atmosphere.ambient_T_blended). Only T_air_K is "
                         "swapped; p_Pa/rho/transport properties still come from US76.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    study = REPO_ROOT / "outputs" / args.study
    case = study / "case"
    manifest = json.loads((study / "assembly" / "manifest.json").read_text(encoding="utf-8"))
    tdir = case / args.time if args.time else latest_time_dir(case)
    if not tdir.is_dir():
        raise SystemExit(f"Time directory not found: {tdir}")

    air = atmosphere(args.altitude)
    blend_fn = AMBIENT_PROFILES[args.ambient_profile]
    T_air_K = blend_fn(args.altitude) if blend_fn else air["T_K"]
    t_sky_base = sky_sink_temperature(args.altitude)
    report = {"study": args.study, "time_dir": tdir.name, "altitude_m": args.altitude,
              "ambient_profile": args.ambient_profile,
              "T_air_K": round(T_air_K, 2), "p_Pa": round(air["p_Pa"], 1),
              "patches": {}}

    targets = [(n, p) for n, p in manifest.get("patches", {}).items()
               if p.get("bc", {}).get("type") == "altitude_environment"]
    if not targets:
        raise SystemExit("No altitude_environment patches in the manifest.")

    for pname, patch in targets:
        region = patch["component"]
        bc = patch["bc"]
        eps = float(bc["emissivity"])
        q_abs = float(bc.get("absorbed_flux_W_m2", 0.0))
        L = float(bc.get("L_char_m", 1.0))
        f = tdir / region / "T"
        if not f.exists():
            raise SystemExit(f"Missing field file: {f}")
        text = f.read_text(encoding="utf-8", errors="replace")
        if "format" in text[:400] and "binary" in text[:400]:
            raise SystemExit(
                f"{f} is in binary format — set 'writeFormat ascii;' in "
                f"{case/'system'/'controlDict'} and re-run the previous segment.")
        span = patch_block(text, pname)
        if span is None:
            raise SystemExit(f"Patch '{pname}' not found in {f}")
        a, b = span
        body = text[a:b + 1]

        t_ref = (args.t_surface_est_C + 273.15 if args.t_surface_est_C is not None
                 else surface_T_from_block(body))
        if t_ref is None:
            t_ref = T_air_K + 20.0
        h_conv = args.h if args.h is not None else natural_convection_h(
            args.altitude, L, max(abs(t_ref - T_air_K), 1.0))
        t_sink = equivalent_sink_temperature(eps, q_abs, t_sky_base)
        film = combined_film(h_conv, T_air_K, eps, t_sink, t_ref)

        body, ok_ta = set_entry(body, "Ta", f"uniform {film['Ta_K']:.2f}")
        body, ok_h = set_entry(body, "h", f"uniform {film['h_W_m2K']:.4g}")
        if not (ok_ta and ok_h):
            raise SystemExit(f"Patch '{pname}' in {f} has no Ta/h entries — "
                             "is it an externalWallHeatFluxTemperature patch?")
        if not args.dry_run:
            f.write_text(text[:a] + body + text[b + 1:], encoding="utf-8")
        report["patches"][f"{region}/{pname}"] = {
            "T_ref_K": round(t_ref, 2), "h_conv_W_m2K": round(h_conv, 4),
            "h_rad_W_m2K": round(film["h_rad_W_m2K"], 4),
            "h_total_W_m2K": round(film["h_W_m2K"], 4),
            "Ta_K": round(film["Ta_K"], 2), "T_sink_K": round(t_sink, 2),
        }

    print(json.dumps(report, indent=2))
    if args.dry_run:
        print("\n(dry run — no files written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
