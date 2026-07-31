#!/usr/bin/env python3
"""Run the multiphase solver for a prepared study and export VTK for post-processing.

Examples:
    python run_case.py --study baseline --np 6
    python run_case.py --study baseline --end-time 0.2        # quick scoping run
    python run_case.py --study baseline --serial --time-limit 1800
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from study_pipeline import solve, extract_kpis  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True)
    ap.add_argument("--np", type=int, default=None, help="MPI ranks (default from params.json)")
    ap.add_argument("--serial", action="store_true", help="Run single-core")
    ap.add_argument("--end-time", type=float, default=None,
                    help="Override endTime [s] (e.g. 0.2 for a smoke run)")
    ap.add_argument("--time-limit", type=int, default=14400, help="Wall-clock limit [s]")
    args = ap.parse_args()

    np_ = 1 if args.serial else args.np
    summary = solve(args.study, n_procs=np_, time_limit_s=args.time_limit,
                    end_time_s=args.end_time)
    print(json.dumps(summary, indent=2))

    kpis = extract_kpis(args.study)
    if kpis:
        print("\nHeadline KPIs:")
        print(json.dumps(kpis, indent=2))
    print("\nNext: post-process with "
          "python .github/skills/post_processing/scripts/plot_fields.py --study", args.study)
    return 0


if __name__ == "__main__":
    sys.exit(main())
