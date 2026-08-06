# Runbook — Local Ollama (`cfd-qwen`) driving a 60-Minute Dwell at 40 km, ETP Copper Straps

**Audience:** an operator running a fully local LLM agent against this repository, and
the `cfd-qwen` model itself. Everything below is executable — no cloud API key needed.
This runbook is intended to be run **entirely unattended** via `run_agent.ps1
-AutoApprove` — every command in Part C, start to finish, proposed and executed by
`cfd-qwen` with no human/Claude takeover.

**Target study:** `balloon-ttp/transient-0-40km-dwell-60min-etp-copper` — a
**direct continuation** of the completed ETP-copper ascent
[OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md)
(`balloon-ttp/transient-0-40km-etp-copper`), exactly mirroring how
[OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN.md)
continues the OFHC ascent. The balloon stops ascending, altitude holds at 40 000 m, and
the same 30 W payload — now with **Cu-ETP (C11000) copper straps, κ 386 W/m·K** instead
of OFHC copper (κ 390) — is solved for another 3600 s (60 min) from the ETP ascent's
actual solved t = 9600 s field state.

**Why this study exists.** The ETP-vs-OFHC ascent comparison already found the strap
material makes essentially no difference at t = 9600 s (+0.06 K at the die, see that
study's report). This dwell continuation checks whether that holds over another hour at
a fixed altitude, or whether the small per-second conduction penalty compounds into
something larger given enough time to reach a new quasi-steady state — the answer is
not assumed, it's measured in C8/C9 below, against the OFHC dwell study's own solved
`balloon-ttp/transient-0-40km-dwell-60min` (already completed: peak values available in
that study's `report/report.md` and `figures/transient_T_history.csv`).

**Status: this runbook has not been executed yet** at the time of writing.

## What this study changes vs. the OFHC dwell baseline

| | OFHC dwell (`transient-0-40km-dwell-60min`) | This runbook (`...-dwell-60min-etp-copper`) |
| --- | --- | --- |
| Source ascent study | `transient-0-40km` (OFHC straps) | **`transient-0-40km-etp-copper`** (ETP straps) |
| `copper_strap_left/right` material | `copper`, override `rho 8940, kappa 390` | **`copper_etp`** library entry (κ 386), no override needed — already correct in the copied manifest |
| Starting state | Ascent's solved t = 9600 s field, OFHC straps | **ETP ascent's own solved t = 9600 s field** — a different field, not just a relabelled copy |
| Altitude | Fixed at 40 000 m | Fixed at 40 000 m (unchanged) |
| Duration solved | 3600 s (60 min), 3 × 1200 s segments | unchanged |
| `end_time_s` | 13200 | unchanged |
| Everything else (CAD, other materials, 30 W load, TCR, `deltaT_s`, `disable_fpe_trap`) | — | identical |

## Part A — Ollama + `cfd-qwen`

```powershell
.\ollama\run_agent.ps1 -SelfTest -Runbook OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN_ETP_COPPER.md
```

Expect the standard readiness signature (Ollama up, `cfd-qwen` built, PASS on the C0
environment check). Rebuild if needed: `ollama create cfd-qwen -f ollama\Modelfile.cfd`.

**Driving this fully unattended (the point of this run):**

```powershell
.\ollama\run_agent.ps1 -AutoApprove -Runbook OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN_ETP_COPPER.md `
  -TranscriptPath ollama\transcripts\transient-0-40km-dwell-60min-etp-copper.log -MaxTurns 150
```

`run_agent.ps1`'s `-AutoApprove` mode executes every proposed command without a
keystroke (the installer hard-block stays active regardless), and now also
**proactively injects a clarifying note the instant a known-benign warning appears in a
command's output** — specifically the `checkMesh reported failures` warning this CAD
always produces (see C5) — *before* the model has a chance to misread it as something
to fix. This was added after three earlier attempts on the sibling ETP-copper ascent
runbook got stuck inventing nonexistent mesh-repair scripts at exactly this warning; see
`agent-data/lessons.md` L012 for the full history. A command-history loop-guard is still
the fallback safety net if the injection doesn't land.

## Part B — What to pull onto the machine

Same solver stack as every other study here (already installed and verified — **never
run an installer**, see C0). Nothing new to install.

| Item | Location | Notes |
| --- | --- | --- |
| Source manifest, surfaces, mesh | `outputs/balloon-ttp/transient-0-40km-etp-copper/assembly/`, `.../mesh/` | Copied wholesale in C1 — materials are **already** `copper_etp`, no reassignment needed this time |
| **Source solved state** | `outputs/balloon-ttp/transient-0-40km-etp-copper/case/9600/` | The ETP ascent's actual field data — copied wholesale in C1, must exist and be complete before starting |
| Staging tool | [stage_transient_bcs.py](stage_transient_bcs.py) | Reused unmodified, called with `--altitude 40000` throughout |
| Post-processing | [transient_history.py](transient_history.py) | Reused unmodified |
| Comparison baseline | `outputs/balloon-ttp/transient-0-40km-dwell-60min/report/report.md`, `.../figures/transient_T_history.csv` | The OFHC dwell study's own solved results — the comparison target for C8/C9 |

---

# Part C — Conducting the simulation

Run every command from the repository root. The interpreter is always
`.venv\Scripts\python.exe`. Study slug: `balloon-ttp/transient-0-40km-dwell-60min-etp-copper`.

## C0 — Environment gate (do not install anything)

```powershell
.venv\Scripts\python.exe .github\skills\solver_environment\scripts\check_environment.py
```

**Gate:** output ends with `READY: full CFD/FEA toolchain available.` Ignore
`setup_report.json` if it disagrees — it is a stale artifact.

## C1 — Seed manifest, mesh AND the ETP ascent's solved t=9600 s state

```powershell
$S = "balloon-ttp/transient-0-40km-dwell-60min-etp-copper"
$SRC = "outputs\balloon-ttp\transient-0-40km-etp-copper"
$new = "outputs\$S"

if (-not (Test-Path "$SRC\case\9600")) { throw "Source ETP ascent study has no solved 9600s state -- it must be completed first." }

New-Item -ItemType Directory -Force "$new\assembly" | Out-Null
Copy-Item "$SRC\assembly\manifest.json" "$new\assembly\manifest.json"
Copy-Item "$SRC\assembly\surfaces.json" "$new\assembly\surfaces.json"
Copy-Item "$SRC\mesh" "$new\mesh" -Recurse

.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study $S --solver '{"mode":"transient","end_time_s":13200,"write_interval_s":120,"deltaT_s":2.0,"n_procs":4,"p_ref_Pa":101325,"T_init_C":20,"disable_fpe_trap":true}'
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study $S --validate
```

**No material reassignment needed here** — unlike the ascent runbook's C1, the copied
manifest already has `copper_strap_left/right` set to `copper_etp` (it came from the
already-solved ETP ascent study). Confirm this before proceeding:

```powershell
.venv\Scripts\python.exe -c "
import json
m = json.load(open('outputs/balloon-ttp/transient-0-40km-dwell-60min-etp-copper/assembly/manifest.json'))
for k in ('copper_strap_left', 'copper_strap_right'):
    c = m['components'][k]
    print(k, c['material'], c['overrides'])
print('end_time_s:', m['solver']['end_time_s'])
"
```

**Expect:** both straps `copper_etp {}`, `end_time_s: 13200`.

## C4/C5 — Build the case, then drop in the ETP ascent's solved state

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

**You will see a `checkMesh` WARNING here.** It is expected — see the driver note in
Part A and C-CHECKMESH below. Do not try to fix the mesh. Proceed to the next command.

Verify the mesh is identical to the ETP ascent source before trusting the field copy:

```powershell
Select-String -Path "outputs\balloon-ttp\transient-0-40km-dwell-60min-etp-copper\prepare_summary.json" -Pattern '"cells"'
Select-String -Path "outputs\balloon-ttp\transient-0-40km-etp-copper\prepare_summary.json" -Pattern '"cells"'
```

**Gate:** the two `"cells"` values must match exactly (both should read `73960`). If
they don't, stop — do not copy the field data below onto a mismatched mesh.

Copy the ETP ascent's actual solved t = 9600 s field state in as this case's restart
point:

```powershell
Copy-Item "outputs\balloon-ttp\transient-0-40km-etp-copper\case\9600" "outputs\balloon-ttp\transient-0-40km-dwell-60min-etp-copper\case\9600" -Recurse
Get-ChildItem "outputs\balloon-ttp\transient-0-40km-dwell-60min-etp-copper\case" -Directory | Where-Object { $_.Name -match '^[\d.]+$' }
```

**Gate:** should list exactly `0` and `9600`.

## C-CHECKMESH — Why the checkMesh WARNING is expected (read this before C5, not after)

This is the same CAD (`spaced out rad+box.step`) every study in this project uses, and
it has the same documented defect: a ~3e-9 m² sliver face on `interface_plate` that
produces high-aspect-ratio and non-orthogonality flags in `checkMesh` (`ok: false`) but
**no `FOAM FATAL ERROR`**. `disable_fpe_trap: true` (already set in the solver block
above) is the correct handling — solid conduction under implicit Euler is
unconditionally stable regardless of that diagnostic number. There is no
`fix_mesh_regions.py`, `refine_mesh.py`, or `smooth_mesh.py` in this repo, and no mesh
regeneration is needed or wanted. If a checkMesh WARNING appears in C5's output: state
that it's the known, expected result, and move directly to the next command below.

## C-ALT — Restage to the exact 40 000 m dwell state

Stage 8 of the ascent used 37 500 m (a midpoint approximation while still climbing);
this study sits at exactly 40 000 m throughout, so restage once before running:

```powershell
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper --altitude 40000
```

**Expect** (atmosphere at exactly 40 000 m): `T_air_K ≈ 250.35`, and for each radiator
patch `h_conv_W_m2K ≈ 0.53`.

## C6 — Smoke test

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper --end-time 9610 --time-limit 300
```

**Gate:** `completed: true`, `final_time: 9610.0`, `n_steps: 5` — 5 steps of 2 s from
the 9600 s restart point, **not** from 0. If `n_steps` is anything else, or the log's
first `Time =` line is `0` rather than `9602`, the restart didn't take — stop and
recheck C1/C5. This smoke window is inside the first real segment below, so no case
reset is needed — continue straight to C7.

## C7 — The 60-minute dwell (9600 → 13200 s), 3 segments

```powershell
# segment 1 : 9600 -> 10800 s
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper --end-time 10800

# segment 2 : 10800 -> 12000 s
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper --altitude 40000
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper --end-time 12000

# segment 3 : 12000 -> 13200 s
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper --altitude 40000
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper --end-time 13200
```

**Per-segment gate:** `completed: true` at the segment end time; the log's first
`Time =` line for the segment is the previous segment's end (not 0 and not 9600
again); no `FOAM FATAL`/`bounding` messages.

**Prune between segments** (keep only the latest and `0` — `9600` is not exempt once a
later time dir exists):

```powershell
$case = "outputs\balloon-ttp\transient-0-40km-dwell-60min-etp-copper\case"
$keep = (Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' } |
         Sort-Object { [double]$_.Name } | Select-Object -Last 1).Name
Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' -and $_.Name -ne $keep -and $_.Name -ne '0' } | Remove-Item -Recurse -Force
"kept: $keep"
```

**Runtime estimate.** The OFHC dwell study solved this in ~127 s of pure solve time
(from its own `run_summary.json`); expect similar here since the mesh, `deltaT_s`, and
step count are identical — call it a few minutes total including decompose/reconstruct
overhead per segment.

## C8 — Post-processing and verification

```powershell
.venv\Scripts\python.exe transient_history.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper --highlight jetson_module,interface_plate,copper_strap_left,radiator_plate,radiator_plate_2
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper
```

**Verification gates (do not report results until all pass):**

| # | Check | Pass criterion |
| --- | --- | --- |
| 1 | Heat still injected | `jetson_heat_source` ≈ 30 W throughout |
| 2 | Box adiabatic | `styrofoam_box`-adjacent external patch integrates to 0.0 W |
| 3 | Temperatures bounded | No region colder than ~−65 °C (40 km sky sink) or hotter than ~200 °C |
| 4 | Restart continuity from the ETP ascent | The first temperature sample at t = 9600 s in this study's `transient_T_history.csv` must match the **ETP ascent study's own final value** (71.334 °C jetson_module / 72.115 °C interface_plate) to within ~0.3 K |
| 5 | Trend at the top | Plateauing, still climbing, or turning over — report what's observed, not assumed |
| 6 | Interface balance | Each coupled interface in `interfaces_W` agrees within a few percent between its two sides |
| 7 | **Material comparison, the actual point of this study** | Compare this study's t = 13200 s peak `jetson_module`/`interface_plate` values against the **OFHC dwell study's own solved values** in `outputs/balloon-ttp/transient-0-40km-dwell-60min/figures/transient_T_history.csv` (its final row) — report the delta in K, and whether it grew, shrank, or stayed the same relative to the +0.06 K seen at t = 9600 s in the ascent comparison |

## C9 — Report

```powershell
.venv\Scripts\python.exe .github\skills\report_generation\scripts\build_report.py --study balloon-ttp/transient-0-40km-dwell-60min-etp-copper --title "Stratospheric Payload Thermal Analysis: 60-Minute Dwell at 40 km, 30 W, Cu-ETP Straps"
```

Then edit the executive summary by hand. State explicitly:

* Peak `jetson_module`/`interface_plate` temperature at t = 13200 s, **and the delta
  against the OFHC dwell study's own solved values at the same time** — this delta,
  and whether it grew relative to the ascent's +0.06 K, is the headline number.
* Whether the trend (gate 5) indicates approach to a steady state at 40 km dwell, for
  both material choices consistently or not.
* All other assumptions/limitations carried unchanged from the ETP ascent and OFHC
  dwell studies — cite those reports rather than restating them.

---

# Part D — Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| C6 smoke test's first `Time =` is `0`, or `n_steps` isn't 5 | The `9600` field directory wasn't actually copied, or `setup_cht_case.py` was re-run after C1's copy | Re-check `case\9600\` exists **after** `setup_cht_case.py` was last run; re-copy if needed |
| `prepare_summary.json`'s cell count doesn't match the ETP ascent study's | Wrong mesh copied, or mesh regenerated instead of reused | Do not copy the field data onto a mismatched mesh — re-copy `mesh/` from the ETP ascent study |
| A checkMesh WARNING appears and the model proposes a fix/refinement command | This is the known, expected warning (see C-CHECKMESH) — the driver injects a clarifying note automatically, but if it's still misread, the loop-guard will catch the resulting command cycle and stop cleanly rather than burn the turn budget | Resume manually from the last successful gate if this happens; see `agent-data/lessons.md` L012 |
| Same failure modes as the ascent runbook otherwise | `FOAM_SIGFPE` abort, fixed-`deltaT` vs `--end-time` window mismatch, stale time-directory pruning | See the ascent runbook's Part D |

---

# Part E — The prompt to give with this runbook

```
You are executing OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN_ETP_COPPER.md Part C
in this repository. Study slug: balloon-ttp/transient-0-40km-dwell-60min-etp-copper.

GOAL
Continue the completed ETP-copper 0->40km ascent study
(balloon-ttp/transient-0-40km-etp-copper) for another 3600 s (60 min) held at a fixed
40000 m altitude, starting from its actual solved t=9600s state, to determine whether
the small (+0.06 K) temperature penalty from Cu-ETP vs OFHC copper straps seen at the
end of the ascent grows, shrinks, or stays the same over an additional hour at fixed
altitude. Compare the final result against the already-completed OFHC dwell study
(balloon-ttp/transient-0-40km-dwell-60min).

ENVIRONMENT -- ALREADY BUILT, NOTHING TO INSTALL
WSL Ubuntu, OpenFOAM v2412 with chtMultiRegion solvers, CalculiX 2.21, Gmsh and all
Python packages are installed and verified. Never run install_solvers.py, setup.ps1,
first_run_setup.py, apt or pip install. C0 is read-only and prints
"READY: full CFD/FEA toolchain available."

KNOWN BENIGN WARNING -- READ BEFORE C5
Setting up the case in C5 will print a checkMesh WARNING (ok: false, high-aspect-ratio
and/or non-orthogonality flags). This is a documented, expected result for this CAD's
known sliver-face defect -- it is NOT a new problem, there is no fix_mesh_regions.py,
refine_mesh.py, or smooth_mesh.py in this repo, and none is needed. If you see this
warning, state that it's the known expected result and move directly to the next
command in Part C. Do not attempt to fix, refine, or regenerate the mesh.

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
- The source ETP ascent study (balloon-ttp/transient-0-40km-etp-copper) MUST already
  have a solved case/9600 directory before C1 -- if it doesn't, stop and say so.
- C1 copies manifest, surfaces AND the case/9600 solved-state directory from the ETP
  ascent study -- materials are already copper_etp in that manifest, no reassignment
  needed (unlike the ascent runbook's C1).
- end_time_s in the manifest is 13200, not 3600 -- time is continuous from the ascent.
- Verify the mesh cell count in C5 matches the ETP ascent study before trusting the
  C1 field-data copy.
- C6's smoke test must show n_steps=5 starting from t=9600, not from 0.
- Altitude is fixed at 40000 m for all of C7.
- C9's report must state the peak-temperature delta against the OFHC dwell study's
  own solved values at t=13200s -- that delta is the actual deliverable.

Start with C0.
```

---

## Reference — files this procedure touches

| Path | Role |
| --- | --- |
| `outputs/balloon-ttp/transient-0-40km-etp-copper/assembly/`, `.../mesh/`, `.../case/9600/` | Source manifest, mesh and solved state — all copied into this study in C1 |
| `outputs/balloon-ttp/transient-0-40km-dwell-60min/report/report.md` | OFHC dwell baseline — the comparison target for this study's C8/C9 |
| [stage_transient_bcs.py](stage_transient_bcs.py) | Reused unmodified |
| [transient_history.py](transient_history.py) | Reused unmodified |
| [ollama/Modelfile.cfd](ollama/Modelfile.cfd) / [ollama/run_agent.ps1](ollama/run_agent.ps1) | `cfd-qwen` build + driver (`-AutoApprove`, proactive known-warning injection, loop-guard) |
| `outputs/balloon-ttp/transient-0-40km-dwell-60min-etp-copper/` | This study's manifest, case, figures, and reports |
