#!/usr/bin/env python3
"""Assemble the final technical report (Markdown + self-contained HTML) for a study.

Example:
    python build_report.py --study baseline --title "Submerged Exhaust CFD Study"
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / ".tmp" / "scripts"))

from study_pipeline import study_dir, load_params  # noqa: E402


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def table(d: dict, headers=("Quantity", "Value")) -> str:
    lines = [f"| {headers[0]} | {headers[1]} |", "| --- | --- |"]
    for k, v in d.items():
        lines.append(f"| {k} | {v} |")
    return "\n".join(lines)


def fig_block(fig_dir: Path, names: list[str]) -> str:
    out = []
    for name in names:
        p = fig_dir / name
        if p.exists():
            out.append(f"![{name}](../figures/{name})\n")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--study", required=True)
    ap.add_argument("--title", default="Submerged Marine Exhaust Discharge — CFD/FEA Investigation")
    ap.add_argument("--author", default="agent-cfd-fea-engineer")
    args = ap.parse_args()

    d = study_dir(args.study)
    cfg = load_params(args.study)
    geo = cfg.get("geometry", {})
    prep = load_json(d / "prepare_summary.json")
    run = load_json(d / "run_summary.json")
    kpis = load_json(d / "kpis.json")
    mesh_ind = load_json(d / "mesh_independence.json")
    fea = load_json(d / "fea" / "fea_summary.json")
    parametric = load_json(d / "parametric_results.json") or []
    decay = load_json(d / "figures" / "decay_metrics.json")
    fig_dir = d / "figures"

    # step_assembly / conjugate_heat_transfer studies (multi-region solid conduction,
    # e.g. cold plates, heat exchangers, balloon payloads) have an entirely different
    # solver, physics and boundary-condition set from the marine-exhaust multiphase CFD
    # study this template was originally written for. Detect that case from the
    # per-component assembly manifest and branch the narrative sections accordingly —
    # otherwise every CHT report describes compressibleInterFoam/pipe geometry that was
    # never run. See self-annealing lesson L007.
    cht_manifest = load_json(d / "case" / "cht_manifest.json")
    cht_kpis = load_json(d / "cht_kpis.json")
    is_cht = bool(cht_manifest.get("components"))

    if is_cht:
        components = cht_manifest.get("components", {})
        patches = cht_manifest.get("patches", {})
        solver = cht_manifest.get("solver", {})
        tcr = cht_manifest.get("thermal_contact_resistances", {})
        step_file = cht_manifest.get("step_file", "-")

        comp_rows = {name: comp.get("material", "-") for name, comp in components.items()}
        bc_rows = {}
        for patch, spec in patches.items():
            bc = spec.get("bc", {})
            comp = spec.get("component", "-")
            bc_rows[f"`{patch}` ({comp})"] = bc.get("description") or bc.get("type", "-")

        mode = solver.get("mode", "-")
        end_time = solver.get("end_time_s")
        problem_statement = (
            f"Conjugate heat transfer analysis of a {len(components)}-component solid "
            f"assembly: coupled conduction across all components, with convection and/or "
            f"radiation applied at the external boundaries listed in Section 3.2. "
            f"Solved in `{mode}` mode"
            + (f" to {end_time} s" if mode == "transient" and end_time else "") + "."
        )
        methodology_extra = ""
        if tcr:
            methodology_extra = ("\n### 3.3 Thermal Contact Resistances\n\n" +
                table({k: f"{v} K/W" if not isinstance(v, dict) else json.dumps(v)
                       for k, v in tcr.items()}, ("Joint", "R_total")))

        md = [f"""# {args.title}

**Study:** `{args.study}` · **Date:** {dt.date.today().isoformat()} · **Prepared by:** {args.author}

## 1. Executive Summary

_TODO (agent): summarise the headline findings — peak component temperatures and
margin, heat rejection at end of run, whether the assembly reached steady state,
and any assumptions baked into the boundary conditions — in 5-8 sentences._

## 2. Problem Statement

{problem_statement}

Source CAD: `{step_file}`, {len(components)} solid components.

## 3. Methodology

| Item | Model |
| --- | --- |
| Solver | OpenFOAM v2412 `chtMultiRegionFoam`/`chtMultiRegionSimpleFoam` (multi-region solid conduction) |
| Regions | {len(components)} solid regions, one per assembly component, conformally meshed and coupled at contact interfaces |
| Mode | {mode}{f", deltaT = {solver.get('deltaT_s')} s, end time = {end_time} s" if mode == "transient" else ""} |

### 3.1 Component Materials

{table(comp_rows, ("Component", "Material"))}

### 3.2 Boundary Conditions

{table(bc_rows, ("Patch (component)", "BC"))}
{methodology_extra}

## 4. Geometry & Domain

{len(components)}-solid assembly imported from the source CAD above and boolean-fragmented
so contact faces are imprinted and conformal across every part-to-part interface.

## 5. Mesh
"""]
    else:
        md = [f"""# {args.title}

**Study:** `{args.study}` · **Date:** {dt.date.today().isoformat()} · **Prepared by:** {args.author}

