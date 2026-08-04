#!/usr/bin/env python3
"""FEA: steady coupled thermal-structural analysis of the exhaust pipe wall.

Pipeline: Gmsh (annular tube, C3D10 tets, tagged physical groups) -> solver-specific
deck -> WSL solve -> results extraction -> summary KPIs. Two interchangeable FEM
backends, selected with --solver:

  ccx   (default) Abaqus-format mesh via meshio -> CalculiX deck -> ccx -> .frd
  elmer            ElmerGrid mesh conversion -> .sif deck -> ElmerSolver -> .vtu
                    (requires install_solvers.py --with-elmer)

Example:
    python run_pipe_fea.py --study baseline --t-inner 400 --t-outer 15
    python run_pipe_fea.py --study baseline --solver elmer
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

import numpy as np  # noqa: E402

from wsl_bridge import run_wsl, ccx_binary  # noqa: E402
from study_pipeline import study_dir, load_params  # noqa: E402
from learning_store import harvest  # noqa: E402

# Physical-group tag numbers baked into both the mesh (gmsh) and the Elmer .sif deck.
ELMER_TAG_INNER, ELMER_TAG_OUTER, ELMER_TAG_FIXED, ELMER_TAG_FAR, ELMER_TAG_BODY = 1, 2, 3, 4, 1


def _classify_surfaces(R: float, Ro: float, L: float) -> dict:
    """Bounding-box classification of the tube's 4 boundary surfaces (gmsh must already
    be initialized with the cut geometry synchronized). Thin-in-x => end cap (fixed at
    x=0, far at x=L); otherwise a cylindrical wall, split by radial half-extent."""
    import gmsh

    tags: dict[str, list[int]] = {"INNER": [], "OUTER": [], "FIXED": [], "FAR": []}
    for dim, tag in gmsh.model.getEntities(2):
        xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(dim, tag)
        if (xmax - xmin) < L * 1e-3:
            tags["FIXED" if abs(xmin) < L * 1e-3 else "FAR"].append(tag)
        else:
            r_half = (ymax - ymin) / 2.0
            tags["OUTER" if abs(r_half - Ro) < abs(r_half - R) else "INNER"].append(tag)
    return tags


def build_tube_mesh(out_inp_mesh: Path, R: float, Ro: float, L: float, size: float) -> dict:
    """Annular tube along x from 0 to L; quadratic tets. Surfaces are tagged with Elmer
    physical groups (harmless for the CalculiX path, which locates node sets by
    geometry instead) so the same mesh serves both FEM backends."""
    import gmsh
    import meshio

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("pipe_tube")
        occ = gmsh.model.occ
        outer = occ.addCylinder(0, 0, 0, L, 0, 0, Ro)
        inner = occ.addCylinder(0, 0, 0, L, 0, 0, R)
        occ.cut([(3, outer)], [(3, inner)])
        occ.synchronize()

        surf_tags = _classify_surfaces(R, Ro, L)
        gmsh.model.addPhysicalGroup(2, surf_tags["INNER"], tag=ELMER_TAG_INNER, name="inner")
        gmsh.model.addPhysicalGroup(2, surf_tags["OUTER"], tag=ELMER_TAG_OUTER, name="outer")
        gmsh.model.addPhysicalGroup(2, surf_tags["FIXED"], tag=ELMER_TAG_FIXED, name="fixed")
        gmsh.model.addPhysicalGroup(2, surf_tags["FAR"], tag=ELMER_TAG_FAR, name="far")
        vols = [t for d, t in gmsh.model.getEntities(3)]
        gmsh.model.addPhysicalGroup(3, vols, tag=ELMER_TAG_BODY, name="pipe")

        gmsh.option.setNumber("Mesh.MeshSizeMax", size)
        gmsh.option.setNumber("Mesh.MeshSizeMin", size / 3)
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.setOrder(2)
        msh_path = out_inp_mesh.with_suffix(".msh")
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.write(str(msh_path))
    finally:
        gmsh.finalize()

    mesh = meshio.read(msh_path)
    tets = [c for c in mesh.cells if c.type == "tetra10"]
    if not tets:
        raise RuntimeError("No quadratic tets generated")
    conn = np.vstack([c.data for c in tets])  # meshio canonical == Abaqus C3D10 order

    # Write the mesh block manually: ccx's free-format reader caps each field at
    # 20 chars, which meshio's 16-digit coordinates exceed.
    lines = ["*NODE"]
    for i, (x, y, z) in enumerate(mesh.points, start=1):
        lines.append(f"{i}, {x:.9e}, {y:.9e}, {z:.9e}")
    lines.append("*ELEMENT, TYPE=C3D10")
    for eid, nodes in enumerate(conn, start=1):
        lines.append(", ".join(str(v) for v in [eid, *(int(n) + 1 for n in nodes)]))
    out_inp_mesh.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"points": mesh.points, "n_nodes": len(mesh.points), "n_elements": int(len(conn)),
            "msh_path": msh_path}


def node_sets(points: np.ndarray, R: float, Ro: float, L: float, tol_frac: float = 0.08) -> dict:
    """1-based node IDs for inner surface, outer surface, and fixed end (x=0)."""
    r = np.hypot(points[:, 1], points[:, 2])
    tol = (Ro - R) * tol_frac
    return {
        "INNER": np.where(np.abs(r - R) < tol)[0] + 1,
        "OUTER": np.where(np.abs(r - Ro) < tol)[0] + 1,
        "FIXED": np.where(np.abs(points[:, 0]) < L * 1e-4 + 1e-9)[0] + 1,
    }


def write_deck(fea_dir: Path, mesh_info: dict, sets: dict, mat: dict,
               T_inner: float, T_outer: float, T_ref: float) -> Path:
    def emit_set(name: str, ids) -> str:
        lines = [f"*NSET, NSET={name}"]
        ids = list(map(int, ids))
        for i in range(0, len(ids), 12):
            lines.append(", ".join(str(x) for x in ids[i:i + 12]))
        return "\n".join(lines)

    # inline the mesh — ccx's *INCLUDE handling is unreliable across passes
    mesh_text = (fea_dir / "pipe_mesh.inp").read_text(encoding="utf-8")

    deck = fea_dir / "pipe.inp"
    body = f"""** Exhaust pipe wall — steady coupled thermal-structural analysis
