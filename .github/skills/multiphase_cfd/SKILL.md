---
name: multiphase_cfd
description: >
  Multiphase CFD simulation of the submerged exhaust discharge: transient compressible
  VOF (compressibleInterFoam), ideal-gas multi-component exhaust mixture (N2/CO2/H2O/O2,
  JANAF cp(T)), constant-density seawater, k-omega SST turbulence, gravity + hydrostatic
  pressure, thermal mixing. Sets up and runs OpenFOAM cases in WSL. Use for "run the CFD",
  "set up the simulation", "change inlet velocity/temperature", "multiphase simulation".
when_to_use: "Setting up or running the multiphase CFD simulation; changing operating conditions."
authority: execute
cost_tier: 3
version: 0.1.0
---

# Multiphase CFD (OpenFOAM compressibleInterFoam)

Physics per the study requirement:

| Requirement | Implementation |
| --- | --- |
| Multiphase gas-liquid interaction | VOF (MULES), `compressibleInterFoam`, surface tension 0.07 N/m |
| Exhaust gas | Frozen N2/CO2/H2O/O2 ideal-gas mixture, JANAF cp(T), Sutherland viscosity |
| Ambient water | Constant density 1025 kg/m3, const cp/mu (T-dependence at refinement stage) |
| Thermal mixing / temperature decay | Energy equation + line samples along jet axis & plume rise |
| Back-pressure | Area-averaged inlet pressure function object every 10 steps |
| Turbulence | k-omega SST with wall functions, inlet intensity 5% (configurable) |
| Gravity / hydrostatic | g = -9.81 z, p_rgh formulation, water column via setFields |

## Operating window (configurable)

`U_in` 10-25 m/s, `T_exhaust_C` 300-550 °C, `T_water_C`, `submergence` (geometry),
`turbulence_intensity`, `end_time_s`, `n_procs`.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/setup_case.py` | Geometry + mesh + full case write + gmshToFoam + checkMesh + setFields |
| `scripts/run_case.py` | decomposePar -> mpirun compressibleInterFoam -> reconstruct -> foamToVTK |

## Usage

```bash
python .github/skills/multiphase_cfd/scripts/setup_case.py --study baseline \
    --config '{"U_in": 15, "T_exhaust_C": 400, "end_time_s": 4.0}'
python .github/skills/multiphase_cfd/scripts/run_case.py --study baseline --np 6
# quick smoke run:
python .github/skills/multiphase_cfd/scripts/run_case.py --study baseline --end-time 0.2
```

Transient VOF on ~0.5-1M cells takes hours; use `--end-time` for short scoping runs
and always report progress from `outputs/<study>/run_summary.json`.

## Outputs

`outputs/<study>/case/` (OpenFOAM case + logs + postProcessing/), `run_summary.json`,
`case/VTK/` for post-processing.

## Learnings

- 2026-07-30: `compressibleInterFoam` crashed in `twoPhaseMixtureThermo::correctThermo()`
  at t≈0.2 s on a coarse (31k-cell) mesh once plume breakup became violent — JANAF
  temperature-bounds excursion. NOTE: `limitTemperature` fvOption does NOT work here —
  `twoPhaseMixtureThermo::he()` is "Not implemented" in OpenFOAM 2412, so the solver
  aborts at startup. Working mitigation: tighter `maxCo/maxAlphaCo` (0.5), smaller
  `maxDeltaT` (0.005), finer mesh in the breakup zone. The finer 381k-cell case
  survived without any guard.
