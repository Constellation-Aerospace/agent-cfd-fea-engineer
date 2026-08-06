# Runbook — Local Ollama (`cfd-qwen`) driving the 0→40 km / 160-minute Ascent Transient, **Sun-Facing (Hot) Case**

**Audience:** an operator running a fully local LLM agent against this repository, and
the `cfd-qwen` model itself. Everything below is executable — no cloud API key needed.

**Target study:** `balloon-ttp/transient-0-40km-hot` — the same 30 W Jetson payload,
hardware and 0→40 km / 9600 s ascent as
[OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md)
(hereafter "the cold-case runbook"), but with `radiator_plate` sun-facing instead of
in shadow. `radiator_plate_2` stays shaded (0 absorbed flux) throughout — this models
one radiator catching direct sun + Earth albedo while its twin on the opposite face of
the payload does not, which is the worst case for that one plate and a like-for-like
comparison against the cold case for everything else.

**Why this study exists.** The cold-case runbook explicitly flagged this as the open
question at its C3/C9 steps: *"Cold case only... For a sun-facing hot case, compute the
absorbed flux term first and fold it into `radiator_plate`'s BC."* That command was
never run in the cold-case study. This runbook runs it, so the 71–72 °C peak reported
for the cold case can be checked against a worst-case sun exposure.

**Status: this runbook has not been executed yet** at the time of writing — ready to
run end-to-end, every number not yet measured is marked as an estimate or assumption.

## What's different from the cold-case runbook

| | Cold case (`transient-0-40km`) | This runbook (`transient-0-40km-hot`) |
| --- | --- | --- |
| `radiator_plate` BC | `altitude_environment`, `absorbed_flux_W_m2: 0.0` (no sun) | `altitude_environment`, `absorbed_flux_W_m2: 107.74` (sun-facing, see C3) |
| `radiator_plate_2` BC | `altitude_environment`, `absorbed_flux_W_m2: 0.0` | unchanged — `absorbed_flux_W_m2: 0.0` (shaded) |
| Everything else | — | identical: same CAD, same manifest/materials/TCR, same 30 W load, same 8×1200 s ascent segments at the same altitudes, same `disable_fpe_trap` |

## C-BUG — a real bug was found and fixed while scoping this study

`environment.py`'s suggested `bc_json` for the `altitude_environment` BC type used to
set `absorbed_flux_W_m2` to the **full** `q_total_W_m2` (solar + albedo + Earth IR).
That double-counts Earth's IR emission: `sky_sink_temperature()` (used downstream by
`cht_case.py`/`stage_transient_bcs.py`) already folds Earth's IR into the sink
temperature via `T_EARTH_EFF = 255 K`, which is numerically the same physical quantity
as `EARTH_IR = 240 W/m2` (`sigma * 255^4 = 239.8 W/m2`). Adding `q_earth_ir` again as a
flux term on top moved the effective sink temperature from **−60 °C to −20 °C at
2500 m** — a 40 °C error — in a quick numerical check before this was fixed.

**Fixed** in `environment.py`: the non-orbit (`altitude_environment`) `bc_json` path now
uses `q_solar + q_albedo` only. The `--orbit`/`space_environment` path was already
correct (it uses `T_SPACE` alone as the base sink, with no separate Earth-IR term to
collide with) and is unchanged. Verified against `pytest tests -q` (all green) before
this runbook was written. If you re-run C3's `environment.py` command and get a
different `absorbed_flux_W_m2` than the one printed here, diff your `environment.py`
against this fix before trusting the new number.

# Part A — Ollama + `cfd-qwen`

Identical setup to the sibling runbooks — nothing to redo. Verify in one command,
executing nothing:

