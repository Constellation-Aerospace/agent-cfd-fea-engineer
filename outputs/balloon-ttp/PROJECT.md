# balloon-ttp — Stratospheric Balloon Payload Thermal Analysis

**What this is:** conjugate heat transfer (conduction + natural convection + grey-body
radiation) analysis of a payload thermally coupled through twin OFHC copper straps
("TTP" — thermal transfer path) to external radiators, carried by a high-altitude
balloon from ground level up through the stratosphere. The payload is a ~30-60 W Jetson
compute module on an aluminum cold plate, inside an EPS-foam insulated enclosure, with
twin white-painted Al 6061 radiator plates rejecting heat to the sky.

**Reference:** no external SOW/ticket reference supplied with this project — treat this
file as the authoritative scope record.
**Status:** active — steady-state baselines validated, transient ascent studies in
progress across increasing altitude/duration envelopes.

## Hardware model

| Component (renamed from raw CAD) | Role | Material |
| --- | --- | --- |
| `jetson_module` | Compute die/module (heat source) | `fr4_pcb` |
| `jetson_heatsink` | Jetson-side heatsink block | `aluminum_6061` |
| `interface_plate` | Cold plate / TTP interface | `aluminum_6061` |
| `connector_block_left/right` | Al clamp blocks, TTP end of each strap | `aluminum_6061` |
| `copper_strap_left/right` | OFHC copper thermal strap braids | `copper` (κ 390 override) |
| `radiator_bracket_left/right` | Al brackets, radiator end of each strap | `aluminum_6061` |
| `radiator_plate`, `radiator_plate_2` | Twin external radiators, white paint | `white_paint_aluminum` (ε 0.85) |
| `styrofoam_box` | Insulated enclosure | `eps_foam` |

CAD source: [inputs/balloon-ttp/](../../inputs/balloon-ttp/) — `assembly.step` (original,
un-spaced radiators) and `spaced out rad+box.step` / `Spaced out radiators.step`
(radiators moved apart, later geometry revision). See `inputs/README.md`'s table.

Thermal contact resistances (bolted joints + PTM7950 phase-change interface at the
die) are solved via `thicknessLayers`/`kappaLayers` on the coupled interfaces — see any
study's `assembly/manifest.json` → `thermal_contact_resistances`.

## Studies

| Study | Type | Envelope | Status |
| --- | --- | --- | --- |
| `cht-30km` | Steady CHT, `chtMultiRegionSimpleFoam` | 30 km US76 ambient (1197 Pa, 193.15 K), convection disabled (negligible at this density), original `assembly.step` geometry, component names not yet renamed | Completed — baseline radiation+conduction check |
| `cht-30km-spaced-radiators` | Steady CHT, `chtMultiRegionSimpleFoam` | Same as above, spaced-radiator geometry variant | Completed — radiator-spacing comparison |
| `transient-0-10km` | Transient CHT, `chtMultiRegionFoam` | 0→10 km, 2400 s (40 min), 60 W load, 8×300 s mission-time segments | Completed (`final_time: 2400.0`) — source manifest for the later transient studies |
| `transient-0-20km` | Transient CHT, `chtMultiRegionFoam` | 0→20 km, 1200 s (20 min), 60 W load, altitude-indexed segments | **Check before reuse** — the persisted `run_summary.json` currently shows only a 0.5 s smoke-test state (see `agent-data/lessons.md` L006: a smoke run's `startFrom latestTime` can leave a stale, non-writeInterval time dir that shadows a full run's true endpoint). Re-run or inspect `case/` time directories directly before citing results. |
| `transient-0-40km` | Transient CHT, `chtMultiRegionFoam` | 0→40 km, 9600 s (160 min), 30 W load, 8×1200 s altitude-indexed segments | Completed (`final_time: 9600.0`, 600 steps) — see `report/report.md`. Result: `jetson_module` 71.274 °C / `interface_plate` 72.055 °C at 40 km, radiators 19.4/19.85 °C max, ≈24.2 W rejected vs 30.1 W injected (shortfall going into thermal mass — still rising, not steady). Twin copper straps modelled as OFHC copper (κ 390 override) |
| `transient-0-40km-etp-copper` | Transient CHT, `chtMultiRegionFoam` | Identical to `transient-0-40km` — same geometry/mesh/BCs/loads — with the twin straps re-materialed to **Cu-ETP/C11000** (κ 386, new `copper_etp` library entry) instead of OFHC copper (κ 390) | Completed (`final_time: 9600.0`, 600 steps) — see `report/report.md`. Result: `jetson_module` 71.334 °C / `interface_plate` 72.115 °C — **+0.06 K vs the OFHC baseline**, i.e. the strap material choice is thermally negligible for this hardware (the bolted-joint TCRs, 1.58 K/W each, dominate the die-to-radiator path over the strap's own conduction resistance). Radiators unchanged to 3 s.f. |
| `transient-0-40km-dwell-60min` | Transient CHT, `chtMultiRegionFoam` | Continuation of `transient-0-40km` (OFHC straps): 60 min held at fixed 40 000 m from the ascent's solved t=9600s state, `end_time_s` 13200 | Completed (`final_time: 13200.0`, 600 steps) — see `report/report.md`. Result: `jetson_module` 78.152 °C / `interface_plate` 78.894 °C at t=13200s, ≈26.34 W rejected vs 30.1 W injected (shortfall shrinking vs the ascent's ~6 W — approaching but not reaching quasi-steady state) |
| `transient-0-40km-dwell-60min-etp-copper` | Transient CHT, `chtMultiRegionFoam` | Continuation of `transient-0-40km-etp-copper` (Cu-ETP straps): identical dwell profile to the OFHC dwell study above | Completed (`final_time: 13200.0`, 600 steps) — see `report/report.md`. Result: `jetson_module` 78.183 °C / `interface_plate` 78.925 °C — **+0.031 K vs the OFHC dwell baseline, smaller than the +0.06 K delta at the ascent's own endpoint** — the material gap shrinks, not grows, over an extended hold. Restart continuity from the ETP ascent verified to 0.045 K |

