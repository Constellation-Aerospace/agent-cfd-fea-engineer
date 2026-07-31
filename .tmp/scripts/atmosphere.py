#!/usr/bin/env python3
"""Aerothermal environment models for satellite / high-altitude thermal analysis.

Provides the physics the CHT toolchain needs above the troposphere:
  * US Standard Atmosphere 1976 (geometric altitude 0-86 km): T, p, rho + air
    transport properties (Sutherland viscosity, k from Pr, cp const)
  * radiative environment: solar constant, Earth albedo/IR, space sink,
    Earth view factor vs altitude, effective sky sink temperature
  * equivalent sink temperature folding absorbed environmental flux into a
    single radiative BC (exact: q_net = eps*sigma*(T_eq^4 - T_s^4))
  * combined convective+radiative film linearisation for the single-Ta
    externalWallHeatFluxTemperature BC (exact at the chosen reference temp)
  * natural-convection film coefficient estimate at altitude (Churchill-Chu
    sphere correlation — rho^2 scaling makes h collapse in the stratosphere)

All SI. Valid altitude range 0-86 km; above that (orbit) use vacuum physics
(space_environment BC — no atmosphere at all).
"""
from __future__ import annotations

import math

G0 = 9.80665                 # m/s^2
R_AIR = 287.053              # J/kg-K
CP_AIR = 1005.0              # J/kg-K
PR_AIR = 0.71
R_EARTH = 6356766.0          # m (US76 geopotential radius)
SIGMA = 5.670374419e-8       # W/m^2-K^4

SOLAR_CONSTANT = 1361.0      # W/m^2 (1 AU mean)
EARTH_ALBEDO = 0.30          # mean bond albedo
EARTH_IR = 240.0             # W/m^2 mean outgoing longwave at surface reference
T_SPACE = 2.7                # K, deep-space sink
T_EARTH_EFF = 255.0          # K, Earth effective emission temperature

# US76 layer table: base geopotential altitude [m], base T [K], lapse [K/m], base p [Pa]
_LAYERS = [
    (0.0,     288.15, -0.0065, 101325.0),
    (11000.0, 216.65,  0.0,    22632.06),
    (20000.0, 216.65,  0.001,  5474.889),
    (32000.0, 228.65,  0.0028, 868.0187),
    (47000.0, 270.65,  0.0,    110.9063),
    (51000.0, 270.65, -0.0028, 66.93887),
    (71000.0, 214.65, -0.002,  3.956420),
]
_H_TOP = 84852.0  # geopotential top of US76 table


def atmosphere(altitude_m: float) -> dict:
    """US Standard Atmosphere 1976 state + air properties at geometric altitude."""
    if altitude_m < 0:
        raise ValueError("altitude_m must be >= 0")
    h = R_EARTH * altitude_m / (R_EARTH + altitude_m)   # geometric -> geopotential
    if h > _H_TOP:
        raise ValueError(f"altitude {altitude_m:.0f} m is above the 86 km US76 limit "
                         "— use vacuum physics (space_environment BC) instead")
    hb, Tb, L, pb = next((lay for lay in reversed(_LAYERS) if h >= lay[0]))
    if L == 0.0:
        T = Tb
        p = pb * math.exp(-G0 * (h - hb) / (R_AIR * Tb))
    else:
        T = Tb + L * (h - hb)
        p = pb * (Tb / T) ** (G0 / (R_AIR * L))
    rho = p / (R_AIR * T)
    mu = 1.458e-6 * T ** 1.5 / (T + 110.4)              # Sutherland
    k = mu * CP_AIR / PR_AIR
    return {"altitude_m": altitude_m, "T_K": T, "T_C": T - 273.15, "p_Pa": p,
            "rho_kg_m3": rho, "mu_Pa_s": mu, "k_W_mK": k, "cp_J_kgK": CP_AIR,
            "Pr": PR_AIR}


def earth_view_factor(altitude_m: float) -> float:
    """View factor from a convex surface element to Earth's disc (0.5 at z=0)."""
    r = R_EARTH / (R_EARTH + max(altitude_m, 0.0))
    return 0.5 * (1.0 - math.sqrt(1.0 - r * r))