```powershell
.\ollama\run_agent.ps1 -SelfTest -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_HOT.md
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
| CAD | [inputs/balloon-ttp/spaced out rad+box.step](../../inputs/balloon-ttp/spaced%20out%20rad+box.step) | Same file the cold 0→40 km study used |
| Reference manifest | `outputs/balloon-ttp/transient-0-40km/assembly/manifest.json` | Already has components renamed, materials assigned, TCR solved for this exact CAD — **copy it, don't re-inspect** |
| Reference mesh | `outputs/balloon-ttp/transient-0-40km/mesh/` | Same geometry, same `factor 1.0` — **copy it, don't re-mesh** (saves a Gmsh run and guarantees an identical mesh to the cold case for direct comparison) |
| Staging tool | [stage_transient_bcs.py](../../stage_transient_bcs.py) | Reused unmodified |
| Post-processing | [transient_history.py](../../transient_history.py) | Reused unmodified |
| Atmosphere/environment model | [.tmp/scripts/atmosphere.py](../../.tmp/scripts/atmosphere.py), [environment.py](../../.github/skills/conjugate_heat_transfer/scripts/environment.py) | `environment.py` carries the C-BUG fix above |

---

# Part C — Conducting the simulation

Run every command from the repository root. The interpreter is always
`.venv\Scripts\python.exe`. Study slug: `balloon-ttp/transient-0-40km-hot`.

## C0 — Environment gate (do not install anything)

```powershell
.venv\Scripts\python.exe .github\skills\solver_environment\scripts\check_environment.py
```

**Gate:** output ends with `READY: full CFD/FEA toolchain available.` If it doesn't,
stop and report — do not run `install_solvers.py`, `setup.ps1`, `first_run_setup.py`,
`apt`, `pip install`, or `winget install`.

## C1 — Seed the manifest and mesh from the completed cold-case study

```powershell
$S = "balloon-ttp/transient-0-40km-hot"
$new = "outputs\$S"
New-Item -ItemType Directory -Force "$new\assembly" | Out-Null
Copy-Item outputs\balloon-ttp\transient-0-40km\assembly\manifest.json "$new\assembly\manifest.json"
Copy-Item outputs\balloon-ttp\transient-0-40km\assembly\surfaces.json "$new\assembly\surfaces.json"
Copy-Item outputs\balloon-ttp\transient-0-40km\mesh "$new\mesh" -Recurse
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study $S --list
```

Component materials, thermal contact resistances and 20 °C uniform initial condition
are unchanged from the cold case (see its runbook's C1/C-TCR tables) — this is the same
hardware and CAD, only the radiator sun-exposure BC changes.

## C2 — Ascent profile and atmosphere (unchanged from the cold case)

Same assumption, same table, same 8×1200 s segments as
[OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md)'s
C2 — 4.1667 m/s constant ascent, mid-altitude atmosphere state per stage. Not repeated
here; reproduce it with the same command from that runbook if needed.

## C3 — Boundary conditions

```powershell
$AM = ".github\skills\step_assembly\scripts\assign_materials.py"

# 30 W Jetson load — identical to the cold case
.venv\Scripts\python.exe $AM --study $S --patch jetson_heat_source --component interface_plate --select ymax `
  --bc '{"type":"heat_flux","q_W_m2":8181.44,"description":"30 W over the TTP contact face (0.003666837 m2)"}'
```