** Generated by agent-cfd-fea-engineer
{mesh_text}
*ELSET, ELSET=EALL, GENERATE
 1, {mesh_info['n_elements']}
{emit_set('INNER', sets['INNER'])}
{emit_set('OUTER', sets['OUTER'])}
{emit_set('FIXED', sets['FIXED'])}
*MATERIAL, NAME=STEEL
*ELASTIC
 {mat['E']}, {mat['nu']}
*EXPANSION, ZERO={T_ref}
 {mat['alpha']}
*CONDUCTIVITY
 {mat['k']}
*DENSITY
 {mat['rho']}
*SPECIFIC HEAT
 {mat['cp']}
*SOLID SECTION, ELSET=EALL, MATERIAL=STEEL
*INITIAL CONDITIONS, TYPE=TEMPERATURE
 NALL, {T_ref}
*STEP
*COUPLED TEMPERATURE-DISPLACEMENT, STEADY STATE
*BOUNDARY
 FIXED, 1, 3
 INNER, 11, 11, {T_inner}
 OUTER, 11, 11, {T_outer}
*NODE FILE
 U, NT
*EL FILE
 S
*END STEP
"""
    deck.write_text(body, encoding="utf-8")
    return deck


def add_nall(mesh_inp: Path, n_nodes: int) -> None:
    with open(mesh_inp, "a", encoding="utf-8") as fh:
        fh.write(f"\n*NSET, NSET=NALL, GENERATE\n 1, {n_nodes}\n")


def parse_frd(frd_path: Path) -> dict[str, np.ndarray]:
    """Minimal CalculiX .frd parser: nodal result blocks -> {block_name: values array}.

    frd nodal lines are fixed-width: ' -1' + 10-char node id + 12-char E-format values.
    """
    blocks: dict[str, list[list[float]]] = {}
    current = None
    for line in frd_path.read_text(encoding="utf-8", errors="replace").splitlines():
        code = line[:5].strip()
        if code == "-4":
            current = line[5:18].strip()
            blocks.setdefault(current, [])
        elif code == "-1" and current is not None:
            vals = []
            body = line[13:]
            for i in range(0, len(body) - 11, 12):
                try:
                    vals.append(float(body[i:i + 12]))
                except ValueError:
                    pass
            if vals:
                blocks[current].append(vals)
        elif code == "-3":
            current = None
    return {k: np.asarray(v) for k, v in blocks.items() if v}


def extract_results_ccx(fea_dir: Path) -> dict:
    """Headline KPIs parsed directly from the .frd (robust); VTU conversion best-effort."""
    out: dict = {}
    frd = fea_dir / "pipe.frd"
    data = parse_frd(frd)

    key_T = next((k for k in data if k.upper().startswith(("NDTEMP", "NT", "TEMP"))), None)
    if key_T is not None:
        T = data[key_T][:, 0]
        out["T_min_C"] = round(float(T.min()), 1)
        out["T_max_C"] = round(float(T.max()), 1)

    key_U = next((k for k in data if k.upper().startswith("DISP")), None)
    if key_U is not None and data[key_U].shape[1] >= 3:
        mag = np.linalg.norm(data[key_U][:, :3], axis=1)
        out["max_displacement_mm"] = round(float(mag.max()) * 1000, 3)

    key_S = next((k for k in data if k.upper().startswith("STRESS")), None)
    if key_S is not None and data[key_S].shape[1] >= 6:
        sxx, syy, szz, sxy, syz, szx = (data[key_S][:, i] for i in range(6))
        mises = np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
                        + 3 * (sxy ** 2 + syz ** 2 + szx ** 2))
        out["max_von_mises_MPa"] = round(float(mises.max()) / 1e6, 1)

    try:
        from ccx2paraview import Converter
        Converter(str(frd), ["vtu"]).run()
        vtus = sorted(fea_dir.glob("pipe*.vtu"))
        if vtus:
            out["vtu_file"] = str(vtus[-1])
    except Exception as exc:  # noqa: BLE001 — visualization export is best-effort
        out["vtu_conversion"] = f"failed: {exc} (KPIs parsed from .frd directly)"
    return out


def _check_elmer_available() -> None:
    r = run_wsl("command -v ElmerSolver && command -v ElmerGrid", check=False)
    if r.returncode != 0:
        raise RuntimeError(
            "ElmerFEM not found in WSL (ElmerSolver/ElmerGrid). Install it with:\n"
            "  python .github/skills/solver_environment/scripts/install_solvers.py --with-elmer")


def write_sif(fea_dir: Path, mesh_dir: str, mat: dict,
              T_inner: float, T_outer: float, T_ref: float) -> Path:
    """Steady coupled heat + linear-elasticity .sif: HeatSolver feeds Temperature into
    StressSolver, which picks up thermal strain automatically from the material's
    Heat Expansion Coefficient / Reference Temperature (Elmer's standard thermal-stress
    coupling — see the ElasticSolve/StressSolve docs). StressSolver also emits a
    'vonmises' nodal field directly, no manual tensor combination needed."""
    sif = fea_dir / "pipe.sif"
    body = f"""Header
  CHECK KEYWORDS Warn
  Mesh DB "." "{mesh_dir}"
  Include Path ""
  Results Directory ""
