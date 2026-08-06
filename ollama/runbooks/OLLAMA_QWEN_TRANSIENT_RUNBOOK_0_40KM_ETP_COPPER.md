# Runbook — Local Ollama (`cfd-qwen`) driving the 0→40 km Ascent, ETP Copper Straps

**Audience:** an operator running a fully local LLM agent against this repository, and
the `cfd-qwen` model itself. Everything below is executable — no cloud API key needed.

**Target study:** `balloon-ttp/transient-0-40km-etp-copper` — a **material-substitution
re-run** of [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md)
(`balloon-ttp/transient-0-40km`). Every geometry, mesh, boundary condition, contact
resistance, and solver setting is **identical** to that study. The only change: the twin
thermal-strap braids (`copper_strap_left`, `copper_strap_right`) are re-materialed from
OFHC copper to **Cu-ETP (C11000, electrolytic tough-pitch copper)**. This runbook exists
to answer one question — does the strap material choice measurably change the payload's
peak temperature at 40 km — not to re-derive anything already validated by the OFHC run.

**Status: this runbook has not been executed yet** at the time of writing.

## What this study changes vs. the OFHC baseline

| | OFHC baseline (`transient-0-40km`) | This runbook (`transient-0-40km-etp-copper`) |
| --- | --- | --- |
| `copper_strap_left/right` material | `copper` library entry, override `rho: 8940, kappa: 390` (OFHC C10100/C10200, ~101% IACS) | **`copper_etp` library entry** (Cu-ETP / C11000, ~100% IACS): `rho: 8940, kappa: 386, cp: 385` — see `agent-data/materials_library.json` |
| Thermal conductivity of the strap | 390 W/m·K | **386 W/m·K** (≈1% lower — CDA/ASM handbook typical values for annealed Cu-ETP vs OFHC at room temp; the oxygen inclusions in ETP shorten the electron mean free path slightly) |
| Density, specific heat | ρ 8940 kg/m³, cp 385 J/kg·K | **unchanged** — neither is meaningfully composition-sensitive between these two coppers |
| Geometry, mesh, CAD | `spaced out rad+box.step`, 12 solids | **identical — mesh copied wholesale, not regenerated** |
| Everything else (30 W load, TCR, altitude profile, `deltaT_s`, `disable_fpe_trap`, radiation, end_time) | — | identical |

**Why a ~1% conductivity delta might still matter or might not.** The strap is not the
dominant resistance in the die-to-radiator path — C-TCR below shows the two bolted
joints per side (1.58 K/W each, in parallel across the twin straps → 1.58 K/W combined)
dwarf the strap's own conduction resistance (`L/(kappa*A)`, a few hundredths of a K/W for
this geometry). A 1% change in strap `kappa` should therefore produce a change in peak
temperature far smaller than 1% of the ~50 K die-to-radiator ΔT — this runbook's C9 report
must state the **observed** number, not this estimate.

# Part A — Ollama + `cfd-qwen`

Identical setup to the sibling runbooks — nothing to redo. Verify in one command,
executing nothing:

```powershell
.\ollama\run_agent.ps1 -SelfTest -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md
```

Expect the same readiness signature documented in the sibling runbooks: Ollama on
`127.0.0.1:11434`, `cfd-qwen` built from `qwen2.5-coder:7b` (32k context, temp 0.1). If
`ollama list` doesn't show `cfd-qwen`, rebuild it:

```powershell
ollama create cfd-qwen -f ollama\Modelfile.cfd
```

**Driving this unattended.** `run_agent.ps1`'s default loop gates every command on a
`Read-Host` prompt, which needs a real interactive console. For an unattended run, use
the `-AutoApprove` mode added alongside this runbook: the model still proposes one
command per turn and still hits the same installer hard-block, but each proposed command
executes without a keystroke, and the full transcript is written to `-TranscriptPath`
for after-the-fact review — supervision moves from per-command approval to transcript
review plus the verification gates already built into this document.

```powershell
.\ollama\run_agent.ps1 -AutoApprove -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md `
  -TranscriptPath ollama\transcripts\transient-0-40km-etp-copper.log -MaxTurns 200
```

# Part B — What to pull onto the machine

Same solver stack as every other study here (already installed and verified — **never
run an installer**, see C0). Nothing new to install.

| Item | Location | Notes |
| --- | --- | --- |
| Source manifest, surfaces, mesh | `outputs/balloon-ttp/transient-0-40km/assembly/`, `.../mesh/` | Copied wholesale in C1 — **mesh is reused unchanged**, geometry didn't change |
| Materials library | `agent-data/materials_library.json` → `solids.copper_etp` | New entry added alongside this runbook — Cu-ETP / C11000 properties, see table above |
| Staging tool | [stage_transient_bcs.py](../../stage_transient_bcs.py) | Reused unmodified, altitude-indexed exactly as the baseline study |
| Post-processing | [transient_history.py](../../transient_history.py) | Reused unmodified |

---

# Part C — Conducting the simulation

Run every command from the repository root. The interpreter is always
`.venv\Scripts\python.exe`. Study slug: `balloon-ttp/transient-0-40km-etp-copper`.

## C0 — Environment gate (do not install anything)

```powershell
.venv\Scripts\python.exe .github\skills\solver_environment\scripts\check_environment.py
```

**Gate:** output ends with `READY: full CFD/FEA toolchain available.` If it doesn't,
stop and report — do not run `install_solvers.py`, `setup.ps1`, `first_run_setup.py`,
`apt`, `pip install`, or `winget install`. Ignore `setup_report.json` if it claims
otherwise; it is a stale artifact, not the authority.

## C1 — Seed manifest, surfaces and mesh from the OFHC ascent study, then swap the strap material

```powershell
$S = "balloon-ttp/transient-0-40km-etp-copper"
$SRC = "outputs\balloon-ttp\transient-0-40km"
$new = "outputs\$S"

New-Item -ItemType Directory -Force "$new\assembly" | Out-Null
Copy-Item "$SRC\assembly\manifest.json" "$new\assembly\manifest.json"
Copy-Item "$SRC\assembly\surfaces.json" "$new\assembly\surfaces.json"
Copy-Item "$SRC\mesh" "$new\mesh" -Recurse

.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study $S `
  --component copper_strap_left --material copper_etp --overrides '{}'
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study $S `
  --component copper_strap_right --material copper_etp --overrides '{}'
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study $S --validate
```

Everything else in the manifest — all other component materials, the four
`thermal_contact_resistances` joints, the three boundary patches (`jetson_heat_source`,
`radiator_plate_outer`, `radiator_plate_2_outer`, `foam_box_outer`), and the solver
block — carries over unchanged from the copied manifest. Confirm only the two strap
components changed:

```powershell
.venv\Scripts\python.exe -c "
import json
m = json.load(open('outputs/balloon-ttp/transient-0-40km-etp-copper/assembly/manifest.json'))
for k in ('copper_strap_left', 'copper_strap_right'):
    c = m['components'][k]
    print(k, c['material'], c['overrides'])
"
```

**Expect:** both straps report `copper_etp {}`.

## C2 — Ascent profile and atmosphere (unchanged from the OFHC baseline)

Identical 8×1200 s altitude-indexed staging, same US76 atmosphere table, same 4.1667 m/s
assumed ascent rate — see
[OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md)'s C2
for the full table and its cross-check against an independent source. Nothing to redo
here; the copied manifest already carries the correct boundary-condition structure, only
the strap material changed in C1.

## C3 — Boundary conditions (unchanged, carried over from the copy)

Already present in the copied manifest (`jetson_heat_source` at 8181.44 W/m² = 30 W over
the 0.003666837 m² TTP contact face, both radiator patches on `altitude_environment`
seeded at 2500 m, `foam_box_outer` adiabatic). Confirm nothing was disturbed by C1:

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study $S --list
```

## C-TCR — Thermal contact resistances (unchanged, carried over from the copy)

Same joint budget as the baseline study — nothing to re-derive:

| Joint | R_total [K/W] | Material |
| --- | --- | --- |
| `interface_plate` ↔ `jetson_heatsink` | 0.10 | PTM7950 phase-change material |
| `interface_plate` ↔ `connector_block_left` | 1.58 | bolted joint |
| `interface_plate` ↔ `connector_block_right` | 1.58 | bolted joint |
| `copper_strap_left` ↔ `radiator_bracket_left` | 1.58 | bolted joint |
| `copper_strap_right` ↔ `radiator_bracket_right` | 1.58 | bolted joint |

