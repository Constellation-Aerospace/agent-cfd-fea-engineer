#!/usr/bin/env python3
"""Run the chtMultiRegion solver (inside WSL) and summarise convergence.

Examples:
    python run_cht_case.py --study hx --smoke          # 50 iterations sanity run
    python run_cht_case.py --study hx                  # full run per manifest solver block
    python run_cht_case.py --study hx --iterations 3000 --n-procs 8
    python run_cht_case.py --study hx --end-time 120   # transient mode
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from cht_pipeline import solve  # noqa: E402

SMOKE_ITERS = 50
SMOKE_TIME_S = 0.5


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True)
    ap.add_argument("--smoke", action="store_true",
                    help=f"Short sanity run ({SMOKE_ITERS} iters / {SMOKE_TIME_S}s)")
    ap.add_argument("--iterations", type=int, default=None, help="Steady: endTime override")
    ap.add_argument("--end-time", type=float, default=None, help="Transient: endTime [s]")
    ap.add_argument("--n-procs", type=int, default=None)
    ap.add_argument("--time-limit", type=int, default=14400, help="Wall-clock limit [s]")
    args = ap.parse_args()

    iters, end_time = args.iterations, args.end_time
    if args.smoke:
        iters = iters or SMOKE_ITERS
        end_time = end_time or SMOKE_TIME_S

    summary = solve(args.study, n_procs=args.n_procs, time_limit_s=args.time_limit,
                    iterations=iters, end_time_s=end_time)
    print(json.dumps(summary, indent=2))
    if not summary["completed"]:
        print(f"\nWARNING: solver did not complete — inspect "
              f"outputs/{args.study}/case/log.{summary['application']}")
        return 2
    print("\nNext: python .github/skills/conjugate_heat_transfer/scripts/cht_kpis.py "
          f"--study {args.study}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
