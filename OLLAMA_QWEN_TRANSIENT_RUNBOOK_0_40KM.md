# Runbook — Local Ollama (`cfd-qwen`) driving the 0→40 km / 160-minute Ascent Transient

**Audience:** an operator running a fully local LLM agent against this repository, and
the `cfd-qwen` model itself. Everything below is executable — no cloud API key needed.

**Target study:** `balloon-ttp/transient-0-40km` — a **30 W** Jetson payload on a
5 mm Al 6061 cold plate (`interface_plate`), coupled through twin OFHC copper straps
(`copper_strap_left/right`) to two external white-painted Al 6061 radiators
(`radiator_plate`, `radiator_plate_2`), all inside an expanded-polystyrene
(`styrofoam_box`) insulated enclosure. Transient conduction + natural convection +
grey radiation from ground level to **40 km over 9600 s (160 minutes)**.

Input geometry: [inputs/balloon-ttp/spaced out rad+box.step](inputs/balloon-ttp/spaced%20out%20rad+box.step)
— the same 12-solid CAD used by the 0→10 km study (radiators spaced apart, box
included in the same STEP file). **Status: this runbook has not been executed yet** —
unlike the two sibling runbooks below, there is no "verified end-to-end" box here.
Every command is ready to run; every number that isn't yet measured is marked as an
estimate or an assumption.

## How this compares to the two existing runbooks

| | [OLLAMA_QWEN_TRANSIENT_RUNBOOK.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK.md) (0→20 km) | [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_10KM.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_10KM.md) (0→10 km) | This runbook (0→40 km) |
| --- | --- | --- | --- |
| Duration | 1200 s | 2400 s (40 min) | **9600 s (160 min)** |
| Ascent rate | 16.667 m/s | not explicit (ISA troposphere only) | **4.1667 m/s (250 m/min)** — chosen below |
| Jetson load | 60 W | 60 W | **30 W** (per this task) |
| Geometry | `assembly.step` | `spaced out rad+box.step` | `spaced out rad+box.step` (**reused as-is**) |
| BC driver | `altitude_environment` (US76 sky-sink, valid >~20 km, used from ground as an approximation) | explicit `convection` BC with hand-derived `h(t)`/`T_amb(t)` | `altitude_environment` (US76), same mechanism as the 20 km study, extended to 40 km where it is fully valid |
| Box BC | convective (`altitude_environment`) | **adiabatic** (insulation forces 100% of load through strap/radiator path) | **adiabatic**, same reasoning as the 10 km study |
| Segments | 6 × 200 s, altitude-indexed | 8 × 300 s, mission-time-indexed | **8 × 1200 s**, altitude-indexed |
| Contact resistances | documented only | solved (`thicknessLayers`/`kappaLayers`) | **solved**, reusing the 10 km study's joint list (same hardware) |
| `disable_fpe_trap` | not needed (different CAD) | **required** — this STEP file has a ~3e-9 m² sliver face | **required**, same CAD |

# Part A — Ollama + `cfd-qwen`

Identical setup to the other two runbooks — nothing to redo. Verify in one command,
executing nothing:

```powershell
.\ollama\run_agent.ps1 -SelfTest -Runbook OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md
```

Expect the same readiness signature documented in the sibling runbooks: Ollama on
`127.0.0.1:11434`, `cfd-qwen` built from `qwen2.5-coder:7b` (32k context, temp 0.1,
`tools` capability), 100% GPU-resident. If `ollama list` doesn't show `cfd-qwen`,
rebuild it:

```powershell
ollama create cfd-qwen -f ollama\Modelfile.cfd
```

**Driver note:** `run_agent.ps1` gates every command on a `Read-Host` prompt — it needs
a real interactive console. If you're driving this non-interactively, execute Part C's
commands yourself; that's a complete manual procedure on its own.

# Part B — What to pull onto the machine

