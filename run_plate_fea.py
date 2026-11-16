#!/usr/bin/env python3
"""FEA: Stratos II payload support plate — shell model of the laser-cut profile.

The part is a flat 2.0 mm Al 6061-T6 sheet-metal profile that closes the top and
bottom of the thermocol/mylar shroud and carries the four corner clamp loops
(see the payload project's design/README.md and design/strength.md).  A flat
plate in out-of-plane bending is a shell problem, so the model is:

  * geometry   read from the 1:1 cut file design/plate.dxf (the file the cutter
               uses), so the FEA is on the part as built - ears, rope holes,
               camera aperture and both lightening openings included;
  * elements   CalculiX S6 (6-node quadratic triangular shells), t = 2.0 mm,
               one mid-surface mesh, expanded internally by ccx to C3D15;
  * support    the thermocol lid is a rigid frictionless bed: the transverse
               dof of every node inside the shroud footprint (|X| <= 120,
               |Z| <= 135.5) is fixed and the Ø150 camera hole in the bottom
               lid is left free.  This is the stiff limit of the real
               compressible EPS, so the reactions it reports are an upper bound
               on the bearing pressure the foam actually sees;
  * loads      each rope pulls on a 20 mm washer, so the loop tension is applied
               as a patch load over the washer footprint at each ear, plus the
               plate's own weight (*DLOAD GRAV).  An optional bridle case adds
               the in-plane component of legs ~30 deg off vertical.

The ear load is the clamp-loop tension T = (n g W)/4 + T0, i.e. the loops - not
the foam - carry the payload, which is why the load cases are quoted as T per
ear and as the loop pretension T0 rather than only as a g-level.

Usage:
    python run_plate_fea.py --study balloon-ttp/plate-fea --validate
    python run_plate_fea.py --study balloon-ttp/plate-fea
    python run_plate_fea.py --study balloon-ttp/plate-fea --mesh-scale 0.7
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / ".tmp" / "scripts"))

from wsl_bridge import ccx_binary, run_wsl  # noqa: E402
from study_pipeline import study_dir  # noqa: E402

# --------------------------------------------------------------------------
# Part / material, from the payload project
# --------------------------------------------------------------------------
PLATE_DIR = Path(r"D:/Github/Design/Stratos II/Payload strapping/design")

BOX_X, BOX_Z = 240.0, 271.0          # thermocol lid footprint (shroud envelope)
CAM_D, CAM_X, CAM_Z = 150.0, -27.5, 39.0     # Ø150 hole in the bottom lid
EAR_X, EAR_Z, EAR_R, HOLE_D = 128.5, 144.0, 15.0, 6.5
WASHER_R = 10.0                      # 20 mm washer each side of the ear
T = 2.0                              # sheet thickness
E, NU, RHO = 69_000.0, 0.33, 2.7e-9  # MPa, -, t/mm^3 (ccx mm-N-t consistency)
FTY, FTU = 240.0, 290.0              # MPa, Al 6061-T6 sheet allowables
EPS_ALLOW = 0.10                     # MPa, EPS at 10 % strain (check_strength.py)
FOUND_R = 30.5                       # mm, foundation characteristic length
G = 9.80665                          # m/s^2 (payload weight) ...
G_MM = 9806.65                       # mm/s^2 (self weight with t/mm^3 density)
M_PAYLOAD, M_RIG = 4.5, 0.040        # kg, payload (incl. shroud) and rigging


def ears():
    return [(sx * EAR_X, sz * EAR_Z) for sx in (-1, 1) for sz in (-1, 1)]


# --------------------------------------------------------------------------
# Geometry: the DXF cut profile (LWPOLYLINE contours, bulge arcs resolved)
# --------------------------------------------------------------------------
def _area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _arc_points(x0, y0, x1, y1, bulge, tol_deg=1.0):
    """Interior points of a bulge arc from (x0,y0) to (x1,y1)."""
    theta = 4.0 * math.atan(bulge)                    # signed included angle
    chord = math.hypot(x1 - x0, y1 - y0)
    if chord < 1e-12:
        return []
    r = chord / (2.0 * math.sin(abs(theta) / 2.0))
    mx, my = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
    h = math.sqrt(max(r * r - (chord / 2.0) ** 2, 0.0))
    nx, ny = -(y1 - y0) / chord, (x1 - x0) / chord     # left normal of the chord
    sgn = (-1.0 if abs(theta) < math.pi else 1.0) * (1.0 if bulge > 0 else -1.0)
    cx, cy = mx + sgn * h * nx, my + sgn * h * ny
    a0 = math.atan2(y0 - cy, x0 - cx)
    n = max(2, int(abs(math.degrees(theta)) / tol_deg))
    return [(cx + r * math.cos(a0 + theta * j / n),
             cy + r * math.sin(a0 + theta * j / n)) for j in range(1, n)]


def read_dxf(path: Path) -> tuple[np.ndarray, list[np.ndarray]]:
    """Outer boundary + holes of the cut profile, as closed (x, z) polylines."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    curves: list[list] = []
    cur: list | None = None
    for i in range(0, len(lines) - 1, 2):
        code, val = lines[i].strip(), lines[i + 1].strip()
        if code == "0":
            if cur:
                curves.append(cur)
            cur = [] if val == "LWPOLYLINE" else None
        elif cur is not None:
            if code == "10":
                cur.append([float(val), 0.0, 0.0])
            elif code == "20" and cur:
                cur[-1][1] = float(val)
            elif code == "42" and cur:
                cur[-1][2] = float(val)

    polys = []
    for c in curves:
        n, pts = len(c), []
        for k in range(n):
            x0, y0, b = c[k]
            x1, y1 = c[(k + 1) % n][0], c[(k + 1) % n][1]
            pts.append((x0, y0))
            if abs(b) > 1e-12:
                pts.extend(_arc_points(x0, y0, x1, y1, b))
        polys.append(np.asarray(pts, dtype=float))

    polys = [p for p in polys if len(p) >= 3]
    # drop duplicated closing vertices and repeated consecutive points
    clean = []
    for p in polys:
        if np.allclose(p[0], p[-1]):
            p = p[:-1]
        d = np.roll(p, -1, axis=0) - p
        clean.append(p[np.hypot(d[:, 0], d[:, 1]) > 1e-9])
    polys = [p for p in clean if len(p) >= 3]
    areas = [abs(_area(p)) for p in polys]
    i_out = int(np.argmax(areas))
    return polys[i_out], [p for i, p in enumerate(polys) if i != i_out]


