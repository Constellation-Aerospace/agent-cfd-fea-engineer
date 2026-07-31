---
name: fea_analysis
description: >
  Finite Element Analysis with CalculiX (ccx): steady coupled thermal-structural analysis
  of the exhaust pipe wall under exhaust-gas / seawater temperature loading. Generates a
  quadratic tet mesh of the pipe tube with Gmsh, writes the CalculiX input deck, solves in
  WSL, and extracts temperature field, thermal stress (von Mises), and displacement.
  Use for "FEA", "thermal stress", "structural analysis", "pipe wall temperature",
  "CalculiX", or strength assessment questions.
when_to_use: "Thermal/structural FEA of the exhaust pipe; stress and deformation assessment."
authority: execute
cost_tier: 2
version: 0.1.0
---

# FEA — Pipe Wall Thermal-Structural (CalculiX)

Steady **coupled temperature-displacement** analysis of the pipe tube (annular cylinder,
C3D10 quadratic tets): inner surface at exhaust temperature, outer surface at seawater
temperature (Dirichlet; film-coefficient BCs are the refinement path once CFD wall heat
transfer coefficients are extracted), one end axially fixed (hull penetration).

Default material: carbon steel (E=200 GPa, nu=0.3, alpha=1.2e-5 1/K, k=45 W/m-K).

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/run_pipe_fea.py` | Mesh -> .inp deck -> ccx solve (WSL) -> results extraction + VTU |

## Usage

```bash
python .github/skills/fea_analysis/scripts/run_pipe_fea.py --study baseline \
    --t-inner 400 --t-outer 15
# geometry overrides:
python .github/skills/fea_analysis/scripts/run_pipe_fea.py --study baseline \
    --diameter 0.35 --thickness 0.015 --length 1.5 --mesh-size 0.02
```

## Outputs

`outputs/<study>/fea/`: `pipe.inp`, `pipe.frd`, `pipe.vtu` (ParaView/PyVista-readable),
`fea_summary.json` (max von Mises stress, max displacement, temperature range).
