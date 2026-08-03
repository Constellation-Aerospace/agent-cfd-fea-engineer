# Setup — agent-cfd-fea-engineer

First-run setup for the CFD/FEA engineering agent. Everything is open-source and runs
locally — **no API keys are required for any solver work**.

## TL;DR (one command)

```powershell
# from this folder, in PowerShell:
.\setup.ps1
```

That runs [first_run_setup.py](first_run_setup.py), which is idempotent (safe to re-run
any time) and chains every stage below, writing `setup_report.json` at the end.
VS Code also triggers it automatically on folder open ("Setup Agent Environment" task).

If WSL Ubuntu is not installed yet, the script stops and tells you to run (admin
PowerShell, reboot afterwards):

```powershell
wsl --install -d Ubuntu
```

…then re-run `.\setup.ps1`.

If Ubuntu is installed but has never been opened, launch it once from the Start menu
and complete the first-run Linux user creation. Until that finishes, WSL can still
prompt with `Create a default Unix user account`, which blocks the solver bridge.

## What gets installed, and where

| Stage | What | Where | Size / time |
| --- | --- | --- | --- |
| host | Python ≥ 3.10 check | Windows | — |
| venv | `.venv` + [requirements.txt](requirements.txt) (gmsh, pyvista, meshio, fluidfoam, numpy, scipy, matplotlib, …) | Windows | ~1 min |
| workspace | `.tmp/`, `memory/`, `outputs/`, optional `.env` | Windows | instant |
| wsl | WSL2 + Ubuntu presence check (never auto-installed — needs admin + reboot) | — | — |
| solvers | OpenFOAM v2412 (`openfoam2412-default` from dl.openfoam.com), CalculiX `ccx`, gmsh | WSL Ubuntu, via apt | ~2 GB, several min first run |
| verify | Full toolchain check incl. CHT tools (`chtMultiRegionSimpleFoam`, `chtMultiRegionFoam`, `splitMeshRegions`, `gmshToFoam`, `foamToVTK`) | both | ~30 s |
| tests | `pytest tests/ -q` CI gate | Windows venv | ~30 s |

Flags: `.\setup.ps1 -CheckOnly` (report only), `-SkipSolvers`, `-SkipTests`
(same flags on `first_run_setup.py` / `setup.sh` as `--check-only` etc.).

## Requirements

- Windows 10/11 with WSL2 support and ~4 GB free disk (solvers + meshes).
- Python 3.10+ on PATH.
- 16 GB RAM recommended for production meshes; parallel runs use up to
  `n_procs` WSL cores (`mpirun --use-hwthread-cpus` is already handled).
- Internet access on first run only (pip + apt downloads).

## Verifying / re-verifying later

```powershell
.venv\Scripts\python.exe .github/skills/solver_environment/scripts/check_environment.py
```

Exit 0 with `READY` = full stack available (including the CHT solvers). Any missing
piece prints a one-line remediation (usually
`python .github/skills/solver_environment/scripts/install_solvers.py`).

## First simulation smoke test (optional but recommended)

Multiphase reference pipeline:

Studies are organised project-wise (`outputs/<project>/<study>` — see
`outputs/README.md`), so pass nested `--study` slugs:

```powershell
.venv\Scripts\python.exe .github/skills/multiphase_cfd/scripts/setup_case.py --study marine-exhaust-cfd/smoke-test
.venv\Scripts\python.exe .github/skills/multiphase_cfd/scripts/run_case.py --study marine-exhaust-cfd/smoke-test --end-time 0.2
```

Heat-exchanger CHT pipeline (with your own multi-part STEP file):

```powershell
.venv\Scripts\python.exe .github/skills/step_assembly/scripts/inspect_step.py --study <project>/hx-demo --step inputs\<project>\assembly.step
.venv\Scripts\python.exe .github/skills/step_assembly/scripts/assign_materials.py --study <project>/hx-demo --list
# ...assign types/materials/BCs (see .github/skills/step_assembly/SKILL.md), then:
.venv\Scripts\python.exe .github/skills/conjugate_heat_transfer/scripts/setup_cht_case.py --study <project>/hx-demo
.venv\Scripts\python.exe .github/skills/conjugate_heat_transfer/scripts/run_cht_case.py --study <project>/hx-demo --smoke
```

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `wsl` not found or no Ubuntu listed | `wsl --install -d Ubuntu` in admin PowerShell, reboot, re-run setup |
| `Create a default Unix user account` | Ubuntu first-run setup is incomplete; open Ubuntu once, create the Linux user, close it, then re-run setup |
| OpenFOAM commands not found in WSL | `python .github/skills/solver_environment/scripts/install_solvers.py` (add `--force` to reinstall) |
| Solver fails on paths with spaces | Handled automatically — `wsl_bridge` reroutes through an NTFS junction; don't move the repo mid-run |
| `$VAR` mangled when running WSL commands by hand | PowerShell expands `$` in double quotes — use single quotes or the bash tool; scripts are unaffected |
| mpirun refuses > 4 ranks | WSL exposes 4 physical cores; `--use-hwthread-cpus` (already in the pipelines) allows 8 |
| STEP geometry 1000× too small/large | Imports are auto-normalised to metres (`Geometry.OCCTargetUnit M`); verify component volumes in the inspect output |
| pip SSL/proxy errors | Corporate proxy: set `HTTPS_PROXY` before running setup |
| `setup_report.json` says `"ready": false` | Fix the listed `[!!]` stage and re-run — every stage is idempotent |

## What setup never does

- No API keys, no cloud calls, no telemetry — solvers are fully local.
- Never auto-installs WSL itself (admin + reboot required — you stay in control).
- Never writes outside this folder, WSL apt, and `~/foamruns/` (WSL-side scratch used
  during solver runs for ext4 I/O speed).
