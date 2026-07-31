"""CI gate for the CHT toolchain: materials library, manifest validation, and the
multi-region case factory — everything that runs without gmsh/WSL/OpenFOAM."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / ".tmp" / "scripts"))

from materials import (get_material, list_materials, fluid_thermo_body,  # noqa: E402
                       solid_thermo_body, kappa_fluid)
from step_assembly import validate_manifest, safe_name  # noqa: E402
import cht_case  # noqa: E402


# ─────────────────────────────── materials ───────────────────────────────────

def test_library_loads_and_has_core_materials():
    mats = list_materials()
    for solid in ("aluminum_6061", "copper", "stainless_316", "titanium_grade2"):
        assert solid in mats["solids"]
    for fluid in ("air", "water", "seawater", "exhaust_gas"):
        assert fluid in mats["fluids"]


def test_material_properties_complete():
    mats = list_materials()
    for name in mats["solids"]:
        p = get_material(name)
        assert p["kind"] == "solid"
        for key in ("rho", "cp", "kappa", "emissivity"):
            assert isinstance(p[key], (int, float)), f"{name}.{key}"
    for name in mats["fluids"]:
        p = get_material(name)
        assert p["kind"] == "fluid"
        for key in ("cp", "mu", "Pr", "molWeight"):
            assert isinstance(p[key], (int, float)), f"{name}.{key}"
        if p["eos"] == "rhoConst":
            assert p["rho"] > 0
        assert kappa_fluid(p) > 0


def test_material_overrides_and_unknown():
    p = get_material("copper", {"kappa": 350})
    assert p["kappa"] == 350
    with pytest.raises(KeyError):
        get_material("unobtainium")


def test_thermo_bodies_render():
    solid = solid_thermo_body(get_material("stainless_316"))
    assert "heSolidThermo" in solid and "kappa       16.3" in solid
    gas = fluid_thermo_body(get_material("air"))
    assert "perfectGas" in gas and "equationOfState\n    {" not in gas
    liq = fluid_thermo_body(get_material("water"))
    assert "rhoConst" in liq and "rho         997" in liq


# ─────────────────────────────── manifest ────────────────────────────────────

def make_manifest(**kw):
    m = {
        "step_file": "dummy.step",
        "components": {
            "hot_gas": {"type": "fluid", "material": "exhaust_gas", "overrides": {},
                        "T_init_C": 300, "solids": [1], "volume_m3": 1e-3,
                        "centroid_m": [0, 0, 0], "bbox_m": [0, 0, 0, 1, 1, 1]},
            "tube": {"type": "solid", "material": "stainless_316", "overrides": {},
                     "T_init_C": None, "solids": [2], "volume_m3": 1e-4,
                     "centroid_m": [0, 0, 1], "bbox_m": [0, 0, 0, 1, 1, 1]},
        },
        "interfaces": [{"components": ["hot_gas", "tube"], "area_m2": 0.1, "n_surfaces": 1}],
        "patches": {
            "gas_in": {"component": "hot_gas", "select": "xmin",
                       "bc": {"type": "velocity_inlet", "U_m_s": 5.0, "T_C": 400}},
            "gas_out": {"component": "hot_gas", "select": "xmax",
                        "bc": {"type": "pressure_outlet", "p_Pa": 101325}},
            "tube_outer": {"component": "tube", "select": "remaining",
                           "bc": {"type": "convection", "h_W_m2K": 12, "T_amb_C": 25,
                                  "emissivity": 0.35}},
        },
        "radiation": {"model": "P1", "emissivity_default": 0.9},
        "solver": {"mode": "steady", "iterations": 100},
    }
    m.update(kw)
    return m


def test_valid_manifest_passes():
    assert validate_manifest(make_manifest()) == []


def test_validation_catches_problems():
    m = make_manifest()
    m["components"]["tube"]["material"] = None
    m["components"]["hot_gas"]["material"] = "copper"          # fluid typed, solid material
    del m["patches"]["gas_out"]                                # inlet without outlet
    m["patches"]["gas_in"]["bc"] = {"type": "velocity_inlet"}  # missing U and T
    problems = "\n".join(validate_manifest(m))
    assert "no material" in problems
    assert "is a solid" in problems
    assert "no pressure_outlet" in problems
    assert "U_m_s or m_dot_kg_s" in problems


def test_safe_name():
    used: set[str] = set()
    assert safe_name("Assembly/Tube Bundle #1", used, "part_1") == "tube_bundle_1"
    assert safe_name("Assembly/Tube Bundle #1", used, "part_2") == "tube_bundle_1_2"
    assert safe_name("123", used, "part_3") == "part_3"


# ─────────────────────────────── case factory ────────────────────────────────

BOUNDARY_TEMPLATE = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       polyBoundaryMesh;
    object      boundary;
}}
{n}
(
{blocks})
"""