Same solver stack as every other study here (OpenFOAM v2412 + Gmsh + CalculiX in WSL,
already installed and verified — **never run an installer**, see C0). Nothing new to
install for this study.

| Item | Location | Notes |
| --- | --- | --- |
| CAD | [inputs/balloon-ttp/spaced out rad+box.step](inputs/balloon-ttp/spaced%20out%20rad+box.step) | Same file the 0→10 km study used |
| Reference manifest | `outputs/balloon-ttp/transient-0-10km/assembly/manifest.json` | Already has components renamed and materials assigned for this exact CAD — **copy it, don't re-inspect** |
| Staging tool | [stage_transient_bcs.py](stage_transient_bcs.py) | Already in the repo root, altitude-indexed, reused unmodified |
| Post-processing | [transient_history.py](transient_history.py) | Already in the repo root, reused unmodified |
| Atmosphere model | [.tmp/scripts/atmosphere.py](.tmp/scripts/atmosphere.py) | US76 0–86 km — cross-checked against an independent source below, matches to within model differences |

---

# Part C — Conducting the simulation

Run every command from the repository root. The interpreter is always
`.venv\Scripts\python.exe`. Study slug: `balloon-ttp/transient-0-40km`.

## C0 — Environment gate (do not install anything)

```powershell
.venv\Scripts\python.exe .github\skills\solver_environment\scripts\check_environment.py
```

**Gate:** output ends with `READY: full CFD/FEA toolchain available.` If it doesn't,
stop and report — do not run `install_solvers.py`, `setup.ps1`, `first_run_setup.py`,
`apt`, `pip install`, or `winget install`. Ignore `setup_report.json` if it claims
otherwise; it is a stale artifact, not the authority.

## C1 — Seed the manifest from the 0→10 km study

Same STEP file, same 12 solids, same component renames — copy rather than
re-`inspect_step`, which would revert every hand-applied name back to `part_N`:

```powershell
$S = "balloon-ttp/transient-0-40km"
$new = "outputs\$S\assembly"
New-Item -ItemType Directory -Force $new | Out-Null
Copy-Item outputs\balloon-ttp\transient-0-10km\assembly\manifest.json $new\manifest.json
Copy-Item outputs\balloon-ttp\transient-0-10km\assembly\surfaces.json $new\surfaces.json
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study $S --list
```

Component → hardware → material map (carried over unchanged — same physical parts):

| Component | Hardware | Material | Why this material |
| --- | --- | --- | --- |
| `radiator_plate`, `radiator_plate_2` | Twin external radiators, white paint | `white_paint_aluminum` (Al 6061 + ε 0.85 override) | **aluminum**, radiators |
| `interface_plate` | Jetson cold plate / TTP interface | `aluminum_6061` | **aluminum**, heat sink |
| `jetson_heatsink` | Jetson-side heatsink block | `aluminum_6061` | **aluminum**, heat sink |
| `connector_block_left`, `connector_block_right` | Al clamp blocks, TTP end of each strap | `aluminum_6061` | **aluminum**, strap ends |
| `radiator_bracket_left`, `radiator_bracket_right` | Al brackets, radiator end of each strap | `aluminum_6061` | **aluminum**, strap ends |
| `copper_strap_left`, `copper_strap_right` | OFHC copper thermal strap braids | `copper` (ρ 8940, κ 390 override — OFHC C10100, not generic oxidised copper) | **copper**, strap braids |
| `styrofoam_box` | Enclosure | `eps_foam` (ρ 30, cp 1300 override) | **polystyrene**, the box — `eps_foam` in `agent-data/materials_library.json` *is* expanded polystyrene, κ 0.033 W/m-K |
| `jetson_module` | Jetson carrier PCB | `fr4_pcb` (cp 950 override) | PCB laminate — distinct from "the box" itself |

Initial condition: uniform 20 °C everywhere (already set by the copied manifest — every
`T_init_C: 20.0`). Confirm:

```powershell
.venv\Scripts\python.exe -c "import json; m=json.load(open('outputs/balloon-ttp/transient-0-40km/assembly/manifest.json')); print({k: v['T_init_C'] for k, v in m['components'].items()})"
```

## C2 — Ascent profile and atmosphere (values pulled from an independent source, not just the repo's own model)

**Assumption — vertical ascent rate.** No flight profile document was supplied for
this study, so a constant-rate vertical ascent is assumed: 40 000 m in 9600 s =
**4.1667 m/s (250 m/min)**. That's inside the range typical of real high-altitude
latex sounding-balloon flights (commonly 4–6 m/s / 250–350 ft/min), and it produces a
clean staging split: **8 segments of 1200 s, each spanning exactly 5000 m**.

**Temperature and pressure — cross-checked against an external reference.** The
1976 US Standard Atmosphere table below is quoted from an independent web source
(pdas.com's digitisation of the official NOAA/NASA/USAF tables), not derived from this
repo's own `atmosphere.py`:

| Altitude [km] | T [K] (web reference) | p [Pa] (web reference) |
| ---: | ---: | ---: |
| 0 | 288.150 | 101 325 |
| 5 | 255.676 | 54 048 |
| 10 | 223.252 | 26 500 |
| 15 | 216.650 | 12 112 |
| 20 | 216.650 | 5 529 |
| 25 | 221.552 | 2 549 |
| 30 | 226.509 | 1 197 |
| 35 | 236.513 | 574.6 |
| 40 | 250.350 | 287.1 |

Running the repo's own `atmosphere.py` at the same altitudes reproduces these to
within the small model/rounding differences you'd expect between two independent US76
implementations (0, 15, 20 and 40 km match to 3+ significant figures; the mid layers
differ by ≤2 K from slightly different interpolation choices). That cross-check is the
point — it confirms `atmosphere.py` is not silently wrong before it drives 9600 s of
solver time.

Segment table, mid-altitude atmosphere state from `atmosphere.py` (used for the actual
BC values below — same model, verified above):

| Stage | t [s] | Mid-altitude [m] | T_air [K] | T_air [°C] | p [Pa] | ρ_air [kg/m³] |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 0 → 1200 | 2 500 | 271.91 | −1.24 | 74 692 | 0.9569 |
| 2 | 1200 → 2400 | 7 500 | 239.46 | −33.69 | 38 300 | 0.5572 |
| 3 | 2400 → 3600 | 12 500 | 216.65 | −56.50 | 17 934 | 0.2884 |
| 4 | 3600 → 4800 | 17 500 | 216.65 | −56.50 | 8 182 | 0.1316 |
| 5 | 4800 → 6000 | 22 500 | 219.07 | −54.08 | 3 746 | 0.0596 |
| 6 | 6000 → 7200 | 27 500 | 224.03 | −49.12 | 1 743 | 0.0271 |
| 7 | 7200 → 8400 | 32 500 | 229.59 | −43.56 | 826 | 0.0125 |
| 8 | 8400 → 9600 | 37 500 | 243.43 | −29.72 | 404 | 0.0058 |

Reproduce this table yourself (nothing here is hand-typed beyond the table
formatting):

```powershell
.venv\Scripts\python.exe -c "
import sys; sys.path.insert(0, '.tmp/scripts')
from atmosphere import atmosphere
for alt in (2500, 7500, 12500, 17500, 22500, 27500, 32500, 37500):
    a = atmosphere(alt)
    print(f'{alt:6.0f} m  T={a[\"T_K\"]:7.2f} K ({a[\"T_C\"]:7.2f} C)  p={a[\"p_Pa\"]:9.1f} Pa  rho={a[\"rho_kg_m3\"]:.4f} kg/m3')
"
```

## C3 — Boundary conditions

```powershell
$AM = ".github\skills\step_assembly\scripts\assign_materials.py"

# 30 W Jetson load over the meshed TTP contact face (0.003666837 m^2, same patch/area
# the 10/20/30 km studies used on this CAD family)
.venv\Scripts\python.exe $AM --study $S --patch jetson_heat_source --component interface_plate --select ymax `
  --bc '{"type":"heat_flux","q_W_m2":8181.44,"description":"30 W over the TTP contact face (0.003666837 m2)"}'

# Radiators: altitude_environment (US76 combined film), cold/no-sun case, seeded at
# the stage-1 mid-altitude (2500 m). h_W_m2K here is the CONVECTIVE seed only (Churchill
# natural-convection estimate at 20 K guessed dT) -- cht_case.py adds the linearised
# radiative term on top of it when it writes the field.
.venv\Scripts\python.exe $AM --study $S --patch radiator_plate_outer   --component radiator_plate   --select remaining `
  --bc '{"type":"altitude_environment","altitude_m":2500,"emissivity":0.85,"absorbed_flux_W_m2":0.0,"L_char_m":0.15,"h_W_m2K":3.83}'
.venv\Scripts\python.exe $AM --study $S --patch radiator_plate_2_outer --component radiator_plate_2 --select remaining `
  --bc '{"type":"altitude_environment","altitude_m":2500,"emissivity":0.85,"absorbed_flux_W_m2":0.0,"L_char_m":0.15,"h_W_m2K":3.83}'

# Box: adiabatic. EPS foam's own job is to decouple the payload from the ambient --
# forcing 100% of the 30 W through the strap/radiator path is the conservative,
# physically-motivated choice, same reasoning the 0->10 km study used.
.venv\Scripts\python.exe $AM --study $S --patch foam_box_outer --component styrofoam_box --select remaining --bc '{"type":"adiabatic"}'

.venv\Scripts\python.exe $AM --study $S --validate
```

**Cold case only.** `absorbed_flux_W_m2: 0.0` is night/no-sun. For a sun-facing hot
case, compute the absorbed flux term first and fold it into `radiator_plate`'s BC
(shaded `radiator_plate_2` stays at 0):

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\environment.py --altitude 2500 --emissivity 0.85 --alpha-solar 0.2 --L-char 0.15
```

**Verify the stage-1 seed before meshing.** With `h_conv = 3.83 W/m²K` (Churchill
estimate at 2500 m, 0.15 m char. length, 20 K guessed ΔT) and a 293.15 K reference
(the 20 °C initial condition — nothing has run yet, so this is the best available
reference), `combined_film` gives:

```powershell
.venv\Scripts\python.exe -c "
import sys; sys.path.insert(0, '.tmp/scripts')
from atmosphere import atmosphere, sky_sink_temperature, equivalent_sink_temperature, combined_film
air = atmosphere(2500.0)
t_sink = equivalent_sink_temperature(0.85, 0.0, sky_sink_temperature(2500.0))
film = combined_film(3.83, air['T_K'], 0.85, t_sink, 293.15)
print({k: round(v, 3) for k, v in film.items()})
"
```

Expect `h_W_m2K ≈ 7.03`, `Ta_K ≈ 245.04`. That's what should appear in
`case/0/radiator_plate/T` after C5 — if it doesn't, C3 didn't take.

## C-TCR — Thermal contact resistances (carried over unchanged)

Same hardware as the 0→10 km study, so the same joint budget applies — already present
in the copied manifest's `thermal_contact_resistances` block, nothing to re-derive:

| Joint | R_total [K/W] | Material |
| --- | --- | --- |
| `interface_plate` ↔ `jetson_heatsink` | 0.10 | PTM7950 phase-change material |
| `interface_plate` ↔ `connector_block_left` | 1.58 | bolted joint |
| `interface_plate` ↔ `connector_block_right` | 1.58 | bolted joint |
| `copper_strap_left` ↔ `radiator_bracket_left` | 1.58 | bolted joint |
| `copper_strap_right` ↔ `radiator_bracket_right` | 1.58 | bolted joint |

`cht_case.py` writes these as `thicknessLayers`/`kappaLayers` on the coupled
interface patches — this is solved, not just documented (confirm after C5 by grepping
`case/0/*/T` for `thicknessLayers`). Combined two-path resistance from die to radiator:
0.10 K/W (die) + [ (1.58+1.58) ∥ (1.58+1.58) ] = 0.10 + 1.58 = **1.68 K/W**. At 30 W
that alone predicts roughly a **50 K** jump from `interface_plate` to the radiator mean
— a sanity bound for C9, not a substitute for the solved result.

## C4 — Solver block

```powershell
.venv\Scripts\python.exe $AM --study $S --solver '{"mode":"transient","end_time_s":9600,"write_interval_s":120,"deltaT_s":2.0,"n_procs":4,"p_ref_Pa":101325,"T_init_C":20,"disable_fpe_trap":true}'
```

`deltaT_s: 2.0` fixed — this assembly is solid-only (no fluid regions).
`adjustTimeStep` collapses toward zero for solid-only cases (`setMultiRegionDeltaT`
has no fluid Courant number to scale against — measured elsewhere on this CAD family:
8144 steps to reach 1.8 µs). Euler-implicit solid conduction is unconditionally stable,
so a fixed step is correct, not a workaround. 9600 s / 2.0 s = 4800 steps total.

`disable_fpe_trap: true` is **required** for this STEP file — see C-FPE.

## C-FPE — Why `disable_fpe_trap` is required for this geometry

This is the same CAD (`spaced out rad+box.step`) the 0→10 km study used, and it has
the same defect: `checkMesh` reports 25 high-aspect-ratio cells (max ratio ~14133)
traced to a ~3e-9 m² sliver face on `interface_plate`, present regardless of global
mesh size. With the default `FOAM_SIGFPE` trap on, that cell produces a diffusion-number
overflow that kills `chtMultiRegionFoam` before the first time step, silently (no
`FOAM FATAL ERROR`, just a stop after the per-region diagnostic printout). Solid
conduction under implicit Euler is unconditionally stable regardless of that
diagnostic number — disabling the trap is a fix for a false-positive abort, not a
physics workaround. `disable_fpe_trap: true` in the solver block (set above) makes
`cht_pipeline.py` prepend `export FOAM_SIGFPE=false;` to the solve invocation.

## C5 — Mesh + case

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\mesh_assembly.py --study $S --factor 1.0
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

Expect the same `checkMesh` warning as the 10 km study (`ok: false`, high-aspect-ratio
only, non-orthogonality reported "OK" even near 90°) — proceed, it's the known,
understood CAD defect from C-FPE, not a new problem.

Confirm the transient extras and time-stepping landed:

```powershell
Select-String -Path outputs\balloon-ttp\transient-0-40km\case\system\controlDict -Pattern 'application|endTime|deltaT|adjustTimeStep|writeControl|writeInterval|writeFormat'
```

Expect `chtMultiRegionFoam`, `endTime 9600`, `deltaT 2`, `adjustTimeStep no`,
`writeInterval 120`, `writeFormat ascii`. ASCII is mandatory — it's what lets C8's
staging script rewrite `Ta`/`h` in a written time directory between segments.

## C6 — Smoke test

`--smoke`'s hard-coded 0.5 s window is smaller than this case's fixed 2.0 s step, so
use an explicit window that's a multiple of `deltaT_s` instead:

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 10 --time-limit 300
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study $S
```

**Gate:** `completed: true`, `final_time: 10.0`, `n_steps: 5`, `jetson_heat_source ≈
30 W`, every `*_wall` external flux `0.0` (the box is adiabatic). Reset to a clean
t=0 before the real run:

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

## C7 — The staged ascent (0 → 9600 s)

`externalWallHeatFluxTemperature` takes static `Ta`/`h` per run, so the 160-minute
flight is run as **8 restart segments of 1200 s**, matching the atmosphere table in
C2 exactly (each segment spans 5000 m). Stage 1 needs no staging call — C3 already set
the ground-side seed BC in `0/`. Stages 2–8 use
[stage_transient_bcs.py](stage_transient_bcs.py) (already in the repo root, reused
unmodified from the 0→20 km study) with **both `--h` and `--t-surface-est-C` omitted**
— that lets it compute `h` from the Churchill natural-convection correlation at the
segment's actual altitude, and read the linearisation reference temperature back from
the radiator's own solved field at the end of the previous segment, which is more
accurate than a fixed guess over a flight this long:

```powershell
# stage 1 : 0 -> 1200 s   (BCs already at 2500 m from C3)
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 1200

# stage 2 : 1200 -> 2400 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 7500
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 2400

# stage 3 : 2400 -> 3600 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 12500
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 3600

# stage 4 : 3600 -> 4800 s   (tropopause)
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 17500
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 4800

# stage 5 : 4800 -> 6000 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 22500
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 6000

# stage 6 : 6000 -> 7200 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 27500
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 7200

# stage 7 : 7200 -> 8400 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 32500
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 8400

# stage 8 : 8400 -> 9600 s   (radiation-dominated, near-vacuum convection)
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 37500
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 9600
```

**Per-stage gate — check all four before starting the next stage:**

1. `run_summary.json` shows `"completed": true` and `final_time` equal to the segment
   end (1200, 2400, …, 9600).
2. The first `Time =` line for the segment in `case\log.chtMultiRegionFoam` is the
   previous segment's end time, not 0 — proves the restart picked up state:
   `Select-String -Path outputs\balloon-ttp\transient-0-40km\case\log.chtMultiRegionFoam -Pattern "^Time = " | Select-Object -First 3`
3. No `FOAM FATAL` or `bounding` messages in the log.
4. `stage_transient_bcs.py`'s printed `T_ref_K` for the radiators should track their
   actual solved temperature. If a radiator drifted far in the segment just run,
   the next segment's linearisation is only exact at that reference — this is
   expected behaviour, not a fault, since the script re-reads the true field each time.

**Prune between stages** — `run_cht_case.py` reprocesses every stored time directory
on each call (`decomposePar`/`reconstructPar`/`foamToVTK`), so per-stage cost grows
if old directories accumulate. With `write_interval_s: 120` over 9600 s that's 80
directories by the end. Delete everything older than the latest before each restart
(never delete the latest — it's the restart point):

```powershell
$case = "outputs\balloon-ttp\transient-0-40km\case"
$keep = (Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' } |
         Sort-Object { [double]$_.Name } | Select-Object -Last 1).Name
Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' -and $_.Name -ne $keep -and $_.Name -ne '0' } | Remove-Item -Recurse -Force
"kept: $keep"
```

**Runtime estimate (extrapolated, not measured for this study).** The 0→10 km study
solved 2400 s at `deltaT_s = 2.0` in 195 s wall clock on a 4-proc RTX 3060 box. Scaling
linearly to 9600 s (4×) gives roughly **13 minutes of solve time**, plus per-segment
decompose/reconstruct/VTK overhead (~20 s × 8 stages ≈ 3 min) — call it **~20–25
minutes total** if pruning is applied between stages, more if it isn't. Run this as a
background process and check `case\log.chtMultiRegionFoam` rather than waiting on the
foreground call.

## C8 — Post-processing and verification

```powershell
.venv\Scripts\python.exe transient_history.py --study $S --highlight jetson_module,interface_plate,copper_strap_left,radiator_plate,radiator_plate_2
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study $S
```

**Verification gates (do not report results until all pass):**

| # | Check | Pass criterion |
| --- | --- | --- |
| 1 | Heat actually injected | `jetson_heat_source` ≈ 30 W throughout. More than a few percent off means the C3 flux/area calculation is wrong |
| 2 | Box adiabatic | Every `styrofoam_box`-adjacent external patch integrates to 0.0 W |
| 3 | Temperatures bounded | No region colder than the coldest sky sink (~−65 °C at 37 500 m, see C2) or hotter than ~200 °C |
| 4 | Restart continuity | No temperature discontinuity across a segment boundary (t = 1200, 2400, …, 8400) in `transient_T_history.csv`. A jump > 1 K means a stage restarted from the wrong time |
| 5 | Thermal lag present | `jetson_module`/`interface_plate` rise smoothly rather than stepping — confirms ρ·cₚ took effect |
| 6 | Convection collapse visible | `radiator_plate`'s combined film `h` should fall by roughly an order of magnitude from stage 1 (~7 W/m²K) to stage 8 (near-vacuum, well under 1 W/m²K) — check the printed `stage_transient_bcs.py` reports across the run |
| 7 | TCR sanity | `interface_plate` minus radiator mean at any time should be in the neighbourhood of the ~50 K analytic estimate from C-TCR (order of magnitude, not exact — that estimate ignores the radiative and conductive fringe terms) |
| 8 | Interface balance | For each coupled interface in `interfaces_W`, the two sides agree within a few percent |

## C9 — Report

```powershell
.venv\Scripts\python.exe .github\skills\report_generation\scripts\build_report.py --study $S --title "Stratospheric Payload Transient Thermal Analysis: 0-40 km, 160 min, 30 W"
```

Then edit the executive summary by hand. State explicitly:

* Peak `jetson_module` (die) temperature, when it occurs, and margin to whatever
  thermal limit applies to this hardware.
* Radiator mean temperature and total radiative rejection at t = 9600 s.
* The assumed constant 4.1667 m/s ascent rate — no flight profile document was
  supplied for this study; if a real flight profile exists, restage C7 against it.
* The `altitude_environment`/US76 BC is used from ground level, same approximation
  the 0→20 km study made — it is exact above ~20 km and conservative below it
  (atmospheric IR is neglected, which undercounts the sky sink term near sea level).
* The 30 W load is the number given for this study; if the real Jetson block's power
  varies with duty cycle, re-run C3/C6–C8 at the actual worst-case wattage.
* Box is modelled adiabatic — no heat escapes except through the strap/radiator path.
* `checkMesh` flags high-aspect-ratio cells only (known CAD sliver, see C-FPE); solved
  with `disable_fpe_trap`, not by fixing the mesh.
* Mesh independence was not performed for this study.

---

# Part D — Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `n_steps: 0`, log ends right after the per-region `Diffusion Number` printout, no error text | `FOAM_SIGFPE` abort on the `interface_plate` sliver cell | Confirm `solver.disable_fpe_trap: true` in the manifest (C4) |
| `n_steps: 0` even with the trap disabled | Fixed `deltaT` (2.0 s) is bigger than the requested `--end-time` window | Use a window that's a multiple of `deltaT_s`, as in C6 |
| `checkMesh` `ok: false` | Read `log.checkMesh` for the line starting `***` — non-orthogonality near 90° is reported "OK" on this geometry and is not the real failure | Compare against C-FPE; if a different `***` line appears, this is a new defect, investigate before proceeding |
| Renamed components revert to `part_N` | `inspect_step.py` was re-run after C1 | Re-copy the manifest from `transient-0-10km`, or redo the C1 rename table by hand; don't re-inspect |
| Restart can't find a patch's `Ta`/`h` entry | `case/<time>/<region>/T` is binary, not ASCII | `writeFormat` must stay `ascii` (verified in C5); if it flipped, `solver.mode`/`deltaT_s` changed after case setup — re-run C5 |
| Temperatures oscillate at interfaces | Solid diffusion number too large for `deltaT_s = 2.0` | Lower `deltaT_s` (2.0 → 1.0), re-`prepare`, re-run from t = 0 |
| Per-stage wall clock keeps growing | Old time directories weren't pruned between stages | Run the C7 prune snippet before every restart |
| Ollama replies truncated / forgets the stage number | `num_ctx` reverted to 4096 | Rebuild with `ollama\Modelfile.cfd`; confirm with `ollama show cfd-qwen` |

---

# Part E — The prompt to give with this runbook

```
You are executing OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md Part C in this repository.
Study slug: balloon-ttp/transient-0-40km.

GOAL
Transient conduction+radiation simulation of a 30 W payload (Jetson block, copper
straps, twin aluminum radiators, polystyrene enclosure) ascending 0 -> 40 km in
9600 s (160 min) at a constant 4.1667 m/s, run as eight 1200 s segments with the
atmosphere re-evaluated per segment from atmosphere.py (US76).

ENVIRONMENT -- ALREADY BUILT, NOTHING TO INSTALL
WSL Ubuntu, OpenFOAM v2412 with chtMultiRegion solvers, CalculiX 2.21, Gmsh and all
Python packages are installed and verified. Never run install_solvers.py, setup.ps1,
first_run_setup.py, apt or pip install. C0 is read-only and prints
"READY: full CFD/FEA toolchain available."

PROTOCOL
- One powershell command per turn, in a fenced powershell block, nothing else.
- Wait for the real output before continuing.
- State the current step id (C0..C9) before each command, and the stage number in C7.
- Never state a temperature, flux, residual or runtime you have not seen in output
  that was actually pasted back to you.
- If a command fails, name the cause in one sentence, then issue a corrected command
  -- do not retry verbatim.
- Do not proceed past a failed verification gate. Say what failed and stop.

EXECUTION RULES SPECIFIC TO THIS STUDY
- Copy the manifest from outputs/balloon-ttp/transient-0-10km/assembly in C1 -- do
  not re-run inspect_step.py, it reverts the component renames.
- disable_fpe_trap must be true in the solver block (C4) -- this CAD has a known
  sliver face that aborts the solver otherwise (see C-FPE).
- In C7, run the prune snippet between stages or per-stage cost grows.
- Stage end times must land on multiples of the 120 s write interval.
- The heat flux (C3) is fixed at 30 W over the 0.003666837 m^2 TTP contact area --
  do not reuse the 60 W value from the sibling 10/20 km studies.

Start with C0.
```

---

## Reference — files this procedure touches

| Path | Role |
| --- | --- |
| [inputs/balloon-ttp/spaced out rad+box.step](inputs/balloon-ttp/spaced%20out%20rad+box.step) | CAD source, 12 solids |
| `outputs/balloon-ttp/transient-0-10km/assembly/manifest.json` | Source manifest — copied into this study in C1 |
| [stage_transient_bcs.py](stage_transient_bcs.py) | Altitude-indexed BC restaging, reused unmodified |
| [transient_history.py](transient_history.py) | CSV/PNG assembly across restart segments, reused unmodified |
| [.tmp/scripts/atmosphere.py](.tmp/scripts/atmosphere.py) | US76 atmosphere, sky sink, `combined_film`, `natural_convection_h` |
| [.tmp/scripts/cht_case.py](.tmp/scripts/cht_case.py) | OpenFOAM case factory; TCR `thicknessLayers`/`kappaLayers`, fixed-step transient controlDict |
| [.tmp/scripts/cht_pipeline.py](.tmp/scripts/cht_pipeline.py) | `prepare()`/`solve()`, `disable_fpe_trap` handling |
| [ollama/Modelfile.cfd](ollama/Modelfile.cfd) / [ollama/run_agent.ps1](ollama/run_agent.ps1) | `cfd-qwen` build + approval-gated driver |
| `outputs/balloon-ttp/transient-0-40km/` | This study's manifest, case, figures, and reports |

Sources for the C2 atmosphere cross-check:
- [Table of the U.S. Standard Atmosphere 1976](https://www.pdas.com/bigtables.html)
- [U.S. Standard Atmosphere: Temperature, Pressure, and Air Properties vs. Altitude](https://www.engineeringtoolbox.com/standard-atmosphere-d_604.html)