## 1. Executive Summary

_TODO (agent): summarise the headline findings — back-pressure margin, thermal decay
distance, plume behaviour, structural adequacy — in 5-8 sentences._

## 2. Problem Statement

CFD investigation of a submerged marine exhaust discharge system under representative
marine conditions: multiphase gas-liquid interaction, thermal mixing and temperature
decay, pressure distribution and exhaust back-pressure, flow field development and
turbulence characteristics, with comparative assessment under varying operating
parameters.

## 3. Methodology

| Item | Model |
| --- | --- |
| Solver | OpenFOAM v2412 `compressibleInterFoam` (transient, compressible VOF) |
| Multiphase | Volume of Fluid (MULES interface compression, cAlpha=1) |
| Turbulence | k-omega SST with standard wall functions |
| Exhaust gas | Frozen N2/CO2/H2O/O2 ideal-gas mixture, JANAF cp(T), Sutherland viscosity |
| Water | Constant density {cfg.get('rho_water', 1025)} kg/m3, constant cp/mu |
| Gravity | 9.81 m/s2, hydrostatic pressure via p_rgh formulation |
| Energy | Sensible internal energy, thermal mixing resolved |

### 3.1 Operating Conditions

{table({
    "Exhaust inlet velocity": f"{cfg.get('U_in')} m/s",
    "Exhaust temperature": f"{cfg.get('T_exhaust_C')} C",
    "Ambient water temperature": f"{cfg.get('T_water_C')} C",
    "Turbulence intensity (inlet)": cfg.get('turbulence_intensity'),
    "Atmospheric pressure": f"{cfg.get('p_atm')} Pa",
    "Simulated physical time": f"{run.get('final_time_s', '-')} s",
})}

### 3.2 Boundary Conditions

| Patch | Type |
| --- | --- |
| inlet | Velocity inlet, fixed T, turbulence intensity {cfg.get('turbulence_intensity')} |
| atmosphere | Total-pressure outlet (atmospheric), backflow-tolerant |
| pipeWall / seaBoundary | No-slip walls; thermal BC adiabatic (to be finalised) |
| Initial field | Water column below z=0 (hydrostatic), gas-filled exhaust pipe at exhaust T |

## 4. Geometry & Domain

{table({
    "Pipe bore diameter": f"{geo.get('pipe_diameter', 0.3)} m",
    "Pipe wall thickness": f"{geo.get('wall_thickness', 0.012)} m",
    "Submergence (axis below surface)": f"{geo.get('submergence', 2.0)} m",
    "Domain (L x W)": f"{geo.get('domain_length', 10)} x {geo.get('domain_width', 6)} m",
    "Water depth / air layer": f"{geo.get('water_depth', 5)} / {geo.get('air_height', 1)} m",
})}

> Geometry is a representative parametric model; confidential CAD will replace it after
> NDA execution without changes to the downstream pipeline.

## 5. Mesh
"""]

    check = prep.get("checkMesh", {})
    if check:
        md.append(table({
            "Cells": check.get("cells"),
            "Max non-orthogonality": check.get("max_non_ortho"),
            "Avg non-orthogonality": check.get("avg_non_ortho"),
            "Max skewness": check.get("max_skewness"),
            "checkMesh": "OK" if check.get("ok") else "WARNINGS — see log",
        }))

    if mesh_ind:
        md.append("\n### 5.1 Mesh Independence (GCI)\n")
        levels = mesh_ind.get("levels", [])
        if levels:
            heads = ["level", "cells", "back_pressure_gauge_Pa", "T_max_axis_K",
                     "thermal_decay_length_10pct_m"]
            md.append("| " + " | ".join(heads) + " |")
            md.append("|" + " --- |" * len(heads))
            for r in levels:
                md.append("| " + " | ".join(str(r.get(h, "-")) for h in heads) + " |")
        for key, g in mesh_ind.get("gci", {}).items():
            md.append(f"\n- **{key}**: observed order p = {g.get('order_p')}, "
                      f"GCI_fine = {g.get('gci_fine_pct')}%, "
                      f"medium vs fine drift = {g.get('medium_vs_fine_pct', '-')}%")

    md.append("\n## 6. Results\n")
    if is_cht:
        if cht_kpis:
            regions = cht_kpis.get("regions", {})
            if regions:
                md.append("### 6.1 Component Temperatures (min/max at final time)\n")
                md.append(table({name: f"{r.get('T_min_C', '-')} to {r.get('T_max_C', '-')} C"
                                  for name, r in regions.items()}, ("Component", "T range")))
            ext = cht_kpis.get("external_W", {})
            if ext:
                md.append("\n### 6.2 External Heat Flows (final time)\n")
                md.append(table({k: f"{v} W" for k, v in ext.items()}, ("Patch", "Q")))
            streams = cht_kpis.get("streams", {})
            if streams:
                md.append("\n### 6.3 Stream KPIs\n")
                md.append(table(streams, ("Stream", "Value")))
        md.append("\n### 6.4 Figures\n")
        md.append(fig_block(fig_dir, [f.name for f in sorted(fig_dir.glob("*.png"))]))
    else:
        if kpis:
            md.append("### 6.1 Headline KPIs\n")
            md.append(table({k: v for k, v in kpis.items() if k != "study"}, ("KPI", "Value")))
        md.append("\n### 6.2 Flow Field\n")
        md.append(fig_block(fig_dir, [f.name for f in sorted(fig_dir.glob("slice_*.png"))]
                            + [f.name for f in sorted(fig_dir.glob("streamlines_*.png"))]))
        md.append("### 6.3 Temperature Decay\n")
        md.append(fig_block(fig_dir, ["temperature_decay.png", "plume_rise.png"]))
        if decay:
            md.append(table({t: json.dumps(v) for t, v in decay.items()}, ("Time", "Metrics")))
        md.append("\n### 6.4 Exhaust Back-Pressure\n")
        md.append(fig_block(fig_dir, ["back_pressure.png"]))

    if fea:
        md.append("\n## 7. FEA — Pipe Wall Thermal-Structural\n")
        md.append(table({
            "Max von Mises stress": f"{fea.get('max_von_mises_MPa', '-')} MPa",
            "Max displacement": f"{fea.get('max_displacement_mm', '-')} mm",
            "Wall temperature range": f"{fea.get('T_min_C', '-')} to {fea.get('T_max_C', '-')} C",
            "Mesh": f"{fea.get('mesh', {}).get('n_elements', '-')} C3D10 elements",
        }))

    if parametric:
        md.append("\n## 8. Parametric Comparison\n")
        ok = [r for r in parametric if "error" not in r]
        if ok:
            heads = list(ok[0].keys())
            md.append("| " + " | ".join(heads) + " |")
            md.append("|" + " --- |" * len(heads))
            for r in ok:
                md.append("| " + " | ".join(str(r.get(h, "-")) for h in heads) + " |")
        md.append(fig_block(fig_dir, ["parametric_trends.png"]))

    if is_cht:
        md.append("""
