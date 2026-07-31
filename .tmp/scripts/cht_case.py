#!/usr/bin/env python3
"""OpenFOAM multi-region conjugate heat transfer case factory.

Writes chtMultiRegionSimpleFoam (steady, default) or chtMultiRegionFoam
(transient) cases from an assembly manifest (see step_assembly.py):

  * one region per assembly component (fluid or solid), coupled at the
    `<regionA>_to_<regionB>` mappedWall interfaces created by splitMeshRegions
  * conduction in solid regions (heSolidThermo, per-component material)
  * convection in fluid regions (buoyant, k-omega SST, per-component fluid)
    and to ambient via externalWallHeatFluxTemperature (h, T_amb)
  * radiation: P1 or fvDOM in participating fluid regions (coupled through
    turbulentTemperatureRadCoupledMixed), plus grey surface-to-ambient
    radiation on external walls via the convection BC's emissivity

Case build order (cht_pipeline drives this):
  write_skeleton() -> gmshToFoam -> splitMeshRegions -cellZones -overwrite
  -> write_regions() (reads each region's actual boundary file) -> solve.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from foam_case import _write, _field
from materials import get_material, fluid_thermo_body, solid_thermo_body

DEFAULT_SOLVER = {
    "mode": "steady",            # steady (chtMultiRegionSimpleFoam) | transient (chtMultiRegionFoam)
    "iterations": 1500,          # steady: pseudo-time steps
    "write_interval": 250,       # steady: write every N iterations
    "end_time_s": 60.0,          # transient
    "write_interval_s": 5.0,     # transient
    "max_co": 2.5,
    "max_di": 10.0,              # solid diffusion number limit (transient)
    "n_procs": 4,
    "p_ref_Pa": 101325.0,
    "T_init_C": 25.0,            # fallback initial temperature (per-component T_init_C wins)
    "g": [0.0, 0.0, -9.81],
    "turbulence_intensity": 0.05,
    "mesh": {},                  # size_max_m / size_min_m / curvature_nodes (step_assembly)
}


def merged_solver(manifest: dict) -> dict:
    out = json.loads(json.dumps(DEFAULT_SOLVER))
    for k, v in (manifest.get("solver") or {}).items():
        out[k] = v
    return out


def region_map(manifest: dict) -> dict[str, dict]:
    """component name -> {'type', 'props', 'T_init'} for every assigned component."""
    slv = merged_solver(manifest)
    out = {}
    for name, comp in manifest["components"].items():
        props = get_material(comp["material"], comp.get("overrides"))
        t_init = comp.get("T_init_C")
        out[name] = {"type": comp["type"], "props": props,
                     "T_init": (slv["T_init_C"] if t_init is None else t_init) + 273.15}
    return out


def patches_for(manifest: dict, component: str) -> dict[str, dict]:
    """Manifest patches belonging to one component: name -> bc dict."""
    out = {}
    for pname, patch in manifest.get("patches", {}).items():
        if patch["component"] == component:
            out[pname] = patch.get("bc", {"type": "adiabatic"})
    return out


# ─────────────────────────── polyMesh boundary handling ──────────────────────

_BND_BLOCK = re.compile(r"(\w[\w.:-]*)\s*\{([^{}]*)\}", re.S)


def read_region_patches(case: Path, region: str) -> dict[str, dict]:
    """Parse constant/<region>/polyMesh/boundary -> {patch: {'type', 'nFaces'}}."""
    text = (case / "constant" / region / "polyMesh" / "boundary").read_text(
        encoding="utf-8", errors="replace")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    body = text.split("(", 1)[1].rsplit(")", 1)[0]
    out = {}
    for m in _BND_BLOCK.finditer(body):
        name, inner = m.group(1), m.group(2)
        t = re.search(r"\btype\s+(\w+)\s*;", inner)
        n = re.search(r"\bnFaces\s+(\d+)\s*;", inner)
        out[name] = {"type": t.group(1) if t else "patch",
                     "nFaces": int(n.group(1)) if n else 0}
    return out


def fix_region_boundary(case: Path, region: str, manifest: dict) -> dict[str, dict]:
    """Set correct base types on external patches (gmshToFoam leaves everything
    'patch'). Interfaces stay mappedWall (written by splitMeshRegions).
    Returns the corrected patch dict."""
    bc_types = {p: b.get("type") for p, b in
                ((pn, pt.get("bc", {})) for pn, pt in manifest.get("patches", {}).items())}
    bfile = case / "constant" / region / "polyMesh" / "boundary"
    text = bfile.read_text(encoding="utf-8", errors="replace")
    patches = read_region_patches(case, region)
    for name, info in patches.items():
        if "_to_" in name or info["type"] == "mappedWall":
            continue
        bc = bc_types.get(name)
        new_type = ("patch" if bc in ("velocity_inlet", "pressure_outlet")
                    else "symmetry" if bc == "symmetry" else "wall")
        text = re.sub(rf"({re.escape(name)}\s*\{{[^}}]*?type\s+)\w+(\s*;)",
                      rf"\g<1>{new_type}\g<2>", text, count=1, flags=re.S)
        text = re.sub(rf"({re.escape(name)}\s*\{{[^}}]*?physicalType\s+)\w+(\s*;)",
                      rf"\g<1>{new_type}\g<2>", text, count=1, flags=re.S)
        patches[name]["type"] = new_type
    bfile.write_text(text, encoding="utf-8")
    return patches


# ─────────────────────────────── skeleton ────────────────────────────────────

def write_skeleton(case: Path, manifest: dict) -> None:
    """Minimum viable top-level dicts so gmshToFoam / splitMeshRegions can run."""
    slv = merged_solver(manifest)
    _write_controldict(case, manifest, functions_body="")
    _write(case, "system/fvSchemes", _fluid_fvschemes(slv["mode"]))
    _write(case, "system/fvSolution", "// per-region dictionaries hold the solver settings\n")
    _write(case, "system/decomposeParDict",
           f"numberOfSubdomains {slv['n_procs']};\n\nmethod          scotch;\n")
    gx, gy, gz = slv["g"]
    _write(case, "constant/g",
           f"dimensions      [0 1 -2 0 0 0 0];\nvalue           ({gx} {gy} {gz});\n",
           "uniformDimensionedVectorField")


def _write_controldict(case: Path, manifest: dict, functions_body: str) -> None:
    slv = merged_solver(manifest)
    if slv["mode"] == "steady":
        head = f"""application     chtMultiRegionSimpleFoam;

startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         {slv['iterations']};
deltaT          1;

writeControl    timeStep;
writeInterval   {slv['write_interval']};
purgeWrite      2;
"""
    else:
        head = f"""application     chtMultiRegionFoam;

startFrom       latestTime;
startTime       0;
stopAt          endTime;
endTime         {slv['end_time_s']};
deltaT          1e-3;

writeControl    adjustable;
writeInterval   {slv['write_interval_s']};
purgeWrite      0;

adjustTimeStep  yes;
maxCo           {slv['max_co']};
maxDi           {slv['max_di']};
maxDeltaT       1;
"""
    _write(case, "system/controlDict", head + f"""writeFormat     binary;
writePrecision  7;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable yes;

functions
{{
{functions_body}}}
""")


# ─────────────────────────────── schemes / solution ──────────────────────────

def _fluid_fvschemes(mode: str) -> str:
    steady = mode == "steady"
    ddt = "steadyState" if steady else "Euler"
    b = "bounded " if steady else ""
    return f"""ddtSchemes
{{
    default         {ddt};
}}

gradSchemes
{{
    default         cellLimited Gauss linear 1;
}}

divSchemes
{{
    default         none;
    div(phi,U)      {b}Gauss linearUpwind limited;
    div(phi,K)      {b}Gauss limitedLinear 1;
    div(phi,h)      {b}Gauss limitedLinear 1;
    div(phi,k)      {b}Gauss upwind;
    div(phi,omega)  {b}Gauss upwind;
    div(Ji,Ii_h)    {b}Gauss linearUpwind grad(Ii_h);
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}}

laplacianSchemes
{{
    default         Gauss linear limited 0.33;
}}

interpolationSchemes
{{
    default         linear;
}}

snGradSchemes
{{
    default         limited 0.33;
}}

