---
name: solver_environment
description: >
  Verify and install the CFD/FEA solver backend: OpenFOAM 2412, CalculiX ccx, Gmsh, and
  optionally ElmerFEM, inside WSL Ubuntu, plus the Windows-side Python stack (gmsh,
  pyvista, meshio, fluidfoam). Track additional FEM backends as they are integrated, but
  keep this skill focused on the core ready-to-run stack. Use before any simulation
  work, when solver commands fail, on a new machine, or when the user asks "is OpenFOAM
  installed", "set up solvers", "install Elmer", or "check the environment".
when_to_use: "At session start before simulations; after any solver-not-found error; on new machines."
authority: execute
cost_tier: 1
version: 0.2.0
---

# Solver Environment

Verifies (and installs, if missing) the full open-source solver toolchain that replaces
commercial codes (ANSYS Fluent / Mechanical) in this workspace:

| Role | Tool | Where |
| --- | --- | --- |
| Multiphase CFD solver | OpenFOAM v2412 (`compressibleInterFoam`) | WSL Ubuntu |
| FEA solver (default) | CalculiX `ccx` 2.21 | WSL Ubuntu |
| FEA solver (optional) | ElmerFEM (`ElmerSolver`, `ElmerGrid`) — see `fea_analysis` skill's `--solver elmer` | WSL Ubuntu |
| FEM extension points | Code_Aster, FEniCSx, deal.II | WSL Ubuntu / Windows Python stack |
| Geometry + meshing | Gmsh (Python API on Windows; CLI also in WSL) | Both |
| Post-processing | PyVista + matplotlib + fluidfoam | Windows venv |

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/check_environment.py` | Full toolchain health check — prints JSON status, exit 0 = ready |
| `scripts/install_solvers.py` | Idempotent install of OpenFOAM/CalculiX/Gmsh (+ optional ElmerFEM) into WSL Ubuntu |

## Usage

```bash
python .github/skills/solver_environment/scripts/check_environment.py
python .github/skills/solver_environment/scripts/install_solvers.py               # install what's missing
python .github/skills/solver_environment/scripts/install_solvers.py --force       # reinstall
python .github/skills/solver_environment/scripts/install_solvers.py --with-elmer  # also build ElmerFEM
```

First run on a new machine: `python first_run_setup.py` at the repo root chains
everything (venv → pip deps → WSL check → this skill's installer → verification →
pytest gate) and writes `setup_report.json`. See `SETUP.md` for the full guide.
The check covers the CHT toolchain too (`chtMultiRegionSimpleFoam`,
`chtMultiRegionFoam`, `splitMeshRegions`, `gmshToFoam`, `foamToVTK`) via the
`openfoam_cht` status key.

## ElmerFEM install (`--with-elmer`)

No Ubuntu 24.04 (noble) apt/PPA package exists yet for ElmerFEM (the CSC PPA only
publishes through jammy/22.04), so `--with-elmer` compiles it from source: a serial,
no-GUI CMake build (`-DWITH_ELMERGUI:BOOL=FALSE -DWITH_MPI:BOOL=FALSE`) cloned to
`/opt/elmerfem` and installed to `/usr/local`. Takes 10-20 minutes; logs land at
`/opt/elmer_configure.log` and `/opt/elmer_build.log` inside WSL. It is opt-in (not
part of the default install) because of that build time — `check_environment.py` treats
it as optional and only prints a note when it's missing, it does not fail the readiness
gate. Re-run `--with-elmer` any time to pick up a newer ElmerFEM `devel` checkout (the
clone is depth-1 and reused if `/opt/elmerfem` already exists — remove that directory
first for a clean re-clone).

## Requirements

- Windows with WSL2 and an Ubuntu distro (`wsl -l -v` must list Ubuntu).
- Python venv with `requirements.txt` installed (`.\setup.ps1` or `first_run_setup.py`).
- No API keys needed — everything runs locally.

## Outputs

`check_environment.py` prints a JSON status block; non-zero exit means something is
missing and `install_solvers.py` should be run. The `elmer` status key is `None` unless
`--with-elmer` has been run — this alone never blocks the "READY" verdict.
