#!/usr/bin/env python3
"""Multi-part STEP assembly ingestion for conjugate heat transfer studies (Gmsh OCC).

Pipeline:
    inspect_step()   import STEP -> boolean-fragment (conformal interfaces) ->
                     enumerate components + contact interfaces -> write
                     outputs/<study>/assembly/manifest.json (+ surfaces.json)
    <agent/user assigns per-component material + type and boundary patches
     in the manifest — see assign helpers or edit the JSON directly>
    mesh_assembly()  re-import + fragment, one physical volume per component
                     (becomes an OpenFOAM cellZone via gmshToFoam), physical
                     surfaces from manifest patch selectors, export Gmsh v2.2

The manifest is the single source of truth downstream (cht_case / cht_pipeline).
STEP files in mm are converted to metres automatically (Geometry.OCCTargetUnit).

Manifest schema (written by inspect_step, edited by assignment):
{
  "step_file": "...", "components": {
      "<name>": {"type": "solid"|"fluid", "material": null|"<library name>",
                  "overrides": {}, "T_init_C": null,
                  "solids": [tags], "volume_m3": v, "centroid_m": [x,y,z],
                  "bbox_m": [xmin,ymin,zmin,xmax,ymax,zmax]}},
  "interfaces": [{"components": [a, b], "area_m2": s, "n_surfaces": n}],
  "patches": {
      "<patchName>": {"component": "<name>",
                       "select": "xmin|xmax|ymin|ymax|zmin|zmax|remaining"
                                 | {"box": [...6 floats...]}
                                 | {"plane": {"axis": "x|y|z", "value": v}}
                                 | {"surfaces": [tags]},
                       "bc": {"type": "velocity_inlet|pressure_outlet|fixed_temperature|"
                                       "heat_flux|convection|adiabatic|symmetry", ...}}},
  "radiation": {"model": "none|P1|fvDOM", "emissivity_default": 0.9},
  "solver": {...}  # see cht_case.DEFAULT_SOLVER
}
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

MANIFEST_NAME = "manifest.json"
SURFACES_NAME = "surfaces.json"


# ─────────────────────────────── helpers ─────────────────────────────────────

def safe_name(raw: str, used: set[str], fallback: str) -> str:
    """OpenFOAM-safe unique region name from a STEP label."""
    name = raw.strip().split("/")[-1]              # gmsh gives 'Assembly/Part' paths
    name = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()
    if not name or not name[0].isalpha():
        name = fallback
    base, i = name, 1
    while name in used:
        i += 1
        name = f"{base}_{i}"
    used.add(name)
    return name


def _import_and_fragment(step_file: str | Path):
    """Import STEP (forced to metres) and fragment all solids so shared/contact
    faces are imprinted and conformal. Returns list of 3D (dim, tag) entities.

    Caller must have gmsh initialised; gmsh is imported lazily so pure-JSON
    manifest operations work without the gmsh package.
    """
    import gmsh
    gmsh.option.setString("Geometry.OCCTargetUnit", "M")
    occ = gmsh.model.occ
    occ.importShapes(str(step_file))
    occ.synchronize()
    vols = gmsh.model.getEntities(3)
    if not vols:
        raise RuntimeError(f"No solids found in STEP file: {step_file}")
    if len(vols) > 1:
        out, _ = occ.fragment(vols, [])
        occ.synchronize()
    return gmsh.model.getEntities(3)


def _volume_info(dim_tag) -> dict:
    import gmsh
    dim, tag = dim_tag
    x, y, z = gmsh.model.occ.getCenterOfMass(dim, tag)
    vol = gmsh.model.occ.getMass(dim, tag)
    bb = gmsh.model.getBoundingBox(dim, tag)
    return {"tag": tag, "volume_m3": vol, "centroid_m": [x, y, z], "bbox_m": list(bb)}


# ─────────────────────────────── inspection ──────────────────────────────────

def inspect_step(step_file: str | Path, out_dir: str | Path) -> dict:
    """Enumerate assembly components + contact interfaces; write manifest template.

    An existing manifest is preserved: geometry data is refreshed but material,
    type, patch, radiation and solver assignments survive re-inspection.
    """
    import gmsh
    step_file = Path(step_file).resolve()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("assembly_inspect")
        vols = _import_and_fragment(step_file)

        used: set[str] = set()
        components: dict[str, dict] = {}
        tag_to_comp: dict[int, str] = {}
        for i, (dim, tag) in enumerate(vols, start=1):
            label = gmsh.model.getEntityName(dim, tag) or ""
            name = safe_name(label, used, f"part_{i}")
            info = _volume_info((dim, tag))
            components[name] = {
                "step_label": label, "type": "solid", "material": None,
                "overrides": {}, "T_init_C": None,
                "solids": [tag], "volume_m3": round(info["volume_m3"], 9),
                "centroid_m": [round(c, 6) for c in info["centroid_m"]],
                "bbox_m": [round(c, 6) for c in info["bbox_m"]],
            }
            tag_to_comp[tag] = name

        # surfaces: 2 parent volumes -> interface; 1 -> external boundary
        interfaces: dict[tuple, dict] = {}
        surfaces: list[dict] = []
        for dim, stag in gmsh.model.getEntities(2):
            up, _ = gmsh.model.getAdjacencies(dim, stag)
            owners = sorted(tag_to_comp[t] for t in up if t in tag_to_comp)
            area = gmsh.model.occ.getMass(dim, stag)
            cx, cy, cz = gmsh.model.occ.getCenterOfMass(dim, stag)
            surfaces.append({"tag": stag, "owners": owners, "area_m2": round(area, 9),
                             "centroid_m": [round(cx, 6), round(cy, 6), round(cz, 6)],
                             "bbox_m": [round(c, 6) for c in gmsh.model.getBoundingBox(dim, stag)]})
            if len(owners) == 2:
                key = tuple(owners)
                rec = interfaces.setdefault(key, {"components": list(key), "area_m2": 0.0,
                                                  "n_surfaces": 0})
                rec["area_m2"] = round(rec["area_m2"] + area, 9)
                rec["n_surfaces"] += 1
    finally:
        gmsh.finalize()

    manifest_path = out_dir / MANIFEST_NAME
    prev = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    prev_comps = prev.get("components", {})
    for name, comp in components.items():
        if name in prev_comps:
            for key in ("type", "material", "overrides", "T_init_C"):
                comp[key] = prev_comps[name].get(key, comp[key])

    manifest = {
        "step_file": str(step_file),
        "components": components,
        "interfaces": sorted(interfaces.values(), key=lambda r: -r["area_m2"]),
        "patches": prev.get("patches", {}),
        "radiation": prev.get("radiation", {"model": "none", "emissivity_default": 0.9}),
        "solver": prev.get("solver", {}),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out_dir / SURFACES_NAME).write_text(json.dumps(surfaces, indent=2), encoding="utf-8")
    return manifest


# ─────────────────────────────── validation ──────────────────────────────────

def validate_manifest(manifest: dict) -> list[str]:
    """Return a list of blocking problems (empty = ready to mesh/setup)."""
    from materials import get_material
    problems = []
    comps = manifest.get("components", {})
    if not comps:
        problems.append("Manifest has no components — run inspection first.")
    for name, comp in comps.items():
        if comp.get("type") not in ("solid", "fluid"):
            problems.append(f"Component '{name}': type must be 'solid' or 'fluid'.")
            continue
        mat = comp.get("material")
        if not mat:
            problems.append(f"Component '{name}': no material assigned.")
            continue
        try:
            props = get_material(mat, comp.get("overrides"))
        except KeyError as e:
            problems.append(f"Component '{name}': {e.args[0]}")
            continue
        if props["kind"] != comp["type"]:
            problems.append(f"Component '{name}' is typed '{comp['type']}' but material "
                            f"'{mat}' is a {props['kind']}.")
    for pname, patch in manifest.get("patches", {}).items():
        if patch.get("component") not in comps:
            problems.append(f"Patch '{pname}': unknown component '{patch.get('component')}'.")
        bc = patch.get("bc", {})
        btype = bc.get("type")
        known = ("velocity_inlet", "pressure_outlet", "fixed_temperature",
                 "heat_flux", "convection", "adiabatic", "symmetry",
                 "space_environment", "altitude_environment")
        if btype not in known:
            problems.append(f"Patch '{pname}': bc.type '{btype}' not in {known}.")
        elif btype == "velocity_inlet" and not (bc.get("U_m_s") or bc.get("m_dot_kg_s")):
            problems.append(f"Patch '{pname}': velocity_inlet needs U_m_s or m_dot_kg_s.")
        elif btype == "velocity_inlet" and bc.get("T_C") is None:
            problems.append(f"Patch '{pname}': velocity_inlet needs T_C.")
        elif btype == "convection" and (bc.get("h_W_m2K") is None or bc.get("T_amb_C") is None):
            problems.append(f"Patch '{pname}': convection needs h_W_m2K and T_amb_C.")
        elif btype == "fixed_temperature" and bc.get("T_C") is None:
            problems.append(f"Patch '{pname}': fixed_temperature needs T_C.")
        elif btype == "heat_flux" and bc.get("q_W_m2") is None:
            problems.append(f"Patch '{pname}': heat_flux needs q_W_m2.")
        elif btype == "space_environment" and not bc.get("emissivity"):
            problems.append(f"Patch '{pname}': space_environment needs emissivity > 0.")
        elif btype == "altitude_environment" and (
                not bc.get("emissivity") or bc.get("altitude_m") is None):
            problems.append(f"Patch '{pname}': altitude_environment needs emissivity > 0 "
                            "and altitude_m.")

    fluids = [n for n, c in comps.items() if c.get("type") == "fluid"]
    for f in fluids:
        pt = [p["bc"]["type"] for p in manifest.get("patches", {}).values()
              if p.get("component") == f and isinstance(p.get("bc"), dict)]
        if "velocity_inlet" in pt and "pressure_outlet" not in pt:
            problems.append(f"Fluid '{f}' has an inlet but no pressure_outlet.")
    if manifest.get("radiation", {}).get("model", "none") not in ("none", "P1", "fvDOM"):
        problems.append("radiation.model must be one of: none, P1, fvDOM.")
    return problems


# ─────────────────────────────── meshing ─────────────────────────────────────

def _match_components(manifest: dict, vols) -> dict[int, str]:
    """Map current fragment volume tags -> component names by centroid+volume
    (robust against OCC tag renumbering between sessions)."""
    import gmsh
    infos = [_volume_info(v) for v in vols]
    mapping: dict[int, str] = {}
    taken: set[int] = set()
    for name, comp in manifest["components"].items():
        cx, cy, cz = comp["centroid_m"]
        best, best_d = None, None
        for info in infos:
            if info["tag"] in taken:
                continue
            d = math.dist((cx, cy, cz), info["centroid_m"])
            if best_d is None or d < best_d:
                best, best_d = info, d
        if best is None:
            raise RuntimeError(f"Component '{name}': no unmatched solid left in STEP.")
        dv = abs(best["volume_m3"] - comp["volume_m3"]) / max(comp["volume_m3"], 1e-30)
        if dv > 0.02:
            raise RuntimeError(
                f"Component '{name}' matched a solid whose volume differs by {dv:.1%} — "
                "the STEP file changed since inspection. Re-run inspection.")
        taken.add(best["tag"])
        mapping[best["tag"]] = name
    return mapping


def _select_surfaces(select, comp_surfaces: list[dict], diag: float) -> list[int]:
    """Evaluate a manifest patch selector against a component's external surfaces."""
    tol = 1e-6 + 1e-3 * diag
    if isinstance(select, dict) and "surfaces" in select:
        wanted = set(select["surfaces"])
        return [s["tag"] for s in comp_surfaces if s["tag"] in wanted]
    if isinstance(select, dict) and "box" in select:
        b = select["box"]
        return [s["tag"] for s in comp_surfaces
                if b[0] <= s["centroid_m"][0] <= b[3]
                and b[1] <= s["centroid_m"][1] <= b[4]
                and b[2] <= s["centroid_m"][2] <= b[5]]
    if isinstance(select, dict) and "plane" in select:
        ax = "xyz".index(select["plane"]["axis"])
        val = float(select["plane"]["value"])
        return [s["tag"] for s in comp_surfaces
                if abs(s["bbox_m"][ax] - val) < tol and abs(s["bbox_m"][ax + 3] - val) < tol]
    if isinstance(select, str) and select != "remaining":
        m = re.fullmatch(r"([xyz])(min|max)", select)
        if not m:
            raise ValueError(f"Unknown patch selector: {select!r}")
        ax = "xyz".index(m.group(1))
        lo = m.group(2) == "min"
        coords = [s["bbox_m"][ax] if lo else s["bbox_m"][ax + 3] for s in comp_surfaces]
        extreme = min(coords) if lo else max(coords)
        out = []
        for s in comp_surfaces:
            flat = (s["bbox_m"][ax + 3] - s["bbox_m"][ax]) < tol
            at = abs((s["bbox_m"][ax] if lo else s["bbox_m"][ax + 3]) - extreme) < tol
            if flat and at:
                out.append(s["tag"])
        return out
    return []  # "remaining" handled by the caller


