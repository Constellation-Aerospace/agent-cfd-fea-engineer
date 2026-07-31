# agent-cfd-fea-engineer

CFD/FEA engineering simulation agent (DOE Framework). Runs complete simulation
studies end-to-end on a **fully local, open-source solver stack** — no commercial
licences, **no API keys**: OpenFOAM v2412 + CalculiX + Gmsh inside WSL Ubuntu, with
a Python orchestration layer (Gmsh OCC, PyVista, matplotlib) on Windows.

## Capabilities

| Pipeline | What it does |
| --- | --- |
| **Multiphase CFD** | Gas–liquid VOF (`compressibleInterFoam`): thermal mixing, temperature decay, back-pressure, k-omega SST turbulence. Reference workload: submerged marine exhaust discharge |
| **Conjugate heat transfer** | Multi-part STEP assembly → per-component material/BC assignment → `chtMultiRegionSimpleFoam`/`chtMultiRegionFoam` with conduction, convection, and radiation (P1/fvDOM + surface-to-ambient) → heat-exchanger KPIs (duty, effectiveness, LMTD, UA, interface fluxes) |
| **Space / high-altitude thermal** | Satellite (vacuum: conduction + radiation, solar/albedo/Earth-IR loads, radiator sizing) and stratospheric balloon payloads (US Standard Atmosphere 1976, rarefied natural convection, sky sinks) via `space_environment` / `altitude_environment` BCs |
| **FEA** | CalculiX `ccx` thermal-structural analysis |
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

## How it works (DOE architecture)

1. **Skills** — `.github/skills/<name>/SKILL.md` define goals, scripts, and outputs;
   the agent reads the SKILL.md before running its scripts.
2. **Orchestration** — the LLM routes between skills and applies engineering
   judgment (sanity checks, convergence, physics bounds).
3. **Execution** — deterministic Python in `.github/skills/*/scripts/` and shared
   utilities in `.tmp/scripts/` (WSL bridge, case factories, pipelines, materials).

## Available skills

| Skill | Purpose |
| --- | --- |
| `solver_environment` | Verify/install OpenFOAM 2412, CalculiX, Gmsh in WSL |
| `geometry_domain` | Parametric exhaust-discharge domain (Gmsh OCC) + STEP export |
| `step_assembly` | Multi-part STEP import, per-component material/BC manifest, conformal assembly mesh |
| `meshing` | Graded tet meshes + mesh independence study with GCI |
| `multiphase_cfd` | compressibleInterFoam VOF case (gas mixture / seawater, k-omega SST) |
| `conjugate_heat_transfer` | Multi-region CHT (conduction/convection/radiation) + heat-exchanger KPIs |
| `fea_analysis` | CalculiX pipe-wall thermal-structural FEA |
| `post_processing` | Contours, streamlines, temperature decay, back-pressure (PyVista) |
| `parametric_study` | Operating-point sweeps (temperature/velocity/depth) + comparison |
| `report_generation` | Final technical report (Markdown + HTML) |
| `diagramming` | Editable draw.io/Mermaid diagrams (block diagrams only; pictorial figures are hand-authored inline SVG/CSS) |

## Repository layout

```
agent-cfd-fea-engineer.code-workspace   ← double-click to open VS Code
first_run_setup.py / setup.ps1 / SETUP.md   one-command environment bootstrap
AGENTS.md                 full agent instructions (skills, rules, pipelines)
.github/skills/           skill definitions + scripts
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