These joint resistances dominate the die-to-radiator path (see the note under "What
this study changes" above) — the ETP-vs-OFHC delta this runbook measures is expected to
be small relative to them.

## C4 — Solver block (unchanged, carried over from the copy)

Already present in the copied manifest: `mode: transient`, `end_time_s: 9600`,
`write_interval_s: 120`, `deltaT_s: 2.0` fixed (solid-only assembly), `disable_fpe_trap:
true` (required for this CAD's known sliver face — see the baseline runbook's C-FPE for
why). Confirm:

```powershell
.venv\Scripts\python.exe -c "import json; print(json.load(open('outputs/balloon-ttp/transient-0-40km-etp-copper/assembly/manifest.json'))['solver'])"
```

**Expect:** `{'mode': 'transient', 'end_time_s': 9600, 'write_interval_s': 120, 'deltaT_s': 2.0, 'n_procs': 4, 'p_ref_Pa': 101325, 'T_init_C': 20, 'disable_fpe_trap': True}`.

## C5 — Case setup (mesh reused, NOT regenerated)

The mesh is geometry-derived, not material-derived — reuse it directly rather than
re-running `mesh_assembly.py`:

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

Expect the same known `checkMesh` warning as the baseline study (high-aspect-ratio only,
non-orthogonality reported "OK") — proceed, it's the known CAD defect, not a new problem.
**Do not re-run `setup_cht_case.py`, `checkMesh`, or `--validate` again to try to
resolve or re-confirm this warning — it will not go away and does not need to. Move
directly to the confirmation commands below, then to C6.** (This warning is exactly
where an earlier attempt at this runbook got stuck in a re-run loop.)
Confirm the transient extras and time-stepping landed, and that the mesh cell count
matches the baseline study exactly (same CAD, same `--factor`):

```powershell
Select-String -Path outputs\balloon-ttp\transient-0-40km-etp-copper\case\system\controlDict -Pattern 'application|endTime|deltaT|adjustTimeStep|writeInterval'
Select-String -Path outputs\balloon-ttp\transient-0-40km-etp-copper\prepare_summary.json -Pattern '"cells"'
Select-String -Path outputs\balloon-ttp\transient-0-40km\prepare_summary.json -Pattern '"cells"'
```

**Gate:** the two `"cells"` values must match exactly. If they don't, stop — something
about the mesh copy or regeneration diverged from the baseline and the comparison would
no longer be apples-to-apples.

Also confirm the strap's `thermophysicalProperties` picked up the new material:

```powershell
Select-String -Path outputs\balloon-ttp\transient-0-40km-etp-copper\case\constant\copper_strap_left\thermophysicalProperties -Pattern 'kappa|rho|Cp'
```

**Expect:** `kappa 386`, `rho 8940`, `Cp 385` — not `kappa 390`.

## C6 — Smoke test

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 10 --time-limit 300
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study $S
```

**Gate:** `completed: true`, `final_time: 10.0`, `n_steps: 5`, `jetson_heat_source ≈
30 W`, every `*_wall` external flux `0.0`. Reset to a clean t=0 before the real run:

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study $S --reuse-mesh
```

## C7 — The staged ascent (0 → 9600 s), identical staging to the baseline study

```powershell
# stage 1 : 0 -> 1200 s   (BCs already at 2500 m from the copied manifest)
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

**Per-stage gate — check all four before starting the next stage** (identical criteria
to the baseline runbook's C7):

1. `run_summary.json` shows `"completed": true` and `final_time` equal to the segment
   end (1200, 2400, …, 9600).
2. The first `Time =` line for the segment in `case\log.chtMultiRegionFoam` is the
   previous segment's end time, not 0.
3. No `FOAM FATAL` or `bounding` messages in the log.
4. `stage_transient_bcs.py`'s printed `T_ref_K` tracks the radiator's actual solved
   temperature.

**Prune between stages** (identical to the baseline study — `run_cht_case.py`
reprocesses every stored time directory on each call):

```powershell
$case = "outputs\balloon-ttp\transient-0-40km-etp-copper\case"
$keep = (Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' } |
         Sort-Object { [double]$_.Name } | Select-Object -Last 1).Name
Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' -and $_.Name -ne $keep -and $_.Name -ne '0' } | Remove-Item -Recurse -Force
"kept: $keep"
```

**Runtime estimate.** Same mesh, same fixed `deltaT_s = 2.0`, same 4800 steps as the
baseline study — expect the same **~20–25 minutes total** with pruning applied between
stages. Run this as a background process and check `case\log.chtMultiRegionFoam` rather
than waiting on the foreground call.

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
| 3 | Temperatures bounded | No region colder than ~−65 °C (37 500 m sky sink) or hotter than ~200 °C |
| 4 | Restart continuity | No temperature discontinuity across a segment boundary in `transient_T_history.csv` |
| 5 | Thermal lag present | `jetson_module`/`interface_plate` rise smoothly, not stepwise |
| 6 | Interface balance | Each coupled interface in `interfaces_W` agrees within a few percent between its two sides |
| 7 | **Material comparison, the actual point of this study** | Compare `jetson_module` and `interface_plate` peak temperature (t = 9600 s) and radiator mean temperature / rejection against the OFHC baseline's own solved values (`outputs/balloon-ttp/transient-0-40km/report/report.md` — `jetson_module` 71.3 °C, `interface_plate` 72.1 °C, radiators ≈8 °C mean, ≈24.2 W rejected vs 30.1 W injected). Report the delta in K/W, not just "similar" or "different" |

## C9 — Report

```powershell
.venv\Scripts\python.exe .github\skills\report_generation\scripts\build_report.py --study $S --title "Stratospheric Payload Transient Thermal Analysis: 0-40 km, 160 min, 30 W, Cu-ETP Straps"
```

Then edit the executive summary by hand. State explicitly:

* Peak `jetson_module`/`interface_plate` temperature at t = 9600 s, **and the delta
  against the OFHC baseline's own solved 71.3 °C / 72.1 °C** — this delta is the
  headline number this whole runbook exists to produce.
* Whether the observed delta is consistent with the ~1% conductivity difference and the
  joint-resistance-dominated path noted above (small, likely sub-0.5 K), or whether
  something larger showed up that needs investigating before trusting it.
* Radiator mean temperature and total radiative rejection at t = 9600 s, compared to the
  baseline's 24.2 W / ≈8 °C.
* All other assumptions/limitations are unchanged from the OFHC baseline — cite
  `outputs/balloon-ttp/transient-0-40km/report/report.md` rather than restating them
  (assumed 4.1667 m/s ascent rate, `altitude_environment` BC from ground level, adiabatic
  box, no mesh independence, known CAD sliver defect).

---

# Part D — Troubleshooting

Identical failure modes to the OFHC baseline runbook — see its Part D. One addition
specific to this study:

| Symptom | Cause | Fix |
| --- | --- | --- |
| `thermophysicalProperties` for the strap still shows `kappa 390`/`rho 8940` from the old override rather than `kappa 386` | C1's `assign_materials.py --material copper_etp` calls were skipped, or `setup_cht_case.py` was run before C1 completed | Re-run both `--component copper_strap_left/right --material copper_etp --overrides '{}'` calls, confirm with the C1 grep, then re-run `setup_cht_case.py --reuse-mesh` |
| Mesh cell count in C5 doesn't match the baseline study's | Mesh wasn't copied wholesale in C1, or `mesh_assembly.py` was run (regenerating a mesh that may differ slightly in cell count/ordering even on identical geometry) | Do not regenerate the mesh — re-copy `outputs\balloon-ttp\transient-0-40km\mesh` wholesale |

---

# Part E — The prompt to give with this runbook

```
You are executing OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md Part C in this
repository. Study slug: balloon-ttp/transient-0-40km-etp-copper.

GOAL
Re-run the completed 0->40km/160min/30W ascent study (balloon-ttp/transient-0-40km),
changing ONLY the twin copper thermal-strap material from OFHC copper (kappa 390 W/m-K)
to Cu-ETP/C11000 electrolytic tough-pitch copper (kappa 386 W/m-K, new "copper_etp"
library entry), to determine whether the strap material choice measurably changes the
payload's peak temperature at 40 km. Geometry, mesh, boundary conditions, contact
resistances and solver settings are all unchanged from the OFHC baseline.

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
- C1 copies manifest, surfaces AND mesh from outputs/balloon-ttp/transient-0-40km --
  the mesh is reused unchanged, do not regenerate it (geometry didn't change).
- C1 must reassign BOTH copper_strap_left and copper_strap_right to material
  "copper_etp" with empty overrides {} -- verify with the printed grep before proceeding.
- C5's mesh cell count must match the baseline study's prepare_summary.json exactly --
  if it doesn't, stop, don't trust a field copy or comparison on a mismatched mesh.
- disable_fpe_trap must stay true in the solver block -- same CAD sliver defect as the
  baseline study.
- C9's report must state the peak-temperature delta against the OFHC baseline's own
  solved 71.3 C (jetson_module) / 72.1 C (interface_plate) values -- that delta is the
  actual deliverable of this runbook.

Start with C0.
```

---

## Reference — files this procedure touches

| Path | Role |
| --- | --- |
| `outputs/balloon-ttp/transient-0-40km/assembly/`, `.../mesh/` | Source manifest, surfaces and mesh — copied wholesale into this study in C1 |
| `agent-data/materials_library.json` → `solids.copper_etp` | New material entry (Cu-ETP / C11000), added alongside this runbook |
| [stage_transient_bcs.py](../../stage_transient_bcs.py) | Altitude-indexed BC restaging, reused unmodified |
| [transient_history.py](../../transient_history.py) | CSV/PNG assembly across restart segments, reused unmodified |
| [ollama/Modelfile.cfd](../Modelfile.cfd) / [ollama/run_agent.ps1](../run_agent.ps1) | `cfd-qwen` build + driver (`-AutoApprove` mode for unattended runs) |
| `outputs/balloon-ttp/transient-0-40km/report/report.md` | OFHC baseline — the comparison target for this study's C8/C9 |
| `outputs/balloon-ttp/transient-0-40km-etp-copper/` | This study's manifest, case, figures, and reports |