**Compute the sun-facing absorbed flux first** — white-paint radiator, α_solar = 0.2 (a
typical white thermal-control paint value; low α/ε ratio is the point of that paint),
ε = 0.85, same 0.15 m characteristic length as the cold case, evaluated at the stage-1
seed altitude (2500 m — Earth's view factor changes only ~8% from 2500 m to 37 500 m
over this ascent, so a single representative value is used for the whole flight, the
same simplification `environment.py`'s docstring calls out as "scoping," not a
flight-review number):

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\environment.py --altitude 2500 --emissivity 0.85 --alpha-solar 0.2 --L-char 0.15
```

**Expect** `absorbed_flux_W_m2` in the printed `bc_json` to be **107.74** (q_solar
68.05 + q_albedo 39.69 W/m2, q_earth_ir excluded per C-BUG). If you get 206.88 instead,
`environment.py` doesn't have the C-BUG fix — stop and fix it before proceeding, or
every downstream number in this study will be wrong by the 40 °C sink-temperature error
described above.

```powershell
# radiator_plate: SUN-FACING — absorbed_flux_W_m2 from the command above
.venv\Scripts\python.exe $AM --study $S --patch radiator_plate_outer   --component radiator_plate   --select remaining `
  --bc '{"type":"altitude_environment","altitude_m":2500,"emissivity":0.85,"absorbed_flux_W_m2":107.74,"L_char_m":0.15,"h_W_m2K":3.83}'

# radiator_plate_2: SHADED — same as the cold case, absorbed_flux_W_m2 stays 0
.venv\Scripts\python.exe $AM --study $S --patch radiator_plate_2_outer --component radiator_plate_2 --select remaining `
  --bc '{"type":"altitude_environment","altitude_m":2500,"emissivity":0.85,"absorbed_flux_W_m2":0.0,"L_char_m":0.15,"h_W_m2K":3.83}'

# Box: adiabatic, same reasoning as the cold case
.venv\Scripts\python.exe $AM --study $S --patch foam_box_outer --component styrofoam_box --select remaining --bc '{"type":"adiabatic"}'

.venv\Scripts\python.exe $AM --study $S --validate
```

**Verify the stage-1 seed before meshing** — `radiator_plate` should show a noticeably
warmer effective sink than the cold case's ≈245 K, `radiator_plate_2` should be
unchanged:

```powershell
.venv\Scripts\python.exe -c "
import sys; sys.path.insert(0, '.tmp/scripts')
from atmosphere import atmosphere, sky_sink_temperature, equivalent_sink_temperature, combined_film
air = atmosphere(2500.0)
t_sink_sun = equivalent_sink_temperature(0.85, 107.74, sky_sink_temperature(2500.0))
film_sun = combined_film(3.83, air['T_K'], 0.85, t_sink_sun, 293.15)
t_sink_shade = equivalent_sink_temperature(0.85, 0.0, sky_sink_temperature(2500.0))
film_shade = combined_film(3.83, air['T_K'], 0.85, t_sink_shade, 293.15)
print('radiator_plate (sun)   :', {k: round(v, 3) for k, v in film_sun.items()})
print('radiator_plate_2 (shade):', {k: round(v, 3) for k, v in film_shade.items()})
"
```

## C-TCR — Thermal contact resistances (carried over unchanged)

Same hardware, same joint budget as the cold case — see that runbook's C-TCR table,
already present in the copied manifest.

## C4 — Solver block

```powershell
.venv\Scripts\python.exe $AM --study $S --solver '{"mode":"transient","end_time_s":9600,"write_interval_s":120,"deltaT_s":2.0,"n_procs":4,"p_ref_Pa":101325,"T_init_C":20,"disable_fpe_trap":true}'
```

Identical to the cold case (`deltaT_s: 2.0` fixed, `disable_fpe_trap: true` required —
same CAD sliver defect, see the cold-case runbook's C-FPE for the full explanation).

## C5 — Case setup (mesh reused, not regenerated)

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

No `mesh_assembly.py` call — C1 already copied the cold case's `mesh/assembly.msh`
wholesale, and `--reuse-mesh` picks it up as-is. Expect the same `checkMesh` warning as
every other study on this CAD (high-aspect-ratio sliver only, known and understood).

Confirm the transient extras landed:

```powershell
Select-String -Path outputs\balloon-ttp\transient-0-40km-hot\case\system\controlDict -Pattern 'application|endTime|deltaT|adjustTimeStep|writeControl|writeInterval|writeFormat'
```

Expect `chtMultiRegionFoam`, `endTime 9600`, `deltaT 2`, `adjustTimeStep no`,
`writeInterval 120`, `writeFormat ascii`.

## C6 — Smoke test

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 10 --time-limit 300
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study $S
```