End

Simulation
  Max Output Level = 5
  Coordinate System = Cartesian
  Coordinate Mapping(3) = 1 2 3
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Output Intervals = 1
  Post File = pipe.vtu
End

Constants
  Gravity(4) = 0 -1 0 9.82
  Stefan Boltzmann = 5.67e-08
End

Body 1
  Target Bodies(1) = {ELMER_TAG_BODY}
  Name = "Pipe"
  Equation = 1
  Material = 1
  Initial Condition = 1
End

Solver 1
  Equation = Heat Equation
  Variable = Temperature
  Procedure = "HeatSolve" "HeatSolver"
  Linear System Solver = Iterative
  Linear System Iterative Method = BiCGStab
  Linear System Preconditioning = ILU1
  Linear System Max Iterations = 500
  Linear System Convergence Tolerance = 1.0e-10
  Steady State Convergence Tolerance = 1.0e-08
  Stabilize = True
End

Solver 2
  Equation = Linear elasticity
  Variable = Displacement
  Variable DOFs = 3
  Procedure = "StressSolve" "StressSolver"
  Linear System Solver = Direct
  Linear System Direct Method = umfpack
  Steady State Convergence Tolerance = 1.0e-08
  Calculate Stresses = True
End

Equation 1
  Name = "Coupled"
  Active Solvers(2) = 1 2
