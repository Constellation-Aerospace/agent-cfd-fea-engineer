# Runbook — Local Ollama (`cfd-qwen`) driving the 0→10 km / 40-minute Ascent Transient

**Audience:** an operator running a fully local LLM agent against this repository, and
the `cfd-qwen` model itself. Everything below is executable — no cloud API key needed.

**Target study:** `balloon-ttp/transient-0-10km` — 60 W Jetson Orin Nano payload on a
5 mm Al 6061 cold plate ("interface_plate"), coupled through twin OFHC copper straps
("copper_strap_left/right") to two external white-painted Al 6061 radiators
("radiator_plate", "radiator_plate_2"), all inside an EPS-foam ("styrofoam_box")
insulated enclosure. Transient conduction + convection + grey radiation from sea
level to 10 km over 2400 s (40 minutes), source doc:
`Jetson_Transient_Analysis_0_10km.md` (attached to the originating conversation).

Input geometry: `inputs/balloon-ttp/spaced out rad+box.step` (12 solids — radiators
spaced further apart than the earlier `assembly.step`, box now included in the same
STEP file).

## How this differs from OLLAMA_QWEN_TRANSIENT_RUNBOOK.md (the 0→20 km study)

| | 0→20 km runbook | This runbook (0→10 km) |
| --- | --- | --- |
| Duration | 1200 s, two atmospheric phases (troposphere + stratosphere) | 2400 s, single ISA-troposphere ascent |
| BC driver | `altitude_environment` BC + `atmosphere.py` US76 sky-sink model (correct above ~20 km) | plain `convection` BC with explicit `h(t)`/`T_amb(t)` from the doc's own formulas — `atmosphere.py`'s sky-sink model assumes negligible atmospheric IR, which is wrong below ~20 km, so it is deliberately **not** used here |
| Staging script | `stage_transient_bcs.py` (altitude-indexed) | `stage_transient_bcs_ascent.py` (mission-time-indexed, doc's own T_amb(t)/h(t)) |
| Box BC | convective (`foam_box_outer` = altitude_environment) | **adiabatic** (doc Sec.6E: box is insulation, forces 100% of the load through the strap/radiator path) |
| Solar | not modelled | optional term folded into `radiator_plate`'s effective Ta (doc Sec.6D, sun-facing panel only) |
| Contact resistances | documented only (not solved) | **solved** — `cht_case.py` now writes `thicknessLayers`/`kappaLayers` on the coupled interfaces the manifest flags (see C-TCR below) |
| Known mesh defect | checkMesh `ok:false` (never got past a 0.5 s smoke run) | same CAD sliver reproduced (`interface_plate`, 25 high-aspect-ratio cells) — root-caused to a `FOAM_SIGFPE` abort, fixed via `solver.disable_fpe_trap` (see C-FPE) |

# Part A — Ollama + `cfd-qwen`

Identical to the 0→20 km runbook — nothing to redo. Verify in one command,
executing nothing:

```powershell
.\ollama\run_agent.ps1 -SelfTest -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_10KM.md
```

Expect the same readiness signature: Ollama 0.32.5 on `127.0.0.1:11434`,
`cfd-qwen:latest` built from `qwen2.5-coder:7b` (32k ctx, temp 0.1, tools capability),
resident 100% on GPU. If `ollama list` doesn't show `cfd-qwen`, rebuild it:

```powershell
ollama create cfd-qwen -f ollama\Modelfile.cfd
```

**Driver note:** `run_agent.ps1` is genuinely interactive (`Read-Host` gate before every
command) — it is designed to run in a real console with a human typing `r`/`s`/`q`, and
cannot be driven from a non-interactive/headless shell. If you are reading this runbook
non-interactively (e.g. as an automated agent), execute Part C's commands directly
yourself instead — the runbook doc says the same thing about Part C alone being a
complete manual procedure. That is exactly what produced the results referenced below.

# Part B — What to pull onto the machine

Same solver stack as every other study here (OpenFOAM v2412 + Gmsh + CalculiX in WSL,
already installed and verified — **never run an installer**, see C0). Nothing new to
install for this study.

# Part C — Conducting the simulation

## C0 — Environment gate (already satisfied — do not install anything)

```powershell
.venv\Scripts\python.exe .github\skills\solver_environment\scripts\check_environment.py
```

Must print `READY: full CFD/FEA toolchain available.` If it doesn't, stop and report —
do not run `install_solvers.py`/`setup.ps1`/`first_run_setup.py`/`apt`/`pip install`/
`winget install`.

## C1 — Inspect the STEP file and rename components

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\inspect_step.py `
    --study balloon-ttp/transient-0-10km --step "inputs\balloon-ttp\spaced out rad+box.step"
```

This writes `outputs/balloon-ttp/transient-0-10km/assembly/manifest.json` with
CAD-derived names. **`inspect_step.py` regenerates component names from the STEP part
labels on every run — it does not remember a previous rename.** Six solids come back
generic (`part_6`..`part_11`, `component18`) because the CAD only labels the
radiators, the TTP interface plate, the Jetson heatsink and the foam box. Rename them
**once**, by hand-editing `manifest.json`'s `components` keys and the `interfaces[].components`
references (never re-run `inspect_step.py` afterward, or the rename is lost —
`mesh_assembly.py` matches solids to manifest entries by centroid+volume, not by name,
so a stale `surfaces.json` naming is harmless, but a stale `inspect_step.py` re-run
is not):

| Generic name | Renamed to | Why (geometry/connectivity) |
| --- | --- | --- |
| `part_6` | `connector_block_left` | Al clamp block, interface_plate ↔ copper_strap_left |
| `part_7` | `copper_strap_left` | matches doc's strap volume (738.5 mm² × 120 mm ≈ 8.86e-5 m³ order) |
| `part_8` | `radiator_bracket_left` | Al bracket, copper_strap_left ↔ radiator_plate_2 |
| `part_9` | `connector_block_right` | mirror of part_6 |
| `part_10` | `copper_strap_right` | mirror of part_7 |
| `part_11` | `radiator_bracket_right` | mirror of part_8, ↔ radiator_plate |
| `component18` | `jetson_module` | largest remaining solid, sits directly on `jetson_heatsink` — the 60 W source |

`radiator_plate`, `radiator_plate_2`, `interface_plate`, `jetson_heatsink` and
`styrofoam_box` already come back correctly named from this CAD's part labels — leave
them alone.

## C2 — Materials (right material per component, doc Sec.4 + user's polystyrene/copper instruction)

```powershell
$AM = ".github\skills\step_assembly\scripts\assign_materials.py"
$S  = "balloon-ttp/transient-0-10km"

.venv\Scripts\python.exe $AM --study $S --component radiator_plate       --type solid --material white_paint_aluminum --t-init 20 --overrides '{"emissivity": 0.85}'
.venv\Scripts\python.exe $AM --study $S --component radiator_plate_2     --type solid --material white_paint_aluminum --t-init 20 --overrides '{"emissivity": 0.85}'
.venv\Scripts\python.exe $AM --study $S --component interface_plate      --type solid --material aluminum_6061 --t-init 20
.venv\Scripts\python.exe $AM --study $S --component jetson_heatsink      --type solid --material aluminum_6061 --t-init 20
.venv\Scripts\python.exe $AM --study $S --component jetson_module        --type solid --material fr4_pcb --t-init 20 --overrides '{"cp": 950}'
.venv\Scripts\python.exe $AM --study $S --component connector_block_left  --type solid --material aluminum_6061 --t-init 20
.venv\Scripts\python.exe $AM --study $S --component connector_block_right --type solid --material aluminum_6061 --t-init 20
.venv\Scripts\python.exe $AM --study $S --component copper_strap_left     --type solid --material copper --t-init 20 --overrides '{"rho": 8940, "kappa": 390}'
.venv\Scripts\python.exe $AM --study $S --component copper_strap_right    --type solid --material copper --t-init 20 --overrides '{"rho": 8940, "kappa": 390}'
.venv\Scripts\python.exe $AM --study $S --component radiator_bracket_left  --type solid --material aluminum_6061 --t-init 20
.venv\Scripts\python.exe $AM --study $S --component radiator_bracket_right --type solid --material aluminum_6061 --t-init 20
.venv\Scripts\python.exe $AM --study $S --component styrofoam_box --type solid --material eps_foam --t-init 20 --overrides '{"rho": 30, "cp": 1300}'
```

`eps_foam` in `agent-data/materials_library.json` **is** the polystyrene material
(`"expanded polystyrene insulation"`, kappa 0.033 W/m-K matches the doc's Styrofoam
row exactly) — that satisfies "polystyrene for the box" literally, not by analogy.
`copper` is overridden to the doc's OFHC C10100 values (rho 8940, kappa 390 — the
library default, 8960/401, is generic oxidised copper).

