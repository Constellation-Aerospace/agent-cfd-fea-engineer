# Lessons — the annealing backlog

Techniques, fixes, and gotchas learned during project work, captured the moment
they surface and tracked until integrated into the harness (a SKILL.md, a core
module, the materials library, or docs). `anneal.py check` refuses to sign off a
session while lessons are OPEN or harness changes are uncommitted.

Format per entry: `## L<nnn> — <title> [OPEN|APPLIED]` + date/project/target/
lesson lines (+ applied note once integrated).

## L001 — gmsh writes STEP in millimetres [APPLIED]
- date: 2026-07-31
- project: -
- target: step_assembly
- lesson: gmsh/OCC always writes STEP in mm regardless of model units; imports are normalised to metres via Geometry.OCCTargetUnit. Geometry round-trip tests must model in mm and assert absolute areas/volumes, not just topology counts.
- applied: 2026-07-31 — documented in step_assembly SKILL.md gotchas; unit assertions in the self-test

## L002 — bare "*.tmp" gitignore glob eats the .tmp directory [APPLIED]
- date: 2026-07-31
- project: -
- target: repo hygiene / workspace generator
- lesson: A basename glob like *.tmp also matches the .tmp/ directory, excluding the shared PYTHONPATH utilities from the repo; no negation can rescue children of an excluded parent. Use ?*.tmp and verify the staged manifest against must-have files before any initial push.
- applied: 2026-07-31 — .gitignore fixed (?*.tmp + !.tmp/scripts/**); lesson recorded in skill-observations log

## L003 — natural convection collapses with altitude (rho^2 in Grashof) [APPLIED]
- date: 2026-07-31
- project: -
- target: conjugate_heat_transfer
- lesson: At stratospheric density (30 km: rho ~ 0.018 kg/m3) natural-convection h drops below ~0.5 W/m2K, so high-altitude thermal design is radiation-dominated; convection is a correction, not the mechanism. Bound designs with sunlit + eclipse radiative cases first.
- applied: 2026-07-31 — atmosphere.py natural_convection_h + SKILL.md space/high-altitude section

## L004 — harness practices from vjvarada/coding-agent-setup [APPLIED]
- date: 2026-07-31
- project: -
- target: self_annealing
- lesson: Adopted: placement-before-building map for lessons (Principle 7), compressed solver output discipline (Principle 2), fail-closed outward actions incl. never auto-commit (HARNESS-PRACTICES 2), tests as necessary-not-sufficient with smoke-run validation (Principle 4).
- applied: 2026-07-31 — encoded in self_annealing SKILL.md 'Harness disciplines' + agent rules 8-9

## L005 — chtMultiRegionSimpleFoam reads p in every region, solids included [APPLIED]
- date: 2026-08-03
- project: balloon-ttp/cht-30km-spaced-radiators
- target: conjugate_heat_transfer / .tmp/scripts/cht_case.py
- lesson: A prior optimisation (commit ed68f37) skipped writing 0/<region>/p for solid regions when solver.mode == "steady", on the assumption only chtMultiRegionFoam (transient) needs it. False — chtMultiRegionSimpleFoam (steady) also reads p for every region incl. solids with zero fluid regions present; without it the solver crashes at region initialisation with "cannot find file .../0/<region>/p". The pre-existing cht-30km baseline case only worked because it predates that optimisation and still has p on disk from the original unconditional write.
- applied: 2026-08-03 — cht_case.py write_regions() now always writes the dummy p field for solid regions regardless of solver.mode; verified against the balloon-ttp/cht-30km-spaced-radiators solid-only steady case (smoke + full 500-iteration run both complete); tests/test_cht.py + full suite pass.

## L006 — smoke run leaves a resume-breaking stale latestTime dir before a full run [OPEN]
- date: 2026-08-03
- project: balloon-ttp/cht-30km-spaced-radiators
- target: conjugate_heat_transfer / run_cht_case.py, cht_pipeline.solve
- lesson: controlDict uses startFrom latestTime with writeInterval 250 but --smoke stops at iteration 50 (not a writeInterval multiple), so the smoke run's endTime write only contains function-object output (e.g. wallHeatFlux), not core fields (T, p) — OpenFOAM only auto-writes fields on a writeInterval boundary, not on early stopAt. A subsequent full run then resumes from that incomplete "50" time dir via startFrom latestTime and crashes reading .../50/<region>/p. Worked around manually here by deleting case/<N> before the full run. Any --smoke then bare run_cht_case.py sequence on a fresh case hits this.
- target fix (not yet made): either purge non-writeInterval-aligned time dirs before a full run, or force startFrom startTime whenever iterations/end_time is explicitly overridden downward then back up, or make --smoke's stop point always land on a writeInterval multiple.

## L007 — build_report.py hardcodes marine-exhaust boilerplate for all study types [APPLIED]
- date: 2026-08-04
- project: balloon-ttp
- target: .github/skills/report_generation/scripts/build_report.py
- lesson: report_generation/scripts/build_report.py's Problem Statement, Methodology, Operating Conditions, Boundary Conditions, Geometry, and Validation Methodology sections are hardcoded for the multiphase marine-exhaust CFD study (compressibleInterFoam, pipe/submergence geometry) regardless of the actual study type. For a CHT study (balloon-ttp/transient-0-40km) this produced a report describing the wrong solver and physics entirely; only the mesh stats and figure embedding are genuinely study-derived. Had to hand-rewrite Sections 1-4, 6, 9, 10 in report.md and regenerate report.html from it (embed logic in build_report.py lines ~210-226) to get a correct report. Fix: make build_report.py branch its narrative sections on study/solver type (read cht_manifest.json's application field, or a study-type flag) instead of always emitting the marine-exhaust template.
- applied: 2026-08-04 — Made build_report.py detect CHT/step_assembly studies via case/cht_manifest.json and branch the Problem Statement, Methodology, Operating Conditions/Materials, Boundary Conditions, Geometry, Results and Validation Methodology sections onto CHT-specific content (component materials, patch BCs, TCR joints, per-region T ranges, external heat flows) instead of the marine-exhaust template. Verified by re-running build_report.py against balloon-ttp/transient-0-40km.

## L008 — ElmerFEM as second FEA backend [APPLIED]
- date: 2026-08-04
- project: harness
- target: fea_analysis
- lesson: Added ElmerFEM as a --solver elmer option in fea_analysis (alongside CalculiX default). No Ubuntu 24.04 apt/PPA package exists, so it must be compiled from source (serial, no-GUI CMake build). The same gmsh mesh serves both solvers by tagging physical groups (inner/outer/fixed/far surfaces, pipe volume) that ElmerGrid carries into mesh.boundary as boundary IDs; CalculiX ignores the tags and keeps using geometry-based node sets. Elmer's StressSolve needs a Direct/umfpack linear solver for the elasticity stage -- the default Iterative/BiCGStab+ILU1 failed to converge after 500 iterations on a ~50k-node mesh. Elmer's StressSolver emits a vonmises nodal field natively (no manual tensor combination like the CalculiX .frd parser needs). Cross-validated: both solvers gave identical max displacement (2.461 mm) and von Mises within ~8% on the same smoke-test case.
- applied: 2026-08-04 — Integrated: fea_analysis SKILL.md (solver table, gotchas), solver_environment SKILL.md (--with-elmer), AGENTS.md solver table, run_pipe_fea.py (--solver elmer path + shared physical-group mesh tagging), wsl_bridge.py/install_solvers.py/check_environment.py (elmer detection+install), tests/test_toolchain.py (3 new tests)

## L009 — environment.py double-counted Earth IR in altitude_environment bc_json [APPLIED]
- date: 2026-08-05
- project: balloon-ttp
- target: .github/skills/conjugate_heat_transfer/scripts/environment.py
- lesson: environment.py's suggested bc_json for the non-orbit (altitude_environment) BC type set absorbed_flux_W_m2 = q_total_W_m2 (solar + albedo + q_earth_ir). But sky_sink_temperature() (used downstream by cht_case.py/stage_transient_bcs.py via equivalent_sink_temperature(eps, absorbed_flux, sky_sink_temperature(altitude))) already folds Earth's IR emission into the sink temperature via T_EARTH_EFF=255K, which is numerically the same physical quantity as EARTH_IR=240 W/m2 (sigma*255^4=239.8 W/m2). Including q_earth_ir again in absorbed_flux_W_m2 double-counts it, moving the effective sink temperature from -60C to -20C at 2500m (a 40C error) -- discovered while setting up a sun-facing hot case for balloon-ttp/transient-0-40km. Fixed by excluding q_earth_ir from the altitude_environment bc_json (only q_solar+q_albedo belong there); the --orbit/space_environment path is unaffected since it uses base_sink_K=T_SPACE alone with no separate Earth-IR term to collide with.
- applied: 2026-08-05 — Fixed environment.py's non-orbit bc_json to use q_solar+q_albedo only for absorbed_flux_W_m2, added an explanatory note field to the CLI output. Verified numerically (sink temp swing -60C -> -20C without the fix) and pytest still passes (62 passed, 3 skipped).

## L010 — assign_materials.py --overrides silently merged instead of replacing [APPLIED]
- date: 2026-08-06
- project: balloon-ttp
- target: .github/skills/step_assembly/scripts/assign_materials.py
- lesson: component.setdefault('overrides', {}).update(json.loads(args.overrides)) meant passing --overrides '{}' to clear a component's overrides (e.g. switching materials and wanting the new material's own defaults) was a silent no-op -- it kept the old material's stale override values (e.g. OFHC kappa=390 survived a switch to a copper_etp material entry with kappa=386, invalidating a material-comparison study until caught by manually diffing thermophysicalProperties). Fixed to full-replace semantics: comp['overrides'] = json.loads(args.overrides). Every existing runbook caller already passes the complete desired override set in one call, so no caller relied on incremental merge.
- applied: 2026-08-06 — Fixed: --overrides now replaces (comp['overrides'] = json.loads(...)) instead of merging. Verified via tests/test_cht.py, tests/test_toolchain.py pass and manual manifest check.
## L011 — ollama/run_agent.ps1 needed a non-interactive AutoApprove mode for unattended runbook execution [APPLIED]
- date: 2026-08-06
- project: balloon-ttp
- target: ollama/run_agent.ps1
- lesson: The original driver only supported interactive Read-Host approval per proposed command, which cannot run from a non-interactive tool shell (stdin is /dev/null). Added -AutoApprove (executes every proposed command unattended, same installer hard-block regex stays active), -TranscriptPath (full turn-by-turn log, retried against transient Windows file-lock contention from concurrent readers), -MaxTurns safety cap, and a command-history-based loop-guard (tracks the last 8 proposed commands; skips+nudges on a repeat, aborts cleanly after it recurs 4x) since a small model can cycle through 2-3 distinct commands (re-inspect a log, re-run a step, re-inspect again) without ever repeating one back-to-back, which a same-as-last-turn check alone would miss.
- applied: 2026-08-06 — Added -AutoApprove, -TranscriptPath (retry-hardened), -MaxTurns, and command-history loop-guard to ollama/run_agent.ps1. Verified via successful C0-C5 unattended runs (3x) and clean loop-guard stop on the checkMesh cycle.
## L012 — cfd-qwen (qwen2.5-coder:7b) cannot reliably recognise a documented benign checkMesh WARNING as expected [APPLIED]
- date: 2026-08-06
- project: balloon-ttp
- target: ollama/Modelfile.cfd
- lesson: Across three unattended AutoApprove attempts on the transient-0-40km-etp-copper runbook, cfd-qwen consistently failed to treat the known, documented, non-fatal checkMesh WARNING (CAD sliver face, ok:false but no FOAM FATAL) as 'proceed, don't fix' -- even after the runbook was strengthened with an explicit 'do not re-run setup_cht_case.py to try to fix this' instruction and the driver added a corrective nudge. It instead invented plausible-sounding but nonexistent remediation scripts (fix_mesh_regions.py, refine_mesh.py, smooth_mesh.py -- none exist in this repo) and cycled between inspecting the log and re-running the step. The run_agent.ps1 loop-guard catches the resulting cycle and stops cleanly (no wasted turn budget / no risk of the model inventing destructive fixes), but a human/Claude currently needs to take over Part C execution from that gate onward -- this is a genuine 7B-model capability limit for this judgment call, not a prompt-engineering-fixable issue at this model size. Future runbooks with a known benign warning at a fixed step should consider pre-clearing/pre-acknowledging it before handoff, or accept takeover at that gate.
- applied: 2026-08-06 — Documented in OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM_ETP_COPPER.md Part D and outputs/balloon-ttp/PROJECT.md as a known limitation; no Modelfile/prompt change attempted further since 3 independent mitigation attempts (base instruction, strengthened instruction, driver loop-guard) all confirmed this is a 7B capability limit, not a prompt-fixable issue.

## L013 — run_agent.ps1: model echoes step-id/prose inside the code fence, breaking PowerShell parsing [APPLIED]
- date: 2026-08-06
- project: balloon-ttp
- target: ollama/run_agent.ps1
- lesson: cfd-qwen sometimes puts the bare runbook step id (e.g. 'C0') or a full English sentence (e.g. 'The checkMesh WARNING is expected, proceed.') as the first line INSIDE the fenced powershell block, not just in prose outside it. Under $ErrorActionPreference='Stop', PowerShell tries to run that text as a command -- best case 'term not recognized', worst case an unterminated string (an apostrophe like file's opens a string literal that's never closed) -- either way the real command on a later line never executes, and the resulting error is opaque. Fixed in Get-Command-Block: strip a leading bare step-id line (regex anchored so Copy-Item etc. are never touched), then strip any further leading lines that look like English sentences (heuristic: starts with a capital letter + lowercase word, doesn't contain PowerShell code markers like $, \, --flag, .py/.exe, or a Verb-Noun cmdlet prefix) until a real code line is found. An all-prose block correctly reduces to an empty string (treated as 'no command').
- applied: 2026-08-06 — Fixed in Get-Command-Block: strips leading step-id and English-sentence lines before execution. Verified via unit tests and a live run that cleared the exact checkMesh-acknowledgment case that previously failed.
## L014 — Windows PowerShell 5.1 strips embedded double-quotes from single-quoted args to native exes [APPLIED]
- date: 2026-08-06
- project: balloon-ttp
- target: ollama/run_agent.ps1
- lesson: Confirmed via minimal repro: & python.exe -c "print(sys.argv[1])" '{"a":"b"}' arrives at the python process as {a:b} -- PS 5.1's native-command argv reconstruction silently drops the double quotes (documented upstream PS behavior, fixed in PS7's $PSNativeCommandArgumentPassing='Standard' which doesn't exist in 5.1). This breaks every --bc/--overrides/--solver JSON argument pattern used throughout this repo's runbooks when actually executed via real PowerShell 5.1 (Invoke-Expression or direct native call, not just Invoke-Expression specifically) -- the resulting json.JSONDecodeError's first stderr line becomes a terminating NativeCommandError under $ErrorActionPreference='Stop', discarding the rest of the traceback and masking the real cause. The fix that works: escape embedded double quotes as \" inside the single-quoted argument (verified: cmd /c also works, doubled double-quotes "" does NOT). Fixed in run_agent.ps1's Get-Command-Block: auto-escapes quotes inside single-quoted {...} argument segments before execution, regardless of how the model formatted the JSON. Prior 'completed' studies that used this JSON pattern were apparently run via a different path (Bash/WSL, or PS7) that doesn't hit this bug -- worth checking if any repo runbook is ever driven by genuine PS5.1 again.
- applied: 2026-08-06 — Fixed in Get-Command-Block: auto-escapes embedded double quotes in single-quoted {...} JSON argument segments before execution. Verified via minimal repro (before: {a:b}, after: {"a":"b"}) and a live run where the --solver JSON call succeeded.
## L015 — cfd-qwen can silently skip a required runbook step and not self-verify its own stated gate [OPEN]
- date: 2026-08-06
- project: balloon-ttp
- target: OLLAMA_QWEN_TRANSIENT_RUNBOOK_DWELL_40KM_60MIN_ETP_COPPER.md
- lesson: On the dwell-60min-etp-copper runbook, cfd-qwen correctly ran C4/C5's setup_cht_case.py and correctly navigated the checkMesh warning (the proactive-injection fix worked), but then skipped the Copy-Item command that restores the prior study's solved case/9600 state, and jumped straight to the C6 smoke test. The smoke test's own JSON output showed n_steps: 4805 (a full fresh solve from t=0, matching 9610s/deltaT=2.0s) instead of the runbook's stated gate of n_steps: 5 -- but the model didn't check its own output against the stated gate, declared the step done, and queued the 3-segment full solve on top of the invalid base. Caught only by a human/Claude reading run_summary.json against the runbook's explicit gate before the expensive multi-segment run compounded it (would have wasted ~10+ minutes of solve time and produced an invalid, non-restart-continuous result). No driver-level fix implemented -- gates are natural-language criteria in the runbook text, not mechanically checkable without study-specific parsing. Mitigation for now: always manually verify n_steps/completed/final_time from run_summary.json against the runbook's stated gate before trusting further unattended progress, especially at any restart/continuation boundary.

## L016 — cfd-qwen conflated a runbook's smoke test with the following real production segment [OPEN]
- date: 2026-08-07
- project: balloon-ttp
- target: OLLAMA_QWEN_TRANSIENT_RUNBOOK_SHORTER_STRAP_3HR.md
- lesson: On the shorter-strap 3-hour-mission runbook, cfd-qwen correctly ran C0-C2 (environment gate, manifest validation, segment-1 BC staging) and C3 (the `--end-time 10` smoke test), but then treated the smoke test as if it were the real segment-1 solve: ran cht_kpis.py, pruned the case directory, and jumped straight to staging segment 2 -- never issuing the actual `--end-time 900` command from C4. It then got stuck retrying the segment-2 staging call 4 times in a row (apologizing each time: "I apologize for the oversight... Let's proceed to stage the boundary conditions for segment 2" -- without ever noticing segment 1's real solve was still missing). This is the same failure class as L015 (skip a required step, don't self-verify against the stated gate), now specifically at the smoke-test/first-production-segment boundary -- the model appears to pattern-match on "a run_cht_case.py call just succeeded" rather than tracking which specific step (smoke test vs. segment N) it was supposed to be on. The driver's 4-repeat command-history loop-guard caught the resulting stuck cycle and stopped cleanly after 11 turns; because the smoke test's 10 s window never reached the case's `writeInterval`, no time directory beyond `case/0` had actually been written, so the case was undamaged and Claude was able to drive the real 12-segment solve directly rather than retry unattended. No driver-level fix implemented yet. Mitigation for the next runbook this happens on: make the smoke-test command and the first production-segment command visually and numerically distinct in Part C, with an explicit "this is NOT segment 1, do not treat it as such" note directly after the smoke-test command -- mirroring the proactive-injection pattern that fixed L012's checkMesh confusion.

## L017 — write_interval_s must divide the segment length evenly, or a segment boundary gets only a partial field write [APPLIED]
- date: 2026-08-07
- project: balloon-ttp
- target: stage_transient_bcs.py, any manifest's solver.write_interval_s
- lesson: `transient-shorter-strap-40km-3hr` used 900 s segments against the manifest's inherited `write_interval_s: 120` default (900/120 = 7.5, not an integer). `chtMultiRegionFoam`'s postProcessing function objects (`wallHeatFlux`, `fieldMinMax`) have their own independent `writeControl timeStep; writeInterval 10;` (10 timesteps = 20 s at `deltaT_s: 2.0`), so a time directory gets written every 20 s regardless of the top-level `writeInterval` -- but only the ones landing on the *top-level* `write_interval_s` (a multiple of 120 in this case) get the full field set (`T`, `p`, ...); every other 20 s directory has only `wallHeatFlux`. Segment 1's end time (900 s) is not a multiple of 120, so its own end-time directory was one of the partial ones -- no `T` field -- and `stage_transient_bcs.py` failed with `Missing field file` when staging segment 2. Confirmed via `log.reconstructPar`: `Reconstructing volScalarFields` lists only `wallHeatFlux` at t=20,40,...,100,140,... but lists `T`, `p`, `wallHeatFlux` at t=120,240,360,... (exact multiples of the top-level writeInterval). Every prior transient study in this project used a segment length (1200 s, 300 s) that happened to divide the inherited 120 s default cleanly, so this never surfaced before. Fixed by setting `write_interval_s: 90` (a divisor of every 900 s segment boundary: 900, 1800, ..., 10800 are all multiples of 90) via `assign_materials.py --solver '{"write_interval_s":90}'` and rebuilding the case with `setup_cht_case.py --reuse-mesh` before the real solve.
- applied: 2026-08-07 -- `transient-shorter-strap-40km-3hr`'s manifest set to `write_interval_s: 90`; verified `case/900/radiator_plate_top/` contains `T`, `p`, `wallHeatFlux` after the fix (vs. only `wallHeatFlux` before it). No general driver/script-level guard added yet -- the next transient study with a new segment length should explicitly check `write_interval_s` divides it before running, per the note now in `outputs/balloon-ttp/PROJECT.md`'s "Assumptions" section.
