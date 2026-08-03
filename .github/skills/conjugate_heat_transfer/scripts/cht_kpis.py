#!/usr/bin/env python3
"""Extract heat-exchanger KPIs from a completed CHT run: per-stream heat duty,
effectiveness, LMTD, UA, energy imbalance, interface heat fluxes, region T extremes.

Example:
    python cht_kpis.py --study hx
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from cht_pipeline import extract_cht_kpis  # noqa: E402
from learning_store import harvest  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True)
    args = ap.parse_args()

    kpis = extract_cht_kpis(args.study)
    print(json.dumps(kpis, indent=2))
    harvest(args.study, case_type="conjugate_heat_transfer")

    hx = kpis.get("heat_exchanger")
    if hx and hx.get("energy_imbalance_pct", 0) > 5:
        print(f"\nWARNING: hot/cold heat duty imbalance {hx['energy_imbalance_pct']}% "
              "— run longer or refine the mesh before quoting these numbers.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