def mesh_assembly(manifest: dict, out_msh: str | Path, mesh_size_factor: float = 1.0) -> dict:
    """Fragment + mesh the assembly. Physical volumes = component names (-> cellZones),
    physical surfaces = manifest patches + '<component>_wall' defaults.
    Writes Gmsh v2.2 for gmshToFoam. Returns stats (incl. patch face counts)."""
    import time
    import gmsh

    problems = validate_manifest(manifest)
    if problems:
        raise RuntimeError("Manifest not ready:\n  - " + "\n  - ".join(problems))

    t0 = time.time()
    out_msh = Path(out_msh)
    out_msh.parent.mkdir(parents=True, exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("assembly_mesh")
        vols = _import_and_fragment(manifest["step_file"])
        tag_to_comp = _match_components(manifest, vols)

        # physical volume per component -> cellZone names for splitMeshRegions
        comp_tags: dict[str, list[int]] = {}
        for tag, comp in tag_to_comp.items():
            comp_tags.setdefault(comp, []).append(tag)
        for comp, tags in comp_tags.items():
            pg = gmsh.model.addPhysicalGroup(3, tags)
            gmsh.model.setPhysicalName(3, pg, comp)

        # classify surfaces: external (1 owner) vs interface (2 owners, left unnamed —
        # splitMeshRegions builds <regionA>_to_<regionB> patches from the cellZones)
        external: dict[str, list[dict]] = {c: [] for c in comp_tags}
        for dim, stag in gmsh.model.getEntities(2):
            up, _ = gmsh.model.getAdjacencies(dim, stag)
            owners = [tag_to_comp[t] for t in up if t in tag_to_comp]
            if len(owners) == 1:
                cx, cy, cz = gmsh.model.occ.getCenterOfMass(dim, stag)
                external[owners[0]].append({
                    "tag": stag, "centroid_m": [cx, cy, cz],
                    "bbox_m": list(gmsh.model.getBoundingBox(dim, stag))})

        bb = gmsh.model.getBoundingBox(-1, -1)
        diag = math.dist(bb[:3], bb[3:])

        assigned: dict[str, list[int]] = {}          # patch name -> surface tags
        claimed: dict[str, set[int]] = {c: set() for c in comp_tags}
        remaining_alias: dict[str, str] = {}         # component -> patch renaming its leftovers
        for pname, patch in manifest.get("patches", {}).items():
            comp = patch["component"]
            if patch.get("select") == "remaining":
                remaining_alias[comp] = pname
                continue
            tags = [t for t in _select_surfaces(patch.get("select"), external[comp], diag)
                    if t not in claimed[comp]]
            if not tags:
                raise RuntimeError(f"Patch '{pname}': selector matched no unclaimed external "
                                   f"surface of component '{comp}'.")
            assigned[pname] = tags
            claimed[comp].update(tags)
        for comp, surfs in external.items():
            leftover = [s["tag"] for s in surfs if s["tag"] not in claimed[comp]]
            if leftover:
                assigned[remaining_alias.get(comp, f"{comp}_wall")] = leftover

        patch_areas = {}
        for pname, tags in assigned.items():
            pg = gmsh.model.addPhysicalGroup(2, tags)
            gmsh.model.setPhysicalName(2, pg, pname)
            patch_areas[pname] = round(sum(gmsh.model.occ.getMass(2, t) for t in tags), 9)

        mesh_cfg = manifest.get("solver", {}).get("mesh", {})
        size_max = float(mesh_cfg.get("size_max_m", diag / 50.0)) * mesh_size_factor
        size_min = float(mesh_cfg.get("size_min_m", size_max / 8.0))
        gmsh.option.setNumber("Mesh.MeshSizeMax", size_max)
        gmsh.option.setNumber("Mesh.MeshSizeMin", size_min)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature",
                              float(mesh_cfg.get("curvature_nodes", 24)))
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        gmsh.option.setNumber("Mesh.Algorithm3D", 10)  # HXT
        gmsh.model.mesh.generate(3)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.write(str(out_msh))

        nodes = gmsh.model.mesh.getNodes()[0]
        _, tet_tags, _ = gmsh.model.mesh.getElements(3)
        stats = {
            "msh_file": str(out_msh),
            "mesh_size_factor": mesh_size_factor,
            "size_max_m": round(size_max, 6), "size_min_m": round(size_min, 6),
            "n_nodes": len(nodes),
            "n_cells_3d": int(sum(len(t) for t in tet_tags)),
            "components": {c: len(t) for c, t in comp_tags.items()},
            "patches": patch_areas,
            "elapsed_s": round(time.time() - t0, 1),
        }
    finally:
        gmsh.finalize()

    out_msh.with_suffix(".stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats
