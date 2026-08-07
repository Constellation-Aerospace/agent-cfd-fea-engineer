# Runbook — Local Ollama (`cfd-qwen`) driving the Shorter-Strap 3-Hour Mission (0→40 km ascent + 60-min dwell)

**Audience:** an operator running a fully local LLM agent against this repository, and
the `cfd-qwen` model itself. Everything below is executable — no cloud API key needed.
This runbook is intended to be run **entirely unattended** via `run_agent.ps1
-AutoApprove` — every command in Part C, start to finish, proposed and executed by
`cfd-qwen` with no human/Claude takeover, **except** the geometry/material/BC setup
(manifest renaming, TCR assignment, radiator inner/outer face split, atmosphere
blending), which is judgment-heavy CAD interpretation that this repo's own
`agent-data/lessons.md` (L012–L017) documents `cfd-qwen` cannot be trusted to do
unattended — see "What Claude already did" below. `cfd-qwen` drives the mechanical,
deterministic part: staging altitude BCs and running the 12 solve segments.

**Target study:** `balloon-ttp/transient-shorter-strap-40km-3hr` — a **new geometry**
(`inputs/balloon-ttp/Shorter straps.step`, shortened TTP straps, radiators restacked
above/below the box instead of split left/right) carried through a **single continuous
3-hour mission**: ascend 0→40 000 m over 2 h at a constant rate, then dwell at 40 000 m
for 1 h, 30 W payload throughout. Ambient temperature below 30 km comes from a
**digitized real sounding** (Kolkata, 12:00 UTC, 19 May 2026) instead of the US76
standard atmosphere every prior study in this project used from ground level;
30–40 km still uses US76, spliced at 30 km. Radiators reject heat from their **outer
face only** — the face touching the box interior is adiabatic, a change from every
prior study in this project, which radiated from the whole non-coupled radiator
surface.

