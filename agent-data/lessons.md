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