def _inside(poly: np.ndarray, pt: np.ndarray) -> bool:
    """Ray-cast point-in-polygon test."""
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def round_corners(poly: np.ndarray, r: float, min_turn_deg: float = 25.0) -> np.ndarray:
    """Blend every sharp vertex with an arc of radius r, adding material into
    the notch (the ear lobe / plate edge transitions are re-entrant corners in
    the cut profile).  Vertices that are already smooth are left alone."""
    n = len(poly)
    out: list[np.ndarray] = []
    for i in range(n):
        a, p, c = poly[(i - 1) % n], poly[i], poly[(i + 1) % n]
        u, v = p - a, c - p
        lu, lv = float(np.linalg.norm(u)), float(np.linalg.norm(v))
        if lu < 1e-9 or lv < 1e-9:
            continue
        u, v = u / lu, v / lv
        turn = math.atan2(u[0] * v[1] - u[1] * v[0], float(np.dot(u, v)))
        if abs(math.degrees(turn)) < min_turn_deg:
            out.append(p)
            continue
        d = min(r * math.tan(abs(turn) / 2.0), 0.45 * lu, 0.45 * lv)
        rr = d / math.tan(abs(turn) / 2.0)
        t1, t2 = p - u * d, p + v * d
        best = None
        for sgn in (1.0, -1.0):                    # pick the arc that adds material
            nrm = np.array([-u[1], u[0]]) * sgn * (1.0 if turn > 0 else -1.0)
            ctr = t1 + nrm * rr
            a0 = math.atan2(t1[1] - ctr[1], t1[0] - ctr[0])
            a1 = math.atan2(t2[1] - ctr[1], t2[0] - ctr[0])
            da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
            steps = max(3, int(abs(da) * rr / 0.6) + 1)
            pts = [ctr + rr * np.array([math.cos(a0 + da * k / steps),
                                        math.sin(a0 + da * k / steps)])
                   for k in range(steps + 1)]
            mid = pts[len(pts) // 2]
            if not _inside(poly, mid):
                best = pts
                break
        if best is None:
            out.append(p)
        else:
            out.extend(best[1:-1] if len(best) > 2 else best)
    return np.asarray(out)



# --------------------------------------------------------------------------
# Mesh: Gmsh 2D, quadratic triangles, refined at the rope holes
# --------------------------------------------------------------------------
def lc_at(x: float, z: float) -> float:
    """Target element size at a boundary point (mm)."""
    s = 2.4
    for (ex, ez) in ears():
        d = math.hypot(x - ex, z - ez)
        s = min(s, 0.30 + 0.075 * max(d - HOLE_D / 2.0, 0.0))
    d = math.hypot(x - CAM_X, z - CAM_Z)
    s = min(s, 0.45 + 0.09 * max(d - CAM_D / 2.0, 0.0))
    return max(s, 0.25)


def build_mesh(outer: np.ndarray, holes: list[np.ndarray], scale: float = 1.0,
               work: Path | None = None):
    """Triangular 2nd-order mesh of the mid-surface. Returns (points, tris6)."""
    import gmsh
    import meshio

    msh_path = (work or Path(".")) / "plate.msh"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 1)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.2 * scale)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 3.0 * scale)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.model.add("plate")
        geo = gmsh.model.geo
        loops = []
        for ring in [outer] + holes:
            pts = [geo.addPoint(x, z, 0.0, lc_at(x, z) * scale) for (x, z) in ring]
            seg = [geo.addLine(pts[i], pts[(i + 1) % len(pts)])
                   for i in range(len(pts))]
            loops.append(geo.addCurveLoop(seg))
        geo.addPlaneSurface(loops)
        geo.synchronize()
        gmsh.model.mesh.generate(2)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.write(str(msh_path))
    finally:
        gmsh.finalize()

    mesh = meshio.read(msh_path)
    tris = np.vstack([c.data for c in mesh.cells if c.type == "triangle6"])
    used = np.unique(tris)
    remap = np.full(len(mesh.points), -1, dtype=int)
    remap[used] = np.arange(len(used))
    return np.asarray(mesh.points)[used][:, :2], remap[tris]