**Gate:** `completed: true`, `final_time: 10.0`, `n_steps: 5`, `jetson_heat_source ≈
30 W`, every `*_wall` external flux `0.0` except the two radiator patches (now nonzero
in opposite senses — `radiator_plate` should show a smaller net loss than
`radiator_plate_2` this early, since it's absorbing sun on top of radiating). Reset to
a clean t=0 before the real run:

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

## C7 — The staged ascent (0 → 9600 s)

Identical mechanics and altitude schedule to the cold case — 8 restart segments of
1200 s each, altitude-indexed. `absorbed_flux_W_m2` is stored per-patch in the manifest
and is **not** recomputed by `stage_transient_bcs.py` between stages (it only refreshes
`h`/`Ta` from the new altitude's air/sky-sink state) — so `radiator_plate` keeps its
107.74 W/m2 sun load and `radiator_plate_2` keeps 0 for the whole flight, exactly as
intended.

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

**Per-stage gate — check all four before starting the next stage** (same as the cold
case): `completed: true` at the segment end time; restart continuity (`Time =` line
starts at the previous segment's end, not 0); no `FOAM FATAL`/`bounding` messages;
`stage_transient_bcs.py`'s printed `T_ref_K` tracking the solved field.

**Prune between stages** (same snippet as the cold case, keep only the latest and `0`):

```powershell
$case = "outputs\balloon-ttp\transient-0-40km-hot\case"
$keep = (Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' } |
         Sort-Object { [double]$_.Name } | Select-Object -Last 1).Name
Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' -and $_.Name -ne $keep -and $_.Name -ne '0' } | Remove-Item -Recurse -Force
"kept: $keep"
```

**Runtime estimate:** same order as the cold case, ~20–25 minutes total with pruning
applied between stages (identical mesh, identical solid-only fixed-step solve — the
only change is the radiator BC values, which doesn't affect solver cost).

## C8 — Post-processing and verification

```powershell
.venv\Scripts\python.exe transient_history.py --study $S --highlight jetson_module,interface_plate,copper_strap_left,radiator_plate,radiator_plate_2
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study $S
```

**Verification gates (do not report results until all pass):**

| # | Check | Pass criterion |
| --- | --- | --- |
| 1 | Heat actually injected | `jetson_heat_source` ≈ 30 W throughout |
| 2 | Box adiabatic | Every `styrofoam_box`-adjacent external patch integrates to 0.0 W |
| 3 | Temperatures bounded | No region colder than the coldest sky sink or hotter than ~200 °C |
| 4 | Restart continuity | No temperature discontinuity > 1 K across any segment boundary |
| 5 | Sun/shade asymmetry visible | `radiator_plate` (sun-facing) should run measurably warmer than `radiator_plate_2` (shaded) throughout — if they track each other, the C3 BC didn't take |
| 6 | Cold-case comparison | `jetson_module`/`interface_plate` peak temperatures should be **at or above** the cold case's 71.3 °C / 72.1 °C — added solar load cannot make the payload run cooler than the no-sun case with everything else equal |
| 7 | TCR sanity | Same ~50 K order-of-magnitude bound from the cold case's C-TCR still applies to the interface_plate-to-radiator drop |
| 8 | Interface balance | Each coupled interface in `interfaces_W` agrees within a few percent between its two sides |

## C9 — Report

```powershell
.venv\Scripts\python.exe .github\skills\report_generation\scripts\build_report.py --study $S --title "Stratospheric Payload Transient Thermal Analysis: 0-40 km, 160 min, 30 W, Sun-Facing Radiator"
```

Then edit the executive summary by hand. State explicitly, in addition to the cold
case's C9 list:

* The delta between this study's peak `jetson_module`/`interface_plate` temperatures
  and the cold case's 71.3 °C / 72.1 °C — this is the number that answers "does sun
  exposure matter for this design."
* `radiator_plate` (sun-facing) vs `radiator_plate_2` (shaded) temperature split at
  t = 9600 s — the asymmetry this BC change is meant to produce.
* The single fixed `absorbed_flux_W_m2 = 107.74` (evaluated at 2500 m, held constant
  for the whole ascent) is a scoping-level simplification, not a flight-review number
  — Earth's view factor changes ~8% over the ascent, and this ignores balloon
  orientation/shadowing dynamics entirely (worst case: continuously sun-normal).
* The `environment.py` Earth-IR double-count bug (C-BUG) was fixed before this study
  ran — note that any report or number produced before that fix used the old, wrong
  `environment.py` and should be treated with suspicion.

---

# Part D — Troubleshooting

Same failure modes as the cold-case runbook's Part D apply unchanged (`FOAM_SIGFPE`
abort, fixed-`deltaT` vs `--end-time` window mismatch, ASCII `writeFormat` requirement,
stale time-directory pruning). One addition specific to this runbook:

| Symptom | Cause | Fix |
| --- | --- | --- |
| `radiator_plate` and `radiator_plate_2` track each other almost exactly | `absorbed_flux_W_m2` wasn't actually set differently on the two patches, or C3 was run with the pre-fix `environment.py` value (206.88) on both | Re-check `case/0/radiator_plate/T`'s `Ta` value against the C3 seed check; confirm `environment.py --altitude 2500 ...` prints 107.74, not 206.88 |

---

# Part E — The prompt to give with this runbook

```
You are executing OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_HOT.md Part C in this repository.
Study slug: balloon-ttp/transient-0-40km-hot.

GOAL
Same 30 W payload, hardware and 0->40 km / 9600 s ascent as the cold-case study
(balloon-ttp/transient-0-40km), but with radiator_plate sun-facing (absorbed solar +
albedo flux applied) while radiator_plate_2 stays shaded. Determine whether sun
exposure meaningfully changes the peak die/cold-plate temperature versus the cold
case's measured 71.3 C / 72.1 C.

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
- Copy BOTH the manifest AND the mesh directory from outputs/balloon-ttp/transient-0-40km
  in C1 -- do not re-run inspect_step.py or mesh_assembly.py, they would revert the
  component renames / produce a mesh that isn't identical to the cold case's.
- In C3, confirm environment.py prints absorbed_flux_W_m2 = 107.74, not 206.88, before
  pasting it into radiator_plate's BC -- the higher number is a known, fixed bug
  (double-counted Earth IR). radiator_plate_2 keeps absorbed_flux_W_m2 = 0.0 (shaded).
- disable_fpe_trap must be true in the solver block (C4) -- same CAD sliver defect as
  every other study on this hardware.
- In C7, run the prune snippet between stages or per-stage cost grows.
- Stage end times must land on multiples of the 120 s write interval.

Start with C0.
```

---

## Reference — files this procedure touches

| Path | Role |
| --- | --- |
| [inputs/balloon-ttp/spaced out rad+box.step](../../inputs/balloon-ttp/spaced%20out%20rad+box.step) | CAD source, 12 solids |
| `outputs/balloon-ttp/transient-0-40km/assembly/manifest.json`, `.../mesh/` | Source manifest and mesh — copied into this study in C1 |
| [.github/skills/conjugate_heat_transfer/scripts/environment.py](../../.github/skills/conjugate_heat_transfer/scripts/environment.py) | Absorbed-flux calculator — carries the C-BUG fix |
| [stage_transient_bcs.py](../../stage_transient_bcs.py) | Altitude-indexed BC restaging, reused unmodified |
| [transient_history.py](../../transient_history.py) | CSV/PNG assembly across restart segments, reused unmodified |
| `outputs/balloon-ttp/transient-0-40km-hot/` | This study's manifest, case, figures, and reports |
