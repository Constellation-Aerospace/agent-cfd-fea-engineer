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

## Space & high-altitude thermal (satellites, stratospheric balloons)

Two extra environment BC types (backed by `.tmp/scripts/atmosphere.py` — US Standard
Atmosphere 1976, solar/albedo/Earth-IR loads, sky sink temperatures):

| BC type | Regime | Physics |
| --- | --- | --- |
| `space_environment` | Orbit / vacuum | Pure radiation to an equivalent sink that folds absorbed solar+albedo+Earth-IR flux into the sink temperature (**exact**). Fields: `emissivity` (req), `absorbed_flux_W_m2`, `sink_T_C` |
| `altitude_environment` | 0–86 km | Rarefied natural convection to US76 air temperature (h estimated from a Churchill sphere correlation with rho² collapse, or given via `h_W_m2K`) + radiation to the sky sink, folded into a single film — exact at `T_surface_est_C` (default air+20 K). Fields: `altitude_m`, `emissivity` (req), `absorbed_flux_W_m2`, `L_char_m` |

Workflow: `scripts/environment.py --altitude 30000 --emissivity 0.9 ...` (add `--orbit`
for vacuum, `--no-sun` for eclipse) prints the environment state, ready-to-paste
`bc_json`, and — for balloons — the full-CFD route (model the surrounding air as a
fluid component with `air_at_altitude()` overrides + `solver.p_ref_Pa` = ambient
pressure, so rarefied natural convection is resolved rather than estimated).
Satellite assemblies are **solid-only** (no fluid regions): conduction through
contacts + radiation at surfaces; `external_W` in the KPIs reports per-surface
radiator rejection. Spacecraft materials in the library: `mli_effective`, `fr4_pcb`,
`aluminum_honeycomb_panel`, `white_paint_aluminum` (α_s≈0.2), `black_anodized_aluminum`
(α_s≈0.86).

Limitations (state in reports): internal cavity radiation between solids needs a
transparent fluid region + fvDOM (or stays conduction-only); orbital fluxes are
scoping-grade averages (`solar_projection` = A_proj/A_total), not orbit-propagated;
run sunlit **and** eclipse cases to bound hot/cold.

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

## Gotchas

- **Solid-only assemblies (no fluid regions) always use a fixed transient step,
  never `adjustTimeStep`.** `setMultiRegionDeltaT` needs a Courant number from a
  fluid region to scale against; with none present the step collapses toward zero
  (measured: 8144 steps to reach 1.8e-6 s). `deltaT_s` is mandatory for a solid-only
  `solver.mode: "transient"` study — pick it directly, don't rely on `max_co`/`max_di`.
  Corollary: `run_cht_case.py --smoke`'s hard-coded 0.5 s window silently produces
  `n_steps: 0` if your fixed `deltaT_s` is larger than 0.5 s — use an explicit
  `--end-time` that's a multiple of `deltaT_s` instead for solid-only smoke tests.
- **A `FOAM FATAL ERROR`-free, silent death right after the per-region "Diffusion
  Number" printout, before any `Time = ` line, at `n_steps: 0`** is a `FOAM_SIGFPE`
  trap firing on a degenerate cell (near-zero volume from an unresolvable CAD sliver
  face), not a real divergence — solid conduction under implicit Euler is
  unconditionally stable regardless of how large the reported diffusion number is.
  Confirm by re-running the same case in WSL with `FOAM_SIGFPE=false` exported before
  `mpirun`; if it then completes cleanly and the KPIs stay physical (heat source
  integrates to the injected wattage, adiabatic walls read 0.0 W), opt the study in
  via manifest `solver.disable_fpe_trap: true` rather than re-meshing — coarsening or
  refining the global mesh size does not remove a fixed-size CAD topology artifact
  (confirmed: identical high-aspect-ratio cell count/ratio at `--factor` 1.0 and 1.3).
  Default is unchanged (trap stays on) for every study that doesn't set the flag.
- **`cht_kpis.py` region T_min/T_max used to silently pick a mid-run segment, not
  the final one, on any staged/restarted transient.** `_find_fo_files()` sorted
  `postProcessing/**/<startTime>/<file>` paths as plain strings; for a run staged
  in 300 s segments (`0,300,600,900,1200,...,2400`), `"900" > "2100"` lexically, so
  the KPI script quietly reported the 900→1200 s segment's numbers as if they were
  the run's final state. Fixed by sorting on the numeric `<startTime>` instead —
  confirmed against `transient_history.py`'s independently-aggregated CSV (which
  was never affected; it de-dupes by numeric time already). Re-run `cht_kpis.py`
  after any multi-segment transient if you suspect stale numbers from before this
  fix.
- **Thermal contact resistances are opt-in, not automatic.** A coupled `<A>_to_<B>`
  interface (`turbulentTemperatureRadCoupledMixed`) assumes perfect contact unless
  the manifest's top-level `thermal_contact_resistances` (hand-edited — no CLI flag
  yet) names that pair with `R_total_K_per_W` + `area_m2`; `cht_case.py` then adds
  `thicknessLayers (0.001)` / `kappaLayers (<computed>)` to both sides of that patch
  (`kappa = thickness / (R_total * area)`). Omitting a joint from that block silently
  models it as perfectly bonded — decide per joint, don't assume the doc's contact
  resistance table is applied just because it's transcribed into the manifest.