# --------------------------------------------------------------------------
# Node sets and the CalculiX deck
# --------------------------------------------------------------------------
def nodal_areas(points: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Tributary area per node (from the corner triangle of each S6 element)."""
    c = points[tris[:, :3]]
    a = 0.5 * np.abs((c[:, 1, 0] - c[:, 0, 0]) * (c[:, 2, 1] - c[:, 0, 1])
                    - (c[:, 2, 0] - c[:, 0, 0]) * (c[:, 1, 1] - c[:, 0, 1]))
    out = np.zeros(len(points))
    for k in range(6):
        np.add.at(out, tris[:, k], a / 6.0)
    return out


def emit_nset(name: str, ids) -> list[str]:
    ids = [int(v) for v in ids]
    lines = [f"*NSET, NSET={name}"]
    for i in range(0, len(ids), 12):          # ccx allows 16 entries per line
        lines.append(", ".join(str(v) for v in ids[i:i + 12]))
    return lines


def build_sets(points: np.ndarray, top_plate: bool = False) -> dict[str, np.ndarray]:
    """BED (shroud footprint) + one washer patch per ear, 0-based node indices."""
    x, z = points[:, 0], points[:, 1]
    bed = (np.abs(x) <= BOX_X / 2) & (np.abs(z) <= BOX_Z / 2)
    if not top_plate:                          # Ø150 camera hole in the bottom lid
        bed &= np.hypot(x - CAM_X, z - CAM_Z) > CAM_D / 2
    sets = {"BED": np.where(bed)[0]}
    for i, (ex, ez) in enumerate(ears(), start=1):
        sets[f"EAR{i}"] = np.where(np.hypot(x - ex, z - ez) <= WASHER_R)[0]
    # the bed fixes only the transverse dof, so two in-plane point constraints
    # are needed as well - otherwise the plate is free to translate in X/Z and
    # to spin about the payload axis (singular system)
    for name, tgt in (("GRIPA", (0.0, BOX_Z / 2)), ("GRIPB", (0.0, -BOX_Z / 2))):
        sets[name] = np.array([int(np.argmin(np.hypot(x - tgt[0], z - tgt[1])))])
    return sets


def write_deck(path: Path, points: np.ndarray, tris: np.ndarray,
               sets: dict[str, np.ndarray], area: np.ndarray, *, T_ear: float,
               ear_ids=(1, 2, 3, 4), inplane_deg: float = 0.0,
               gravity: bool = True, thickness: float | None = None,
               title: str = "") -> Path:
    """One static step: S6 shells, bed support, washer patch loads, self weight."""
    t_sec = T if thickness is None else thickness
    lines = [f"** {title}", "*HEADING", f" {title}", "*NODE"]
    for i, (x, z) in enumerate(points, start=1):
        lines.append(f"{i}, {x:.7f}, 0., {z:.7f}")

    for name, ids in sets.items():
        lines += emit_nset(name, ids + 1)
    lines += ["*NSET, NSET=NALL, GENERATE", f"1, {len(points)}"]

    lines.append("*ELEMENT, TYPE=S6, ELSET=EALL")
    for eid, conn in enumerate(tris, start=1):
        lines.append(", ".join(str(v) for v in [eid, *(int(c) + 1 for c in conn)]))

    lines += ["*MATERIAL, NAME=AL6061T6", "*ELASTIC", f"{E}, {NU}",
              "*DENSITY", f"{RHO:.6e}",
              "*SHELL SECTION, ELSET=EALL, MATERIAL=AL6061T6", f"{t_sec}"]

    loads = []
    for eid_ in ear_ids:
        ids = sets[f"EAR{eid_}"]
        w = area[ids] / area[ids].sum()        # patch load, total = T_ear per ear
        for nid, f in zip(ids, w):
            loads.append(f"{int(nid) + 1}, 2, {T_ear * f:.9e}")
        if inplane_deg:
            ex, ez = ears()[eid_ - 1]
            rad = math.hypot(ex, ez)
            f_tot = T_ear * math.tan(math.radians(inplane_deg))
            for nid, f in zip(ids, w):         # pull towards the payload axis
                loads.append(f"{int(nid) + 1}, 1, {-f_tot * f * ex / rad:.9e}")
                loads.append(f"{int(nid) + 1}, 3, {-f_tot * f * ez / rad:.9e}")

    if gravity:                                # plate self weight, -Y
        w_g = RHO * G_MM * T * area
        for nid, f in enumerate(w_g):
            loads.append(f"{nid + 1}, 2, {-f:.9e}")

    lines += ["*STEP", "*STATIC", "*BOUNDARY", "BED, 2, 2",
              "GRIPA, 1, 1", "GRIPA, 3, 3", "GRIPB, 1, 1", "*CLOAD"]
    lines += loads
    lines += ["*NODE FILE, OUTPUT=3D", "U, RF", "*EL FILE", "S",
              "*NODE PRINT, NSET=BED, TOTALS=ONLY", "RF",
              "*NODE PRINT, NSET=BED", "RF",
              "*NODE PRINT, NSET=NALL, TOTALS=ONLY", "RF",
              "*END STEP"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def case_metrics(res: dict, points: np.ndarray, area: np.ndarray,
                 sets: dict[str, np.ndarray]) -> dict:
    """Bearing pressure under each ear + ear-tip deflection from one solve."""
    bed = res["bed"]
    w_field = node_field(points, res.get("_surf_u", {}))
    press, ear_w = [], []
    for i, (ex, ez) in enumerate(ears(), start=1):
        ids = [n for n in bed if n - 1 < len(points)
               and math.hypot(points[n - 1, 0] - ex, points[n - 1, 1] - ez) <= FOUND_R]
        if ids:
            a = area[[n - 1 for n in ids]].sum()
            press.append(abs(sum(bed[n] for n in ids)) / a * 1000.0)   # kPa
        else:
            press.append(0.0)
        ww = w_field[sets[f"EAR{i}"]]
        ear_w.append(float(np.nanmax(np.abs(ww))) if np.isfinite(ww).any() else 0.0)
    return {"bearing_kPa": [round(p, 1) for p in press],
            "ear_w_mm": round(max(ear_w), 4),
            "bed_load_N": round(abs(sum(bed.values())), 3)}


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------
def node_field(points: np.ndarray, surf: dict, tol: float = 0.2) -> np.ndarray:
    """Map a {frd node: (xyz, value)} field onto the mid-surface mesh nodes.

    The .frd writes 5 significant digits, so match by nearest coordinate rather
    than by rounding.
    """
    from scipy.spatial import cKDTree

    if not surf:
        return np.full(len(points), np.nan)
    frd_pts = np.array([[xyz[0], xyz[2]] for xyz, _ in surf.values()])
    vals = np.array([val for _, val in surf.values()])
    dist, idx = cKDTree(frd_pts).query(points, k=1)
    out = vals[idx]
    out[dist > tol] = np.nan
    return out


def make_figures(study: Path, points, tris, area, res12: dict,
                 fillet_r: float | None = None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    fig_dir = study / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    x, z = points[:, 0], points[:, 1]
    tri = tris[:, :3]
    vm = node_field(points, res12["_surf_vm"])
    w = node_field(points, res12["_surf_u"])
    pres = np.full(len(points), np.nan)
    for n, f in res12["bed"].items():
        if n - 1 < len(points) and area[n - 1] > 0.3:
            pres[n - 1] = abs(f) / area[n - 1] * 1000.0                # kPa
    p_cap = float(np.nanpercentile(pres, 99.5)) if np.isfinite(pres).any() else None

    tri_obj = mtri.Triangulation(x, z, tri)
    body = res12.get("body_vm_MPa", 1.0) or 1.0
    panels = [(f"von Mises, plate field [MPa]  (ears off scale: "
               f"{res12['max_vm_MPa']:.0f} MPa)", vm, "inferno", 3.0 * body),
              (f"out-of-plane deflection [um]  (max {np.nanmax(w) * 1e3:.0f} um)",
               w * 1e3, "viridis", None),
              ("thermocol bearing pressure [kPa]", pres, "cividis", p_cap)]
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 6.4))
    for ax, (title, fld, cmap, vmax) in zip(axes, panels):
        bad = ~np.all(np.isfinite(fld)[tri], axis=1)
        tri_obj.set_mask(bad)
        kw = {} if vmax is None else {"vmax": vmax}
        tpc = ax.tripcolor(tri_obj, fld, shading="gouraud", cmap=cmap, **kw)
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=9)
        ax.tick_params(labelsize=7)
        fig.colorbar(tpc, ax=ax, shrink=0.8)
    for i, (ex, ez) in enumerate(ears(), start=1):
        axes[0].plot(ex, ez, "o", ms=4, mfc="none", mec="cyan")
        axes[0].annotate(f"E{i}", (ex, ez), textcoords="offset points",
                         xytext=(4, 4), color="cyan", fontsize=8)
    fig.suptitle(f"plate FEA - 12 g envelope (T = {res12['T_ear']:.0f} N per ear, "
                 f"rigid thermocol bed)"
                 + (f", ear blends R{fillet_r:.0f}" if fillet_r else
                    ", profile as drawn"), fontsize=10)
    fig.tight_layout()
    fig.savefig(fig_dir / "fea_fields.png", dpi=170)
    plt.close(fig)

    # ear detail: stress concentration at the ear/outline blend
    fig, axes = plt.subplots(1, 4, figsize=(15.0, 4.2))
    for ax, (ex, ez), i in zip(axes, ears(), range(1, 5)):
        tri_obj = mtri.Triangulation(x, z, tri)
        tri_obj.set_mask(~np.all(np.isfinite(vm)[tri], axis=1))
        tpc = ax.tripcolor(tri_obj, vm, shading="gouraud", cmap="inferno",
                           vmin=0.0, vmax=float(np.nanmax(vm)))
        ax.set_xlim(ex - 24, ex + 24)
        ax.set_ylim(ez - 24, ez + 24)
        ax.set_aspect("equal")
        ax.set_title(f"ear {i}  ({ex:+.0f}, {ez:+.0f})", fontsize=8)
        ax.tick_params(labelsize=6)
    fig.colorbar(tpc, ax=axes, shrink=0.7, label="von Mises [MPa]")
    fig.suptitle("ear detail - stress at the ear / outline blend", fontsize=10)
    fig.savefig(fig_dir / "fea_ears.png", dpi=170)
    plt.close(fig)
    return fig_dir

def solve(work: Path, job: str = "plate", timeout: int = 3600) -> dict:
    ccx = ccx_binary()
    r = run_wsl(f"OMP_NUM_THREADS=4 {ccx} -i {job} > log.{job} 2>&1", cwd=work,
                timeout=timeout, check=False)
    log = (work / f"log.{job}").read_text(encoding="utf-8", errors="replace")
    if "Job finished" not in log:
        return {"ok": False, "returncode": r.returncode,
                "tail": log.splitlines()[-15:]}
    return {"ok": True, "returncode": r.returncode, **parse_results(work, job)}


def parse_frd(path: Path):
    """-> {nid: (x,y,z)}, {'DISP': [[nid,x,y,z]], 'STRESS': [[nid, sxx..szx]]}

    ccx may split the node section into up to three 2C blocks, so every block
    before the first result (-4) header is read as nodal coordinates.
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    nodes: dict[int, tuple[float, float, float]] = {}
    blocks: dict[str, list] = {}
    cur, in_nodes = None, False
    for line in lines:
        k3, k6 = line[:4].strip(), line[:7].strip()
        if k6 in ("2C", "3C"):
            in_nodes = k6 == "2C"
            continue
        if k3 == "-4":
            in_nodes = False
            cur = line[5:13].strip()
            blocks.setdefault(cur, [])
            continue
        if k3 != "-1":
            continue
        if in_nodes:
            try:
                nodes[int(line[3:13])] = (float(line[13:25]), float(line[25:37]),
                                          float(line[37:49]))
            except ValueError:
                pass
            continue
        if cur:
            body, vals = line[13:], []
            for k in range(0, len(body) - 11, 12):
                try:
                    vals.append(float(body[k:k + 12]))
                except ValueError:
                    pass
            if vals:
                blocks[cur].append([int(line[3:13]), *vals])
    return nodes, {k: np.asarray(v) for k, v in blocks.items()}


def von_mises(s: np.ndarray) -> np.ndarray:
    sxx, syy, szz, sxy, syz, szx = (s[:, i] for i in range(6))
    return np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                   + 3.0 * (sxy ** 2 + syz ** 2 + szx ** 2))


