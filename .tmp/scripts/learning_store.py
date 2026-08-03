#!/usr/bin/env python3
"""Self-learning recommender: harvests every completed study's inputs, solver
knobs, and outcome quality into agent-data/learning_history.json, then
recommends solver settings for a new case by weighted-kNN similarity to past
runs of the same case type.

There is no separate "training" step — harvesting *is* the learning. Each
completed study becomes one more example the recommender can draw on, so
recommendations get more numerous and (via the confidence score) more
trustworthy the more studies accumulate.

Case types: multiphase_cfd, conjugate_heat_transfer, fea_analysis.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUTPUTS = REPO / "outputs"
HISTORY_FILE = Path(os.getenv("LEARNING_HISTORY_FILE",
                              str(REPO / "agent-data" / "learning_history.json")))


def flatten(d: dict, prefix: str = "") -> dict:
    """Flatten nested dicts to dot-path numeric features (bools -> 0/1,
    strings/lists/None dropped — only comparable numeric features survive)."""
    out: dict = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        elif isinstance(v, bool):
            out[key] = 1.0 if v else 0.0
        elif isinstance(v, (int, float)):
            out[key] = float(v)
    return out


def _load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ─────────────────────────── case-type profiles ──────────────────────────────
# Each profile splits into a *feature* extractor (query-time inputs, available
# before a study is even run) and a *record* builder (features + knobs actually
# used + a quality score, only available once the study has completed).

MULTIPHASE_KNOBS = ["max_co", "n_procs", "write_interval_s", "end_time_s"]


def _multiphase_features(params: dict) -> dict:
    feats = flatten(params)
    for k in MULTIPHASE_KNOBS:
        feats.pop(k, None)
    return feats


def _multiphase_record(d: Path) -> dict | None:
    params = _load_json(d / "params.json")
    run = _load_json(d / "run_summary.json")
    if not params or not run:
        return None
    prep = _load_json(d / "prepare_summary.json")
    all_flat = flatten(params)
    knobs = {k: all_flat[k] for k in MULTIPHASE_KNOBS if k in all_flat}
    score = 1.0
    if prep and not (prep.get("checkMesh", {}) or {}).get("ok", True):
        score -= 0.4
    if not run.get("completed", False):
        score -= 0.5
    co = run.get("max_courant_final")
    if co is not None:
        if co > 5:
            score -= 0.3
        elif co > 1.5:
            score -= 0.1
    outcome = {"completed": run.get("completed"), "max_courant_final": co,
               "wall_clock_s": run.get("wall_clock_s"),
               "mesh_ok": (prep.get("checkMesh", {}) or {}).get("ok")}
    return {"features": _multiphase_features(params), "knobs": knobs,
            "quality": _clip01(score), "outcome": outcome}


def _cht_features(manifest: dict) -> dict:
    comps = manifest.get("components", {})
    n_solid = sum(1 for c in comps.values() if c.get("type") == "solid")
    n_fluid = sum(1 for c in comps.values() if c.get("type") == "fluid")
    total_vol = sum(float(c.get("volume_m3", 0.0)) for c in comps.values())
    interfaces = manifest.get("interfaces", [])
    total_iface_area = sum(float(i.get("area_m2", 0.0)) for i in interfaces)
    patches = manifest.get("patches", {})
    n_radiative = sum(
        1 for p in patches.values()
        if p.get("bc", {}).get("type") in ("altitude_environment", "space_environment"))
    total_flux_in = sum(float(p.get("bc", {}).get("q_W_m2", 0.0)) for p in patches.values())
    solver = manifest.get("solver", {})
    feats = {
        "n_components": float(len(comps)),
        "n_solid": float(n_solid),
        "n_fluid": float(n_fluid),
        "total_volume_m3": total_vol,
        "n_interfaces": float(len(interfaces)),
        "total_interface_area_m2": total_iface_area,
        "n_patches": float(len(patches)),
        "n_radiative_patches": float(n_radiative),
        "total_heat_flux_in_W_m2": total_flux_in,
        "ambient_T_K": solver.get("ambient_T_K"),
        "ambient_pressure_Pa": solver.get("ambient_pressure_Pa"),
    }
    return {k: float(v) for k, v in feats.items() if v is not None}


def _cht_record(d: Path) -> dict | None:
    manifest = _load_json(d / "assembly" / "manifest.json")
    run = _load_json(d / "run_summary.json")
    if not manifest or not run:
        return None
    kpis = _load_json(d / "cht_kpis.json")
    knobs = {}
    if run.get("n_procs") is not None:
        knobs["n_procs"] = float(run["n_procs"])
    score = 1.0
    if not run.get("completed", False):
        score -= 0.5
    residuals = run.get("final_residuals", {}) or {}
    worst = max(residuals.values()) if residuals else None
    if worst is not None:
        if worst > 1e-2:
            score -= 0.2
        elif worst > 1e-3:
            score -= 0.05
    imbalance = (kpis.get("heat_exchanger", {}) or {}).get("energy_imbalance_pct")
    if imbalance is not None:
        if imbalance > 10:
            score -= 0.3
        elif imbalance > 5:
            score -= 0.1
    outcome = {"completed": run.get("completed"), "worst_residual": worst,
               "energy_imbalance_pct": imbalance, "wall_clock_s": run.get("wall_clock_s")}
    return {"features": _cht_features(manifest), "knobs": knobs,
            "quality": _clip01(score), "outcome": outcome}


def _fea_features(summary: dict) -> dict:
    feats = {}
    feats.update(flatten(summary.get("geometry", {})))
    feats.update(flatten(summary.get("loads", {})))
    feats.update(flatten(summary.get("material", {})))
    return feats


def _fea_record(d: Path) -> dict | None:
    summary = _load_json(d / "fea" / "fea_summary.json")
    if not summary:
        return None
    knobs = flatten(summary.get("mesh", {}))
    score = 1.0
    if "max_von_mises_MPa" not in summary and "T_max_C" not in summary:
        score -= 0.3
    outcome = {k: summary.get(k) for k in
               ("T_min_C", "T_max_C", "max_displacement_mm", "max_von_mises_MPa") if k in summary}
    return {"features": _fea_features(summary), "knobs": knobs,
            "quality": _clip01(score), "outcome": outcome}


CASE_PROFILES = {
    "multiphase_cfd": {
        "identify": lambda d: (d / "run_summary.json").exists() and not (d / "assembly").is_dir(),
        "record": _multiphase_record,
    },
    "conjugate_heat_transfer": {
        "identify": lambda d: (d / "run_summary.json").exists() and (d / "assembly").is_dir(),
        "record": _cht_record,
    },
    "fea_analysis": {
        "identify": lambda d: (d / "fea" / "fea_summary.json").exists(),
        "record": _fea_record,
    },
}


def detect_case_type(slug: str) -> str | None:
    d = OUTPUTS / slug
    for case_type, profile in CASE_PROFILES.items():
        if profile["identify"](d):
            return case_type
    return None


def query_features_for_study(case_type: str, slug: str) -> dict:
    """Feature side only (no run required) — for recommending settings on a
    study that has been set up but not yet solved."""
    d = OUTPUTS / slug
    if case_type == "multiphase_cfd":
        return _multiphase_features(_load_json(d / "params.json"))
    if case_type == "conjugate_heat_transfer":
        return _cht_features(_load_json(d / "assembly" / "manifest.json"))
    if case_type == "fea_analysis":
        return _fea_features(_load_json(d / "fea" / "fea_summary.json"))
    raise ValueError(f"unknown case_type '{case_type}'")


def discover_studies() -> dict:
    """case_type -> [slug, ...] for every completed study under outputs/."""
    found: dict = {k: [] for k in CASE_PROFILES}
    for run_summary in OUTPUTS.glob("**/run_summary.json"):
        slug = str(run_summary.parent.relative_to(OUTPUTS)).replace("\\", "/")
        ct = detect_case_type(slug)
        if ct:
            found[ct].append(slug)
    for fea_summary in OUTPUTS.glob("**/fea/fea_summary.json"):
        slug = str(fea_summary.parent.parent.relative_to(OUTPUTS)).replace("\\", "/")
        if slug not in found["fea_analysis"]:
            found["fea_analysis"].append(slug)
    return found


def _load_history() -> dict:
    h = _load_json(HISTORY_FILE)
    for k in CASE_PROFILES:
        h.setdefault(k, {})
    return h


def _save_history(history: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")


def harvest(slug: str, case_type: str | None = None) -> dict:
    """Extract and upsert one study's learning record (keyed by slug — re-harvesting
    an updated study replaces its old record, so re-runs correct prior data)."""
    ct = case_type or detect_case_type(slug)
    if ct is None:
        return {"skipped": f"no recognised case-type artifacts for study '{slug}'"}
    rec = CASE_PROFILES[ct]["record"](OUTPUTS / slug)
    if rec is None:
        return {"skipped": f"study '{slug}' has no completed run artifacts yet"}
    rec = {"slug": slug, "harvested": _dt.date.today().isoformat(), **rec}
    history = _load_history()
    history[ct][slug] = rec
    _save_history(history)
    return {"case_type": ct, **rec}


def harvest_all() -> dict:
    found = discover_studies()
    results: dict = {"harvested": {}, "skipped": []}
    for ct, slugs in found.items():
        for slug in slugs:
            rec = harvest(slug, case_type=ct)
            if "skipped" in rec:
                results["skipped"].append(slug)
            else:
                results["harvested"].setdefault(ct, []).append(slug)
    return results


# ─────────────────────────────── recommend ────────────────────────────────────

def recommend(case_type: str, query_features: dict, k: int = 5) -> dict:
    """Weighted-kNN recommendation: solver knobs from the k most similar past
    runs of this case type, weighted by (similarity * recorded quality).
    Confidence rises with the number of matching runs and their quality — this
    is the "gets better with every simulation" mechanism: there is no cap, no
    retraining step, and no stale model — every harvested study is live data
    the very next time recommend() is called."""
    history = _load_history().get(case_type, {})
    entries = list(history.values())
    if not entries:
        return {"confidence": 0.0, "n_history": 0,
                "note": f"no history yet for '{case_type}' — using skill defaults. "
                        "Recommendations unlock after the first harvested study."}

    all_keys = {key for e in entries for key in e["features"]}
    stds = {}
    for key in all_keys:
        vals = [e["features"][key] for e in entries if key in e["features"]]
        if len(vals) < 2:
            stds[key] = 1.0
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        stds[key] = math.sqrt(var) or 1.0

    scored = []
    for e in entries:
        shared = [key for key in query_features if key in e["features"]]
        if not shared:
            continue
        dist = math.sqrt(sum(((query_features[key] - e["features"][key]) / stds[key]) ** 2
                              for key in shared) / len(shared))
        weight = e["quality"] * math.exp(-dist)
        scored.append((weight, dist, e))

    if not scored:
        return {"confidence": 0.0, "n_history": len(entries),
                "note": f"{len(entries)} past '{case_type}' run(s) on file, but none share "
                        "a feature with this query — using skill defaults."}

    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:k]

    knob_keys = {key for _, _, e in top for key in e["knobs"]}
    recommended = {}
    for key in knob_keys:
        contributors = [(w, e["knobs"][key]) for w, _, e in top if key in e["knobs"]]
        if not contributors:
            continue
        wsum = sum(w for w, _ in contributors) or 1e-9
        recommended[key] = round(sum(w * v for w, v in contributors) / wsum, 6)

    avg_quality = sum(e["quality"] for _, _, e in top) / len(top)
    confidence = round(min(1.0, len(scored) / 5.0) * avg_quality, 3)

    return {
        "confidence": confidence,
        "n_history": len(entries),
        "n_matches": len(scored),
        "recommended_knobs": recommended,
        "nearest_examples": [
            {"slug": e["slug"], "distance": round(dist, 3), "quality": e["quality"]}
            for _, dist, e in top
        ],
    }
