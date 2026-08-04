---
name: fea_analysis
description: >
  Finite Element Analysis with CalculiX (default) and ElmerFEM as a selectable backend:
  steady coupled thermal-structural analysis of the exhaust pipe wall under exhaust-gas
  / seawater temperature loading. Generates a quadratic tet mesh of the pipe tube with
  Gmsh, writes the solver input deck, solves in WSL, and extracts temperature field,
  thermal stress (von Mises), and displacement. Use for "FEA", "thermal stress",
  "structural analysis", "pipe wall temperature", "CalculiX", "Elmer", "ElmerFEM", or
  strength assessment questions.
when_to_use: "Thermal/structural FEA of the exhaust pipe; stress and deformation assessment."
authority: execute
cost_tier: 2
version: 0.2.0
---

# FEA — Pipe Wall Thermal-Structural (CalculiX default, ElmerFEM selectable)

Steady **coupled temperature-displacement** analysis of the pipe tube (annular cylinder,
C3D10 quadratic tets): inner surface at exhaust temperature, outer surface at seawater
temperature (Dirichlet; film-coefficient BCs are the refinement path once CFD wall heat
transfer coefficients are extracted), one end axially fixed (hull penetration).

Default material: carbon steel (E=200 GPa, nu=0.3, alpha=1.2e-5 1/K, k=45 W/m-K).

## Solver backends

The same Gmsh mesh (tets + tagged physical groups: inner/outer/fixed-end surfaces, pipe
volume) feeds either FEM backend, selected with `--solver`:

| `--solver` | Tool | Deck | Result read from |
| --- | --- | --- | --- |
| `ccx` (default) | CalculiX `ccx` | Abaqus-style `.inp` | `.frd` (parsed directly) |
| `elmer` | ElmerFEM `ElmerSolver` | `.sif` | `.vtu` (nodal `temperature`, `displacement`, `vonmises`) |

Elmer solves the same physics — `HeatSolver` for the temperature field, then
`StressSolve` for linear elasticity, which picks up thermal strain automatically from
the material's `Heat Expansion Coefficient` / `Reference Temperature` (Elmer's standard
thermal-stress coupling). Unlike CalculiX's `.frd`, Elmer's `StressSolver` emits a
`vonmises` nodal field directly — no manual tensor combination needed. Use `elmer` when
you want a second solver for cross-checking a result, or want ElmerFEM's broader
multiphysics solver library for a future extension (contact, shells, modal, etc.)
beyond what this skill's script currently wires up.

Requires ElmerFEM in WSL — see the `solver_environment` skill
(`install_solvers.py --with-elmer`). There is no Ubuntu 24.04 apt/PPA package yet, so
it is compiled from source (serial, no GUI); the script raises a clear error naming
that install command if `ElmerSolver`/`ElmerGrid` aren't found.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/run_pipe_fea.py` | Mesh -> deck (ccx or elmer) -> solve (WSL) -> results extraction |

## Usage

```bash
python .github/skills/fea_analysis/scripts/run_pipe_fea.py --study baseline \
    --t-inner 400 --t-outer 15
# geometry overrides:
python .github/skills/fea_analysis/scripts/run_pipe_fea.py --study baseline \
    --diameter 0.35 --thickness 0.015 --length 1.5 --mesh-size 0.02
# ElmerFEM instead of CalculiX:
python .github/skills/fea_analysis/scripts/run_pipe_fea.py --study baseline --solver elmer
```

## Outputs

`outputs/<study>/fea/`: `fea_summary.json` (solver used, max von Mises stress, max
displacement, temperature range) plus solver-specific files —
CalculiX: `pipe.inp`, `pipe.frd`, `pipe.vtu` (ParaView/PyVista-readable);
ElmerFEM: `pipe.sif`, `pipe_mesh/` (ElmerGrid mesh dir), `pipe_mesh/pipe_t0001.vtu`.

## Gotchas

- The CalculiX path locates node sets (inner/outer/fixed) by geometry (radius, x
  position) after meshing; the Elmer path needs gmsh **physical groups** tagged before
  meshing so `ElmerGrid` can carry boundary IDs into `mesh.boundary`. Both are produced
  by the same `build_tube_mesh()` — if you add new BCs, tag the corresponding surface
  with `gmsh.model.addPhysicalGroup` and add a matching `Boundary Condition` block in
  `write_sif()`, not just a CalculiX node set.
- Elmer's elasticity solve failed to converge with the default iterative solver
  (BiCGStab/ILU1, >500 iterations) on this problem size; `write_sif()` uses a **direct**
  solver (`umfpack`) for `StressSolve` instead, which is robust at this scale (~50k
  nodes) and only marginally slower.