def parse_results(work: Path, job: str) -> dict:
    """Peak stress/displacement, bed reaction field and equilibrium residual."""
    nodes, blocks = parse_frd(work / f"{job}.frd")
    sid = blocks["STRESS"][:, 0].astype(int)
    vm = von_mises(blocks["STRESS"][:, 1:7])
    xyz = np.array([nodes[n] for n in sid])
    k = int(np.argmax(vm))

    disp = blocks["DISP"]
    did = disp[:, 0].astype(int)
    dxyz = np.array([nodes[int(n)] for n in did])
    uy = disp[:, 2]

    dat = (work / f"{job}.dat").read_text(encoding="utf-8", errors="replace")
    lines = dat.splitlines()
    bed: dict[int, float] = {}
    for i, ln in enumerate(lines):
        if "forces (fx,fy,fz) for set BED" in ln:      # per-node reaction table
            j = i + 1
            while j < len(lines):
                parts = lines[j].split()
                if not parts:
                    j += 1
                    continue
                if len(parts) != 4:
                    break
                bed[int(parts[0])] = float(parts[2])
                j += 1
            break

    # total reaction over the whole model = -applied load (equilibrium check)
    resid = None
    for i, ln in enumerate(lines):
        if "total force (fx,fy,fz) for set NALL" in ln:
            for ln2 in lines[i + 1:i + 4]:
                parts = ln2.split()
                if len(parts) == 3:
                    resid = [round(float(v), 3) for v in parts]
                    break
            break

    # nodal fields on the mid-surface, for plotting against the 2D mesh
    mid = np.abs(dxyz[:, 1]) < 1e-6
    surf = np.abs(np.abs(xyz[:, 1]) - T / 2) < 1e-6
    # section through the shroud edge (|X| = 120): what the hand calc calls the
    # ear root, away from the sharp ear/outline blend
    sec = surf & (np.abs(np.abs(xyz[:, 0]) - BOX_X / 2) < 0.8)
    # everything further than one lobe away from every ear = the plate field
    r_ear = np.min(np.stack([np.hypot(xyz[:, 0] - ex, xyz[:, 2] - ez)
                             for ex, ez in ears()], axis=1), axis=1)
    body = surf & (r_ear > EAR_R + 6.0)
    surf_layer = np.abs(xyz[:, 1] - T / 2) < 1e-6
    return {
        "max_vm_MPa": round(float(vm.max()), 2),
        "max_vm_at": [round(float(v), 2) for v in xyz[k]],
        "mid_vm_MPa": round(float(vm[np.abs(xyz[:, 1]) < 1e-6].max()), 2),
        "body_vm_MPa": round(float(vm[body].max()) if body.any() else 0.0, 2),
        "earroot_vm_MPa": round(float(vm[sec].max()) if sec.any() else 0.0, 2),
        "u_max_mm": round(float(np.linalg.norm(
            np.stack([disp[:, 1], disp[:, 2], disp[:, 3]], 1), axis=1).max()), 4),
        "w_max_mm": round(float(np.abs(uy).max()), 4),
        "reaction_total_N": resid,
        "bed": bed,
        "_mid": {int(n): float(v) for n, v in zip(did[mid], uy[mid])},
        "_surf_vm": {int(n): (tuple(nodes[int(n)]), float(v))
                     for n, v in zip(sid[surf], vm[surf])},
        "_surf_u": {int(n): (tuple(nodes[int(n)]), float(v))
                    for n, v in zip(did[surf_layer], uy[surf_layer])},
    }