**Status: executed.** `cfd-qwen` completed C0-C3 correctly (environment gate, manifest
verification, BC staging, smoke test) but then conflated the C3 smoke test with the
real segment-1 solve — ran KPIs/pruned/staged segment 2 without ever issuing the
actual `--end-time 900` command — and got stuck retrying the segment-2 staging call.
The driver's 4-repeat loop-guard stopped it cleanly at turn 11 with the case
undamaged (see `outputs/balloon-ttp/PROJECT.md` L016). Claude Sonnet 5 drove the
remaining 12-segment solve directly rather than retry unattended, and in doing so
caught a second, unrelated issue: `write_interval_s: 120` (inherited from prior
studies' 1200 s segments) doesn't divide this study's 900 s segments evenly, so each
segment boundary was only getting a partial field write — fixed to `90` (see
`outputs/balloon-ttp/PROJECT.md` L017) before the real solve. Final result: `report/report.md`
in `outputs/balloon-ttp/transient-shorter-strap-40km-3hr/`.

## What Claude already did (do not repeat these steps)

The following judgment calls are not mechanical and are **out of scope for `cfd-qwen`**
— they are done, and `cfd-qwen` should treat their outputs as ground truth:

1. **Inspected** `inputs/balloon-ttp/Shorter straps.step` with `inspect_step.py` — 9
   components, none of the old part labels (`connector_block_*`, `copper_strap_*`,
   `radiator_bracket_*`) survive; the CAD export names 3 of the 9 solids just
   `Component1` with no distinguishing sub-label (a real CAD-export gap, not a
   modelling choice — see `step_assembly` SKILL.md's gotcha on unlabeled parts).
2. **Renamed** components directly in `assembly/manifest.json` (renaming does not
   survive a second `inspect_step.py` run — see the same gotcha) to:
   `interface_plate`, `jetson_heatsink`, `jetson_module`, `radiator_plate_top`,
   `radiator_plate_bottom`, `strap_top`, `connector_bottom`, `strap_bottom`,
   `styrofoam_box`. The bottom TTP path is a 2-hop chain
   (`interface_plate → connector_bottom → strap_bottom → radiator_plate_bottom`); the
   top path is a single-hop bridge (`interface_plate → strap_top →
   radiator_plate_top`) — an asymmetry in the CAD itself, not an error.
3. **Assigned materials**: `interface_plate`/`jetson_heatsink` → `aluminum_6061`;
   `jetson_module` → `fr4_pcb` (`cp` override 950); `radiator_plate_top/bottom` →
   `white_paint_aluminum` (emissivity override 0.85); `strap_top`/`connector_bottom`/
   `strap_bottom` → `copper` (OFHC, `rho` 8940 / `kappa` 390 override — **all 3**
   unlabeled shortened-TTP solids are modelled as bulk copper since the CAD gives no
   way to split aluminum-connector from copper-strap material zones; this is
   conservative (higher conductivity than the aluminum it may partly represent) and,
   per the prior `transient-0-40km-etp-copper` study, strap material was already shown
   thermally negligible next to the bolted-joint TCRs); `styrofoam_box` → `eps_foam`
   (`rho` 30 / `cp` 1300 override).
4. **Thermal contact resistances** — same 1.58 K/W bolted-joint budget at every
   connector-to-plate and strap-to-radiator junction, 0.1 K/W PTM7950 at the die, as
   every prior study in this project; re-mapped onto the new component names (see
   `assembly/manifest.json` → `thermal_contact_resistances` and its `notes` key for
   the full reasoning).
5. **Radiator inner/outer face split** (the actual point of this study's radiation
   change): `radiator_plate_top`'s thin axis is Z (bbox z: 0.0802–0.0822 m); its
   `zmax` face is the one further from the payload/box centroid (outer, sky-facing)
   and gets the `altitude_environment` BC; `zmin` (inner, box-facing) is `adiabatic`.
   `radiator_plate_bottom` is the mirror image (`zmin` outer, `zmax` inner). Confirmed
   in the post-mesh smoke test: `radiator_plate_top_inner`/`radiator_plate_bottom_inner`
   external heat flux = **0.0 W** exactly, `..._outer` = −8.03 W each at t=10 s — the
   inner faces are radiating and convecting nothing, as required.
6. **Ambient temperature blend** — added `atmosphere.kolkata_12z_19may_T()` (a
   0.5 km-resolution digitized table, pixel-calibrated off
   `inputs/Graphs and other inputs/Temp profile 0-30km.jpeg`'s axis gridlines, "19 May"
   curve, 12:00 UTC panel) and `atmosphere.ambient_T_blended()` (that table below
   30 km, US76 at/above it). Wired into `stage_transient_bcs.py` as a new
   `--ambient-profile kolkata_12z_19may` flag (default remains `us76`, unchanged, for
   every other study in this project). The two sources agree to ~0.3 K at the 30 km
   splice (US76 226.51 K vs sounding 226.25 K) — no visible discontinuity in `Ta`.
   Only the ambient/sink temperature is swapped; pressure/density/transport properties
   powering the natural-convection film coefficient still come from US76 (no pressure
   data was digitized from the image).
7. **Ascent rate** — not measured (no flight profile supplied), assumed **constant**
   at 40 000 m / 7200 s = **5.5556 m/s**, chosen so the mission's own schedule (2 h to
   40 km, then 1 h dwell) lands on clean 5 km / 900 s segment boundaries — same
   reasoning every prior transient study in this project used for its own assumed rate.
8. **Heat load** — kept at 30 W (unchanged from `transient-0-40km`/`-etp-copper`); the
   user did not ask to change the electrical load, only the geometry, atmosphere, and
   radiator BC.
9. **Meshed** (`mesh_assembly.py --level medium`, 117 152 cells, 4.0 s) and **built the
   case** (`setup_cht_case.py --reuse-mesh`). `checkMesh` reports `ok: false`
   (max non-orthogonality 84.5°, max skewness 8.5) — the same class of thin-plate/
   sliver-face defect every CAD in this project has shown (see `C-CHECKMESH` below);
   **no `FOAM FATAL ERROR`**, confirmed clean in the smoke test.
10. **Smoke-tested** (`run_cht_case.py --end-time 10`): `completed: true`,
    `n_steps: 5`, no crash. `writeInterval` is 120 s and the smoke window (10 s) never
    reached it, so **no time directory beyond `0` was ever written** — the case on disk
    is still the pristine t=0 initial condition, ready for segment 1.
11. **Refined the heat-source flux** from an area estimate to the actual meshed patch
    area: `jetson_heat_source` on `interface_plate`'s `xmin` face (0.003769446 m²
    measured) → `q_W_m2 = 30 / 0.003769446 = 7958.73`.