def fake_region(case: Path, region: str, patches: dict[str, tuple[str, int]]):
    blocks = "".join(
        f"    {name}\n    {{\n        type            {ptype};\n"
        f"        nFaces          {n};\n        startFace       0;\n    }}\n"
        for name, (ptype, n) in patches.items())
    bnd = case / "constant" / region / "polyMesh" / "boundary"
    bnd.parent.mkdir(parents=True, exist_ok=True)
    bnd.write_text(BOUNDARY_TEMPLATE.format(n=len(patches), blocks=blocks),
                   encoding="utf-8")


@pytest.fixture
def cht_case_dir(tmp_path):
    case = tmp_path / "case"
    fake_region(case, "hot_gas", {
        "gas_in": ("patch", 10), "gas_out": ("patch", 10),
        "hot_gas_wall": ("patch", 40), "hot_gas_to_tube": ("mappedWall", 20)})
    fake_region(case, "tube", {
        "tube_outer": ("patch", 30), "tube_to_hot_gas": ("mappedWall", 20)})
    return case


def test_write_regions_full_case(cht_case_dir):
    manifest = make_manifest()
    cht_case.write_skeleton(cht_case_dir, manifest)
    info = cht_case.write_regions(cht_case_dir, manifest,
                                  patch_areas={"gas_in": 0.01})
    assert info["fluid_regions"] == ["hot_gas"]
    assert info["solid_regions"] == ["tube"]

    # regionProperties + top-level dicts
    rp = (cht_case_dir / "constant" / "regionProperties").read_text(encoding="utf-8")
    assert "fluid (hot_gas)" in rp and "solid (tube)" in rp
    cd = (cht_case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    assert "chtMultiRegionSimpleFoam" in cd
    assert "massFlow_gas_in" in cd and "Tbulk_gas_out" in cd
    assert "wallHeatFlux_tube" in cd

    # fluid fields: inlet velocity, coupled interface, radiation field present (P1)
    U = (cht_case_dir / "0" / "hot_gas" / "U").read_text(encoding="utf-8")
    assert "surfaceNormalFixedValue" in U and "-5.0" in U
    T = (cht_case_dir / "0" / "hot_gas" / "T").read_text(encoding="utf-8")
    assert "turbulentTemperatureRadCoupledMixed" in T
    assert "kappaMethod      fluidThermo" in T.replace("kappaMethod     ", "kappaMethod      ")
    assert (cht_case_dir / "0" / "hot_gas" / "G").exists()

    # solid: only T, coupled with solidThermo, convection+radiation to ambient
    Ts = (cht_case_dir / "0" / "tube" / "T").read_text(encoding="utf-8")
    assert "solidThermo" in Ts and "externalWallHeatFluxTemperature" in Ts
    assert "emissivity" in Ts
    assert not (cht_case_dir / "0" / "tube" / "U").exists()

    # thermo + radiation dicts
    thermo = (cht_case_dir / "constant" / "tube" / "thermophysicalProperties"
              ).read_text(encoding="utf-8")
    assert "heSolidThermo" in thermo
    rad = (cht_case_dir / "constant" / "hot_gas" / "radiationProperties"
           ).read_text(encoding="utf-8")
    assert "P1" in rad
    bre = (cht_case_dir / "constant" / "hot_gas" / "boundaryRadiationProperties"
           ).read_text(encoding="utf-8")
    assert "0.35" in bre  # tube (stainless_316) emissivity on the coupled patch

    # boundary types fixed: inlet/outlet patch, default wall
    bnd = (cht_case_dir / "constant" / "hot_gas" / "polyMesh" / "boundary"
           ).read_text(encoding="utf-8")
    patches = cht_case.read_region_patches(cht_case_dir, "hot_gas")
    assert patches["gas_in"]["type"] == "patch"
    assert patches["hot_gas_wall"]["type"] == "wall"
    assert patches["hot_gas_to_tube"]["type"] == "mappedWall"
    assert "mappedWall" in bnd


def test_write_regions_transient_and_no_radiation(cht_case_dir):
    manifest = make_manifest(radiation={"model": "none", "emissivity_default": 0.9},
                             solver={"mode": "transient", "end_time_s": 10})
    cht_case.write_skeleton(cht_case_dir, manifest)
    cht_case.write_regions(cht_case_dir, manifest)
    cd = (cht_case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    assert "chtMultiRegionFoam" in cd and "maxDi" in cd
    assert not (cht_case_dir / "0" / "hot_gas" / "G").exists()
    T = (cht_case_dir / "0" / "hot_gas" / "T").read_text(encoding="utf-8")
    assert "qrNbr           none" in T and "qr              none" in T


def test_missing_region_raises(cht_case_dir):
    manifest = make_manifest()
    manifest["components"]["extra"] = dict(manifest["components"]["tube"],
                                           material="copper")
    cht_case.write_skeleton(cht_case_dir, manifest)
    with pytest.raises(RuntimeError, match="missing after splitMeshRegions"):
        cht_case.write_regions(cht_case_dir, manifest)