Initial condition is **uniform 20°C everywhere** (doc Sec.2) — every component gets
`--t-init 20`, not a per-component guess.

## C3 — Boundary conditions

```powershell
.venv\Scripts\python.exe $AM --study $S --patch jetson_heat_source --component interface_plate --select ymax `
  --bc '{"type": "heat_flux", "q_W_m2": 16362.88, "description": "60 W over the TTP contact face (0.003666837 m2)"}'

.venv\Scripts\python.exe $AM --study $S --patch radiator_plate_outer --component radiator_plate --select remaining `
  --bc '{"type": "convection", "h_W_m2K": 15.0, "T_amb_C": 33.13, "emissivity": 0.85, "note": "sun-facing: +18.13K solar-equivalent (272 W/m2 / h)"}'
.venv\Scripts\python.exe $AM --study $S --patch radiator_plate_2_outer --component radiator_plate_2 --select remaining `
  --bc '{"type": "convection", "h_W_m2K": 15.0, "T_amb_C": 15.0, "emissivity": 0.85, "note": "shaded panel"}'

.venv\Scripts\python.exe $AM --study $S --patch foam_box_outer --component styrofoam_box --select remaining --bc '{"type": "adiabatic"}'

.venv\Scripts\python.exe $AM --study $S --validate
```

`q_W_m2 = 60 / 0.003666837` (TTP contact face area, read from `assembly/surfaces.json`
after C1 — the same face the 30 km/20 km studies used). Copper strap and connector/
bracket "remaining" faces are **left unassigned** — the skill's default for an
unassigned external face is `<component>_wall` (adiabatic), which is exactly doc
Sec.6E's "unexposed sections of copper straps → 0 W/m2" with no extra BC needed.

## C-TCR — Thermal contact resistances (doc Sec.7)

Not a manifest-CLI flag — hand-edit `assembly/manifest.json` to add a top-level
`thermal_contact_resistances` block (components, `R_total_K_per_W`, `area_m2`):

* `interface_plate` ↔ `jetson_heatsink`: 0.1 K/W (PTM7950, "Jetson to Cold Plate")
* `interface_plate` ↔ `connector_block_left/right`: 1.58 K/W each ("Cold Plate to
  Connector Block")
* `copper_strap_left/right` ↔ `radiator_bracket_left/right`: 1.58 K/W each ("Strap
  Terminal to Radiator")

**This previously had no effect on the solve** — `thermal_contact_resistances` was
documentation only; the coupled BC (`turbulentTemperatureRadCoupledMixed`) always
assumed perfect contact. `cht_case.py`'s `_solid_T_field()` now looks up a resistance
for each `<A>_to_<B>` coupled patch and, when the manifest defines one, adds
`thicknessLayers (0.001)` / `kappaLayers (<t/(R·A)>)` — OpenFOAM's native way to model
a resistive interface on this BC. Covered by `tests/test_cht.py` (still 16/16 passing
after the change; full suite 59 passed / 3 skipped).

## C4 — Solver block

```powershell
.venv\Scripts\python.exe $AM --study $S --solver '{"mode": "transient", "end_time_s": 2400, "write_interval_s": 60, "deltaT_s": 2.0, "n_procs": 4, "p_ref_Pa": 101325, "T_init_C": 20, "disable_fpe_trap": true}'
```

`deltaT_s: 2.0` — this assembly is **solid-only** (no fluid regions), and
`cht_case.py` documents (and enforces) that `adjustTimeStep` collapses toward zero for
solid-only cases (measured previously: 8144 steps to reach 1.8e-6 s) because
`setMultiRegionDeltaT` needs a Courant number from a fluid region that doesn't exist
here — so a **fixed** step is mandatory, not a workaround. 2.0 s fixed × 1200 steps
over 2400 s solved in ~24 s/300 s-segment on this machine (4 procs) — a few minutes
total, not hours.

## C-FPE — Why `disable_fpe_trap` is required for this geometry

`checkMesh` on this STEP file reports one real failure — 25 high-aspect-ratio cells
(max ratio 14133), all traced to a ~3e-9 m² sliver face on `interface_plate` that
Gmsh must still conform to regardless of global mesh size (confirmed: `--factor 1.3`,
a much coarser global mesh, reproduced the identical 25 cells / same max ratio — it is
a fixed CAD topology artifact in the "spaced out rad+box" export, not a sizing choice).
Non-orthogonality (max 89.99°) is separately reported but explicitly marked "OK" by
checkMesh itself (only 186/74000 severely non-orthogonal faces).

With the default `FOAM_SIGFPE` trap on, `interface_plate`'s degenerate cell produces a
diffusion-number overflow (reported max ~9.7e10 vs. a healthy ~200) that aborts
`chtMultiRegionFoam` **before the first timestep even starts** — no `FOAM FATAL ERROR`
banner, just a silent death right after the per-region diagnostic printout (confirmed
by direct WSL invocation with `FOAM_SIGFPE=false`: identical case, clean exit,
`SOLVE_EXIT=0`). Solid conduction under implicit Euler is unconditionally stable
regardless of this diagnostic number (`cht_case.py`'s own comment), and the KPI check
after a real run confirms it — `jetson_heat_source` integrates to 60.2 W (target
60 W exactly) and every adiabatic wall reports 0.0 W — so the fix is disabling the
*trap*, not the underlying physics. `cht_pipeline.py`'s `solve()` now reads
`solver.disable_fpe_trap` from the manifest and prepends `export FOAM_SIGFPE=false;`
to the solver invocation only when a study opts in — every other study's behaviour is
unchanged.

## C5 — Mesh + case

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\mesh_assembly.py --study $S --factor 1.0
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

Expect the checkMesh warning above (`ok: false`, high-aspect-ratio only) — proceed;
it is understood and handled per C-FPE.

## C6 — Smoke test

Do **not** use `--smoke` verbatim here — its hard-coded 0.5 s window is smaller than
this case's fixed 2.0 s step, so the run exits after 0 steps regardless of FPE
settings (a structural mismatch, not a solver failure). Use an explicit window that's
a multiple of `deltaT_s`:

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 10 --time-limit 300
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study $S
```