wallDist
{{
    method          meshWave;
}}
"""


def _solid_fvschemes(mode: str) -> str:
    ddt = "steadyState" if mode == "steady" else "Euler"
    return f"""ddtSchemes
{{
    default         {ddt};
}}

gradSchemes
{{
    default         Gauss linear;
}}

divSchemes
{{
    default         none;
}}

laplacianSchemes
{{
    default         Gauss linear limited 0.33;
}}

interpolationSchemes
{{
    default         linear;
}}

snGradSchemes
{{
    default         limited 0.33;
}}
"""


def _fluid_fvsolution(mode: str, sealed: bool, p_ref: float) -> str:
    ref = f"    pRefCell        0;\n    pRefValue       {p_ref};\n" if sealed else ""
    if mode == "steady":
        return f"""solvers
{{
    p_rgh
    {{
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }}

    "(U|h|k|omega|G)"
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-7;
        relTol          0.1;
    }}

    "Ii.*"
    {{
        solver          GAMG;
        smoother        symGaussSeidel;
        tolerance       1e-4;
        relTol          0;
        maxIter         5;
    }}
}}

SIMPLE
{{
    momentumPredictor yes;
    nNonOrthogonalCorrectors 1;
    rhoMin          0.05;
    rhoMax          2000;
{ref}}}

relaxationFactors
{{
    fields
    {{
        rho             1.0;
        p_rgh           0.7;
    }}
    equations
    {{
        U               0.3;
        h               0.5;
        "(k|omega)"     0.7;
        G               0.7;
        "ILambda.*"     0.7;
        qr              0.7;
    }}
}}
"""
    return f"""solvers
{{
    "rho.*"
    {{
        solver          diagonal;
    }}

    "p_rgh.*"
    {{
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }}

    p_rghFinal
    {{
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }}

    "(U|h|k|omega|G)"
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-7;
        relTol          0.1;
    }}

    "(U|h|k|omega|G)Final"
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0;
    }}

    "Ii.*"
    {{
        solver          GAMG;
        smoother        symGaussSeidel;
        tolerance       1e-4;
        relTol          0;
        maxIter         5;
    }}
}}

PIMPLE
{{
    momentumPredictor yes;
    nOuterCorrectors 1;
    nCorrectors     2;
    nNonOrthogonalCorrectors 1;
{ref}}}
"""


def _solid_fvsolution(mode: str) -> str:
    if mode == "steady":
        return """solvers
{
    h
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-7;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 1;
}

relaxationFactors
{
    equations
    {
        h               0.9;
    }
}
"""
    return """solvers
{
    "h.*"
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-7;
        relTol          0.1;
    }

    hFinal
    {
        solver          PCG;
        preconditioner  DIC;
        tolerance       1e-8;
        relTol          0;
    }
}

PIMPLE
{
    nNonOrthogonalCorrectors 1;
}
"""


# ─────────────────────────────── radiation ───────────────────────────────────

def _radiation_body(model: str, props: dict) -> str:
    if model == "none":
        return "radiation       off;\n\nradiationModel  none;\n"
    a = props.get("absorption_coeff_1_m", 0.0)
    common = f"""radiation       on;

radiationModel  {model};

solverFreq      {5 if model == 'P1' else 10};

absorptionEmissionModel constant;

constantCoeffs
{{
    absorptivity    {a};
    emissivity      {a};
    E               0;
}}

scatterModel    none;

sootModel       none;
"""
    if model == "fvDOM":
        common += """