## 9. Validation Methodology

- **Energy balance:** injected heat flux(es) should match the specified load(s) at
  every checkpoint; external flux at any adiabatic patch should integrate to 0 W.
- **Interface balance:** each coupled component-to-component interface should agree
  between the two sides reporting it, within a few percent.
- **Restart continuity** (transient studies only): no temperature discontinuity at a
  segment restart boundary greater than ~1 K.
- **Physical plausibility:** no region colder than the coldest applicable sink
  temperature or implausibly hot given the load and materials.
- **Not performed unless noted above:** mesh independence; benchmark against measured
  hardware data.
- _TODO (agent): confirm each of the above against this study's actual `cht_kpis.json`
  and restart logs, and note this study's specific assumptions/limitations here._

## 10. Conclusions & Recommendations

_TODO (agent): fill from the results above._
""")
    else:
        md.append("""
## 9. Validation Methodology

- **Mesh independence:** 3-level refinement with Grid Convergence Index (Section 5.1).
- **Physical plausibility checks:** back-pressure vs. hydrostatic + dynamic head estimate;
  jet centreline decay vs. classical turbulent jet correlations (T ~ 1/x far field);
  global mass/energy balance from solver logs.
- **Benchmark path:** validation against published submerged buoyant jet experiments
  (e.g. turbulent buoyant jet temperature decay data) recommended before design sign-off.
- **Limitations:** representative geometry (pre-NDA); frozen exhaust composition
  (no condensation/dissolution); constant water properties; adiabatic walls pending
  thermal BC definition; RANS turbulence (no LES of interface breakup).

## 10. Conclusions & Recommendations

_TODO (agent): fill from the results above._
""")

    report_dir = d / "report"
    report_dir.mkdir(exist_ok=True)
    md_text = "\n".join(md)
    (report_dir / "report.md").write_text(md_text, encoding="utf-8")

    # self-contained HTML with figures embedded as data URIs
    try:
        import markdown as md_lib
        html_body = md_lib.markdown(md_text, extensions=["tables"])
    except ImportError:
        html_body = "<pre>" + md_text.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
    for fig in fig_dir.glob("*.png"):
        rel = f"../figures/{fig.name}"
        if rel in html_body:
            b64 = base64.b64encode(fig.read_bytes()).decode()
            html_body = html_body.replace(rel, f"data:image/png;base64,{b64}")
    html = ("<!doctype html><html><head><meta charset='utf-8'><title>" + args.title +
            "</title><style>body{font-family:Segoe UI,Arial,sans-serif;max-width:960px;"
            "margin:2em auto;padding:0 1em;line-height:1.5}table{border-collapse:collapse}"
            "td,th{border:1px solid #ccc;padding:4px 10px}img{max-width:100%}</style>"
            "</head><body>" + html_body + "</body></html>")
    (report_dir / "report.html").write_text(html, encoding="utf-8")

    print(f"Report written:\n  {report_dir / 'report.md'}\n  {report_dir / 'report.html'}")
    print("\nNOTE: fill the Executive Summary and Conclusions sections (marked TODO).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
