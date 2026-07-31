#!/usr/bin/env python3
"""Exhaust gas mixture properties — representative marine diesel exhaust.

Computes mixture molar mass and mole-fraction-weighted NASA-7 (JANAF) polynomial
coefficients for a multi-component ideal-gas mixture of N2 / CO2 / H2O / O2, and
emits the OpenFOAM `thermophysicalProperties.gas` janaf coefficient block.

The frozen-mixture approach: coefficients are averaged on a molar basis, which is
exact for cp of an ideal-gas mixture with fixed composition. Temperature-dependent
cp comes from the JANAF polynomials; viscosity/conductivity use Sutherland's law.

Usage:
    python exhaust_properties.py                          # default composition
    python exhaust_properties.py --mole-fractions "N2=0.757,O2=0.132,CO2=0.055,H2O=0.056"
    python exhaust_properties.py --json                   # machine-readable output
"""
from __future__ import annotations

import argparse
import json

R_UNIVERSAL = 8314.462618  # J/(kmol K)

# Molar masses [kg/kmol]
MOLAR_MASS = {"N2": 28.0134, "O2": 31.9988, "CO2": 44.0095, "H2O": 18.01528}

# NASA-7 polynomial coefficients (GRI-Mech 3.0 / CHEMKIN thermodynamic database).
# Format: (low_T_coeffs a1..a7 for 300-1000 K, high_T_coeffs a1..a7 for 1000-5000 K)
NASA7 = {
    "N2": (
        [3.298677e00, 1.4082404e-03, -3.963222e-06, 5.641515e-09, -2.444854e-12, -1.0208999e03, 3.950372e00],
        [2.92664e00, 1.4879768e-03, -5.68476e-07, 1.0097038e-10, -6.753351e-15, -9.227977e02, 5.980528e00],
    ),
    "O2": (
        [3.212936e00, 1.1274864e-03, -5.75615e-07, 1.3138773e-09, -8.768554e-13, -1.005249e03, 6.034738e00],
        [3.697578e00, 6.135197e-04, -1.258842e-07, 1.775281e-11, -1.1364354e-15, -1.2339301e03, 3.189166e00],
    ),
    "CO2": (
        [2.275724e00, 9.922072e-03, -1.0409113e-05, 6.866686e-09, -2.117280e-12, -4.837314e04, 1.018849e01],
        [4.453623e00, 3.140168e-03, -1.278410e-06, 2.393996e-10, -1.6690333e-14, -4.896696e04, -9.553959e-01],
    ),
    "H2O": (
        [3.386842e00, 3.474982e-03, -6.354696e-06, 6.968581e-09, -2.506588e-12, -3.020811e04, 2.590233e00],
        [2.672145e00, 3.056293e-03, -8.73026e-07, 1.200996e-10, -6.391618e-15, -2.989921e04, 6.862817e00],
    ),
}

# Representative marine diesel exhaust, mole fractions (typical medium-speed
# diesel at moderate load; refine at detailed engineering stage).
DEFAULT_MOLE_FRACTIONS = {"N2": 0.757, "O2": 0.132, "CO2": 0.055, "H2O": 0.056}

# Sutherland transport for the gas mixture (air-like; dominated by N2)
SUTHERLAND_AS = 1.4792e-06  # kg/(m s K^0.5)
SUTHERLAND_TS = 116.0       # K


def mixture_properties(mole_fractions: dict[str, float]) -> dict:
    """Mole-fraction-weighted mixture molar mass and NASA-7 coefficients."""
    total = sum(mole_fractions.values())
    x = {k: v / total for k, v in mole_fractions.items()}
    unknown = set(x) - set(NASA7)
    if unknown:
        raise ValueError(f"Unknown species: {unknown}. Supported: {sorted(NASA7)}")

    mw = sum(x[s] * MOLAR_MASS[s] for s in x)
    low = [sum(x[s] * NASA7[s][0][i] for s in x) for i in range(7)]
    high = [sum(x[s] * NASA7[s][1][i] for s in x) for i in range(7)]

    # cp at reference temps for sanity reporting [J/(kg K)]
    def cp(coeffs, T):
        a = coeffs
        return (a[0] + a[1]*T + a[2]*T**2 + a[3]*T**3 + a[4]*T**4) * R_UNIVERSAL / mw

    return {
        "composition_mole_fractions": x,
        "molar_mass_kg_per_kmol": round(mw, 4),
        "mass_fractions": {s: round(x[s] * MOLAR_MASS[s] / mw, 4) for s in x},
        "nasa7_low_300_1000K": low,
        "nasa7_high_1000_5000K": high,
        "cp_at_400C_J_per_kgK": round(cp(low, 673.15), 1),
        "cp_at_25C_J_per_kgK": round(cp(low, 298.15), 1),
        "R_specific_J_per_kgK": round(R_UNIVERSAL / mw, 2),
        "sutherland_As": SUTHERLAND_AS,
        "sutherland_Ts": SUTHERLAND_TS,
    }


def openfoam_janaf_block(props: dict) -> str:
    """Render the OpenFOAM janaf thermodynamics + specie block for the gas phase."""
    fmt = lambda c: " ".join(f"{v:.9e}" for v in c)
    return f"""    specie
    {{
        molWeight   {props['molar_mass_kg_per_kmol']};
    }}
    thermodynamics
    {{
        Tlow            200;
        Thigh           5000;
        Tcommon         1000;
        highCpCoeffs    ( {fmt(props['nasa7_high_1000_5000K'])} );
        lowCpCoeffs     ( {fmt(props['nasa7_low_300_1000K'])} );
    }}
    transport
    {{
        As          {props['sutherland_As']};
        Ts          {props['sutherland_Ts']};
    }}"""


def parse_fractions(spec: str) -> dict[str, float]:
    out = {}
    for pair in spec.split(","):
        k, v = pair.split("=")
        out[k.strip()] = float(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mole-fractions", type=str, default=None,
                    help='e.g. "N2=0.757,O2=0.132,CO2=0.055,H2O=0.056"')
    ap.add_argument("--json", action="store_true", help="Print JSON only")
    args = ap.parse_args()

    fractions = parse_fractions(args.mole_fractions) if args.mole_fractions else DEFAULT_MOLE_FRACTIONS
    props = mixture_properties(fractions)

    if args.json:
        print(json.dumps(props, indent=2))
    else:
        print(json.dumps({k: v for k, v in props.items() if "nasa7" not in k}, indent=2))
        print("\n// OpenFOAM gas-phase mixture block:\n")
        print(openfoam_janaf_block(props))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