fvDOMCoeffs
{
    nPhi        3;
    nTheta      5;
    tolerance   1e-3;
    maxIter     10;
}
"""
    return common


def _boundary_radiation_body(region: str, patches: dict, manifest: dict,
                             regions: dict) -> str:
    default_e = manifest.get("radiation", {}).get("emissivity_default", 0.9)
    lines = [f'".*"\n{{\n    type            lookup;\n'
             f'    emissivity      {default_e};\n    absorptivity    {default_e};\n}}\n']
    comp_patches = patches_for(manifest, region)
    for pname in patches:
        e = None
        if "_to_" in pname:
            other = pname.split("_to_")[-1]
            info = regions.get(other)
            if info and info["type"] == "solid":
                e = info["props"].get("emissivity")
        elif pname in comp_patches:
            e = comp_patches[pname].get("emissivity")
        if e is not None:
            lines.append(f"{pname}\n{{\n    type            lookup;\n"
                         f"    emissivity      {e};\n    absorptivity    {e};\n}}\n")
    return "\n".join(lines)


# ─────────────────────────────── field generation ────────────────────────────

def _inlet_velocity_estimate(bc: dict, props: dict, area: float | None) -> float:
    if bc.get("U_m_s"):
        return abs(float(bc["U_m_s"]))
    m_dot = float(bc.get("m_dot_kg_s", 0.0))
    rho = props.get("rho") or 101325.0 * props["molWeight"] / (8314.5 * (bc.get("T_C", 25) + 273.15))
    if area:
        return abs(m_dot) / (rho * area)
    return 1.0


def _fluid_fields(region: str, patches: dict, manifest: dict, regions: dict,
                  patch_areas: dict | None) -> dict[str, dict]:
    """Return {field_name: {patch: spec}} for one fluid region."""
    slv = merged_solver(manifest)
    rad_model = manifest.get("radiation", {}).get("model", "none")
    props = regions[region]["props"]
    T0 = regions[region]["T_init"]
    p0 = slv["p_ref_Pa"]
    I = slv["turbulence_intensity"]
    comp_bcs = patches_for(manifest, region)

    U_ref = 1.0
    for bc in comp_bcs.values():
        if bc.get("type") == "velocity_inlet":
            U_ref = max(U_ref, _inlet_velocity_estimate(
                bc, props, (patch_areas or {}).get(next(
                    p for p, b in comp_bcs.items() if b is bc))))
    k0 = max(1.5 * (I * U_ref) ** 2, 1e-5)
    omega0 = max(math.sqrt(k0) / 0.05, 1.0)

    fields: dict[str, dict] = {f: {} for f in
                               ("U", "p", "p_rgh", "T", "k", "omega", "nut", "alphat")}
    if rad_model == "P1":
        fields["G"] = {}
    elif rad_model == "fvDOM":
        fields["IDefault"] = {}

    for pname, pinfo in patches.items():
        bc = comp_bcs.get(pname, {"type": "adiabatic"})
        btype = bc.get("type", "adiabatic")
        is_iface = "_to_" in pname or pinfo["type"] == "mappedWall"

        if btype == "symmetry" and not is_iface:
            for f in fields:
                fields[f][pname] = {"type": "symmetry"}
            continue

        if is_iface or btype in ("adiabatic", "fixed_temperature", "heat_flux", "convection"):
            fields["U"][pname] = {"type": "noSlip"}
            fields["p_rgh"][pname] = {"type": "fixedFluxPressure", "value": f"uniform {p0}"}
            fields["p"][pname] = {"type": "calculated", "value": f"uniform {p0}"}
            fields["k"][pname] = {"type": "kqRWallFunction", "value": f"uniform {k0:.6g}"}
            fields["omega"][pname] = {"type": "omegaWallFunction", "value": f"uniform {omega0:.6g}"}
            fields["nut"][pname] = {"type": "nutkWallFunction", "value": "uniform 0"}
            fields["alphat"][pname] = {"type": "compressible::alphatWallFunction",
                                       "Prt": "0.85", "value": "uniform 0"}
            if is_iface:
                other = pname.split("_to_")[-1]
                nbr_fluid = regions.get(other, {}).get("type") == "fluid"
                qr = "qr" if rad_model != "none" else "none"
                qr_nbr = "qr" if (rad_model != "none" and nbr_fluid) else "none"
                fields["T"][pname] = {
                    "type": "compressible::turbulentTemperatureRadCoupledMixed",
                    "Tnbr": "T", "qrNbr": qr_nbr, "qr": qr,
                    "kappaMethod": "fluidThermo", "value": f"uniform {T0}"}
            elif btype == "fixed_temperature":
                fields["T"][pname] = {"type": "fixedValue",
                                      "value": f"uniform {bc['T_C'] + 273.15}"}
            elif btype == "heat_flux":
                fields["T"][pname] = {"type": "externalWallHeatFluxTemperature",
                                      "mode": "flux", "q": f"uniform {bc['q_W_m2']}",
                                      "kappaMethod": "fluidThermo", "value": f"uniform {T0}"}
            elif btype == "convection":
                spec = {"type": "externalWallHeatFluxTemperature", "mode": "coefficient",
                        "Ta": f"uniform {bc['T_amb_C'] + 273.15}",
                        "h": f"uniform {bc['h_W_m2K']}",
                        "kappaMethod": "fluidThermo", "value": f"uniform {T0}"}
                if bc.get("emissivity"):
                    spec["emissivity"] = f"{bc['emissivity']}"
                fields["T"][pname] = spec
            else:
                fields["T"][pname] = {"type": "zeroGradient"}
            if "G" in fields:
                fields["G"][pname] = {"type": "MarshakRadiation", "value": "uniform 0"}
            if "IDefault" in fields:
                fields["IDefault"][pname] = {"type": "greyDiffusiveRadiation",
                                             "value": "uniform 0"}
            continue

        if btype == "velocity_inlet":
            T_in = bc["T_C"] + 273.15
            if bc.get("m_dot_kg_s"):
                fields["U"][pname] = {"type": "flowRateInletVelocity",
                                      "massFlowRate": f"constant {bc['m_dot_kg_s']}",
                                      "rhoInlet": f"{props.get('rho', 1.2)}",
                                      "value": "uniform (0 0 0)"}
            else:
                fields["U"][pname] = {"type": "surfaceNormalFixedValue",
                                      "refValue": f"uniform {-abs(bc['U_m_s'])}"}
            fields["p_rgh"][pname] = {"type": "fixedFluxPressure", "value": f"uniform {p0}"}
            fields["p"][pname] = {"type": "calculated", "value": f"uniform {p0}"}
            fields["T"][pname] = {"type": "fixedValue", "value": f"uniform {T_in}"}
            fields["k"][pname] = {"type": "turbulentIntensityKineticEnergyInlet",
                                  "intensity": f"{I}", "value": f"uniform {k0:.6g}"}
            area = (patch_areas or {}).get(pname)
            mix_len = 0.07 * math.sqrt(4 * area / math.pi) if area else 0.01
            fields["omega"][pname] = {"type": "turbulentMixingLengthFrequencyInlet",
                                      "mixingLength": f"{mix_len:.4g}",
                                      "value": f"uniform {omega0:.6g}"}
            fields["nut"][pname] = {"type": "calculated", "value": "uniform 0"}
            fields["alphat"][pname] = {"type": "calculated", "value": "uniform 0"}
        elif btype == "pressure_outlet":
            p_out = bc.get("p_Pa", p0)
            T_back = bc.get("T_C", regions[region]["T_init"] - 273.15) + 273.15
            fields["U"][pname] = {"type": "pressureInletOutletVelocity",
                                  "value": "uniform (0 0 0)"}
            fields["p_rgh"][pname] = {"type": "prghPressure", "p": f"uniform {p_out}",
                                      "value": f"uniform {p_out}"}
            fields["p"][pname] = {"type": "calculated", "value": f"uniform {p_out}"}
            fields["T"][pname] = {"type": "inletOutlet", "inletValue": f"uniform {T_back}",
                                  "value": f"uniform {T_back}"}
            fields["k"][pname] = {"type": "inletOutlet", "inletValue": f"uniform {k0:.6g}",
                                  "value": f"uniform {k0:.6g}"}
            fields["omega"][pname] = {"type": "inletOutlet",
                                      "inletValue": f"uniform {omega0:.6g}",
                                      "value": f"uniform {omega0:.6g}"}
            fields["nut"][pname] = {"type": "calculated", "value": "uniform 0"}
            fields["alphat"][pname] = {"type": "calculated", "value": "uniform 0"}
        if "G" in fields:
            fields["G"][pname] = {"type": "MarshakRadiation", "value": "uniform 0"}
        if "IDefault" in fields:
            fields["IDefault"][pname] = {"type": "greyDiffusiveRadiation",
                                         "value": "uniform 0"}
    return fields


def _solid_T_field(region: str, patches: dict, manifest: dict, regions: dict) -> dict:
    rad_model = manifest.get("radiation", {}).get("model", "none")
    T0 = regions[region]["T_init"]
    comp_bcs = patches_for(manifest, region)
    out = {}
    for pname, pinfo in patches.items():
        bc = comp_bcs.get(pname, {"type": "adiabatic"})
        btype = bc.get("type", "adiabatic")
        if "_to_" in pname or pinfo["type"] == "mappedWall":
            other = pname.split("_to_")[-1]
            nbr_fluid = regions.get(other, {}).get("type") == "fluid"
            qr_nbr = "qr" if (rad_model != "none" and nbr_fluid) else "none"
            out[pname] = {"type": "compressible::turbulentTemperatureRadCoupledMixed",
                          "Tnbr": "T", "qrNbr": qr_nbr, "qr": "none",
                          "kappaMethod": "solidThermo", "value": f"uniform {T0}"}
        elif btype == "fixed_temperature":
            out[pname] = {"type": "fixedValue", "value": f"uniform {bc['T_C'] + 273.15}"}
        elif btype == "heat_flux":
            out[pname] = {"type": "externalWallHeatFluxTemperature", "mode": "flux",
                          "q": f"uniform {bc['q_W_m2']}", "kappaMethod": "solidThermo",
                          "value": f"uniform {T0}"}
        elif btype == "convection":
            spec = {"type": "externalWallHeatFluxTemperature", "mode": "coefficient",
                    "Ta": f"uniform {bc['T_amb_C'] + 273.15}", "h": f"uniform {bc['h_W_m2K']}",
                    "kappaMethod": "solidThermo", "value": f"uniform {T0}"}
            if bc.get("emissivity"):
                spec["emissivity"] = f"{bc['emissivity']}"
            out[pname] = spec
        elif btype == "symmetry":
            out[pname] = {"type": "symmetry"}
        else:
            out[pname] = {"type": "zeroGradient"}
    return out


# ─────────────────────────────── region writing ──────────────────────────────

def discover_regions(case: Path) -> list[str]:
    return sorted(p.parent.parent.name
                  for p in (case / "constant").glob("*/polyMesh/boundary"))


def write_regions(case: Path, manifest: dict, patch_areas: dict | None = None) -> dict:
    """Write all per-region files. Requires splitMeshRegions to have run already."""
    case = Path(case)
    slv = merged_solver(manifest)
    regions = region_map(manifest)
    rad_model = manifest.get("radiation", {}).get("model", "none")
    found = discover_regions(case)
    missing = [r for r in regions if r not in found]
    if missing:
        raise RuntimeError(f"Regions missing after splitMeshRegions: {missing}; found {found}")

    fluids = [r for r in found if regions.get(r, {}).get("type") == "fluid"]
    solids = [r for r in found if regions.get(r, {}).get("type") == "solid"]
    _write(case, "constant/regionProperties",
           f"regions\n(\n    fluid ({' '.join(fluids)})\n    solid ({' '.join(solids)})\n);\n")

    dims = {"U": ("volVectorField", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)"),
            "p": ("volScalarField", "[1 -1 -2 0 0 0 0]", None),
            "p_rgh": ("volScalarField", "[1 -1 -2 0 0 0 0]", None),
            "T": ("volScalarField", "[0 0 0 1 0 0 0]", None),
            "k": ("volScalarField", "[0 2 -2 0 0 0 0]", "uniform 1e-4"),
            "omega": ("volScalarField", "[0 0 -1 0 0 0 0]", "uniform 10"),
            "nut": ("volScalarField", "[0 2 -1 0 0 0 0]", "uniform 0"),
            "alphat": ("volScalarField", "[1 -1 -1 0 0 0 0]", "uniform 0"),
            "G": ("volScalarField", "[1 0 -3 0 0 0 0]", "uniform 0"),
            "IDefault": ("volScalarField", "[1 0 -3 0 0 0 0]", "uniform 0")}

    for r in fluids:
        patches = fix_region_boundary(case, r, manifest)
        props = regions[r]["props"]
        T0 = regions[r]["T_init"]
        p0 = slv["p_ref_Pa"]
        fields = _fluid_fields(r, patches, manifest, regions, patch_areas)
        internals = {"p": f"uniform {p0}", "p_rgh": f"uniform {p0}", "T": f"uniform {T0}"}
        for fname, patch_specs in fields.items():
            cls, dim, default_int = dims[fname]
            internal = internals.get(fname, default_int)
            _write(case, f"0/{r}/{fname}",
                   _field(cls, fname, dim, internal, patch_specs), cls)
        _write(case, f"constant/{r}/thermophysicalProperties", fluid_thermo_body(props))
        _write(case, f"constant/{r}/turbulenceProperties",
               "simulationType  RAS;\n\nRAS\n{\n    RASModel        kOmegaSST;\n"
               "    turbulence      on;\n    printCoeffs     on;\n}\n")
        _write(case, f"constant/{r}/radiationProperties", _radiation_body(rad_model, props))
        if rad_model != "none":
            _write(case, f"constant/{r}/boundaryRadiationProperties",
                   _boundary_radiation_body(r, patches, manifest, regions))
        sealed = not any(
            patches_for(manifest, r).get(p, {}).get("type") == "pressure_outlet"
            for p in patches)
        _write(case, f"system/{r}/fvSchemes", _fluid_fvschemes(slv["mode"]))
        _write(case, f"system/{r}/fvSolution",
               _fluid_fvsolution(slv["mode"], sealed, slv["p_ref_Pa"]))
        _write(case, f"system/{r}/decomposeParDict",
               f"numberOfSubdomains {slv['n_procs']};\n\nmethod          scotch;\n")

    for r in solids:
        patches = fix_region_boundary(case, r, manifest)
        props = regions[r]["props"]
        _write(case, f"0/{r}/T",
               _field("volScalarField", "T", "[0 0 0 1 0 0 0]",
                      f"uniform {regions[r]['T_init']}",
                      _solid_T_field(r, patches, manifest, regions)), "volScalarField")
        _write(case, f"constant/{r}/thermophysicalProperties", solid_thermo_body(props))
        _write(case, f"constant/{r}/radiationProperties",
               "radiation       off;\n\nradiationModel  none;\n")
        _write(case, f"system/{r}/fvSchemes", _solid_fvschemes(slv["mode"]))
        _write(case, f"system/{r}/fvSolution", _solid_fvsolution(slv["mode"]))
        _write(case, f"system/{r}/decomposeParDict",
               f"numberOfSubdomains {slv['n_procs']};\n\nmethod          scotch;\n")

    _write_controldict(case, manifest, _function_objects(manifest, fluids, solids))
    (case / "cht_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"fluid_regions": fluids, "solid_regions": solids, "radiation": rad_model}


# ─────────────────────────────── function objects ────────────────────────────

def _function_objects(manifest: dict, fluids: list[str], solids: list[str]) -> str:
    slv = merged_solver(manifest)
    every = 50 if slv["mode"] == "steady" else 10
    blocks = []
    for r in fluids + solids:
        blocks.append(f"""    minMaxT_{r}
    {{
        type            fieldMinMax;
        libs            (fieldFunctionObjects);
        region          {r};
        fields          (T);
        location        no;
        writeControl    timeStep;
        writeInterval   {every};
        log             no;
    }}

    wallHeatFlux_{r}
    {{
        type            wallHeatFlux;
        libs            (fieldFunctionObjects);
        region          {r};
        writeControl    timeStep;
        writeInterval   {every};
        log             no;
    }}
""")
    for pname, patch in manifest.get("patches", {}).items():
        bc = patch.get("bc", {})
        if bc.get("type") not in ("velocity_inlet", "pressure_outlet"):
            continue
        r = patch["component"]
        blocks.append(f"""    massFlow_{pname}
    {{
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        region          {r};
        regionType      patch;
        name            {pname};
        operation       sum;
        fields          (phi);
        writeFields     no;
        writeControl    timeStep;
        writeInterval   {every};
        log             no;
    }}

    Tbulk_{pname}
    {{
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        region          {r};
        regionType      patch;
        name            {pname};
        operation       weightedAverage;
        weightField     phi;
        fields          (T);
        writeFields     no;
        writeControl    timeStep;
        writeInterval   {every};
        log             no;
    }}
""")
    return "\n".join(blocks)
