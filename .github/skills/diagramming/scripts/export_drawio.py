#!/usr/bin/env python3
"""Export .drawio files to PNG/SVG via the draw.io web export API.

No local draw.io installation required. Adapted from
sales-prospector/.github/skills/proposal/scripts/export_drawio_to_png.py.

Usage:
    python export_drawio.py --input diagrams/domain.drawio --output diagrams/domain.png
    python export_drawio.py --input-dir diagrams --output-dir diagrams
    python export_drawio.py --input d.drawio --output d.svg --format svg

Fallbacks if the API is unreachable:
  1. VS Code draw.io extension (hediet.vscode-drawio): right-click -> Export
  2. draw.io desktop CLI: drawio --export --format png --output out.png in.drawio
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

EXPORT_URL = "https://exp.draw.io/ImageExport4/export"


def export(drawio_path: Path, out_path: Path, fmt: str, scale: float) -> bool:
    xml = drawio_path.read_text(encoding="utf-8")
    try:
        resp = requests.post(
            EXPORT_URL,
            data={"format": fmt, "xml": xml, "scale": scale,
                  "extras": '{"globalVars":{}}'},
            timeout=60,
        )
        resp.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(resp.content)
        print(f"  ok  {drawio_path.name} -> {out_path}  ({len(resp.content)//1024} KB)")
        return True
    except Exception as e:  # noqa: BLE001 — report and continue batch
        print(f"  FAIL {drawio_path.name}: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input")
    ap.add_argument("--output")
    ap.add_argument("--input-dir")
    ap.add_argument("--output-dir")
    ap.add_argument("--format", default="png", choices=("png", "svg"))
    ap.add_argument("--scale", type=float, default=2.0)
    args = ap.parse_args()

    if args.input and args.output:
        ok = export(Path(args.input), Path(args.output), args.format, args.scale)
        return 0 if ok else 1
    if args.input_dir and args.output_dir:
        files = sorted(Path(args.input_dir).glob("*.drawio"))
        if not files:
            print("no .drawio files in", args.input_dir)
            return 1
        n_ok = sum(
            export(f, Path(args.output_dir) / f"{f.stem}.{args.format}",
                   args.format, args.scale)
            for f in files
        )
        print(f"exported {n_ok}/{len(files)}")
        return 0 if n_ok == len(files) else 1
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
