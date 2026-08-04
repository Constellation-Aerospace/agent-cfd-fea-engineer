# cfd-fea-engineer — Purpose

This agent performs CFD (Computational Fluid Dynamics) and FEA (Finite Element Analysis)
engineering studies end-to-end. Its reference workload is a submerged marine exhaust
discharge investigation: hot multi-component diesel exhaust gas (N2/CO2/H2O/O2, ideal gas)
discharging into seawater, evaluating multiphase gas-liquid interaction (VOF), thermal
mixing and temperature decay, pressure distribution and exhaust back-pressure, flow field
development and turbulence (k-omega SST), and comparative parametric studies.

The pipeline covers: parametric geometry preparation (Gmsh), domain and mesh generation
with mesh independence studies, multiphase CFD simulation (OpenFOAM compressibleInterFoam
running inside WSL Ubuntu), FEA thermal/structural analysis with a default CalculiX ccx
path and other FEM backends when the problem needs them, post-processing (PyVista:
velocity/temperature/pressure contours, volume fraction, streamlines, temperature decay
curves, back-pressure monitoring), parametric sweeps, and a final technical report
(Markdown/HTML with embedded figures).

It also handles conjugate heat transfer on user-supplied CAD: a multi-part STEP assembly
is imported (step_assembly skill), each sub-component is typed fluid/solid and assigned a
material from agent-data/materials_library.json plus boundary conditions (inlets, outlets,
fixed T, heat flux, convection+radiation to ambient), and the coupled
conduction/convection/radiation problem is solved with chtMultiRegionSimpleFoam /
chtMultiRegionFoam (conjugate_heat_transfer skill) — producing heat-exchanger KPIs
(heat duty, effectiveness, LMTD, UA, interface fluxes).

The same CHT toolchain covers space and high-altitude thermal analysis (satellites,
stratospheric balloon payloads): `.tmp/scripts/atmosphere.py` provides the US Standard
Atmosphere 1976 (0–86 km), sky sink temperatures, and solar/albedo/Earth-IR heat loads;
manifest BC types `space_environment` (vacuum — exact equivalent-sink radiation) and
`altitude_environment` (rarefied convection + sky radiation) attach those environments
to any component surface. Satellite assemblies run solid-only (conduction + surface
radiation, per-surface radiator rejection in the KPIs); balloon payloads can also model
the surrounding rarefied air as a fluid region (materials.air_at_altitude) to resolve
natural convection explicitly. The environment.py helper turns altitude/orbit inputs
into ready-to-paste boundary conditions and radiator-area hints.

All solvers are open-source and run locally: OpenFOAM 2412 + Gmsh in WSL, with a default
FEA path through CalculiX and other FEM backends available for the right physics,
Python stack (gmsh, pyvista, meshio, fluidfoam, numpy, scipy, matplotlib) on Windows.
No API keys are required for solving. Skills live in `.github/skills/*/SKILL.md`; the
WSL bridge utility is `.tmp/scripts/wsl_bridge.py`. First-run setup:
`python first_run_setup.py` (see SETUP.md). Outputs are organised project-wise:
`outputs/<project>/<study>` with nested `--study <project>/<study>` slugs.
