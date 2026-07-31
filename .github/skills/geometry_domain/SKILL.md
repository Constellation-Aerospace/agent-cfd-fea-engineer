---
name: geometry_domain
description: >
  Parametric geometry and computational-domain preparation for CFD studies using the Gmsh
  OCC kernel. Builds the submerged marine exhaust discharge domain (pipe bore + wall,
  water column, air layer, free surface) with named boundary patches, and exports STEP for
  records. Use when the user asks to create/modify geometry, change pipe diameter,
  submergence depth, domain size, or prepare the domain for meshing.
when_to_use: "Creating or changing the computational domain; adjusting pipe/domain dimensions; exporting STEP."
authority: write
cost_tier: 1
version: 0.1.0
---

# Geometry & Domain Preparation

Builds the parametric fluid domain for the submerged exhaust discharge problem.
The actual product CAD is confidential (arrives post-NDA); until then the geometry is a
representative parametric model: a horizontal exhaust pipe (bore D, wall thickness t)
penetrating the side of a rectangular sea domain at submergence depth Hs, with an air
layer above the free surface (z = 0, gravity -z).

Boundary patches produced (used by every downstream step — do not rename):
`inlet`, `atmosphere`, `pipeWall`, `seaBoundary`.

## Parameters (all metres, SI)

| Key | Default | Meaning |
| --- | --- | --- |
| `pipe_diameter` | 0.30 | bore D |
| `wall_thickness` | 0.012 | pipe wall |
| `pipe_external_length` | 1.0 | upstream approach outside domain |
| `pipe_penetration` | 0.5 | protrusion into the sea domain |
| `submergence` | 2.0 | pipe axis depth below free surface |
| `domain_length` / `domain_width` | 10.0 / 6.0 | box extents |
| `water_depth` / `air_height` | 5.0 / 1.0 | below / above free surface |

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/build_geometry.py` | Validate parameters, save `params.json`, export STEP |

The geometry core lives in `.tmp/scripts/marine_exhaust_geometry.py` (shared with the
meshing skill). When the confidential CAD arrives, replace `build_model()` there —
keep the same patch names and the whole pipeline continues to work.

## Usage

```bash
python .github/skills/geometry_domain/scripts/build_geometry.py --study my-study \
    --set pipe_diameter=0.35 --set submergence=3.0 --export-step
```

## Outputs

`outputs/<study>/params.json` (geometry block), `outputs/<study>/geometry/domain.step`.
