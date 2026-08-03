# agent-cfd-fea-engineer

CFD/FEA engineering simulation agent (DOE Framework v2). Reference workload: submerged
marine exhaust discharge — hot multi-component diesel exhaust into seawater (multiphase
VOF, thermal mixing, back-pressure, k-omega SST turbulence). Also: conjugate heat
transfer on multi-part STEP assemblies (heat exchangers) — per-component materials/BCs,
conduction + convection + radiation via `chtMultiRegion*Foam`.

- **Solvers:** OpenFOAM v2412 (`compressibleInterFoam`, `chtMultiRegionSimpleFoam`/
  `chtMultiRegionFoam`) + CalculiX ccx in WSL Ubuntu;
  Gmsh + PyVista on the Windows side. Bridge: `.tmp/scripts/wsl_bridge.py`.
- **Skills:** `.github/skills/*/SKILL.md` — read the relevant SKILL.md before running
  its scripts. Outputs are project-wise: `outputs/<project>/<study-slug>/`
  (nested `--study` slugs; see `outputs/README.md`).
- **Shared harness:** `AGENTS.md` holds the full operating instructions; the same skills
  are consumed by Claude Code via `CLAUDE.md` + generated `.claude/skills/` proxies.
  Author changes under `.github/` only, then run
  `python .tmp/scripts/sync_agent_docs.py` (gated by `tests/test_agent_docs.py`).
- **Pipeline:** geometry → mesh → case → smoke run → production run → post-processing →
  mesh independence → parametric sweep → FEA → report.
- **Rules:** never fabricate results; smoke-run new configs (`--end-time 0.2`); sanity-check
  physics (back-pressure > hydrostatic, T within [water, exhaust]); SI units, °C/kPa in
  reports. Run scripts with the venv Python from the repo root.
- **Self-annealing:** log every newly learned technique/gotcha
  (`.github/skills/self_annealing/scripts/anneal.py log`), integrate lessons into the
  target skills, and at session end run `anneal.py check --run-tests` — when changes
  are uncommitted, present the suggested commit and prompt the user to commit.
