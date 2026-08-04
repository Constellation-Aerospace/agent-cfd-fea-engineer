#!/usr/bin/env python3
"""Drive the balloon-ttp 0-10 km / 40-minute transient CHT solve end to end.

Runs chtMultiRegionFoam in 300 s restart segments (0,300,600,...,2400), calling
stage_transient_bcs_ascent.py before each segment to retarget the radiator
`convection` BCs (Ta, h) to that segment's midpoint mission time, per the
ascent profile in Jetson_Transient_Analysis_0_10km.md Section 6. Each segment
is solved with cht_pipeline.solve() (native WSL storage, decompose ->
chtMultiRegionFoam -> reconstruct -> foamToVTK). Progress and every segment's
run_summary are appended to <study>/transient_run_log.json as the run
proceeds, so a killed/resumed run can be inspected without waiting for the end.

Usage:
    python run_transient_10km.py --study balloon-ttp/transient-0-10km
    python run_transient_10km.py --study balloon-ttp/transient-0-10km --resume
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / ".tmp" / "scripts"))

from cht_pipeline import solve, study_dir  # noqa: E402
from stage_transient_bcs_ascent import (patch_region_T, t_amb_c, h_ascent,  # noqa: E402
                                        Q_SOLAR_W_M2)

SEGMENTS_S = [0, 300, 600, 900, 1200, 1500, 1800, 2100, 2400]


def stage(study: str, time_dir: str, t_mid: float) -> dict:
    case = study_dir(study) / "case"
    tdir = case / time_dir
    Ta_shaded_K = t_amb_c(t_mid) + 273.15
    h_val = h_ascent(t_mid)
    Ta_sun_K = Ta_shaded_K + Q_SOLAR_W_M2 / h_val
    patch_region_T(tdir / "radiator_plate" / "T", "radiator_plate_outer", Ta_sun_K, h_val, False)
    patch_region_T(tdir / "radiator_plate_2" / "T", "radiator_plate_2_outer", Ta_shaded_K, h_val, False)
    return {"time_dir": time_dir, "t_mid_s": t_mid, "T_amb_C": round(t_amb_c(t_mid), 3),
            "h_W_m2K": round(h_val, 4), "Ta_sun_K": round(Ta_sun_K, 3),
            "Ta_shaded_K": round(Ta_shaded_K, 3)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True)
    ap.add_argument("--resume", action="store_true",
                    help="Skip segments already recorded in transient_run_log.json")
    args = ap.parse_args()

    log_path = study_dir(args.study) / "transient_run_log.json"
    log: list[dict] = json.loads(log_path.read_text()) if (args.resume and log_path.exists()) else []
    done_ends = {e["end_time_s"] for e in log if e.get("ok")}

    for i in range(len(SEGMENTS_S) - 1):
        t_start, t_end = SEGMENTS_S[i], SEGMENTS_S[i + 1]
        if t_end in done_ends:
            print(f"[skip] segment {t_start}->{t_end}s already completed")
            continue
        t_mid = (t_start + t_end) / 2.0
        stage_info = stage(args.study, str(t_start), t_mid)
        print(f"[stage] {json.dumps(stage_info)}")

        t0 = time.time()
        summary = solve(args.study, end_time_s=t_end, time_limit_s=1800)
        entry = {"segment": [t_start, t_end], "end_time_s": t_end, "stage": stage_info,
                 "run_summary": summary, "wall_clock_s": round(time.time() - t0, 1),
                 "ok": bool(summary.get("completed")) and summary.get("final_time") == t_end}
        log.append(entry)
        log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
        print(f"[segment {t_start}->{t_end}s] ok={entry['ok']} "
              f"final_time={summary.get('final_time')} n_steps={summary.get('n_steps')} "
              f"wall_clock={entry['wall_clock_s']}s")
        if not entry["ok"]:
            print(f"ABORT: segment {t_start}->{t_end}s did not complete cleanly — "
                  f"inspect case/log.chtMultiRegionFoam", file=sys.stderr)
            return 1

    print(f"Transient run complete: {SEGMENTS_S[0]}s -> {SEGMENTS_S[-1]}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
