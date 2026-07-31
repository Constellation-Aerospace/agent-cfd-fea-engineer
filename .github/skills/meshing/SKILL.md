---
name: meshing
description: >
  Mesh generation and mesh independence studies. Generates graded tetrahedral meshes with
  Gmsh (jet-region, near-wall, and free-surface refinement), converts to OpenFOAM polyMesh
  via gmshToFoam, checks quality with checkMesh, and runs a 3-level mesh independence study
  with Grid Convergence Index (GCI) reporting. Use for "generate the mesh", "refine the
  mesh", "mesh independence", "grid convergence", or mesh-quality questions.
when_to_use: "Generating/refining meshes; mesh quality checks; mesh independence / GCI studies."
authority: execute
cost_tier: 2
version: 0.1.0
---

# Meshing & Mesh Independence

Unstructured tet meshes (Gmsh HXT) with refinement zones: jet development region
(D/6), near pipe walls (D/6), free-surface band (D/2.5), plume-rise corridor.
A single `mesh_size_factor` scales the whole distribution — the knob for the mesh
independence study (smaller factor = finer mesh, roughly cells ~ factor^-3).

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/generate_mesh.py` | Mesh one study at a chosen refinement level, report stats |
| `scripts/mesh_independence.py` | 3-level study: mesh -> short solve -> KPI comparison + GCI |

## Usage

```bash
# Single mesh (levels: coarse=1.3, medium=1.0, fine=0.72, or --factor X)
python .github/skills/meshing/scripts/generate_mesh.py --study baseline --level medium

# Mesh independence study (runs three short simulations — takes hours)
python .github/skills/meshing/scripts/mesh_independence.py --study baseline \
    --sim-time 1.0 --np 6
```

## Method

The independence study compares KPIs (inlet back-pressure, axis peak temperature,
thermal decay length) across coarse/medium/fine meshes and computes the Grid
Convergence Index (Roache): observed order p from the three solutions, GCI_fine with
safety factor 1.25. KPI drift < ~3% between medium and fine indicates independence.

## Outputs

- `outputs/<study>/mesh/exhaust.msh` + `.stats.json`
- `outputs/<study>-mesh-<level>/` (independence sub-studies)
- `outputs/<study>/mesh_independence.json` + `mesh_independence.csv`
