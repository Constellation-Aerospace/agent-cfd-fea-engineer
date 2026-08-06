# ollama/runbooks/ — cfd-qwen study runbooks

Each file here is a **complete, self-contained procedure** for reproducing one
`balloon-ttp` transient CHT study end to end — written to be handed to the local
`cfd-qwen` model via [`../run_agent.ps1`](../run_agent.ps1), but equally readable and
followable by hand or by another agent. See [`../README.md`](../README.md) for how the
driver itself works (setup, safety model, `-AutoApprove` mode, known limitations).

Every runbook follows the same five-part structure:

- **Part A** — Ollama/`cfd-qwen` setup and readiness check
- **Part B** — what source data the study pulls in (CAD, a prior study's manifest/mesh/
  solved state, shared helper scripts)
- **Part C** — the numbered, gated command sequence (`C0`, `C1`, …) that actually builds
  and solves the case, with an explicit pass/fail gate after every step
- **Part D** — troubleshooting table, symptom → cause → fix
- **Part E** — the exact prompt to hand `cfd-qwen` (or another agent) to execute Part C

## Index

| Runbook | Target study | Envelope | Status |
| --- | --- | --- | --- |
| [OLLAMA_QWEN_TRANSIENT_RUNBOOK.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK.md) | `balloon-ttp/transient-0-20km` | 0→20 km, 1200 s (20 min), 60 W, original `assembly.step` geometry, 6×200 s segments | ⚠️ Re-run/verify before citing — a smoke-run artifact may shadow the true endpoint (`agent-data/lessons.md` L006) |
| [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_10KM.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_10KM.md) | `balloon-ttp/transient-0-10km` | 0→10 km, 2400 s (40 min), 60 W, spaced-radiator geometry, 8×300 s mission-time segments | ✅ Completed — source manifest for every later transient study |
| [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md) | `balloon-ttp/transient-0-40km` | 0→40 km, 9600 s (160 min), 30 W, 8×1200 s altitude-indexed segments, OFHC copper straps | ✅ Completed — see study's `report/report.md` |
| [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md) | `balloon-ttp/transient-0-40km-etp-copper` | Identical to the above, twin straps re-materialed to **Cu-ETP/C11000** | ✅ Completed — see [outputs/balloon-ttp/etp-vs-ohfc-copper-comparison/report.md](../../outputs/balloon-ttp/etp-vs-ohfc-copper-comparison/report.md) for the full material comparison |
| [OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_HOT.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_HOT.md) | `balloon-ttp/transient-0-40km-hot` | Identical ascent to `transient-0-40km`, but `radiator_plate` sun-facing (`radiator_plate_2` stays shaded) — worst-case sun exposure vs. the cold-case baseline | ⬜ Not yet executed — ready to run |
| [OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN.md) | `balloon-ttp/transient-0-40km-dwell-60min` | Continuation of `transient-0-40km`: 60 min held at fixed 40 000 m from the ascent's solved t=9600s state, `end_time_s` 13200, OFHC straps | ✅ Completed — see study's `report/report.md` |
| [OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN_ETP_COPPER.md](OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN_ETP_COPPER.md) | `balloon-ttp/transient-0-40km-dwell-60min-etp-copper` | Continuation of `transient-0-40km-etp-copper`: identical dwell profile, Cu-ETP straps | ✅ Completed — see [outputs/balloon-ttp/etp-vs-ohfc-copper-comparison/report.md](../../outputs/balloon-ttp/etp-vs-ohfc-copper-comparison/report.md) |

## How the studies relate

```
transient-0-10km  ──(source manifest for CAD family)──▶  transient-0-20km, 0-40km*, 0-40km-hot

transient-0-40km (OFHC) ──(ascent, 9600s)──▶ transient-0-40km-dwell-60min (+60min @ 40km)
        │
        └─(swap straps to Cu-ETP)─▶ transient-0-40km-etp-copper ──▶ transient-0-40km-dwell-60min-etp-copper
```

*`transient-0-40km` reuses `transient-0-10km`'s renamed-component manifest as its own
starting point (copied, not re-inspected — re-running `inspect_step.py` on an
already-worked study reverts hand-applied component renames back to `part_N`).

## Running one

From the repository root:

```powershell
# verify cfd-qwen reads the runbook correctly — executes nothing
.\ollama\run_agent.ps1 -SelfTest -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md

# interactive: model proposes one command per turn, you approve each with 'r'
.\ollama\run_agent.ps1 -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md

# unattended: every command executes automatically, full transcript logged
.\ollama\run_agent.ps1 -AutoApprove -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md `
  -TranscriptPath ollama\transcripts\my-run.log
```

Every runbook's own Part A repeats the exact `-SelfTest` invocation for that file, and
Part E has the prompt to paste if driving a session by hand instead of through
`run_agent.ps1`.

**Before trusting an `-AutoApprove` run's results**, read `../README.md`'s safety-model
section — `cfd-qwen` has repeatedly needed a human/Claude to catch a silently-skipped
required step before it propagated into an expensive solve. Check `run_summary.json`'s
`completed`/`final_time`/`n_steps` against the runbook's own stated gate at each restart
boundary, not just at the end.

## Writing a new runbook

Copy the closest sibling (same CAD family, similar mission profile) rather than
starting from scratch — every runbook in this folder was built by cloning a prior one
and updating only what actually changed (materials, altitude profile, load, geometry).
Keep the Part A–E structure and the explicit per-step verification gates; they're what
let both a 7B local model and a human catch a bad step before it reaches an expensive
solve.
