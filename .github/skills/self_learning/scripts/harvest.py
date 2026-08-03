#!/usr/bin/env python3
"""Harvest completed studies into the learning history (agent-data/learning_history.json).

Examples:
    python harvest.py --study marine-exhaust-cfd/baseline
    python harvest.py --all               # sweep every completed study under outputs/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from learning_store import harvest, harvest_all  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--study", help="Study slug to harvest, e.g. project/study")
    g.add_argument("--all", action="store_true", help="Harvest every completed study")
    ap.add_argument("--case-type", default=None,
                    choices=["multiphase_cfd", "conjugate_heat_transfer", "fea_analysis"],
                    help="Override auto-detection (only used with --study)")
    args = ap.parse_args()

    if args.all:
        print(json.dumps(harvest_all(), indent=2))
        return 0

    result = harvest(args.study, case_type=args.case_type)
    print(json.dumps(result, indent=2))
    return 1 if "skipped" in result else 0


if __name__ == "__main__":
    sys.exit(main())
