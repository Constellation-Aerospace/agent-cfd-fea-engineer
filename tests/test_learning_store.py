"""CI gate for the self-learning recommender: feature extraction, harvesting,
and the weighted-kNN recommendation, all on synthetic data (no WSL/solver)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / ".tmp" / "scripts"))

import learning_store as ls  # noqa: E402


def _write_multiphase_study(outputs: Path, slug: str, *, U_in: float, T_exhaust_C: float,
                             submergence: float, max_co: float, n_procs: int,
                             completed: bool, courant: float, mesh_ok: bool) -> None:
    d = outputs / slug
    d.mkdir(parents=True, exist_ok=True)
    params = {"U_in": U_in, "T_exhaust_C": T_exhaust_C, "T_water_C": 15.0,
              "max_co": max_co, "n_procs": n_procs, "write_interval_s": 0.4,
              "end_time_s": 4.0, "geometry": {"submergence": submergence}}
    (d / "params.json").write_text(json.dumps(params), encoding="utf-8")
    (d / "prepare_summary.json").write_text(
        json.dumps({"checkMesh": {"ok": mesh_ok}}), encoding="utf-8")
    (d / "run_summary.json").write_text(json.dumps({
        "completed": completed, "max_courant_final": courant,
        "wall_clock_s": 120.0, "n_procs": n_procs,
    }), encoding="utf-8")


def test_flatten_handles_nesting_and_bools():
    out = ls.flatten({"a": 1, "b": {"c": 2.5, "d": True}, "e": "skip", "f": [1, 2]})
    assert out == {"a": 1.0, "b.c": 2.5, "b.d": 1.0}


def test_detect_case_type_multiphase_vs_cht(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "OUTPUTS", tmp_path)
    _write_multiphase_study(tmp_path, "proj/mp", U_in=15, T_exhaust_C=400,
                            submergence=2.0, max_co=0.9, n_procs=6,
                            completed=True, courant=0.8, mesh_ok=True)
    assert ls.detect_case_type("proj/mp") == "multiphase_cfd"

    d = tmp_path / "proj/cht"
    (d / "assembly").mkdir(parents=True)
    (d / "assembly" / "manifest.json").write_text("{}", encoding="utf-8")
    (d / "run_summary.json").write_text(json.dumps({"completed": True, "n_procs": 4}),
                                        encoding="utf-8")
    assert ls.detect_case_type("proj/cht") == "conjugate_heat_transfer"


def test_harvest_upserts_by_slug(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "OUTPUTS", tmp_path)
    history_file = tmp_path / "learning_history.json"
    monkeypatch.setattr(ls, "HISTORY_FILE", history_file)

    _write_multiphase_study(tmp_path, "proj/a", U_in=15, T_exhaust_C=400,
                            submergence=2.0, max_co=0.9, n_procs=6,
                            completed=True, courant=0.8, mesh_ok=True)
    rec = ls.harvest("proj/a")
    assert rec["case_type"] == "multiphase_cfd"
    assert rec["knobs"]["max_co"] == 0.9
    assert rec["quality"] == 1.0

    history = json.loads(history_file.read_text(encoding="utf-8"))
    assert "proj/a" in history["multiphase_cfd"]

    # re-harvest after a "fix" (bad Courant) replaces the record, doesn't duplicate
    _write_multiphase_study(tmp_path, "proj/a", U_in=15, T_exhaust_C=400,
                            submergence=2.0, max_co=0.9, n_procs=6,
                            completed=True, courant=8.0, mesh_ok=True)
    rec2 = ls.harvest("proj/a")
    assert rec2["quality"] < 1.0
    history = json.loads(history_file.read_text(encoding="utf-8"))
    assert len(history["multiphase_cfd"]) == 1


def test_harvest_skips_incomplete_study(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "OUTPUTS", tmp_path)
    monkeypatch.setattr(ls, "HISTORY_FILE", tmp_path / "history.json")
    (tmp_path / "proj/only-params").mkdir(parents=True)
    (tmp_path / "proj/only-params/params.json").write_text("{}", encoding="utf-8")
    rec = ls.harvest("proj/only-params", case_type="multiphase_cfd")
    assert "skipped" in rec


def test_recommend_no_history_reports_zero_confidence(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "OUTPUTS", tmp_path)
    monkeypatch.setattr(ls, "HISTORY_FILE", tmp_path / "history.json")
    out = ls.recommend("multiphase_cfd", {"U_in": 15.0})
    assert out["confidence"] == 0.0
    assert out["n_history"] == 0


def test_recommend_confidence_rises_with_more_matching_history(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "OUTPUTS", tmp_path)
    monkeypatch.setattr(ls, "HISTORY_FILE", tmp_path / "history.json")

    for i in range(2):
        _write_multiphase_study(tmp_path, f"proj/s{i}", U_in=15.0 + i, T_exhaust_C=400,
                                submergence=2.0, max_co=0.9, n_procs=6,
                                completed=True, courant=0.8, mesh_ok=True)
        ls.harvest(f"proj/s{i}")
    query = {"U_in": 15.5, "T_exhaust_C": 400.0, "geometry.submergence": 2.0}
    low = ls.recommend("multiphase_cfd", query)

    for i in range(2, 6):
        _write_multiphase_study(tmp_path, f"proj/s{i}", U_in=15.0 + (i % 3), T_exhaust_C=400,
                                submergence=2.0, max_co=0.9, n_procs=6,
                                completed=True, courant=0.8, mesh_ok=True)
        ls.harvest(f"proj/s{i}")
    high = ls.recommend("multiphase_cfd", query)

    assert high["n_history"] > low["n_history"]
    assert high["confidence"] >= low["confidence"]
    assert high["recommended_knobs"]["max_co"] == 0.9
    assert high["recommended_knobs"]["n_procs"] == 6


def test_recommend_downweights_low_quality_neighbours(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "OUTPUTS", tmp_path)
    monkeypatch.setattr(ls, "HISTORY_FILE", tmp_path / "history.json")

    # a well-converged run at n_procs=6 ...
    _write_multiphase_study(tmp_path, "proj/good", U_in=15.0, T_exhaust_C=400,
                            submergence=2.0, max_co=0.9, n_procs=6,
                            completed=True, courant=0.8, mesh_ok=True)
    ls.harvest("proj/good")
    # ... and a blown-up run (bad mesh + huge Courant) at the same inputs, n_procs=1
    _write_multiphase_study(tmp_path, "proj/bad", U_in=15.0, T_exhaust_C=400,
                            submergence=2.0, max_co=0.9, n_procs=1,
                            completed=False, courant=50.0, mesh_ok=False)
    ls.harvest("proj/bad")

    out = ls.recommend("multiphase_cfd", {"U_in": 15.0, "T_exhaust_C": 400.0,
                                          "geometry.submergence": 2.0})
    assert out["recommended_knobs"]["n_procs"] == 6


def test_cht_features_are_generic_not_hardcoded_to_component_names():
    manifest = {
        "components": {"weird_name_1": {"type": "solid", "volume_m3": 1e-4},
                       "weird_name_2": {"type": "fluid", "volume_m3": 2e-4}},
        "interfaces": [{"area_m2": 0.01}],
        "patches": {"p1": {"bc": {"type": "altitude_environment"}}},
        "solver": {"ambient_T_K": 193.15, "ambient_pressure_Pa": 1197.0},
    }
    feats = ls._cht_features(manifest)
    assert feats["n_solid"] == 1.0
    assert feats["n_fluid"] == 1.0
    assert feats["n_radiative_patches"] == 1.0
    assert feats["ambient_T_K"] == 193.15
