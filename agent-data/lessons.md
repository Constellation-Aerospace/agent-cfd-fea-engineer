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
