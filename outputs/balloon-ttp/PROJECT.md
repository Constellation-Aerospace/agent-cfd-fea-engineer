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
| `transient-0-40km` | Transient CHT, `chtMultiRegionFoam` | 0→40 km, 9600 s (160 min), 30 W load, 8×1200 s altitude-indexed segments | Completed (`final_time: 9600.0`, 600 steps) — see `report/report.md`. Result: `jetson_module` 71.3 °C / `interface_plate` 72.1 °C at 40 km, radiators ≈8 °C mean, ≈24.2 W rejected vs 30.1 W injected (shortfall going into thermal mass — still rising, not steady) |

Full step-by-step reproduction procedures (including the exact CLI commands, BC
staging, and verification gates for each transient study) live in the repo-root
runbooks — written for a local Ollama (`cfd-qwen`) agent but equally usable manually:

- [OLLAMA_QWEN_TRANSIENT_RUNBOOK.md](../../OLLAMA_QWEN_TRANSIENT_RUNBOOK.md) — 0→20 km
- [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_10KM.md](../../OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_10KM.md) — 0→10 km
- [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md](../../OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md) — 0→40 km

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
