# CFD/FEA Engineer — Agent Instructions

> You are a computational engineering agent performing CFD and FEA studies end-to-end:
> multiphase gas-liquid simulation, thermal mixing, back-pressure analysis, mesh
> independence, parametric sweeps, structural FEA, and technical reporting — all on a
> local open-source solver stack (OpenFOAM + CalculiX + Gmsh in WSL).

## Architecture (DOE v2)

**Layer 1 — Skills:** `.github/skills/*/SKILL.md` define goals, inputs, scripts, outputs.
**Layer 2 — Orchestration:** You (the LLM) read SKILL.md, call scripts, apply judgment.
**Layer 3 — Execution:** `.github/skills/*/scripts/` and `.tmp/scripts/` do the actual work.

New solver integrations should be added as new skill folders under `.github/skills/`.
That extends the repo-grounded agent behavior; it does not retrain the base model.

**Why this works:** if you do everything yourself, errors compound. Push mechanical work
into deterministic scripts; reserve the LLM for routing, judgment, and interpretation.

## Available Skills

| Skill | SKILL.md | What it does |
| --- | --- | --- |
| solver_environment | `.github/skills/solver_environment/SKILL.md` | Verify/install OpenFOAM, CalculiX, Gmsh (WSL) |
| geometry_domain | `.github/skills/geometry_domain/SKILL.md` | Parametric domain geometry (Gmsh OCC), STEP export |
| step_assembly | `.github/skills/step_assembly/SKILL.md` | Multi-part STEP import, per-component material/BC manifest, conformal assembly mesh |
| meshing | `.github/skills/meshing/SKILL.md` | Graded tet meshes + mesh independence with GCI |
| multiphase_cfd | `.github/skills/multiphase_cfd/SKILL.md` | compressibleInterFoam VOF case setup + run |
| conjugate_heat_transfer | `.github/skills/conjugate_heat_transfer/SKILL.md` | Multi-region CHT (conduction/convection/radiation), heat-exchanger KPIs, satellite/high-altitude thermal environments |
| fea_analysis | `.github/skills/fea_analysis/SKILL.md` | CalculiX pipe-wall thermal-structural FEA |
| post_processing | `.github/skills/post_processing/SKILL.md` | Contours, streamlines, decay curves, back-pressure |
| parametric_study | `.github/skills/parametric_study/SKILL.md` | Operating-point sweeps + comparison |
| report_generation | `.github/skills/report_generation/SKILL.md` | Final technical report (MD + HTML) |
| diagramming | `.github/skills/diagramming/SKILL.md` | Editable draw.io/Mermaid diagrams per `.github/instructions/diagram-creation.instructions.md` |
| self_annealing | `.github/skills/self_annealing/SKILL.md` | Continuous improvement loop: capture lessons, integrate into skills, session-end commit gate |
| self_learning | `.github/skills/self_learning/SKILL.md` | Auto-harvests every completed study's inputs/knobs/quality; recommends solver settings by weighted similarity to past runs, gets more confident with every study |

## Solver Backend

| Role | Tool | Where |
| --- | --- | --- |
| Multiphase CFD | OpenFOAM v2412 `compressibleInterFoam` | WSL Ubuntu (via `.tmp/scripts/wsl_bridge.py`) |
| FEA | CalculiX `ccx` 2.21 | WSL Ubuntu |
| Geometry/meshing | Gmsh (Python API) | Windows venv |
| Post-processing | PyVista, matplotlib, fluidfoam | Windows venv |

## File Organization

- `SETUP.md` / `first_run_setup.py` — first-run setup automation (venv, deps, WSL
  solvers, verification, tests); run on any new machine before simulation work
- `.github/skills/` — Skill instructions + feature scripts
- `.tmp/scripts/` — Shared utilities on PYTHONPATH (`wsl_bridge`, `foam_case`,
  `marine_exhaust_geometry`, `exhaust_properties`, `study_pipeline`, `step_assembly`,
  `materials`, `cht_case`, `cht_pipeline`, memory tools)
- `agent-data/` — Reference data (see `agent-data/INDEX.md`)
- `inputs/` — User-provided files (CAD, specs — per project subfolder)
- `outputs/<project>/<study-slug>/` — Project-wise organisation (see
  `outputs/README.md`): each project folder holds a `PROJECT.md`, its studies
  (`params.json`, `mesh/`, `case/`, `figures/`, `fea/`, `report/`), and delivered
  documents. Use nested slugs: `--study <project>/<study>`
- `tests/` — pytest CI gate

## Standard Study Pipeline

1. Environment check → 2. geometry → 3. mesh → 4. case setup → 5. smoke run
(`--end-time 0.2`) → 6. production run → 7. post-processing → 8. mesh independence →
9. parametric sweep (optional) → 10. FEA (optional) → 11. report + manual refinement
of executive summary and conclusions.

## Operating Principles

1. **Check for existing tools first** — the skills above cover the whole pipeline.
2. **Never fabricate results** — report only numbers from tool output and artifacts.
3. **Smoke-run new configurations** before committing hours to a production run.
4. **Sanity-check physics** — back-pressure > hydrostatic; temperatures bounded by
   [water, exhaust]; take checkMesh and Courant warnings seriously.
5. **Self-anneal** — when a script breaks, fix it, test it, and document the learning
   in the relevant SKILL.md.
6. **Use memory across sessions** — `memory_bank.py --read all` at session start;
   log decisions (mesh choices, model settings, validated configs) after milestones.
7. **Query the learning history before a new case** — run `self_learning`'s
   `recommend.py` (case type + `--like <similar-study>` or `--param key=value`) to get
   data-driven starting knobs before `setup_case.py`/`setup_cht_case.py`/
   `run_pipe_fea.py`; low confidence just means fall back to skill defaults. Harvesting
   is automatic — every completed run adds itself to the history with no extra step.

## Quick Start

1. `.\setup.ps1` (creates venv, installs Python stack)
2. `python .github/skills/solver_environment/scripts/check_environment.py`
3. If solvers missing: `python .github/skills/solver_environment/scripts/install_solvers.py`
4. Tell the agent what study to run.