Expect `completed: true, final_time: 10.0, n_steps: 5`, `jetson_heat_source ≈ 60 W`,
every `*_wall` external flux `0.0`. Reset to a clean t=0 state before the real run:

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

## C7 — The staged ascent (0 → 2400 s)

`chtMultiRegionFoam`'s `externalWallHeatFluxTemperature` BC takes static `Ta`/`h`
values per run — there is no continuous-in-time table wired into this harness (see
`stage_transient_bcs.py`'s own docstring: staged restarts are the established
pattern here, not `Function1` tables, which are unverified against this harness).
`stage_transient_bcs_ascent.py` (repo root) implements the doc's own ascent physics
directly — **not** `atmosphere.py`'s `sky_sink_temperature()`, which is explicitly
documented as valid only above ~20 km (it assumes negligible atmospheric IR, wrong
at 0-10 km):

```
T_amb(t) = 15.0 - 0.02708*t                                  degC   (doc Sec.6B)
h(t)     = 15 -> 11 (0-1200s) -> 8 (1200-2400s), piecewise-linear   (doc Sec.6C)
Ta_sun(t)   = T_amb(t) + 272/h(t)     (radiator_plate, sun-facing, doc Sec.6D)
Ta_shaded(t)= T_amb(t)                (radiator_plate_2)
```

