#!/usr/bin/env python3
"""Material library accessor + OpenFOAM thermophysical dictionary generation.

Backs the per-component material assignment for conjugate heat transfer studies.
The data lives in agent-data/materials_library.json; every property can be
overridden per-study through the assembly manifest ("overrides" on a component).

Usage (import):
    from materials import load_library, get_material, fluid_thermo_body, solid_thermo_body
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LIBRARY_PATH = REPO_ROOT / "agent-data" / "materials_library.json"

_cache: dict | None = None


def load_library() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    return _cache


def list_materials() -> dict:
    lib = load_library()
    return {"solids": sorted(lib["solids"]), "fluids": sorted(lib["fluids"])}


def get_material(name: str, overrides: dict | None = None) -> dict:
    """Return material properties with kind ('solid'|'fluid') resolved and overrides applied."""
    lib = load_library()
    if name in lib["solids"]:
        props = {"kind": "solid", "name": name, **lib["solids"][name]}
    elif name in lib["fluids"]:
        props = {"kind": "fluid", "name": name, **lib["fluids"][name]}
    else:
        known = list_materials()
        raise KeyError(
            f"Unknown material '{name}'. Known solids: {', '.join(known['solids'])}; "
            f"fluids: {', '.join(known['fluids'])}")
    props.update(overrides or {})
    return props


def kappa_fluid(props: dict) -> float:
    """Thermal conductivity of a fluid from mu, cp, Pr (const-transport model)."""
    return props["mu"] * props["cp"] / props["Pr"]


def solid_thermo_body(props: dict) -> str:
    """constant/<region>/thermophysicalProperties body for a solid region (heSolidThermo)."""
    return f"""thermoType
{{
    type            heSolidThermo;
    mixture         pureMixture;
    transport       constIso;
    thermo          hConst;
    equationOfState rhoConst;
    specie          specie;
    energy          sensibleEnthalpy;
}}

// {props['name']}: rho {props['rho']} kg/m3, cp {props['cp']} J/kg-K, kappa {props['kappa']} W/m-K
mixture
{{
    specie
    {{
        molWeight   {props.get('molWeight', 50.0)};
    }}
    transport
    {{
        kappa       {props['kappa']};
    }}
    thermodynamics
    {{
        Hf          0;
        Cp          {props['cp']};
    }}
    equationOfState
    {{
        rho         {props['rho']};
    }}
}}
"""


def fluid_thermo_body(props: dict) -> str:
    """constant/<region>/thermophysicalProperties body for a fluid region (heRhoThermo)."""
    eos = props.get("eos", "perfectGas")
    eos_block = ("    equationOfState\n    {\n"
                 f"        rho         {props['rho']};\n    }}\n") if eos == "rhoConst" else ""
    return f"""thermoType
{{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState {eos};
    specie          specie;
    energy          sensibleEnthalpy;
}}

// {props['name']}: cp {props['cp']} J/kg-K, mu {props['mu']} Pa-s, Pr {props['Pr']}
mixture
{{
    specie
    {{
        molWeight   {props['molWeight']};
    }}
{eos_block}    thermodynamics
    {{
        Cp          {props['cp']};
        Hf          0;
    }}
    transport
    {{
        mu          {props['mu']};
        Pr          {props['Pr']};
    }}
}}
"""


if __name__ == "__main__":
    print(json.dumps(list_materials(), indent=2))
