#!/usr/bin/env python3
"""Recommend solver settings for a new case from past harvested studies of the
same case type (weighted-kNN over harvested runs — see learning_store.py).

Examples:
    # query features from an existing (run or not-yet-run) study's own inputs
    python recommend.py --case-type multiphase_cfd --like marine-exhaust-cfd/next-run

    # or supply query features by hand
    python recommend.py --case-type conjugate_heat_transfer \\
        --param n_components=8 --param total_volume_m3=0.0004 --param ambient_T_K=193.15
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from learning_store import query_features_for_study, recommend  # noqa: E402


def _parse_param(raw: str) -> tuple[str, float]:
    key, _, value = raw.partition("=")
    if not _:
        raise argparse.ArgumentTypeError(f"--param expects key=value, got '{raw}'")
    return key, float(value)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case-type", required=True,
                    choices=["multiphase_cfd", "conjugate_heat_transfer", "fea_analysis"])
    ap.add_argument("--like", default=None,
                    help="Study slug to pull query features from (its params.json / "
                         "manifest.json / fea_summary.json)")
    ap.add_argument("--param", action="append", default=[], type=_parse_param,
                    help="key=value query feature (repeatable); merges over --like")
    ap.add_argument("-k", type=int, default=5, help="Neighbours to weight over (default 5)")
    args = ap.parse_args()

    features = dict(query_features_for_study(args.case_type, args.like)) if args.like else {}
    features.update(dict(args.param))
    if not features:
        print("No query features given — pass --like <study> and/or --param key=value.",
              file=sys.stderr)
        return 2

    print(json.dumps(recommend(args.case_type, features, k=args.k), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
