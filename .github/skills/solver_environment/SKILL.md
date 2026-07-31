---
name: solver_environment
description: >
  Verify and install the CFD/FEA solver backend: OpenFOAM 2412, CalculiX ccx, and Gmsh
  inside WSL Ubuntu, plus the Windows-side Python stack (gmsh, pyvista, meshio, fluidfoam).
  Use before any simulation work, when solver commands fail, on a new machine, or when the
  user asks "is OpenFOAM installed", "set up solvers", or "check the environment".
when_to_use: "At session start before simulations; after any solver-not-found error; on new machines."
authority: execute
cost_tier: 1
version: 0.1.0
---

# Solver Environment

Verifies (and installs, if missing) the full open-source solver toolchain that replaces
commercial codes (ANSYS Fluent / Mechanical) in this workspace:

| Role | Tool | Where |
| --- | --- | --- |
| Multiphase CFD solver | OpenFOAM v2412 (`compressibleInterFoam`) | WSL Ubuntu |
| FEA solver | CalculiX `ccx` 2.21 | WSL Ubuntu |
| Geometry + meshing | Gmsh (Python API on Windows; CLI also in WSL) | Both |
| Post-processing | PyVista + matplotlib + fluidfoam | Windows venv |

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/check_environment.py` | Full toolchain health check — prints JSON status, exit 0 = ready |
| `scripts/install_solvers.py` | Idempotent install of OpenFOAM/CalculiX/Gmsh into WSL Ubuntu |

## Usage

```bash
python .github/skills/solver_environment/scripts/check_environment.py
python .github/skills/solver_environment/scripts/install_solvers.py          # install what's missing
python .github/skills/solver_environment/scripts/install_solvers.py --force  # reinstall
```

First run on a new machine: `python first_run_setup.py` at the repo root chains
everything (venv → pip deps → WSL check → this skill's installer → verification →
pytest gate) and writes `setup_report.json`. See `SETUP.md` for the full guide.
The check covers the CHT toolchain too (`chtMultiRegionSimpleFoam`,
`chtMultiRegionFoam`, `splitMeshRegions`, `gmshToFoam`, `foamToVTK`) via the
`openfoam_cht` status key.

## Requirements

- Windows with WSL2 and an Ubuntu distro (`wsl -l -v` must list Ubuntu).
- Python venv with `requirements.txt` installed (`.\setup.ps1` or `first_run_setup.py`).
- No API keys needed — everything runs locally.

## Outputs

`check_environment.py` prints a JSON status block; non-zero exit means something is
missing and `install_solvers.py` should be run.