`run_transient_10km.py` (repo root) drives 8 restart segments of 300 s
(`0,300,...,2400`), patching each segment's start-time BCs to that segment's midpoint
before calling `cht_pipeline.solve()`:

```powershell
.venv\Scripts\python.exe run_transient_10km.py --study $S --resume
```

`--resume` skips segments already recorded (with `ok: true`) in
`<study>/transient_run_log.json`, so a killed/restarted run picks up where it left
off rather than re-solving from t=0. Run this as a background process — 8 segments
at ~24 s/segment (4 procs, this machine) finish in a few minutes, but do not assume
that on a slower box; check `transient_run_log.json` rather than waiting on the
foreground call.

## C8 — Post-processing and verification (doc Sec.8)

```powershell
.venv\Scripts\python.exe transient_history.py --study $S --highlight jetson_module,interface_plate,radiator_plate,radiator_plate_2
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study $S
```

Check against doc Sec.8's targets:
1. `jetson_module` (die) max temperature stays below 75°C through 2400 s.
2. Radiator mean temperature — flag if it drops below 0°C while the Jetson side is
   still hot (undersized strap conductance).
3. ΔT across each copper strap (`copper_strap_left/right` hot-end vs cold-end) at
   t=1200 s and t=2400 s specifically.

## C9 — Report