End

Material 1
  Name = "Steel"
  Density = {mat['rho']}
  Heat Conductivity = {mat['k']}
  Heat Capacity = {mat['cp']}
  Youngs Modulus = {mat['E']}
  Poisson Ratio = {mat['nu']}
  Heat Expansion Coefficient = {mat['alpha']}
  Reference Temperature = {T_ref}
End

Initial Condition 1
  Temperature = {T_ref}
End

Boundary Condition 1
  Target Boundaries(1) = {ELMER_TAG_INNER}
  Name = "Inner"
  Temperature = {T_inner}
End

Boundary Condition 2
  Target Boundaries(1) = {ELMER_TAG_OUTER}
  Name = "Outer"
  Temperature = {T_outer}
End

Boundary Condition 3
  Target Boundaries(1) = {ELMER_TAG_FIXED}
  Name = "Fixed"
  Displacement 1 = 0.0
  Displacement 2 = 0.0
  Displacement 3 = 0.0
End
"""
    sif.write_text(body, encoding="utf-8")
    return sif


def run_elmer(fea_dir: Path, msh_path: Path) -> str:
    """ElmerGrid (gmsh -> Elmer mesh format 2) then ElmerSolver. Returns the mesh
    subdirectory name (needed to locate the .vtu results afterwards)."""
    mesh_dir = msh_path.stem
    run_wsl(f"rm -rf {mesh_dir} && ElmerGrid 14 2 {msh_path.name} > log.elmergrid 2>&1",
            cwd=fea_dir, timeout=300)
    (fea_dir / "ELMERSOLVER_STARTINFO").write_text("pipe.sif\n1\n", encoding="utf-8")
    run_wsl("ElmerSolver > log.elmersolver 2>&1", cwd=fea_dir, timeout=3600)
    return mesh_dir


def extract_results_elmer(fea_dir: Path, mesh_dir: str) -> dict:
    """KPIs read straight from Elmer's .vtu (nodal temperature/displacement/vonmises)."""
    out: dict = {}
    vtus = sorted((fea_dir / mesh_dir).glob("pipe_t*.vtu"))
    if not vtus:
        return out
    out["vtu_file"] = str(vtus[-1])

    import pyvista as pv
    m = pv.read(str(vtus[-1]))
    T = m.point_data.get("temperature")
    if T is not None:
        out["T_min_C"] = round(float(T.min()), 1)
        out["T_max_C"] = round(float(T.max()), 1)
    disp = m.point_data.get("displacement")
    if disp is not None:
        mag = np.linalg.norm(disp, axis=1)
        out["max_displacement_mm"] = round(float(mag.max()) * 1000, 3)
    vm = m.point_data.get("vonmises")
    if vm is not None:
        out["max_von_mises_MPa"] = round(float(vm.max()) / 1e6, 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True)
    ap.add_argument("--solver", choices=["ccx", "elmer"], default="ccx",
                     help="FEM backend: CalculiX (default) or ElmerFEM")
    ap.add_argument("--t-inner", type=float, default=None, help="Inner wall temp [C] (default: study exhaust T)")
    ap.add_argument("--t-outer", type=float, default=None, help="Outer wall temp [C] (default: study water T)")
    ap.add_argument("--diameter", type=float, default=None, help="Bore D [m] (default from study geometry)")
    ap.add_argument("--thickness", type=float, default=None, help="Wall thickness [m]")
    ap.add_argument("--length", type=float, default=1.5, help="Analysed tube length [m]")
    ap.add_argument("--mesh-size", type=float, default=None, help="Target element size [m]")
    ap.add_argument("--E", type=float, default=200e9)
    ap.add_argument("--nu", type=float, default=0.3)
    ap.add_argument("--alpha", type=float, default=1.2e-5)
    ap.add_argument("--conductivity", type=float, default=45.0)
    args = ap.parse_args()

    cfg = load_params(args.study)
    geo = cfg.get("geometry", {})
    D = args.diameter if args.diameter else geo.get("pipe_diameter", 0.30)
    t = args.thickness if args.thickness else geo.get("wall_thickness", 0.012)
    R, Ro, L = D / 2, D / 2 + t, args.length
    T_inner = args.t_inner if args.t_inner is not None else cfg.get("T_exhaust_C", 400.0)
    T_outer = args.t_outer if args.t_outer is not None else cfg.get("T_water_C", 15.0)
    size = args.mesh_size if args.mesh_size else max(t * 1.2, math.pi * D / 60)

    if args.solver == "elmer":
        _check_elmer_available()

    fea_dir = study_dir(args.study) / "fea"
    fea_dir.mkdir(parents=True, exist_ok=True)

    print(f"Meshing tube D={D} t={t} L={L} (target size {size:.4f} m)...")
    mesh_inp = fea_dir / "pipe_mesh.inp"
    info = build_tube_mesh(mesh_inp, R, Ro, L, size)
    add_nall(mesh_inp, info["n_nodes"])
    print(f"  {info['n_nodes']} nodes, {info['n_elements']} C3D10 elements")

    mat = {"E": args.E, "nu": args.nu, "alpha": args.alpha, "k": args.conductivity,
           "rho": 7850.0, "cp": 490.0}

    if args.solver == "ccx":
        sets = node_sets(np.asarray(info["points"]), R, Ro, L)
        print(f"  sets: inner={len(sets['INNER'])}, outer={len(sets['OUTER'])}, fixed={len(sets['FIXED'])}")
        write_deck(fea_dir, info, sets, mat, T_inner, T_outer, T_ref=T_outer)

        print("Running CalculiX (WSL)...")
        ccx = ccx_binary()
        run_wsl(f"OMP_NUM_THREADS=4 {ccx} -i pipe > log.ccx 2>&1", cwd=fea_dir, timeout=3600)
        log = (fea_dir / "log.ccx").read_text(encoding="utf-8", errors="replace")
        if "Job finished" not in log:
            print("ERROR: CalculiX did not finish cleanly. Log tail:")
            print("\n".join(log.splitlines()[-25:]))
            return 1
        results = extract_results_ccx(fea_dir)
    else:
        write_sif(fea_dir, info["msh_path"].stem, mat, T_inner, T_outer, T_ref=T_outer)

        print("Running ElmerFEM (WSL)...")
        mesh_dir = run_elmer(fea_dir, info["msh_path"])
        log = (fea_dir / "log.elmersolver").read_text(encoding="utf-8", errors="replace")
        if "ALL DONE" not in log:
            print("ERROR: ElmerSolver did not finish cleanly. Log tail:")
            print("\n".join(log.splitlines()[-25:]))
            return 1
        results = extract_results_elmer(fea_dir, mesh_dir)

    summary = {
        "study": args.study,
        "solver": args.solver,
        "geometry": {"bore_D_m": D, "wall_t_m": t, "length_m": L},
        "loads": {"T_inner_C": T_inner, "T_outer_C": T_outer},
        "material": mat,
        "mesh": {"n_nodes": info["n_nodes"], "n_elements": info["n_elements"]},
        **results,
    }
    (fea_dir / "fea_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    harvest(args.study, case_type="fea_analysis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