Full step-by-step reproduction procedures (including the exact CLI commands, BC
staging, and verification gates for each transient study) live in
[ollama/runbooks/](../../ollama/runbooks/) — written for a local Ollama (`cfd-qwen`)
agent but equally usable manually:

- [OLLAMA_QWEN_TRANSIENT_RUNBOOK.md](../../ollama/runbooks/OLLAMA_QWEN_TRANSIENT_RUNBOOK.md) — 0→20 km
- [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_10KM.md](../../ollama/runbooks/OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_10KM.md) — 0→10 km
- [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md](../../ollama/runbooks/OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md) — 0→40 km
- [OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN.md](../../ollama/runbooks/OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN.md) — 60 min dwell at 40 km
- [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md](../../ollama/runbooks/OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md) — 0→40 km, Cu-ETP straps
- [OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN_ETP_COPPER.md](../../ollama/runbooks/OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN_ETP_COPPER.md) — 60 min dwell at 40 km, Cu-ETP straps

`ollama/run_agent.ps1 -AutoApprove` drives a runbook unattended (no `Read-Host`
approval loop) with `cfd-qwen`; see the tool's own `-?`/header comment. **Known
limitations** (see `agent-data/lessons.md` for the full writeups, L012–L016):
`cfd-qwen` (qwen2.5-coder:7b) reliably drives simple deterministic sequences (env
checks, file copies, material/solver assignment) but has repeatedly shown it cannot be
trusted to run a multi-step Part C fully unattended without a human/Claude reviewing
the transcript before results are reported:
1. Misreads a documented, expected non-fatal `checkMesh` WARNING as something to fix,
   inventing nonexistent mesh-repair scripts (fixed with a proactive driver-level
   note injected the instant the warning appears — effective after 3 failed attempts
   without it).
2. Echoes the bare step id or plain-English commentary *inside* the fenced code
   block instead of only in prose outside it, breaking PowerShell parsing (fixed:
   the driver now strips leading non-code lines before executing).
3. Windows PowerShell 5.1 itself strips embedded double-quotes from single-quoted
   JSON arguments passed to native executables (`--solver '{"mode":...}'` arrives at
   python.exe as invalid JSON) — a driver/OS-level bug, not model-specific, but it
   only surfaces via model-generated commands that use this JSON-argument pattern
   (which every runbook does). Fixed: the driver auto-escapes embedded quotes before
   execution.
4. **Not yet mitigated at the driver level:** silently skipping a required step
   (e.g. copying in a prior study's solved field state before a restart) and not
   self-verifying its own stated gate before declaring success and moving on. This
   produced an invalid "smoke test" that solved from a fresh initial condition
   instead of restarting, undetected by the model itself — caught only by a
   human/Claude checking `n_steps` against the gate before the full multi-segment
   solve compounded the error. No general fix implemented yet; continue reviewing
   `run_summary.json`/`n_steps` against each runbook's stated gate before trusting an
   unattended run's downstream results.

Shared helper scripts referenced by those runbooks (repo root, reused unmodified
across studies): `stage_transient_bcs.py` (altitude-indexed BC restaging between
segments), `transient_history.py` (CSV/PNG assembly across restart segments).

## Assumptions carried across every transient study

- **Ascent rate is assumed, not measured** — no flight profile document was supplied
  for this project. Each transient runbook picks a constant vertical rate (e.g.
  4.1667 m/s for the 0→40 km study) chosen to land segment boundaries on clean
  altitude/time splits. Re-stage against a real flight profile if one becomes
  available.
- **Enclosure is modelled adiabatic** — conservative, forces 100% of the electrical
  load through the strap/radiator path rather than leaking through the foam.
- **`altitude_environment` (US76 sky-sink) BC is used from ground level** even though
  it is only exact above ~20 km (below that, neglecting atmospheric IR undercounts the
  sky sink term — conservative, not exact).
- Mesh independence has not been performed for any transient study in this project.

## Known gotchas (see `agent-data/lessons.md` for the full harness-level writeups)

- `spaced out rad+box.step` has a ~3e-9 m² sliver face on `interface_plate` that trips
  the default `FOAM_SIGFPE` trap before the first time step with no visible error;
  `solver.disable_fpe_trap: true` in the manifest is required for every study on that
  geometry (not a physics workaround — solid conduction under implicit Euler is
  unconditionally stable regardless of that diagnostic).
- Re-running `inspect_step.py` on an already-worked study reverts hand-applied
  component renames back to `part_N` — copy a sibling study's `assembly/manifest.json`
  instead of re-inspecting when reusing the same CAD.