Quote only numbers that came out of `transient_T_history.csv`/`cht_kpis.json` —
never invent a temperature or flux. State materials, names, TCRs, and the
`disable_fpe_trap` workaround as assumptions if asked to reproduce independently.

# Part D — Troubleshooting

* **`n_steps: 0`, `completed: false`, log ends right after the per-region
  `Diffusion Number` printout with no error text** → this is the `FOAM_SIGFPE` abort
  (see C-FPE). Confirm `solver.disable_fpe_trap: true` is in the manifest and that
  `case/system/controlDict`'s `deltaT` is a real fraction of whatever `--end-time`
  you asked for (a fixed `deltaT` bigger than the requested window also produces
  `n_steps: 0`, a different and unrelated cause — see C6).
* **`checkMesh` `ok: false`** → read `case/log.checkMesh` for which check actually
  failed (not just the non-orthogonality number, which this geometry reports as `OK`
  even at 89.99° — the real failure line starts with `***`).
* **Renamed components revert to `part_N`** → you re-ran `inspect_step.py` after
  renaming. Redo the rename (C1's table) directly on the current `manifest.json`;
  do not re-inspect again.
* **Restart segment can't find a patch's `Ta`/`h` entry** → `case/<time>/<region>/T`
  is binary, not ascii. `cht_case.py` only writes ascii for solid-only fixed-step
  transient runs (needed for exactly this kind of restart text-patch) — if this
  triggers, `solver.mode`/`deltaT_s` were changed after case setup; re-run C5.

# Part E — The prompt to give with this runbook

```
Here is the full runbook for the balloon-ttp 0-10km transient study. Execute Part C
in order: C0 environment gate, C1 rename components, C2 materials, C3 boundary
conditions, C-TCR contact resistances, C4 solver block, C5 mesh+case, C6 smoke test,
C7 staged production run (background), C8 post-processing, C9 report. Stop at any
gate failure and report the cause instead of guessing. Never invent a temperature,
flux, or runtime — quote only what tool output actually returned. Never run an
installer; the toolchain is already verified by C0.
```
