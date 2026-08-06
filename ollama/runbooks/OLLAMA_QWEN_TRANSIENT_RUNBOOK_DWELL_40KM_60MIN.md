# Runbook — Local Ollama (`cfd-qwen`) driving a 60-Minute Dwell at 40 km

**Audience:** an operator running a fully local LLM agent against this repository, and
the `cfd-qwen` model itself. Everything below is executable — no cloud API key needed.

**Target study:** `balloon-ttp/transient-0-40km-dwell-60min` — a **direct continuation**
of the completed cold-case ascent
[OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md)
(`balloon-ttp/transient-0-40km`). That study answered "what does the payload reach by
the time it gets to 40 km." This one answers "what happens next" — the balloon stops
ascending, altitude holds at 40 000 m, and the same 30 W payload is solved for another
3600 s (60 min) from the exact solved thermal state the ascent ended in.

**Why a separate study slug instead of just running the ascent study longer.** The
ascent study's own report already states `9600 s` as its endpoint and reports numbers
against that. Continuing it in place would silently invalidate that report. Cloning the
manifest, mesh **and the solved t = 9600 s field state** into a new study directory
keeps both deliverables intact and independently reproducible — see C1 for exactly
what is copied and why it's valid to drop the field data in unmodified.

**Status: this runbook has not been executed yet** at the time of writing.

## What this study changes vs. the ascent

| | Ascent (`transient-0-40km`) | This runbook (`transient-0-40km-dwell-60min`) |
| --- | --- | --- |
| Starting state | `T_init_C: 20` uniform at t = 0 | **The ascent's actual solved field at t = 9600 s**, copied in, not re-initialised |
| Altitude | Changes every 1200 s, 8 segments, 0 → 40 000 m | **Fixed at 40 000 m** for the entire run |
| Duration solved | 9600 s (160 min) | **3600 s (60 min)**, run as 3 × 1200 s segments purely to refresh the radiative linearisation reference temperature — altitude itself never changes |
| `end_time_s` in the manifest | 9600 | **13200** (9600 + 3600) — time is a continuous clock carried over from the ascent, not reset to 0 |
| Everything else (CAD, materials, 30 W load, TCR, `deltaT_s`, `disable_fpe_trap`) | — | identical |

# Part A — Ollama + `cfd-qwen`

Identical setup to the sibling runbooks — nothing to redo:

```powershell
.\ollama\run_agent.ps1 -SelfTest -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN.md
```

**Driver note:** `run_agent.ps1` gates every command on a `Read-Host` prompt. If you're
driving this non-interactively, execute Part C's commands yourself.

# Part B — What to pull onto the machine

Same solver stack as every other study here (already installed and verified — **never
run an installer**, see C0). Nothing new to install.

