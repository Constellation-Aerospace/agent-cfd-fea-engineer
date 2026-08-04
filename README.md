# agent-cfd-fea-engineer

CFD/FEA engineering simulation agent (DOE Framework). Runs complete simulation
Studies end-to-end on a **fully local, open-source solver stack** — no commercial
licences, **no API keys**: OpenFOAM v2412 + Gmsh inside WSL Ubuntu, with a default FEA
path through CalculiX and other FEM backends available when the physics calls for them,
plus a Python orchestration layer (Gmsh OCC, PyVista, matplotlib) on Windows.

## Capabilities

| Pipeline | What it does |
| --- | --- |
| **Multiphase CFD** | Gas–liquid VOF (`compressibleInterFoam`): thermal mixing, temperature decay, back-pressure, k-omega SST turbulence. Reference workload: submerged marine exhaust discharge |
| **Conjugate heat transfer** | Multi-part STEP assembly → per-component material/BC assignment → `chtMultiRegionSimpleFoam`/`chtMultiRegionFoam` with conduction, convection, and radiation (P1/fvDOM + surface-to-ambient) → heat-exchanger KPIs (duty, effectiveness, LMTD, UA, interface fluxes) |
| **Space / high-altitude thermal** | Satellite (vacuum: conduction + radiation, solar/albedo/Earth-IR loads, radiator sizing) and stratospheric balloon payloads (US Standard Atmosphere 1976, rarefied natural convection, sky sinks) via `space_environment` / `altitude_environment` BCs |
| **FEA** | CalculiX `ccx` thermal-structural analysis, with other FEM backends when needed |
| **Supporting** | Parametric geometry (Gmsh OCC), graded tet meshing + mesh independence (GCI), parametric sweeps, post-processing (contours, streamlines, decay curves), technical reports (MD/HTML), draw.io/Mermaid diagramming |

## Quick start

**Instant:** double-click `agent-cfd-fea-engineer.code-workspace` — VS Code opens,
runs setup on folder-trust, and offers the recommended extensions. Then pick
**"cfd-fea-engineer"** in the Copilot Chat agent dropdown.

**Manual:**

```powershell
.\setup.ps1        # idempotent: venv → deps → WSL check → solvers → verify → tests
```

See **[SETUP.md](SETUP.md)** for prerequisites (Windows + WSL2 + Python 3.10+),
what gets installed where, flags (`-CheckOnly`, `-SkipSolvers`), and
troubleshooting. If WSL Ubuntu is missing, setup stops and tells you exactly what
to run. Re-verify any time:

```powershell
.venv\Scripts\python.exe .github/skills/solver_environment/scripts/check_environment.py
```

Before the first solver run, open Ubuntu once and complete the Linux user creation
prompt. If WSL reports `Create a default Unix user account`, the solver bridge is not
ready yet even though WSL itself is installed.

## First heat-exchanger study (multi-part STEP file)

```powershell
.venv\Scripts\python.exe .github/skills/step_assembly/scripts/inspect_step.py --study <project>/hx --step inputs\<project>\assembly.step
.venv\Scripts\python.exe .github/skills/step_assembly/scripts/assign_materials.py --study <project>/hx --list
# assign fluid/solid types, materials, boundary conditions (SKILL.md has the schema), then:
.venv\Scripts\python.exe .github/skills/conjugate_heat_transfer/scripts/setup_cht_case.py --study <project>/hx
.venv\Scripts\python.exe .github/skills/conjugate_heat_transfer/scripts/run_cht_case.py --study <project>/hx --smoke
.venv\Scripts\python.exe .github/skills/conjugate_heat_transfer/scripts/cht_kpis.py --study <project>/hx
```

Multiphase reference pipeline: see "Typical Study" in [AGENTS.md](AGENTS.md).

## Satellite / high-altitude balloon thermal

Compute the thermal environment and get ready-to-paste boundary conditions:

```powershell
# stratospheric balloon payload at 30 km (white paint, 0.5 m characteristic size)
.venv\Scripts\python.exe .github/skills/conjugate_heat_transfer/scripts/environment.py --altitude 30000 --emissivity 0.9 --alpha-solar 0.2 --L-char 0.5

# LEO satellite, sunlit hot case + radiator area hint for 200 W dissipation
.venv\Scripts\python.exe .github/skills/conjugate_heat_transfer/scripts/environment.py --orbit --altitude 500000 --emissivity 0.88 --alpha-solar 0.2 --internal-power 200

# eclipse cold case
.venv\Scripts\python.exe .github/skills/conjugate_heat_transfer/scripts/environment.py --orbit --altitude 500000 --emissivity 0.88 --no-sun
```

Paste the printed `bc_json` onto the exposed surfaces via `assign_materials.py`,
then run the same CHT pipeline as above. Satellite assemblies are solid-only
(conduction + radiation, vacuum); balloon studies can model the surrounding
rarefied air as a fluid region for resolved natural convection. Physics backing:
US Standard Atmosphere 1976, view-factor-weighted sky sinks, solar/albedo/Earth-IR
loads — see the `conjugate_heat_transfer` SKILL.md for models and limitations.

## Learning from every simulation

Every completed study (multiphase CFD, CHT, FEA) is automatically harvested — its
inputs, the solver knobs used, and an outcome-quality score — into
`agent-data/learning_history.json`. Query it before setting up a similar case:

```powershell
.venv\Scripts\python.exe .github/skills/self_learning/scripts/recommend.py `
    --case-type conjugate_heat_transfer --like <project>/<a-similar-study>
```

Returns a confidence score, recommended solver knobs, and the nearest past studies
it drew from — confidence rises automatically as more studies accumulate, with no
retraining step. See the `self_learning` SKILL.md for what's learned per case type.

## How it works (DOE architecture)

1. **Skills** — `.github/skills/<name>/SKILL.md` define goals, scripts, and outputs;
   the agent reads the SKILL.md before running its scripts.
2. **Orchestration** — the LLM routes between skills and applies engineering
   judgment (sanity checks, convergence, physics bounds).
3. **Execution** — deterministic Python in `.github/skills/*/scripts/` and shared
   utilities in `.tmp/scripts/` (WSL bridge, case factories, pipelines, materials).

The harness is authored once and shared by every agentic tool: GitHub Copilot and
Copilot Chat enter through `.github/copilot-instructions.md` /
`.github/agents/cfd-fea-engineer.agent.md`, Claude Code through
[CLAUDE.md](CLAUDE.md), and any AGENTS.md-aware tool through
[AGENTS.md](AGENTS.md) — all of them running the same `.github/skills/`.
`.claude/skills/` holds generated proxies; refresh them with
`python .tmp/scripts/sync_agent_docs.py` after adding or renaming a skill.

## Extending with more solvers

Committing new solver code to this repo does not retrain the base model weights. It
does extend the repo-grounded agent behavior because the agent reads new `SKILL.md`
files and can now execute repo skill scripts dynamically.

1. Add `.github/skills/<solver_name>/SKILL.md` with the solver workflow, inputs,
   outputs, and guardrails.
2. Add Python entry points under `.github/skills/<solver_name>/scripts/`.
3. Commit the new skill to the repo.
4. Use `list_available_skill_scripts` to confirm discovery and `run_skill_script` to
   execute the new solver workflow.

That keeps solver onboarding version-controlled and makes uploaded solver integrations
available without changing `agents.py` again.

A new skill is picked up by every tool at once. After adding one, run
`python .tmp/scripts/sync_agent_docs.py` so Claude Code's proxies include it.

## Available skills

| Skill | Purpose |
| --- | --- |
| `solver_environment` | Verify/install OpenFOAM 2412, CalculiX, Gmsh in WSL; track additional FEM backends |
| `geometry_domain` | Parametric exhaust-discharge domain (Gmsh OCC) + STEP export |
| `step_assembly` | Multi-part STEP import, per-component material/BC manifest, conformal assembly mesh |
| `meshing` | Graded tet meshes + mesh independence study with GCI |
| `multiphase_cfd` | compressibleInterFoam VOF case (gas mixture / seawater, k-omega SST) |
| `conjugate_heat_transfer` | Multi-region CHT (conduction/convection/radiation), heat-exchanger KPIs, satellite/high-altitude environments (`environment.py`) |
| `fea_analysis` | CalculiX pipe-wall thermal-structural FEA, extensible to other FEM backends |
| `post_processing` | Contours, streamlines, temperature decay, back-pressure (PyVista) |
| `parametric_study` | Operating-point sweeps (temperature/velocity/depth) + comparison |
| `report_generation` | Final technical report (Markdown + HTML) |
| `diagramming` | Editable draw.io/Mermaid diagrams (block diagrams only; pictorial figures are hand-authored inline SVG/CSS) |
| `self_annealing` | Continuous improvement loop: lessons captured per project (`agent-data/lessons.md`), integrated into skills, session-end commit gate |
| `self_learning` | Auto-harvests every completed study's inputs/knobs/outcome quality (`agent-data/learning_history.json`); recommends solver settings by weighted similarity to past runs — recommendations improve with every simulation, no retraining step |

## Repository layout

```
agent-cfd-fea-engineer.code-workspace   ← double-click to open VS Code
first_run_setup.py / setup.ps1 / SETUP.md   one-command environment bootstrap
AGENTS.md                 full agent instructions (skills, rules, pipelines)
CLAUDE.md                 Claude Code entry point → AGENTS.md + Claude-specific notes
.github/skills/           skill definitions + scripts (canonical)
.claude/skills/           generated proxies so Claude Code discovers the same skills
.tmp/scripts/             shared utilities: wsl_bridge, foam_case, cht_case,
                          step_assembly, materials, study/cht pipelines, memory
agent-data/               reference data + materials_library.json
inputs/<project>/         user-provided CAD/specs (confidential — not committed)
outputs/<project>/<study>/  project-wise studies: params, mesh, case, figures, report
tests/                    pytest CI gate (case factories testable without WSL)
memory/                   persistent agent memory
```

## Ground rules

- Never fabricate simulation results — every number comes from solver output.
- Smoke-run every new configuration before a production run.
- Sanity-check physics (CHT energy balance < 5 %, bounded temperatures,
  back-pressure > hydrostatic) and take `checkMesh`/Courant warnings seriously.
- SI units internally; °C and kPa (gauge vs absolute stated) in reports.

---

*This workspace was generated from the [DOE Framework](https://github.com/vjvarada/DOE-Framework-Agentic-AI)
and extended with the conjugate heat transfer toolchain.*
