#!/usr/bin/env python3
"""Mid-plane contour plots + streamlines from the study's VTK output.

Examples:
    python plot_fields.py --study baseline              # latest time
    python plot_fields.py --study baseline --time 2.0   # nearest written time
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from study_pipeline import study_dir, load_params  # noqa: E402

FIELDS = {
    "U": ("Velocity magnitude [m/s]", "viridis"),
    "T": ("Temperature [K]", "inferno"),
    "p": ("Pressure [Pa]", "coolwarm"),
    "alpha.water": ("Water volume fraction [-]", "Blues"),
}


def find_vtk_series(case: Path):
    """Return sorted [(time, path)] for internal-mesh VTK files (vtm or vtu)."""
    vtk_dir = case / "VTK"
    if not vtk_dir.exists():
        raise FileNotFoundError(f"No VTK output at {vtk_dir} — run foamToVTK first (run_case.py does this)")
    series = []
    for f in list(vtk_dir.glob("*.vtm")) + list(vtk_dir.glob("*/internal.vtu")):
        m = re.search(r"_(\d+)$", f.stem) or re.search(r"_(\d+)", f.parent.name)
        if m:
            series.append((int(m.group(1)), f))
    if not series:
        raise FileNotFoundError(f"No time-stamped VTK files under {vtk_dir}")
    return sorted(series)


def load_mesh(path: Path):
    import pyvista as pv
    obj = pv.read(str(path))
    if isinstance(obj, pv.MultiBlock):
        obj = obj.combine(merge_points=True)
    return obj


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True)
    ap.add_argument("--time", type=float, default=None, help="Select nearest written time")
    ap.add_argument("--window", type=int, nargs=2, default=(1400, 900))
    args = ap.parse_args()

    import pyvista as pv
    pv.OFF_SCREEN = True

    d = study_dir(args.study)
    cfg = load_params(args.study)
    series = find_vtk_series(d / "case")
    idx = -1
    if args.time is not None:
        # OpenFOAM writes time-index suffixes; map by position in sorted list
        times = [s[0] for s in series]
        idx = min(range(len(times)), key=lambda i: abs(i / max(1, len(times) - 1) - 0))
        # fall back to nearest by fraction of endTime
        end_t = float(cfg.get("end_time_s", 4.0))
        idx = min(range(len(series)), key=lambda i: abs((i / max(1, len(series) - 1)) * end_t - args.time))
    stamp, path = series[idx]
    mesh = load_mesh(path)
    tag = f"t{stamp}"
    fig_dir = d / "figures"
    fig_dir.mkdir(exist_ok=True)

    sl = mesh.slice(normal="y", origin=(0, 0, 0))
    made = []
    for field, (title, cmap) in FIELDS.items():
        if field not in sl.point_data and field not in sl.cell_data:
            continue
        pl = pv.Plotter(off_screen=True, window_size=list(args.window))
        data = sl
        scalars = field
        if field == "U":
            if "U" not in data.point_data:
                data = data.cell_data_to_point_data()
            data["Umag"] = (data["U"] ** 2).sum(axis=1) ** 0.5
            scalars = "Umag"
        pl.add_mesh(data, scalars=scalars, cmap=cmap, scalar_bar_args={"title": title})
        pl.view_xz()
        pl.camera.zoom(1.3)
        out = fig_dir / f"slice_{field.replace('.', '_')}_{tag}.png"
        pl.screenshot(str(out))
        pl.close()
        made.append(out.name)

    # streamlines seeded at the pipe outlet, colored by temperature
    geo = cfg.get("geometry", {})
    D = geo.get("pipe_diameter", 0.30)
    Lpen = geo.get("pipe_penetration", 0.5)
    Hs = geo.get("submergence", 2.0)
    if "U" in mesh.point_data:
        seeds = pv.Disc(center=(Lpen + 0.02, 0, -Hs), inner=0, outer=D * 0.45,
                        normal=(1, 0, 0), r_res=4, c_res=12)
        try:
            stream = mesh.streamlines_from_source(seeds, vectors="U", max_length=20.0)
            pl = pv.Plotter(off_screen=True, window_size=list(args.window))
            pl.add_mesh(mesh.outline(), color="grey")
            pl.add_mesh(stream.tube(radius=D / 40), scalars="T" if "T" in stream.point_data else None,
                        cmap="inferno", scalar_bar_args={"title": "T [K]"})
            pl.view_xz()
            out = fig_dir / f"streamlines_{tag}.png"
            pl.screenshot(str(out))
            pl.close()
            made.append(out.name)
        except Exception as exc:  # noqa: BLE001 — streamlines can fail on early/degenerate fields
            print(f"streamlines skipped: {exc}")

    print(f"Wrote {len(made)} figure(s) to {fig_dir}:")
    for name in made:
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