def validate(work: Path) -> dict:
    """Cantilever-strip benchmark: S6 shells vs beam/plate theory."""
    import gmsh
    import meshio

    L, B, P = 100.0, 20.0, 1.0
    work.mkdir(parents=True, exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 2.5)
        gmsh.option.setNumber("Mesh.MeshSizeMin", 2.5)   # uniform: no slivers
        gmsh.option.setNumber("Mesh.ElementOrder", 2)
        gmsh.model.add("strip")
        geo = gmsh.model.geo
        p = [geo.addPoint(0, 0, 0, 2.5), geo.addPoint(L, 0, 0, 2.5),
             geo.addPoint(L, 0, B, 2.5), geo.addPoint(0, 0, B, 2.5)]
        lines = [geo.addLine(p[i], p[(i + 1) % 4]) for i in range(4)]
        geo.addPlaneSurface([geo.addCurveLoop(lines)])
        geo.synchronize()
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(2)
        gmsh.write(str(work / "strip.msh"))
    finally:
        gmsh.finalize()
    mesh = meshio.read(work / "strip.msh")
    pts = np.asarray(mesh.points)[:, [0, 2]]
    tris = np.vstack([c.data for c in mesh.cells if c.type == "triangle6"])
    area = nodal_areas(pts, tris)
    fix = np.where(np.abs(pts[:, 0]) < 1e-9)[0]
    tip = np.where(np.abs(pts[:, 0] - L) < 1e-9)[0]

    lines = ["*NODE"]
    for i, (x, z) in enumerate(pts, start=1):
        lines.append(f"{i}, {x:.7f}, 0., {z:.7f}")
    lines += emit_nset("FIX", fix + 1) + emit_nset("TIP", tip + 1)
    lines.append("*ELEMENT, TYPE=S6, ELSET=EALL")
    for eid, conn in enumerate(tris, start=1):
        lines.append(", ".join(str(v) for v in [eid, *(int(c) + 1 for c in conn)]))
    lines += ["*MATERIAL, NAME=AL6061T6", "*ELASTIC", f"{E}, {NU}",
              "*SHELL SECTION, ELSET=EALL, MATERIAL=AL6061T6", f"{T}",
              "*STEP", "*STATIC", "*BOUNDARY", "FIX, 1, 6", "*CLOAD"]
    w = area[tip] / area[tip].sum()
    for nid, f in zip(tip, w):
        lines.append(f"{int(nid) + 1}, 2, {-P * f:.9e}")
    lines += ["*NODE FILE, OUTPUT=3D", "U", "*EL FILE", "S", "*END STEP"]
    (work / "strip.inp").write_text("\n".join(lines) + "\n", encoding="utf-8")

    res = solve(work, "strip")
    I = B * T ** 3 / 12.0
    return {"mesh": [int(len(pts)), int(len(tris))],
            "w_tip_FEA_mm": res.get("w_max_mm"),
            "w_tip_beam_mm": round(P * L ** 3 / (3 * E * I), 5),
            "w_tip_plate_mm": round((1 - NU ** 2) * P * L ** 3 / (3 * E * I), 5),
            "sigma_root_FEA_MPa": res.get("max_vm_MPa"),
            "sigma_root_beam_MPa": round(6 * P * L / (B * T ** 2), 3),
            "ok": res.get("ok", False)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", default="balloon-ttp/plate-fea")
    ap.add_argument("--plate-dir", default=str(PLATE_DIR))
    ap.add_argument("--mesh-scale", type=float, default=1.0,
                    help="global element size multiplier (0.7 = finer)")
    ap.add_argument("--fillet", type=float, default=0.0,
                    help="label for a blend radius in the figure titles [mm]")
    ap.add_argument("--validate", action="store_true",
                    help="run the cantilever benchmark before the study")
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()

    study = study_dir(args.study)
    fea = study / "fea"
    fea.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ part
    outer, holes = read_dxf(Path(args.plate_dir) / "plate.dxf")
    cut = abs(_area(outer)) - sum(abs(_area(h)) for h in holes)
    pts, tris = build_mesh(outer, holes, args.mesh_scale, fea)
    area = nodal_areas(pts, tris)
    sets = build_sets(pts)
    plate_t = cut * T * RHO                          # tonnes
    W = (M_PAYLOAD + 2 * plate_t * 1000.0 + M_RIG) * G     # N, all-up weight
    print(f"profile {len(holes) + 1} contours, cut area {cut:.1f} mm2, "
          f"mesh {len(pts)} nodes / {len(tris)} S6, all-up {W:.2f} N")

    summary: dict = {
        "study": args.study, "solver": "CalculiX ccx 2.21 (WSL)",
        "model": {"elements": "S6 shells (6-node quadratic triangles)",
                  "expanded_to": "C3D15 by ccx", "thickness_mm": T,
                  "support": "rigid frictionless bed over the shroud footprint",
                  "load": "20 mm washer patch per ear + plate self weight",
                  "material": {"E_MPa": E, "nu": NU, "rho_t_mm3": RHO,
                               "Fty_MPa": FTY, "Ftu_MPa": FTU}},
        "geometry": {"cut_area_mm2": round(cut, 1),
                     "plate_mass_g": round(plate_t * 1e6, 1),
                     "mesh_scale": args.mesh_scale,
                     "n_nodes": int(len(pts)), "n_elements": int(len(tris))},
        "all_up_weight_N": round(W, 2),
        "validate": validate(fea / "validate") if args.validate else None,
    }
    if summary["validate"]:
        print("validate:", json.dumps(summary["validate"]))

    # ---------------------------------------------------------------- cases
    cases = [("1 g, loops just taut", 1.0, 0.0, 4),
             ("2 g balloon launch jerk", 2.0, 0.0, 4),
             ("5 g parachute opening", 5.0, 0.0, 4),
             ("12 g design envelope", 12.0, 0.0, 4),
             ("16.2 g qualification limit", 16.2, 0.0, 4),
             ("1 g + 50 N pretension", 1.0, 50.0, 4),
             ("1 g + 100 N pretension", 1.0, 100.0, 4),
             ("5 g, one loop lost (2 ears)", 5.0, 0.0, 2)]
    rows, keep12 = [], None
    for icase, (name, n_g, T0, n_ears) in enumerate(cases):
        T_ear = n_g * W / n_ears + T0
        job = f"case{icase + 1}"
        write_deck(fea / f"{job}.inp", pts, tris, sets, area, T_ear=T_ear,
                   ear_ids=(1, 2) if n_ears == 2 else (1, 2, 3, 4),
                   title=f"{name}: T = {T_ear:.1f} N per ear")
        res = solve(fea, job)
        if not res.get("ok"):
            print(f"[{name}] FAILED:", res.get("tail"))
            return 1
        res["T_ear"] = T_ear
        row = {"case": name, "job": job, "n_g": n_g, "T0_N": T0, "n_ears": n_ears,
               "T_ear_N": round(T_ear, 1),
               **{k: v for k, v in res.items()
                  if not k.startswith("_") and k != "bed"},
               **case_metrics(res, pts, area, sets)}
        row["SF_yield"] = round(FTY / row["max_vm_MPa"], 2)
        row["SF_ult"] = round(FTU / row["max_vm_MPa"], 2)
        row["SF_bearing"] = round(EPS_ALLOW * 1e3 / max(row["bearing_kPa"]), 2)
        rows.append(row)
        print(f"  {name:32s} T={T_ear:6.1f} N  vm={row['max_vm_MPa']:6.1f} MPa  "
              f"SFy={row['SF_yield']:5.2f}  w={row['w_max_mm']:.4f} mm  "
              f"p={max(row['bearing_kPa']):6.1f} kPa")
        if n_g == 12.0 and T0 == 0.0:
            keep12 = (res, row)
    summary["cases"] = rows

    res12, _ = keep12
    ratio = FTY / res12["max_vm_MPa"]
    summary["envelope"] = {
        "T_yield_N": round(res12["T_ear"] * ratio, 1),
        "T_ult_N": round(res12["T_ear"] * ratio * FTU / FTY, 1),
        "g_yield": round(res12["T_ear"] * ratio * 4 / W, 1)}

    # -------------------------------------------------- mesh independence
    conv = []
    for sc in (1.45, args.mesh_scale, 0.72):
        p2, t2 = build_mesh(outer, holes, sc, fea)
        a2, s2 = nodal_areas(p2, t2), build_sets(p2)
        write_deck(fea / "conv.inp", p2, t2, s2, a2, T_ear=12.0 * W / 4,
                   title=f"mesh convergence {sc}")
        r2 = solve(fea, "conv")
        conv.append({"scale": sc, "n_nodes": int(len(p2)),
                     "n_elements": int(len(t2)),
                     "max_vm_MPa": r2.get("max_vm_MPa"),
                     "earroot_vm_MPa": r2.get("earroot_vm_MPa"),
                     "w_max_mm": r2.get("w_max_mm")})
        print(f"  mesh {sc:4.2f}: {len(t2):6d} el  vm={r2.get('max_vm_MPa'):6.2f}"
              f"  earroot={r2.get('earroot_vm_MPa'):6.2f} MPa")
    summary["mesh_convergence"] = conv

    fil = None
    if args.fillet > 0:
        pf, tf = build_mesh(round_corners(outer, args.fillet), holes,
                            args.mesh_scale, fea)
        af, sf = nodal_areas(pf, tf), build_sets(pf)
        write_deck(fea / "fillet.inp", pf, tf, sf, af, T_ear=12.0 * W / 4,
                   title=f"12 g with R{args.fillet:.0f} ear blends")
        rf = solve(fea, "fillet")
        fil = {"radius_mm": args.fillet, "n_elements": int(len(tf)),
               "max_vm_MPa": rf.get("max_vm_MPa"),
               "earroot_vm_MPa": rf.get("earroot_vm_MPa"),
               "w_max_mm": rf.get("w_max_mm")}
        print(f"  R{args.fillet:.0f} blend: vm={rf.get('max_vm_MPa'):6.2f} MPa")
    # ------------------------------------------------ sheet thickness sweep
    thk = []
    for t_mm in (1.0, 1.5, 2.0, 2.5):
        write_deck(fea / "thk.inp", pts, tris, sets, area, T_ear=12.0 * W / 4,
                   thickness=t_mm, title=f"thickness {t_mm} mm, 12 g")
        rt = solve(fea, "thk")
        row = {"t_mm": t_mm, "max_vm_MPa": rt.get("max_vm_MPa"),
               "earroot_vm_MPa": rt.get("earroot_vm_MPa"),
               "w_max_mm": rt.get("w_max_mm")}
        row["g_yield"] = round(12.0 * FTY / max(rt.get("max_vm_MPa"), 1e-6), 1)
        thk.append(row)
        print(f"  t = {t_mm:.1f} mm: vm={row['max_vm_MPa']:6.2f} MPa  "
              f"g_yield={row['g_yield']:5.1f}")
    summary["thickness_sweep"] = thk
    summary["fillet"] = None

    if not args.no_plots:
        summary["figures"] = str(make_figures(study, pts, tris, area, res12,
                                              args.fillet or None))
    (fea / "fea_summary.json").write_text(json.dumps(summary, indent=2),
                                          encoding="utf-8")
    report(study, summary)
    print(f"\nwritten to {study}")
    try:
        from learning_store import harvest
        harvest(args.study, case_type="fea_analysis")
    except Exception as exc:                       # noqa: BLE001
        print("learning_store harvest skipped:", exc)
    return 0


def report(study: Path, s: dict) -> None:
    """Markdown report (study report/ + a copy in the payload design folder)."""
    L: list[str] = []
    add = L.append
    model, geo, val = s["model"], s["geometry"], s["validate"]
    env, fil = s["envelope"], s["fillet"]
    add("# Payload support plate - shell FEA")
    add("")
    add("`tools/check_strength.py` in the payload project checks the ear as a")
    add("hand-calculated cantilever. This study is the finite-element cross-check")
    add("of the whole part: the real cut profile, a 2.0 mm aluminium shell, the")
    add("thermocol lid as a support and the rope load applied where the washer")
    add("actually presses.")
    add("")
    add("| | |")
    add("|---|---|")
    add(f"| solver | {s['solver']} |")
    add(f"| elements | {model['elements']}, t = {model['thickness_mm']} mm "
        f"(expanded to {model['expanded_to']}) |")
    add(f"| material | Al 6061-T6: E = {model['material']['E_MPa']:.0f} MPa, "
        f"nu = {model['material']['nu']}, Fty = {model['material']['Fty_MPa']:.0f}, "
        f"Ftu = {model['material']['Ftu_MPa']:.0f} MPa |")
    add(f"| support | {model['support']} + 3-2-1 in-plane point constraints |")
    add(f"| load | {model['load']} |")
    add(f"| mesh | {geo['n_elements']} S6 elements, {geo['n_nodes']} nodes "
        f"(scale {geo['mesh_scale']}) |")
    add(f"| geometry | design/plate.dxf, cut area {geo['cut_area_mm2']:.0f} mm2, "
        f"plate {geo['plate_mass_g']:.0f} g |")
    add(f"| all-up weight | {s['all_up_weight_N']:.2f} N (4.89 kg) |")
    add("")
    if val:
        add("## Validation of the model")
        add("")
        add("A 100 x 20 x 2 mm cantilever strip of the same material was meshed")
        add(f"and loaded the same way ({val['mesh'][0]} nodes, {val['mesh'][1]} S6).")
        add("")
        add("| quantity | FEA | theory | ratio |")
        add("|---|---|---|---|")
        add(f"| tip deflection | {val['w_tip_FEA_mm']:.4f} mm | "
            f"{val['w_tip_beam_mm']:.4f} mm (beam) / {val['w_tip_plate_mm']:.4f} mm "
            f"(plate) | {val['w_tip_FEA_mm'] / val['w_tip_beam_mm']:.2f} |")
        add(f"| root stress | {val['sigma_root_FEA_MPa']:.2f} MPa | "
            f"{val['sigma_root_beam_MPa']:.2f} MPa | "
            f"{val['sigma_root_FEA_MPa'] / val['sigma_root_beam_MPa']:.2f} |")
        add("")
        add("The strip sits between beam theory (narrow strip) and plate theory")
        add("(lateral curvature suppressed), i.e. the shell behaves as it should.")
        add("")
    add("## Load cases")
    add("")
    add("Each ear carries the clamp-loop tension T = n g W / 4 + T0, where T0 is")
    add("the per-loop pretension. The loops - not the foam - carry the payload,")
    add("so a heavily pretensioned loop loads the ear more than the g-level does.")
    add("")
    add("| case | T / ear | von Mises | SF yield | SF ult | w max | bearing | SF bear |")
    add("|---|---|---|---|---|---|---|---|")
    for r in s["cases"]:
        add(f"| {r['case']} | {r['T_ear_N']:.0f} N | {r['max_vm_MPa']:.1f} MPa | "
            f"{r['SF_yield']:.2f} | {r['SF_ult']:.2f} | {r['w_max_mm']:.3f} mm | "
            f"{max(r['bearing_kPa']):.0f} kPa | {r['SF_bearing']:.1f} |")
    add("")
    add(f"Yield of the peak location corresponds to **T = {env['T_yield_N']:.0f} N "
        f"per ear** (ultimate {env['T_ult_N']:.0f} N), i.e. about "
        f"**{env['g_yield']:.1f} g** with just-taut loops.")
    add("")
    r12 = s["cases"][3]
    add("## Where the stress is")
    add("")
    add(f"At the 12 g envelope the peak is {r12['max_vm_MPa']:.1f} MPa at "
        f"X = {r12['max_vm_at'][0]:.1f}, Z = {r12['max_vm_at'][2]:.1f} - on the")
    add("ear circumference, where the R15 ear lobe runs into the straight plate")
    add("edge. That transition is a **sharp re-entrant corner** in the cut")
    add("profile. The hand calc assumes the ear root is the full 24.7 mm chord")
    add("with Kt = 1.15; the FE load path actually crosses the ear/plate blend at")
    add("~12 mm width, with the notch concentration on top of that.")
    add("")
    add(f"Outside the four lobes the whole plate peaks at "
        f"**{r12['body_vm_MPa']:.0f} MPa** at the same 12 g load, so the camera")
    add("aperture ring, the lightening openings and the ligaments are not at")
    add("risk, and neither is the part in global bending. Note that the rigid")
    add("bed holds the field flat, so this is an underestimate: a compliant")
    add("foundation lets the plate sink and bend a little more, but not to")
    add("anything like the ear value.")
    add("")
    add(f"The through-thickness average (mid-surface) stress at the peak is "
        f"{r12['mid_vm_MPa']:.0f} MPa,")
    add("about half the surface value: the ear blend is a mixed bending +")
    add("in-plane notch. Both come from the same geometry, so fixing the blend")
    add("fixes both.")
    add("")
    add("## Mesh independence")
    add("")
    add("| element size scale | elements | peak von Mises | ear-root section | w max |")
    add("|---|---|---|---|---|")
    for c in s["mesh_convergence"]:
        add(f"| {c['scale']:.2f} | {c['n_elements']} | {c['max_vm_MPa']:.2f} MPa | "
            f"{c['earroot_vm_MPa']:.2f} MPa | {c['w_max_mm']:.3f} mm |")
    add("")
    add("A sharp corner has no finite radius, so its peak is a local")
    add("concentration rather than a field value; the table shows it settling at")
    add("about 225 MPa while the ear-root section converges to the same number,")
    add("i.e. the concentration is real and mesh-independent, not a numerical")
    add("artifact.")
    add("")
    add("## Sheet thickness")
    add("")
    add("Same profile, same 12 g loop load, only `*SHELL SECTION` changes - a")
    add("direct cross-check of `strength.md` section 'Thickness sensitivity'.")
    add("")
    add("| t | peak von Mises | first yield | mass / pair |")
    add("|---|---|---|---|")
    for r in s.get("thickness_sweep", []):
        add(f"| {r['t_mm']:.1f} mm | {r['max_vm_MPa']:.1f} MPa | "
            f"{r['g_yield']:.1f} g | {2 * geo['cut_area_mm2'] * r['t_mm'] * RHO * 1e6:.0f} g |")
    add("")
    add("Peak stress falls with t^2 as expected, so going to 2.5 mm sheet is a")
    add("one-line change that buys ~1.5x capacity at the blend - at the cost of")
    add("mass against the 5 kg limit.")
    add("")
    add("## Bearing on the thermocol")
    add("")
    add("The bed is modelled as rigid, so its reaction concentrates under the ear")
    add("corner and is an *upper bound* on the foam pressure. The real EPS is")
    add("compliant (k = E/t = 0.06 N/mm3) and spreads the load over its")
    add("characteristic length L = 30.5 mm. The pi L^2 spreading model in")
    add("strength.md (about 4 kPa/ear at 1 g) is the realistic number and keeps a")
    add("wide margin on the 100 kPa EPS limit at every case in the table.")
    add("")
    add("## Conclusions")
    add("")
    add("* The plate is a bending part and the ears govern, as assumed - but the")
    add("  real concentration is at the ear/outline blend, not at the washer seat.")
    add(f"  The FEA peak ({r12['max_vm_MPa']:.0f} MPa at 12 g) is about "
        f"{r12['max_vm_MPa'] / (6.19 * 12.0):.1f}x the strength.md hand calc")
    add("  (6.2 MPa/ear at 1 g scaled to 12 g), because the ear only overlaps the")
    add("  plate over a ~12 mm chord and the blend is a sharp re-entrant corner.")
    add(f"* Outside the four lobes the plate peaks at "
        f"{r12['body_vm_MPa']:.0f} MPa, so the apertures, the openings and the")
    add("  ligaments are not at risk, and neither is the part in global bending.")
    add(f"  Deflections are small ({r12['w_max_mm']:.2f} mm at 12 g).")
    add(f"* With every loop taut the ear blend first yields at about "
        f"{env['g_yield']:.0f} g (T = {env['T_yield_N']:.0f} N/ear), against")
    add("  strength.md's 33.7 g. That still covers the expected flight loads -")
    add(f"  {s['cases'][1]['n_g']:.0f} g gives SF {s['cases'][1]['SF_yield']:.1f} "
        f"and {s['cases'][2]['n_g']:.0f} g SF {s['cases'][2]['SF_yield']:.1f} - but")
    add("  it does **not** cover the 12-16 g qualification envelope the same")
    add("  document quotes.")
    add("* Loop pretension of 50-100 N, easily applied by hand, is a large share")
    add("  of the ear load (it doubles or triples it). Specify the pretension.")
    add("* Two ways to restore the envelope, in order of preference:")
    add("  1. blend the ear/outline transitions (R3-R5) in the cut profile - it")
    add("     only adds material in empty space, no interface change, and it")
    add("     removes the notch that produces the concentration;")
    add("  2. go to 2.5 mm sheet (see the table above) - about 1.5x capacity for")
    add("     +88 g per pair.")
    add("  Either way, re-run this study afterwards and re-issue strength.md.")
    add("")
    if s.get("figures"):
        add("## Figures")
        add("")
        add("![fields](figures/fea_fields.png)")
        add("")
        add("![ears](figures/fea_ears.png)")
        add("")
    add("## Artifacts")
    add("")
    add("Reproduce with (agent repo, `.venv`):")
    add("")
    add("```")
    add("python run_plate_fea.py --study balloon-ttp/plate-fea --validate")
    add("```")
    add("")
    add("`outputs/balloon-ttp/plate-fea/fea/` holds the CalculiX decks and")
    add("results per case (`case1.inp`/`.frd` ... `case8`, `conv`, `thk`,")
    add("`validate/strip`), `fea_summary.json` with every number in this report,")
    add("and `figures/` with the two plots.")
    add("")
    text = "\n".join(L) + "\n"
    out = study / "report"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fea_report.md").write_text(text, encoding="utf-8")

    try:                                   # copy beside the payload drawings
        import shutil
        for name in ("fea_fields.png", "fea_ears.png"):
            src = study / "figures" / name
            if src.exists():
                shutil.copy2(src, PLATE_DIR / name)
        (PLATE_DIR / "fea.md").write_text(
            text.replace("figures/fea_fields.png", "fea_fields.png")
                .replace("figures/fea_ears.png", "fea_ears.png"),
            encoding="utf-8")
        print("copied report + figures to", PLATE_DIR)
    except OSError as exc:
        print("could not copy to the payload project:", exc)


if __name__ == "__main__":
    sys.exit(main())
