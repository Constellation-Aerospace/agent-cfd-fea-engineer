#!/usr/bin/env python3
"""Parametric geometry for a submerged marine exhaust discharge domain (Gmsh OCC).

Placeholder geometry until the confidential CAD arrives (post-NDA): a horizontal
exhaust pipe (bore D, wall thickness t) penetrating the side wall of a rectangular
water/air domain, discharging at submergence depth Hs below the free surface (z=0).
Gravity acts in -z. The domain includes an air layer above the free surface so the
plume can vent through the top "atmosphere" pressure boundary.

Boundary patches (physical groups):
    inlet       — exhaust gas velocity inlet (pipe entrance disk)
    atmosphere  — domain top, total-pressure outlet
    pipeWall    — pipe bore, exterior, and tip surfaces (no-slip)
    seaBoundary — domain sides/bottom (treated as far-field walls)

The real CAD (STEP) can replace `build_model()` later — keep the same physical
group names and the rest of the pipeline is unchanged.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DEFAULT_PARAMS = {
    "pipe_diameter": 0.30,      # bore D [m]
    "wall_thickness": 0.012,    # pipe wall [m]
    "pipe_external_length": 1.0,  # upstream approach length outside domain [m]
    "pipe_penetration": 0.5,    # length protruding into the water domain [m]
    "submergence": 2.0,         # pipe axis depth below free surface [m]
    "domain_length": 10.0,      # x extent [m]
    "domain_width": 6.0,        # y extent [m]
    "water_depth": 5.0,         # below free surface [m]
    "air_height": 1.0,          # above free surface [m]
}

PATCHES = ("inlet", "atmosphere", "pipeWall", "seaBoundary")


def build_model(params: dict, mesh_size_factor: float = 1.0):
    """Build the Gmsh OCC model + refinement fields. Caller must gmsh.initialize() first.

    Returns a dict mapping patch name -> list of surface tags.
    """
    import gmsh

    p = {**DEFAULT_PARAMS, **params}
    D = p["pipe_diameter"]
    R = D / 2.0
    Ro = R + p["wall_thickness"]
    Lext = p["pipe_external_length"]
    Lpen = p["pipe_penetration"]
    Hs = p["submergence"]
    Lx, Ly = p["domain_length"], p["domain_width"]
    Hd, Ha = p["water_depth"], p["air_height"]

    if Hs + Ro > Hd or Hs - Ro < 0:
        raise ValueError("Pipe must be fully submerged inside the water column: "
                         f"need Ro < Hs < water_depth - Ro (Hs={Hs}, Ro={Ro}, Hd={Hd})")

    occ = gmsh.model.occ
    box = occ.addBox(0, -Ly / 2, -Hd, Lx, Ly, Hd + Ha)
    bore = occ.addCylinder(-Lext, 0, -Hs, Lext + Lpen, 0, 0, R)
    shell = occ.addCylinder(-Lext, 0, -Hs, Lext + Lpen, 0, 0, Ro)
    bore2 = occ.addCylinder(-Lext, 0, -Hs, Lext + Lpen, 0, 0, R)
    annulus, _ = occ.cut([(3, shell)], [(3, bore2)])

    fused, _ = occ.fuse([(3, box)], [(3, bore)])
    fluid, _ = occ.cut(fused, annulus)
    occ.synchronize()

    if len(fluid) != 1:
        raise RuntimeError(f"Expected a single fluid volume, got {len(fluid)}")
    vol = fluid[0]

    tol = 1e-4
    groups: dict[str, list[int]] = {name: [] for name in PATCHES}
    for dim, tag in gmsh.model.getBoundary([vol], oriented=False):
        cx, cy, cz = gmsh.model.occ.getCenterOfMass(dim, tag)
        rr = math.hypot(cy, cz + Hs)  # radial distance from pipe axis
        if abs(cx + Lext) < tol and rr < Ro:
            groups["inlet"].append(tag)
        elif abs(cz - Ha) < tol:
            groups["atmosphere"].append(tag)
        elif rr < Ro + tol and -Lext - tol < cx < Lpen + tol:
            groups["pipeWall"].append(tag)
        else:
            groups["seaBoundary"].append(tag)

    for name, tags in groups.items():
        if not tags:
            raise RuntimeError(f"Patch classification failed: no surfaces for '{name}'")
        pg = gmsh.model.addPhysicalGroup(2, tags)
        gmsh.model.setPhysicalName(2, pg, name)
    pgv = gmsh.model.addPhysicalGroup(3, [vol[1]])
    gmsh.model.setPhysicalName(3, pgv, "fluid")

    # ── Mesh size fields ────────────────────────────────────────────────────
    f = mesh_size_factor
    size_jet = D / 6 * f        # jet development region
    size_pipe = D / 6 * f       # near pipe walls
    size_surface = D / 2.5 * f  # free-surface band (VOF interface)
    size_far = min(Lx, Ly, Hd) / 12 * f

    fields = []
    jet = gmsh.model.mesh.field.add("Cylinder")
    gmsh.model.mesh.field.setNumber(jet, "Radius", 3.5 * R)
    gmsh.model.mesh.field.setNumber(jet, "XCenter", Lpen + 4 * D)
    gmsh.model.mesh.field.setNumber(jet, "YCenter", 0)
    gmsh.model.mesh.field.setNumber(jet, "ZCenter", -Hs)
    gmsh.model.mesh.field.setNumber(jet, "XAxis", 5 * D)
    gmsh.model.mesh.field.setNumber(jet, "YAxis", 0)
    gmsh.model.mesh.field.setNumber(jet, "ZAxis", 0)
    gmsh.model.mesh.field.setNumber(jet, "VIn", size_jet)
    gmsh.model.mesh.field.setNumber(jet, "VOut", size_far)
    fields.append(jet)

    near_pipe = gmsh.model.mesh.field.add("Distance")
    gmsh.model.mesh.field.setNumbers(near_pipe, "SurfacesList", groups["pipeWall"] + groups["inlet"])
    gmsh.model.mesh.field.setNumber(near_pipe, "Sampling", 60)
    thr = gmsh.model.mesh.field.add("Threshold")
    gmsh.model.mesh.field.setNumber(thr, "InField", near_pipe)
    gmsh.model.mesh.field.setNumber(thr, "SizeMin", size_pipe)
    gmsh.model.mesh.field.setNumber(thr, "SizeMax", size_far)
    gmsh.model.mesh.field.setNumber(thr, "DistMin", 2 * D)
    gmsh.model.mesh.field.setNumber(thr, "DistMax", 8 * D)
    fields.append(thr)

    surf = gmsh.model.mesh.field.add("Box")
    gmsh.model.mesh.field.setNumber(surf, "XMin", 0)
    gmsh.model.mesh.field.setNumber(surf, "XMax", Lx)
    gmsh.model.mesh.field.setNumber(surf, "YMin", -Ly / 2)
    gmsh.model.mesh.field.setNumber(surf, "YMax", Ly / 2)
    gmsh.model.mesh.field.setNumber(surf, "ZMin", -0.4)
    gmsh.model.mesh.field.setNumber(surf, "ZMax", 0.4)
    gmsh.model.mesh.field.setNumber(surf, "VIn", size_surface)
    gmsh.model.mesh.field.setNumber(surf, "VOut", size_far)
    fields.append(surf)

    # Plume rise corridor between pipe tip and free surface
    rise = gmsh.model.mesh.field.add("Box")
    gmsh.model.mesh.field.setNumber(rise, "XMin", Lpen)
    gmsh.model.mesh.field.setNumber(rise, "XMax", Lpen + 10 * D)
    gmsh.model.mesh.field.setNumber(rise, "YMin", -3 * D)
    gmsh.model.mesh.field.setNumber(rise, "YMax", 3 * D)
    gmsh.model.mesh.field.setNumber(rise, "ZMin", -Hs)
    gmsh.model.mesh.field.setNumber(rise, "ZMax", 0.4)
    gmsh.model.mesh.field.setNumber(rise, "VIn", size_jet * 1.6)
    gmsh.model.mesh.field.setNumber(rise, "VOut", size_far)
    fields.append(rise)

    fmin = gmsh.model.mesh.field.add("Min")
    gmsh.model.mesh.field.setNumbers(fmin, "FieldsList", fields)
    gmsh.model.mesh.field.setAsBackgroundMesh(fmin)

    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)  # HXT (fast parallel Delaunay)
    return groups


def generate_mesh(params: dict, out_msh: str | Path, mesh_size_factor: float = 1.0,
                  order: int = 1) -> dict:
    """Generate the volume mesh and write a Gmsh v2.2 .msh (for gmshToFoam).

    Returns a stats dict (node/element counts, timing).
    """
    import time
    import gmsh

    t0 = time.time()
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("marine_exhaust")
        build_model(params, mesh_size_factor)
        gmsh.model.mesh.generate(3)
        if order > 1:
            gmsh.model.mesh.setOrder(order)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        out_msh = Path(out_msh)
        out_msh.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(out_msh))

        nodes = gmsh.model.mesh.getNodes()[0]
        _, tet_tags, _ = gmsh.model.mesh.getElements(3)
        n_cells = sum(len(t) for t in tet_tags)
        stats = {
            "msh_file": str(out_msh),
            "mesh_size_factor": mesh_size_factor,
            "n_nodes": len(nodes),
            "n_cells_3d": int(n_cells),
            "elapsed_s": round(time.time() - t0, 1),
            "params": {**DEFAULT_PARAMS, **params},
        }
        Path(out_msh).with_suffix(".stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
        return stats
    finally:
        gmsh.finalize()


def export_step(params: dict, out_step: str | Path) -> str:
    """Export the fluid-domain solid as STEP (for records / CAD exchange)."""
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("marine_exhaust_cad")
        build_model(params)
        out_step = Path(out_step)
        out_step.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(out_step))
        return str(out_step)
    finally:
        gmsh.finalize()
