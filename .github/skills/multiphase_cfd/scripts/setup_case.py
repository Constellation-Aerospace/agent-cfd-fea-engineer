#!/usr/bin/env python3
"""Set up the complete multiphase CFD case: geometry -> mesh -> case -> init fields.

Examples:
    python setup_case.py --study baseline
    python setup_case.py --study hot-fast --config '{"U_in": 25, "T_exhaust_C": 550}'
    python setup_case.py --study baseline --mesh-factor 0.72   # finer mesh
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from study_pipeline import prepare  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True, help="Study slug under outputs/")
    ap.add_argument("--config", type=str, default=None,
                    help="JSON dict or path to JSON file with solver/geometry config")
    ap.add_argument("--mesh-factor", type=float, default=1.0,
                    help="Mesh size factor (1.0 medium, 0.72 fine, 1.3 coarse)")
    ap.add_argument("--reuse-mesh", action="store_true", help="Keep existing mesh if present")
    args = ap.parse_args()

    cfg = {}
    if args.config:
        p = Path(args.config)
        cfg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else json.loads(args.config)

    summary = prepare(args.study, cfg, mesh_size_factor=args.mesh_factor,
                      reuse_mesh=args.reuse_mesh)
    print(json.dumps(summary, indent=2))
    if summary.get("warning"):
        print(f"\nWARNING: {summary['warning']}")
        return 2
    print(f"\nCase ready: {summary['case_dir']}")
    print("Next: python .github/skills/multiphase_cfd/scripts/run_case.py --study", args.study)
    return 0


if __name__ == "__main__":
    sys.exit(main())
