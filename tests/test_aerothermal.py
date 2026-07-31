"""CI gate for the satellite / high-altitude thermal capability: US76 atmosphere,
radiative environment math, and the space/altitude environment BCs — no WSL needed."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / ".tmp" / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

from atmosphere import (atmosphere, sky_sink_temperature, earth_view_factor,  # noqa: E402
                        equivalent_sink_temperature, natural_convection_h,
                        combined_film, absorbed_environmental_flux)
from materials import air_at_altitude  # noqa: E402
from step_assembly import validate_manifest  # noqa: E402
import cht_case  # noqa: E402
from test_cht import fake_region, make_manifest  # noqa: E402


# ─────────────────────────────── atmosphere ──────────────────────────────────

def test_us76_sea_level():
    a = atmosphere(0)
    assert a["T_K"] == pytest.approx(288.15)
    assert a["p_Pa"] == pytest.approx(101325, rel=1e-6)
    assert a["rho_kg_m3"] == pytest.approx(1.225, rel=1e-3)


def test_us76_tropopause_and_stratosphere():
    a11 = atmosphere(11000)          # geometric; geopotential ~10.98 km
    assert a11["T_K"] == pytest.approx(216.8, abs=0.5)
    assert a11["p_Pa"] == pytest.approx(22700, rel=0.01)
    a30 = atmosphere(30000)          # balloon float altitude
    assert a30["T_K"] == pytest.approx(226.5, abs=1.0)
    assert a30["p_Pa"] == pytest.approx(1197, rel=0.02)
    assert a30["rho_kg_m3"] == pytest.approx(0.0184, rel=0.03)


def test_us76_bounds():
    with pytest.raises(ValueError):
        atmosphere(-1)
    with pytest.raises(ValueError):
        atmosphere(90000)            # above table — vacuum physics territory


def test_radiative_environment():
    assert earth_view_factor(0) == pytest.approx(0.5, abs=1e-6)
    assert sky_sink_temperature(0) == pytest.approx(214.4, abs=0.5)
    assert sky_sink_temperature(500e3) == pytest.approx(190.7, abs=1.0)
    # folding 300 W/m2 absorbed into an eps=0.9 radiative sink
    t_eq = equivalent_sink_temperature(0.9, 300.0)
    assert t_eq == pytest.approx(276.9, abs=0.5)
    with pytest.raises(ValueError):
        equivalent_sink_temperature(0.0, 100.0)


def test_natural_convection_collapses_with_altitude():
    h0 = natural_convection_h(0, 0.5, 20)
    h30 = natural_convection_h(30000, 0.5, 20)
    assert h0 > 2.0
    assert h30 < 1.0
    assert h30 < h0 / 3


def test_combined_film_linearisation():
    film = combined_film(1.0, 226.5, 0.9, 200.0, 300.0)
    assert film["h_rad_W_m2K"] == pytest.approx(3.32, abs=0.05)
    assert 200.0 < film["Ta_K"] < 226.5    # blend between air and colder sink


def test_absorbed_flux_and_air_overrides():
    loads = absorbed_environmental_flux(500e3, 0.86, 0.88, sun=True)
    assert loads["q_solar_W_m2"] == pytest.approx(1361 * 0.86 * 0.25, rel=1e-6)
    assert loads["q_total_W_m2"] > loads["q_solar_W_m2"]
    dark = absorbed_environmental_flux(500e3, 0.86, 0.88, sun=False)
    assert dark["q_solar_W_m2"] == 0.0 and dark["q_earth_ir_W_m2"] > 0
    air = air_at_altitude(30000)
    assert air["p_ref_Pa"] == pytest.approx(1197, rel=0.02)
    assert air["overrides"]["mu"] == pytest.approx(1.49e-5, rel=0.03)


# ─────────────────────────── satellite (vacuum) case ─────────────────────────

def satellite_manifest():
    m = make_manifest()
    m["components"]["hot_gas"].update({"type": "solid", "material": "black_anodized_aluminum"})
    m["components"] = {"chassis": m["components"].pop("hot_gas"),
                       "tube": m["components"]["tube"]}
    m["patches"] = {
        "radiator": {"component": "chassis", "select": "zmax",
                     "bc": {"type": "space_environment", "emissivity": 0.88,
                            "absorbed_flux_W_m2": 150.0}},
        "mli_side": {"component": "tube", "select": "remaining",
                     "bc": {"type": "altitude_environment", "altitude_m": 30000,
                            "emissivity": 0.9, "L_char_m": 0.5}},
    }
    m["radiation"] = {"model": "none", "emissivity_default": 0.9}
    return m


def test_environment_bc_validation():
    m = satellite_manifest()
    assert validate_manifest(m) == []
    m["patches"]["radiator"]["bc"].pop("emissivity")
    m["patches"]["mli_side"]["bc"].pop("altitude_m")
    problems = "\n".join(validate_manifest(m))
    assert "space_environment needs emissivity" in problems
    assert "altitude_environment needs" in problems


def test_solid_only_vacuum_case(tmp_path):
    case = tmp_path / "case"
    fake_region(case, "chassis", {
        "radiator": ("patch", 20), "chassis_wall": ("patch", 40),
        "chassis_to_tube": ("mappedWall", 10)})
    fake_region(case, "tube", {
        "mli_side": ("patch", 30), "tube_to_chassis": ("mappedWall", 10)})
    manifest = satellite_manifest()
    cht_case.write_skeleton(case, manifest)
    info = cht_case.write_regions(case, manifest)
    assert info["fluid_regions"] == [] and set(info["solid_regions"]) == {"chassis", "tube"}

    rp = (case / "constant" / "regionProperties").read_text(encoding="utf-8")
    assert "fluid ()" in rp

    # radiator: pure radiation to the equivalent sink (h = 0, emissivity set)
    T = (case / "0" / "chassis" / "T").read_text(encoding="utf-8")
    assert "externalWallHeatFluxTemperature" in T
    assert "h               uniform 0" in T
    assert "emissivity      0.88" in T
    # equivalent sink for eps=0.88, q=150: (150/(0.88*sigma))^0.25 ~ 234 K
    assert "uniform 234." in T

    # balloon-altitude side: combined convective+radiative film, h > 0
    Ts = (case / "0" / "tube" / "T").read_text(encoding="utf-8")
    assert "externalWallHeatFluxTemperature" in Ts
    assert "uniform 0;" not in Ts.split("mli_side")[1].split("}")[0]

    # no fluid machinery in a vacuum case
    assert not (case / "0" / "chassis" / "U").exists()
    cd = (case / "system" / "controlDict").read_text(encoding="utf-8")
    assert "massFlow" not in cd and "wallHeatFlux_chassis" in cd
