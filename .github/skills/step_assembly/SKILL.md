---
name: step_assembly
description: >
  Multi-part STEP assembly ingestion for conjugate heat transfer studies. Imports a
  multi-body STEP file with the Gmsh OCC kernel, boolean-fragments the parts so contact
  faces are imprinted and conformal, enumerates every component (name, volume, bounding
  box) and every part-to-part contact interface, and writes an assignment manifest.
  Materials and boundary conditions are then assigned per component, and a single
  conformal mesh is generated with one cellZone per component — ready for
  splitMeshRegions and chtMultiRegionFoam. Use when the user provides a CAD assembly
  (heat exchanger, cold plate, enclosure) and wants per-part thermal simulation.
when_to_use: "Importing a multi-part STEP file; assigning materials/BCs to sub-components; meshing an assembly for multi-region (CHT) simulation."
authority: write
cost_tier: 1
version: 0.1.0
---

# STEP Assembly Ingestion & Per-Component Assignment

Turns a multi-part STEP file into a validated, meshable multi-region model. The
central artifact is the **assembly manifest** (`outputs/<study>/assembly/manifest.json`)
— the single source of truth for component types, materials, boundary conditions,
radiation settings, and solver options. Everything downstream (meshing, case
generation, KPIs) reads it.

## Workflow

1. **Inspect** — `scripts/inspect_step.py --study <slug> --step <file.step>`
   - Units are auto-normalised to metres (`Geometry.OCCTargetUnit M`), so mm CAD is fine.
   - Component names come from STEP part labels (sanitised to OpenFOAM-safe names).
   - Contact interfaces are detected geometrically (fragment → faces shared by two solids).
   - Writes `manifest.json` (assignments preserved across re-inspection) and
     `surfaces.json` (per-surface centroid/area/bbox, to help write patch selectors).
2. **Assign** — `scripts/assign_materials.py` (or edit the manifest directly)
   - Every component needs `type` (`fluid`/`solid`) and a `material` from
     `agent-data/materials_library.json` (override any property via `overrides`).
   - Fluid passages in a heat exchanger are usually separate solids in good CAD. If the
     CAD has no fluid solids, ask for the CAD to be re-exported with flow volumes, or
     model the wetted region separately — this skill does not create fluid volumes.
   - Boundary patches: named selectors on a component's *external* surfaces
     (`xmin|xmax|ymin|ymax|zmin|zmax`, a `{"box": ...}`/`{"plane": ...}` selector, or
     `remaining` to rename the leftovers). Unselected external surfaces become
     `<component>_wall` (adiabatic no-slip by default).
   - BC types: `velocity_inlet` (U_m_s or m_dot_kg_s + T_C), `pressure_outlet` (p_Pa),
     `fixed_temperature` (T_C), `heat_flux` (q_W_m2), `convection` (h_W_m2K + T_amb_C,
     optional emissivity → adds grey radiation to ambient), `adiabatic`, `symmetry`.
   - `--validate` reports everything that blocks meshing/case setup.
3. **Mesh** — `scripts/mesh_assembly.py --study <slug> --level medium`
   - One physical volume per component → gmshToFoam turns them into cellZones →
     `splitMeshRegions -cellZones` builds regions and `<A>_to_<B>` coupled interfaces.
   - Sizing: global max/min from assembly diagonal (override via manifest
     `solver.mesh.size_max_m` / `size_min_m`), curvature-adaptive for tube bundles.
   - Mesh independence: rerun with `--factor` and compare KPIs (see `meshing` skill GCI).

## Outputs

`outputs/<study>/assembly/manifest.json`, `assembly/surfaces.json`,
`outputs/<study>/mesh/assembly.msh` (+ `.stats.json` with per-patch areas used for
inlet turbulence estimates downstream).

## Gotchas

- Interfaces require actual geometric contact in CAD (coincident faces). Gaps —
  even 0.1 mm — mean no thermal coupling; inspect the reported interface list and
  areas, and treat a missing expected interface as a CAD problem to raise.
- If the STEP file changes, re-run inspection: component matching is by
  centroid+volume and refuses to proceed on >2 % volume mismatch.
- CAD without part labels yields auto-names like `open_cascade_step_translator_7_8_1_1`.
  Renaming the component keys in the manifest is safe (matching is geometric, not
  by name) — do it before assigning patches, and keep names OpenFOAM-safe.
- Do not put `_to_` in component names — it is reserved for interface patch names.