## What this study changes vs. every prior transient study in this project

| | Prior studies (`transient-0-40km*`, dwell variants) | This study |
| --- | --- | --- |
| CAD | `spaced out rad+box.step` (radiators split left/right, X axis) | **`Shorter straps.step`** (radiators stacked top/bottom, Z axis; much shorter TTP path) |
| Ambient T, 0–30 km | US76 from ground level (documented as an approximation below ~20 km) | **Digitized Kolkata 12:00 UTC, 19-May-2026 sounding** |
| Ambient T, 30–40 km | US76 | US76 (unchanged — same splice point the mission's own schedule lands on) |
| Radiator radiation | Whole non-coupled external surface (front + back both radiate) | **Outer face only** — inner (box-facing) face is `adiabatic` |
| Mission profile | 0→40 km ascent only, or a separate 60-min dwell continuation study | **Single continuous study**: 0→40 km ascent (2 h) directly followed by 60-min dwell (3 h total, one manifest, one `end_time_s`) |
| Segments | 8×1200 s ascent (4.1667 m/s) [+ separate 3×1200 s dwell study] | **12×900 s** (8 ascent @ 5.5556 m/s + 4 dwell), one continuous restart chain |
| Strap material | OFHC copper or Cu-ETP, distinct connector/strap/bracket solids | OFHC copper, **3 unlabeled solids per the CAD's own export gap** (see above) |

## Part A — Ollama + `cfd-qwen`

```powershell
.\ollama\run_agent.ps1 -SelfTest -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_SHORTER_STRAP_3HR.md
```

Expect the standard readiness signature (Ollama up, `cfd-qwen` built, PASS on the C0
environment check). Rebuild if needed: `ollama create cfd-qwen -f ollama\Modelfile.cfd`.

**Driving this fully unattended:**

```powershell
.\ollama\run_agent.ps1 -AutoApprove -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_SHORTER_STRAP_3HR.md `
  -TranscriptPath ollama\transcripts\transient-shorter-strap-40km-3hr.log -MaxTurns 200
```

`-AutoApprove` executes every proposed command without a keystroke (the installer
hard-block stays active regardless) and proactively injects a clarifying note the
instant the known-benign `checkMesh` WARNING appears in a command's output — see
`C-CHECKMESH` below and `agent-data/lessons.md` L012 for why this exists. A
command-history loop-guard is the fallback safety net.

## Part B — What to pull onto the machine

Same solver stack as every other study here (already installed and verified — **never
run an installer**, see C0). Nothing new to install.

| Item | Location | Notes |
| --- | --- | --- |
| Manifest, mesh, case (already built by Claude) | `outputs/balloon-ttp/transient-shorter-strap-40km-3hr/{assembly,mesh,case}/` | Ready to solve from `case/0/` — do not re-inspect, re-assign, or re-mesh |
| CAD source | `inputs/balloon-ttp/Shorter straps.step` | Read-only, already ingested |
| Kolkata sounding image | `inputs/Graphs and other inputs/Temp profile 0-30km.jpeg` | Already digitized into `.tmp/scripts/atmosphere.py` — do not re-digitize |
| Staging tool | [stage_transient_bcs.py](../../stage_transient_bcs.py) | New `--ambient-profile kolkata_12z_19may` flag — **use it on every call in this runbook**, ascent and dwell alike (the function auto-splices to US76 above 30 km internally) |
| Post-processing | [transient_history.py](../../transient_history.py) | Reused unmodified |

---

# Part C — Conducting the simulation

Run every command from the repository root. The interpreter is always
`.venv\Scripts\python.exe`. Study slug: `balloon-ttp/transient-shorter-strap-40km-3hr`.

## C0 — Environment gate (do not install anything)

```powershell
.venv\Scripts\python.exe .github\skills\solver_environment\scripts\check_environment.py
```

**Gate:** output ends with `READY: full CFD/FEA toolchain available.` Ignore
`setup_report.json` if it disagrees — it is a stale artifact.

## C1 — Verify the manifest, mesh, and case Claude already built

Do **not** run `inspect_step.py`, `assign_materials.py`, or `mesh_assembly.py` for
this study — the manifest, mesh, and case already exist and are correct. Just confirm:

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-shorter-strap-40km-3hr --validate
Get-ChildItem "outputs\balloon-ttp\transient-shorter-strap-40km-3hr\case" -Directory | Where-Object { $_.Name -match '^[\d.]+$' }
```

**Gate:** `Manifest is ready for meshing/case setup.`, and the case directory lists
exactly `0` (the pristine initial condition — Claude's smoke test never reached
`writeInterval` 120 s, so nothing beyond `0` was written).

## C2 — Stage segment 1's boundary condition onto `case/0`

Segment 1 covers 0→900 s, ascending through the 0–5000 m band; stage its BC at the
band's mid-altitude (2500 m), same convention every segment below uses:

```powershell
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-shorter-strap-40km-3hr --altitude 2500 --ambient-profile kolkata_12z_19may
```

**Expect:** `"ambient_profile": "kolkata_12z_19may"`, `T_air_K` around 290 (≈16.9°C —
the digitized Kolkata sounding at 2500 m, not US76's colder ≈-2°C at the same
altitude).

## C-CHECKMESH — Why the checkMesh WARNING is expected (read this before C3, not after)

This CAD (`Shorter straps.step`) has thin, short connecting solids and a
high-aspect-ratio mesh region, giving the same class of `checkMesh` flag
(`ok: false`, high non-orthogonality/skewness) every CAD in this project has shown —
**no `FOAM FATAL ERROR`**, and Claude's own smoke test (C0 above, "What Claude already
did" item 10) already confirmed the solve runs cleanly through this warning. There is
no `fix_mesh_regions.py`, `refine_mesh.py`, or `smooth_mesh.py` in this repo, and none
is needed or wanted. If a checkMesh WARNING appears in any command's output below:
state that it's the known, expected result, and move directly to the next command.

## C3 — Smoke test (confirm the staged BC solves cleanly before the full run)

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-shorter-strap-40km-3hr --end-time 10 --time-limit 300
```

**Gate:** `completed: true`, `final_time: 10.0`, `n_steps: 5`, first `Time =` line in
the log is `0` (fresh start, not a restart). No `FOAM FATAL`. This smoke window is
inside segment 1 below (900 s), and `writeInterval` (120 s) will not be reached by it,
so no case reset is needed — continue straight to C4.

## C4 — The 3-hour mission, 12 segments (900 s each)

**Convention:** stage the BC at each segment's *mid-altitude* before running it — the
average condition over that 900 s band, same convention `transient-0-40km` used with
its 1200 s / 5000 m segments. Ascent rate is the constant 5.5556 m/s assumed in
"What Claude already did" item 7. **Every** `stage_transient_bcs.py` call below uses
`--ambient-profile kolkata_12z_19may` — the function handles the 30 km US76 splice
internally, so there is nothing altitude-dependent to remember here.

| Seg | t window [s] | Alt band [m] | Mid-alt [m] (staging altitude) | T_air [°C] at mid-alt | p [Pa] at mid-alt |
| --- | --- | --- | --- | --- | --- |
| 1 | 0 → 900 | 0 – 5 000 | 2 500 | 16.90 | 74 692 |
| 2 | 900 → 1800 | 5 000 – 10 000 | 7 500 | −10.97 | 38 300 |
| 3 | 1800 → 2700 | 10 000 – 15 000 | 12 500 | −49.20 | 17 934 |
| 4 | 2700 → 3600 | 15 000 – 20 000 | 17 500 | −78.15 | 8 182 |
| 5 | 3600 → 4500 | 20 000 – 25 000 | 22 500 | −60.26 | 3 746 |
| 6 | 4500 → 5400 | 25 000 – 30 000 | 27 500 | −47.89 | 1 743 |
| 7 | 5400 → 6300 | 30 000 – 35 000 | 32 500 | −43.56 (US76 side of the splice) | 826 |
| 8 | 6300 → 7200 | 35 000 – 40 000 | 37 500 | −29.72 | 404 |
| 9 | 7200 → 8100 | 40 000 (dwell) | 40 000 | −22.80 | 287 |
| 10 | 8100 → 9000 | 40 000 (dwell) | 40 000 | −22.80 | 287 |
| 11 | 9000 → 9900 | 40 000 (dwell) | 40 000 | −22.80 | 287 |
| 12 | 9900 → 10800 | 40 000 (dwell) | 40 000 | −22.80 | 287 |

Segment 1's BC is already staged (C2) — run it directly, then repeat stage→run→prune
for segments 2–12:

```powershell
$S = "balloon-ttp/transient-shorter-strap-40km-3hr"

# segment 1 : 0 -> 900 s (BC already staged in C2)
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 900

# segment 2 : 900 -> 1800 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 7500 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 1800

# segment 3 : 1800 -> 2700 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 12500 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 2700

# segment 4 : 2700 -> 3600 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 17500 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 3600

# segment 5 : 3600 -> 4500 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 22500 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 4500

# segment 6 : 4500 -> 5400 s (last segment before the 30 km US76 splice)
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 27500 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 5400

# segment 7 : 5400 -> 6300 s (first segment on the US76 side of the splice)
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 32500 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 6300

# segment 8 : 6300 -> 7200 s (ascent complete, 40 km reached)
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 37500 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 7200

# segment 9 : 7200 -> 8100 s (dwell begins, fixed 40000 m)
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 40000 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 8100

# segment 10 : 8100 -> 9000 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 40000 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 9000

# segment 11 : 9000 -> 9900 s
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 40000 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 9900

# segment 12 : 9900 -> 10800 s (mission complete)
.venv\Scripts\python.exe stage_transient_bcs.py --study $S --altitude 40000 --ambient-profile kolkata_12z_19may
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study $S --end-time 10800
```

**Per-segment gate:** `completed: true` at the segment's end time; the log's first
`Time =` line for the segment is the previous segment's end (not 0 and not a repeat of
an earlier time) — proves the restart picked up state; no `FOAM FATAL`/`bounding`
messages; `stage_transient_bcs.py`'s printed `ambient_profile` field reads
`"kolkata_12z_19may"` on every call.

**Prune between segments** (keep only the latest and `0`):

```powershell
$case = "outputs\balloon-ttp\transient-shorter-strap-40km-3hr\case"
$keep = (Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' } |
         Sort-Object { [double]$_.Name } | Select-Object -Last 1).Name
Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' -and $_.Name -ne $keep -and $_.Name -ne '0' } | Remove-Item -Recurse -Force
"kept: $keep"
```

**Runtime estimate.** This is a solid-only CHT case (no fluid region) — the prior
9600 s/60 min dwell studies in this project solved at roughly 1 s of wall-clock per
30–40 s of simulated time. 10800 s of mission time should solve in well under 10
minutes of pure solve time; call it 15–20 minutes total across 12 segments including
decompose/reconstruct overhead per segment.

## C5 — Post-processing and verification

```powershell
.venv\Scripts\python.exe transient_history.py --study balloon-ttp/transient-shorter-strap-40km-3hr --highlight jetson_module,interface_plate,strap_top,strap_bottom,radiator_plate_top,radiator_plate_bottom
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study balloon-ttp/transient-shorter-strap-40km-3hr
```

**Verification gates (do not report results until all pass):**

| # | Check | Pass criterion |
| --- | --- | --- |
| 1 | Heat still injected | `jetson_heat_source` ≈ 30 W throughout |
| 2 | Box adiabatic | `styrofoam_box_outer` integrates to 0.0 W |
| 3 | **Radiator inner faces radiate nothing** | `radiator_plate_top_inner` and `radiator_plate_bottom_inner` external heat flux = 0.0 W at every reported time — this is the actual point of this study's BC change |
| 4 | Radiator outer faces are the only ones rejecting heat | `radiator_plate_top_outer`/`radiator_plate_bottom_outer` are the only nonzero external radiator patches |
| 5 | Temperatures bounded | No region colder than ~−80°C (coldest ambient the mission sees, the tropopause band) or hotter than ~200°C |
| 6 | Trend at the end of the dwell | Plateauing, still climbing, or turning over — report what's observed, not assumed |
| 7 | Interface balance | Each coupled interface in `interfaces_W` agrees within a few percent between its two sides |
| 8 | Segment count | Exactly 12 segments solved, final time 10800 s |

## C6 — Report

```powershell
.venv\Scripts\python.exe .github\skills\report_generation\scripts\build_report.py --study balloon-ttp/transient-shorter-strap-40km-3hr --title "Stratospheric Payload Thermal Analysis: Shorter-Strap Geometry, 3-Hour Mission (0-40 km Ascent + 60-min Dwell), Kolkata Sounding, Outer-Face-Only Radiation"
```

Then edit the executive summary by hand. State explicitly:

* Peak `jetson_module`/`interface_plate` temperature and when in the mission it
  occurs (during ascent, or at the end of the dwell).
* Whether the outer-only radiator BC (vs. every prior study's whole-surface
  radiation) measurably changed peak temperatures relative to
  `transient-0-40km`/`transient-0-40km-dwell-60min` — those studies are not a like-for-
  like geometry comparison (different CAD, different atmosphere source), so frame any
  comparison as qualitative, not a controlled delta.
* Confirmation of gate 3 (inner-face radiation is exactly zero) as the headline
  boundary-condition result.
* All assumptions carried in "What Claude already did" above, cited rather than
  restated.

Claude will build the final per-component temperature vs. time-and-altitude figure
separately after this report — do not attempt that plot here.

---

# Part D — Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| A segment's first `Time =` is `0` or repeats an earlier segment's end time | `startFrom latestTime` didn't pick up the previous segment's state, or a stale time directory wasn't pruned | Re-check the case directory listing before the segment; re-run the prune snippet |
| `stage_transient_bcs.py` output has no `ambient_profile` key or shows `"us76"` | `--ambient-profile kolkata_12z_19may` was dropped from the command | Reissue the staging call with the flag — do not proceed to the segment's solve without it |
| A checkMesh WARNING appears and the model proposes a fix/refinement command | This is the known, expected warning (see C-CHECKMESH) — the driver injects a clarifying note automatically, but if it's still misread, the loop-guard will catch the resulting command cycle | Resume manually from the last successful gate |
| `radiator_plate_*_inner` shows nonzero external heat flux in C5 | The manifest's inner-face patch selector or BC got altered | Stop — do not report results. This is a correctness gate, not a warning; escalate to Claude/a human rather than continuing |
| `stage_transient_bcs.py` fails with `Missing field file: ...\<time>\<region>\T` | The segment's end time isn't a multiple of the manifest's `write_interval_s` (900 s segments need `write_interval_s` to be a divisor of 900, e.g. 90 — the inherited default of 120 does not divide 900) — that end time only got a partial (`wallHeatFlux`-only) write from the postProcessing function objects' own independent `writeInterval 10` (timesteps), not a full field write | Already fixed in this study's manifest (`write_interval_s: 90`) before the real solve — if this recurs, check `manifest.json`'s `solver.write_interval_s` against the segment length before re-running |
| FOAM_SIGFPE abort | Not expected for this CAD in Claude's smoke test, but if seen: set `disable_fpe_trap: true` in the manifest's `solver` block (`assign_materials.py --study $S --solver '{"disable_fpe_trap":true}'`), then re-run `setup_cht_case.py --reuse-mesh` before resuming the segment sequence | See `agent-data/lessons.md` for the `spaced out rad+box.step` precedent this mirrors |

---

# Part E — The prompt to give with this runbook

```
You are executing OLLAMA_QWEN_TRANSIENT_RUNBOOK_SHORTER_STRAP_3HR.md Part C in this
repository. Study slug: balloon-ttp/transient-shorter-strap-40km-3hr.

GOAL
Run the already-built (by Claude) shorter-strap CHT case through a continuous 3-hour
mission: 0->40000 m ascent over 2 h (8 segments of 900 s, staged at each segment's
mid-altitude using the Kolkata-sounding-blended ambient profile), then 60 min dwell at
40000 m (4 more segments of 900 s). Verify the radiator inner faces radiate exactly
zero throughout -- that is the actual point of this study's boundary-condition change.

ENVIRONMENT -- ALREADY BUILT, NOTHING TO INSTALL
WSL Ubuntu, OpenFOAM v2412 with chtMultiRegion solvers, CalculiX 2.21, Gmsh and all
Python packages are installed and verified. Never run install_solvers.py, setup.ps1,
first_run_setup.py, apt or pip install. C0 is read-only and prints
"READY: full CFD/FEA toolchain available."

DO NOT RE-DO CLAUDE'S SETUP WORK
The manifest, mesh, and case already exist and are correct (component renaming,
material assignment, thermal contact resistances, radiator inner/outer patch split,
atmosphere blending in stage_transient_bcs.py). Do not run inspect_step.py,
assign_materials.py (except the read-only --validate in C1), or mesh_assembly.py for
this study. Start from C1 (verification only).

KNOWN BENIGN WARNING -- READ BEFORE C3
Setting up/running this case may print a checkMesh WARNING (ok: false, high-aspect-
ratio and/or non-orthogonality flags). This is a documented, expected result for this
CAD -- it is NOT a new problem, there is no fix_mesh_regions.py, refine_mesh.py, or
smooth_mesh.py in this repo, and none is needed. If you see this warning, state that
it's the known expected result and move directly to the next command in Part C. Do not
attempt to fix, refine, or regenerate the mesh.

PROTOCOL
- One powershell command per turn, in a fenced powershell block, nothing else.
- Wait for the real output before continuing.
- State the current step id (C0..C6) before each command, and the segment number
  (1-12) during C4.
- Never state a temperature, flux, residual or runtime you have not seen in output
  that was actually pasted back to you.
- If a command fails, name the cause in one sentence, then issue a corrected command
  -- do not retry verbatim.
- Do not proceed past a failed verification gate. Say what failed and stop.

EXECUTION RULES SPECIFIC TO THIS STUDY
- Every stage_transient_bcs.py call in C2 and C4 MUST include
  --ambient-profile kolkata_12z_19may -- there are no exceptions, ascent or dwell.
- Segment altitudes to stage (mid-altitude convention): 2500, 7500, 12500, 17500,
  22500, 27500, 32500, 37500, then 40000 for all 4 dwell segments -- see the table in
  C4.
- Segment end times: 900, 1800, 2700, 3600, 4500, 5400, 6300, 7200, 8100, 9000, 9900,
  10800 -- 12 segments total, all 900 s.
- After the full solve, gate 3 in C5 (radiator inner-face heat flux = 0.0 W) is the
  most important check in this runbook -- do not report results if it fails.
- C6's report must state where in the mission (ascent vs. dwell) the peak temperature
  occurs.

Start with C0.
```

---

## Reference — files this procedure touches

| Path | Role |
| --- | --- |
| `inputs/balloon-ttp/Shorter straps.step` | Source CAD, read-only |
| `inputs/Graphs and other inputs/Temp profile 0-30km.jpeg` | Source sounding image, read-only, already digitized |
| `outputs/balloon-ttp/transient-shorter-strap-40km-3hr/assembly/manifest.json` | Manifest — renamed components, materials, TCRs, radiator inner/outer patches, solver block (`end_time_s: 10800`) |
| `outputs/balloon-ttp/transient-shorter-strap-40km-3hr/mesh/`, `.../case/` | Mesh (117 152 cells) and case, built and smoke-tested by Claude |
| [.tmp/scripts/atmosphere.py](../../.tmp/scripts/atmosphere.py) | `kolkata_12z_19may_T()` + `ambient_T_blended()` — new, additive, default (`us76`) behaviour unchanged for every other study |
| [stage_transient_bcs.py](../../stage_transient_bcs.py) | New `--ambient-profile` flag — new, additive |
| [transient_history.py](../../transient_history.py) | Reused unmodified |
| [ollama/Modelfile.cfd](../Modelfile.cfd) / [ollama/run_agent.ps1](../run_agent.ps1) | `cfd-qwen` build + driver (`-AutoApprove`, proactive known-warning injection, loop-guard) |
| `outputs/balloon-ttp/transient-shorter-strap-40km-3hr/` | This study's manifest, case, figures, and reports |
