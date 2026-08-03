# .github/skills/ — the skill library

One folder per capability. Each contains a `SKILL.md` (goal, when to use it, inputs,
CLI usage, outputs, guardrails, limitations) and a `scripts/` folder of deterministic
Python entry points. **The agent reads `SKILL.md` before running that skill's
scripts** — the Markdown is the contract, the scripts are the execution.

| Skill | Purpose |
| --- | --- |
| `solver_environment` | Verify/install OpenFOAM v2412, CalculiX, Gmsh in WSL (`check_environment.py` is the readiness gate) |
| `geometry_domain` | Parametric exhaust-discharge domain (Gmsh OCC) + STEP export |
| `step_assembly` | Multi-part STEP import, per-component material/BC manifest, conformal assembly mesh |
| `meshing` | Graded tet meshes + mesh independence study with GCI |
| `multiphase_cfd` | `compressibleInterFoam` VOF case (gas mixture / seawater, k-omega SST) |
| `conjugate_heat_transfer` | Multi-region CHT (conduction/convection/radiation), heat-exchanger KPIs, satellite/high-altitude environments (`environment.py`) |
| `fea_analysis` | CalculiX thermal-structural FEA |
| `post_processing` | Contours, streamlines, temperature decay, back-pressure (PyVista) |
| `parametric_study` | Operating-point sweeps (temperature/velocity/depth) + comparison |
| `report_generation` | Final technical report (Markdown + HTML) |
| `diagramming` | Editable draw.io/Mermaid diagrams (block diagrams only) |
| `self_annealing` | Continuous-improvement loop: capture lessons, integrate into skills, session-end commit gate |

## Layout

```
<skill_name>/
  SKILL.md          goal, inputs, outputs, usage, guardrails  ← read this first
  scripts/*.py      CLI entry points, run from the repo root with the venv Python
```

Scripts take `--study <project>/<study-slug>` and write under
`outputs/<project>/<study-slug>/`. Shared logic (WSL bridge, case factories,
materials, pipelines) lives in `.tmp/scripts/`, not here — skill scripts are thin
CLI wrappers over it.

## Adding a skill

1. `mkdir <skill_name>/scripts`, write `SKILL.md` with the workflow and guardrails.
2. Add the Python entry points under `scripts/`.
3. Add a row to the table above and to the repo `README.md` / `AGENTS.md`.
4. Add a contract test in `tests/test_toolchain.py` (script paths are asserted there).
5. Commit — discovery is dynamic, `agents.py` needs no change.
