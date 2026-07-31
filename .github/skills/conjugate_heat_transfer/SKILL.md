---
name: conjugate_heat_transfer
description: >
  Multi-region conjugate heat transfer simulation for heat exchangers and thermal
  assemblies: conduction in per-component solid regions, forced/buoyant convection in
  fluid regions (k-omega SST), and radiation (P1 or fvDOM participating media, grey
  surface-to-ambient on external walls). Builds and runs chtMultiRegionSimpleFoam
  (steady) or chtMultiRegionFoam (transient) cases from the step_assembly manifest,
  then extracts heat-exchanger KPIs: heat duty per stream, effectiveness, LMTD, UA,
  energy balance, interface heat fluxes. Use for heat exchanger performance, cold
  plates, exhaust heat recovery, enclosure cooling, any solid-fluid thermal coupling.
when_to_use: "Heat exchanger / conjugate heat transfer simulation; conduction+convection+radiation studies on a multi-part assembly; thermal duty, effectiveness, LMTD analysis."
authority: execute
cost_tier: 3
version: 0.1.0
---

# Conjugate Heat Transfer (chtMultiRegionFoam)

Consumes a completed `step_assembly` manifest (components typed, materials assigned,
BCs defined — run `assign_materials.py --validate` first) and drives the OpenFOAM
multi-region CHT toolchain inside WSL.

## Physics coverage

| Mechanism | Model |
| --- | --- |
| Conduction (solids) | heSolidThermo, constIso kappa per material |
| Convection (fluids) | buoyant compressible SIMPLE/PIMPLE, k-omega SST, wall functions |
| Convection to ambient | `externalWallHeatFluxTemperature` (h, T_amb) on external walls |
| Solid-fluid coupling | `turbulentTemperatureRadCoupledMixed` on `<A>_to_<B>` interfaces |
| Radiation, participating media | P1 (cheap, optically thick-ish exhaust/flue gas) or fvDOM (accurate, expensive) in fluid regions; per-patch emissivity from solid material / manifest |
| Radiation to ambient | emissivity on `convection` BCs (works with radiation model `none`) |

Radiation guidance: `none` for water/water HX (transparent liquids), `P1` when a hot
gas stream participates (CO2/H2O), `fvDOM` only when radiation dominates and P1
accuracy is in doubt. Radiation across a gas gap between two solids requires a
participating fluid region in the gap with P1/fvDOM active.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/setup_cht_case.py` | Mesh (or reuse) → gmshToFoam → splitMeshRegions → write all per-region fields, thermo, radiation, schemes, function objects |
| `scripts/run_cht_case.py` | Run solver in WSL-native storage (`--smoke` first!), reconstruct, foamToVTK -allRegions |
| `scripts/cht_kpis.py` | Heat duty per stream, effectiveness, LMTD, UA, imbalance, interface fluxes, T extremes |

## Standard sequence

```bash
python .github/skills/step_assembly/scripts/inspect_step.py --study hx --step CAD/hx.step
python .github/skills/step_assembly/scripts/assign_materials.py --study hx ... # + --validate
python .github/skills/conjugate_heat_transfer/scripts/setup_cht_case.py --study hx
python .github/skills/conjugate_heat_transfer/scripts/run_cht_case.py --study hx --smoke
python .github/skills/conjugate_heat_transfer/scripts/run_cht_case.py --study hx
python .github/skills/conjugate_heat_transfer/scripts/cht_kpis.py --study hx
```

Steady (`solver.mode: "steady"`, default) is right for HX rating/sizing; transient for
startup/thermal-shock. Post-process VTK output per region with the `post_processing`
skill (PyVista reads `case/VTK/<region>/...`).

## Sanity checks (never skip)

- Energy balance: |Q_hot| vs |Q_cold| imbalance < 5 % before quoting effectiveness;
  the KPI script warns otherwise (under-converged or under-resolved).
- Effectiveness must be in (0, 1); LMTD requires both terminal ΔT > 0 — a null LMTD
  means a temperature cross or an unconverged solution.
- All region temperatures must lie within [min inlet/ambient, max inlet] unless a
  heat_flux BC injects power.
- Interface heat fluxes on the two sides of the same interface should match within a
  few percent (reported per region in `interfaces_W`).
- Steady runs: check `final_residuals` in run_summary.json (h and p_rgh ≲ 1e-4).
- Mesh independence: repeat at `--mesh-factor` 1.3/1.0/0.72 and compare Q/effectiveness.