def sky_sink_temperature(altitude_m: float) -> float:
    """Effective radiative sink [K] seen by an exposed surface: Earth IR below,
    deep space above, weighted by view factor (atmospheric emission neglected —
    conservative above ~20 km, where balloon/satellite work lives)."""
    f_e = earth_view_factor(altitude_m)
    return (f_e * T_EARTH_EFF ** 4 + (1.0 - f_e) * T_SPACE ** 4) ** 0.25


def absorbed_environmental_flux(altitude_m: float, absorptivity_solar: float,
                                emissivity_ir: float, sun: bool = True,
                                solar_projection: float = 0.25) -> dict:
    """Rough orbit-average absorbed flux [W/m^2] on a convex body.

    solar_projection = A_projected/A_total (0.25 for a sphere, ~0.3-0.5 for a
    flat panel tracking the sun). Returns the components and the total —
    intended for scoping; replace with orbital-average tools for flight review.
    """
    f_e = earth_view_factor(altitude_m)
    q_solar = SOLAR_CONSTANT * absorptivity_solar * solar_projection if sun else 0.0
    q_albedo = SOLAR_CONSTANT * EARTH_ALBEDO * absorptivity_solar * f_e if sun else 0.0
    q_ir = EARTH_IR * emissivity_ir * f_e
    return {"q_solar_W_m2": q_solar, "q_albedo_W_m2": q_albedo,
            "q_earth_ir_W_m2": q_ir, "q_total_W_m2": q_solar + q_albedo + q_ir}


def equivalent_sink_temperature(emissivity: float, absorbed_flux_W_m2: float = 0.0,
                                base_sink_K: float = T_SPACE) -> float:
    """Sink temperature [K] that folds absorbed flux into a pure radiative BC:
    q_net = q_abs - eps*sigma*(Ts^4 - Tsink^4) == eps*sigma*(Teq^4 - Ts^4)."""
    if emissivity <= 0:
        raise ValueError("emissivity must be > 0 for a radiative environment BC")
    return (base_sink_K ** 4 + absorbed_flux_W_m2 / (emissivity * SIGMA)) ** 0.25


def natural_convection_h(altitude_m: float, L_char_m: float = 1.0,
                         dT_K: float = 20.0) -> float:
    """Natural-convection film coefficient estimate [W/m^2-K] at altitude
    (Churchill sphere correlation; Gr ~ rho^2 so h collapses with altitude)."""
    a = atmosphere(altitude_m)
    T_film = a["T_K"] + dT_K / 2.0
    beta = 1.0 / T_film
    gr = G0 * beta * abs(dT_K) * L_char_m ** 3 * a["rho_kg_m3"] ** 2 / a["mu_Pa_s"] ** 2
    ra = gr * a["Pr"]
    nu = 2.0 + 0.589 * ra ** 0.25 / (1.0 + (0.469 / a["Pr"]) ** (9 / 16)) ** (4 / 9)
    return nu * a["k_W_mK"] / L_char_m


def combined_film(h_conv_W_m2K: float, T_air_K: float, emissivity: float,
                  T_sink_K: float, T_ref_K: float) -> dict:
    """Fold convection (to T_air) + radiation (to T_sink) into a single
    (h, Ta) pair for externalWallHeatFluxTemperature, exact at T_ref:
    h_rad = eps*sigma*(T_ref^2 + T_sink^2)(T_ref + T_sink)."""
    h_rad = emissivity * SIGMA * (T_ref_K ** 2 + T_sink_K ** 2) * (T_ref_K + T_sink_K)
    h_tot = h_conv_W_m2K + h_rad
    ta = ((h_conv_W_m2K * T_air_K + h_rad * T_sink_K) / h_tot) if h_tot > 0 else T_air_K
    return {"h_W_m2K": h_tot, "h_conv_W_m2K": h_conv_W_m2K, "h_rad_W_m2K": h_rad,
            "Ta_K": ta, "T_ref_K": T_ref_K}