| Item | Location | Notes |
| --- | --- | --- |
| Source manifest + mesh | `outputs/balloon-ttp/transient-0-40km/assembly/`, `.../mesh/` | Copied wholesale in C1 |
| **Source solved state** | `outputs/balloon-ttp/transient-0-40km/case/9600/` | The actual field data this study starts from — copied wholesale in C1, **must exist and be complete** before starting |
| Staging tool | [stage_transient_bcs.py](../../stage_transient_bcs.py) | Reused unmodified, called with `--altitude 40000` throughout (refreshes the linearisation reference temperature only — the altitude argument doesn't change between segments here) |
| Post-processing | [transient_history.py](../../transient_history.py) | Reused unmodified |

---

# Part C — Conducting the simulation

Run every command from the repository root. The interpreter is always
`.venv\Scripts\python.exe`. Study slug: `balloon-ttp/transient-0-40km-dwell-60min`.

## C0 — Environment gate (do not install anything)

```powershell
.venv\Scripts\python.exe .github\skills\solver_environment\scripts\check_environment.py
```

**Gate:** output ends with `READY: full CFD/FEA toolchain available.`

## C1 — Seed manifest, mesh AND the solved t=9600 s state from the ascent study

```powershell
$S = "balloon-ttp/transient-0-40km-dwell-60min"
$SRC = "outputs\balloon-ttp\transient-0-40km"
$new = "outputs\$S"

if (-not (Test-Path "$SRC\case\9600")) { throw "Source study has no solved 9600s state — run the ascent runbook to completion first." }

New-Item -ItemType Directory -Force "$new\assembly" | Out-Null
Copy-Item "$SRC\assembly\manifest.json" "$new\assembly\manifest.json"
Copy-Item "$SRC\assembly\surfaces.json" "$new\assembly\surfaces.json"
Copy-Item "$SRC\mesh" "$new\mesh" -Recurse

.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study $S --solver '{"mode":"transient","end_time_s":13200,"write_interval_s":120,"deltaT_s":2.0,"n_procs":4,"p_ref_Pa":101325,"T_init_C":20,"disable_fpe_trap":true}'
```

`end_time_s: 13200` (not 3600) — `controlDict`'s clock is continuous from the ascent,
matching the time directory names (`9600`, `10800`, ...) this study will produce.
Materials, TCR and the 30 W `jetson_heat_source` BC carry over unchanged from the
copied manifest — nothing else to set in C3 for this study.

## C4/C5 — Build the case, then drop in the ascent's solved state

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

Expect the same known `checkMesh` warning as every study on this CAD. **Verify the
mesh really is identical to the source before trusting the field copy below** — cell
count must match exactly:

```powershell
Select-String -Path "outputs\balloon-ttp\transient-0-40km-dwell-60min\prepare_summary.json" -Pattern '"cells"'
```

**Gate:** must read `73960` (or whatever the ascent study's own `prepare_summary.json`
shows — diff the two if this repo's mesh factor/CAD ever changes). If it doesn't
match, stop — do not copy the field data below onto a different mesh.

Now copy the ascent's actual solved t = 9600 s field state in as this case's starting
point (`chtMultiRegionFoam`'s `startFrom latestTime` will pick this up as the restart
point once it exists alongside `0`):

```powershell
Copy-Item "outputs\balloon-ttp\transient-0-40km\case\9600" "outputs\balloon-ttp\transient-0-40km-dwell-60min\case\9600" -Recurse
Get-ChildItem "outputs\balloon-ttp\transient-0-40km-dwell-60min\case" -Directory | Where-Object { $_.Name -match '^[\d.]+$' }
```

**Gate:** should list exactly `0` and `9600`.

## C-ALT — Restage to the exact 40 000 m dwell state

Stage 8 of the ascent used **37 500 m** (the midpoint of its 35–40 km segment) as its
representative altitude — a reasonable approximation while still climbing, but this
study is not climbing, it's sitting at exactly 40 000 m. Restage once before running:

```powershell
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-40km-dwell-60min --altitude 40000
```

**Expect** (atmosphere at exactly 40 000 m, cross-checked against the ascent study's
own C2 table extrapolation): `T_air_K ≈ 250.35`, and for each radiator patch
`h_conv_W_m2K ≈ 0.53` (slightly below stage 8's 0.60, consistent with thinner air at
the true top vs. the 37 500 m midpoint used to get there).

## C6 — Smoke test

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-40km-dwell-60min --end-time 9610 --time-limit 300
```

**Gate:** `completed: true`, `final_time: 9610.0`, `n_steps: 5` — 5 steps of 2 s from
the 9600 s restart point, **not** from 0. If `n_steps` is anything else, or the log's
first `Time =` line is `0` rather than `9602`, the restart didn't take — stop and
recheck C1/C5 before continuing. This smoke window is inside the first real segment
below, so no case reset is needed afterward — just continue to C7.

## C7 — The 60-minute dwell (9600 → 13200 s), 3 segments

Altitude never changes in this phase; each restage below is purely to refresh the
radiative linearisation reference temperature from the freshly solved field, the same
role it played on every ascent segment.

```powershell
# segment 1 : 9600 -> 10800 s
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-40km-dwell-60min --end-time 10800

# segment 2 : 10800 -> 12000 s
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-40km-dwell-60min --altitude 40000
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-40km-dwell-60min --end-time 12000

# segment 3 : 12000 -> 13200 s
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-40km-dwell-60min --altitude 40000
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-40km-dwell-60min --end-time 13200
```

**Per-segment gate:** `completed: true` at the segment end time; the log's first
`Time =` line for the segment is the previous segment's end (not 0 and not 9600 again);
no `FOAM FATAL`/`bounding` messages.

**Prune between segments** (same snippet as the ascent runbooks, keep only the latest
and `0` — note `9600` is **not** exempt here once a later time dir exists, unlike the
initial `0`, since it's no longer the earliest state worth keeping):

```powershell
$case = "outputs\balloon-ttp\transient-0-40km-dwell-60min\case"
$keep = (Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' } |
         Sort-Object { [double]$_.Name } | Select-Object -Last 1).Name
Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' -and $_.Name -ne $keep -and $_.Name -ne '0' } | Remove-Item -Recurse -Force
"kept: $keep"
```

**Runtime estimate:** 3600 s at the same `deltaT_s = 2.0` fixed-step solid-only solve
as the ascent — roughly a third of the ascent's own ~13 minutes of pure solve time,
call it **~5–8 minutes total** with pruning applied between segments.

## C8 — Post-processing and verification

```powershell
.venv\Scripts\python.exe transient_history.py --study balloon-ttp/transient-0-40km-dwell-60min --highlight jetson_module,interface_plate,copper_strap_left,radiator_plate,radiator_plate_2
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study balloon-ttp/transient-0-40km-dwell-60min
```

**Verification gates (do not report results until all pass):**

| # | Check | Pass criterion |
| --- | --- | --- |
| 1 | Heat still injected | `jetson_heat_source` ≈ 30 W throughout |
| 2 | Box adiabatic | `styrofoam_box`-adjacent external patch integrates to 0.0 W |
| 3 | Temperatures bounded | No region colder than ~−65 °C (40 km sky sink) or hotter than ~200 °C |
| 4 | **Restart continuity from the ascent, not just within this study** | The first temperature sample at t = 9600 s in this study's `transient_T_history.csv` must match the ascent study's own final value (71.3 °C / 72.1 °C peak) to within ~0.3 K — this is the join between the two studies, more important here than the usual inter-segment check |
| 5 | Trend at the top | This is the actual question the study exists to answer: do component temperatures **plateau** (approaching a steady state at fixed altitude), **keep climbing** at roughly the same rate as during ascent (thermal mass still charging, unaffected by altitude having stopped changing), or **turn over and fall**? Report the observed trend, don't assume one |
| 6 | Interface balance | Each coupled interface in `interfaces_W` agrees within a few percent between its two sides, consistent with the ascent study's own ~7% baseline |

## C9 — Report

```powershell
.venv\Scripts\python.exe .github\skills\report_generation\scripts\build_report.py --study balloon-ttp/transient-0-40km-dwell-60min --title "Stratospheric Payload Thermal Analysis: 60-Minute Dwell at 40 km, 30 W"
```

Then edit the executive summary by hand. State explicitly:

* The peak temperature reached by t = 13200 s (end of dwell) and how it compares to the
  ascent's own t = 9600 s value — the delta over the 60-minute hold is the headline
  number.
* Whether the trend (gate 5 above) indicates the assembly is approaching a steady
  state at 40 km, or would keep climbing well past 13200 s if held there longer — say
  which, from what was actually observed, not from extrapolation.
* This study assumes the balloon holds exactly at 40 000 m for the full 60 minutes —
  if the real mission profile continues ascending, descends, or drifts, this doesn't
  apply past the point where altitude actually starts changing again.
* Carries forward all of the ascent study's own assumptions/limitations (constant
  ascent rate to get here, cold/no-sun case, adiabatic box, no mesh independence,
  known CAD sliver defect) — cite that report rather than restating them.

---

# Part D — Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| C6 smoke test's first `Time =` is `0`, or `n_steps` isn't 5 | The `9600` field directory wasn't actually copied into this study's case, or `setup_cht_case.py` was re-run after C1's copy (which wipes and rebuilds the case) | Re-check `case\9600\` exists in this study **after** `setup_cht_case.py` was last run, not before; re-copy if needed |
| `prepare_summary.json`'s cell count doesn't match the ascent study's | Mesh factor or CAD changed since the ascent ran, or the wrong mesh was copied | Do not copy the field data onto a mismatched mesh — either re-copy the correct `mesh/` from the ascent study, or re-run the ascent study first |
| Temperatures at t = 9600 s in this study don't match the ascent study's own final values | Field copy was incomplete (missing a region, or `uniform/` folder) | Re-copy the entire `case\9600\` directory, not individual region subfolders |
| Same failure modes as the ascent runbook otherwise | `FOAM_SIGFPE` abort, fixed-`deltaT` vs `--end-time` window mismatch, stale time-directory pruning | See the ascent runbook's Part D |

---

# Part E — The prompt to give with this runbook

```
You are executing OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN.md Part C in this
repository. Study slug: balloon-ttp/transient-0-40km-dwell-60min.

GOAL
Continue the completed 0->40km ascent study (balloon-ttp/transient-0-40km) for another
3600 s (60 min) held at a fixed 40000 m altitude, starting from its actual solved t=9600s
state (not a fresh 20C initial condition), to determine whether the payload's
temperature trend plateaus, keeps climbing, or turns over once the ascent stops.

ENVIRONMENT -- ALREADY BUILT, NOTHING TO INSTALL
WSL Ubuntu, OpenFOAM v2412 with chtMultiRegion solvers, CalculiX 2.21, Gmsh and all
Python packages are installed and verified. Never run install_solvers.py, setup.ps1,
first_run_setup.py, apt or pip install. C0 is read-only and prints
"READY: full CFD/FEA toolchain available."

PROTOCOL
- One powershell command per turn, in a fenced powershell block, nothing else.
- Wait for the real output before continuing.
- State the current step id (C0..C9) before each command, and the segment number in C7.
- Never state a temperature, flux, residual or runtime you have not seen in output
  that was actually pasted back to you.
- If a command fails, name the cause in one sentence, then issue a corrected command
  -- do not retry verbatim.
- Do not proceed past a failed verification gate. Say what failed and stop.

EXECUTION RULES SPECIFIC TO THIS STUDY
- The source ascent study (balloon-ttp/transient-0-40km) MUST already have a solved
  case/9600 directory before C1 -- if it doesn't, stop and say so rather than starting
  a fresh 20C run under this altitude-only-dwell runbook's assumptions.
- C1 copies manifest, mesh AND the case/9600 solved-state directory -- all three, not
  just the manifest like the other runbooks' C1.
- end_time_s in the manifest is 13200, not 3600 -- time is continuous from the ascent.
- Verify the mesh cell count in C5 matches the source study before trusting the C1
  field-data copy.
- C6's smoke test must show n_steps=5 starting from t=9600, not from 0 -- if it starts
  from 0 the restart didn't take, stop and fix C1/C5 before continuing.
- Altitude is fixed at 40000 m for all of C7 -- the restage calls between segments are
  only refreshing the linearisation reference temperature, not changing altitude.

Start with C0.
```

---

## Reference — files this procedure touches

| Path | Role |
| --- | --- |
| `outputs/balloon-ttp/transient-0-40km/assembly/`, `.../mesh/`, `.../case/9600/` | Source manifest, mesh and solved state — all three copied into this study in C1 |
| [stage_transient_bcs.py](../../stage_transient_bcs.py) | Reused unmodified, called at a fixed altitude to refresh the linearisation reference temperature only |
| [transient_history.py](../../transient_history.py) | Reused unmodified |
| `outputs/balloon-ttp/transient-0-40km-dwell-60min/` | This study's manifest, case, figures, and reports |
