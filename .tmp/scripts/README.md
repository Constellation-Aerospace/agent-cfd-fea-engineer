# .tmp/scripts/ — shared utilities

The library layer. Skill scripts in `.github/skills/*/scripts/` are thin CLI wrappers;
the physics, case writers, and infrastructure live here. Tracked in git despite
sitting under `.tmp/` — see the negation in `.gitignore` (`.tmp/*` is ignored,
`.tmp/scripts/**` is not). Everything else under `.tmp/` is machine-local scratch.

Import by putting this folder on `sys.path` (the pattern used throughout the tests):

```python
sys.path.insert(0, str(REPO / ".tmp" / "scripts"))
```

## Solver bridge and case factories

| Module | Role |
| --- | --- |
| `wsl_bridge.py` | Run OpenFOAM / CalculiX / Gmsh commands inside WSL Ubuntu from Windows; path translation and scratch-dir handling |
| `foam_case.py` | `compressibleInterFoam` VOF case factory (transient, compressible, two-phase) |
| `cht_case.py` | Multi-region case factory — `chtMultiRegionSimpleFoam` (steady) / `chtMultiRegionFoam` (transient) |
| `step_assembly.py` | Multi-part STEP ingestion (Gmsh OCC): component discovery, manifest, conformal assembly mesh |
| `marine_exhaust_geometry.py` | Parametric submerged-discharge domain (Gmsh OCC) |

## Physics and properties

| Module | Role |
| --- | --- |
| `materials.py` | Material library accessor + OpenFOAM thermophysical dictionary generation |
| `exhaust_properties.py` | Marine diesel exhaust mixture properties (molar mass, mole-fraction-weighted transport) |
| `atmosphere.py` | US Standard Atmosphere 1976 + radiative environment models for satellite / high-altitude thermal |

## Pipelines

| Module | Role |
| --- | --- |
| `study_pipeline.py` | End-to-end CFD study: geometry → mesh → case → solve → KPIs (shared by `multiphase_cfd`, `meshing`, `parametric_study`) |
| `cht_pipeline.py` | STEP assembly → multi-region mesh → CHT case → solve → heat-exchanger KPIs |
| `task_graph.py` | DAG execution plans with checkpointing and resume |

## Agent infrastructure

| Module | Role |
| --- | --- |
| `memory_bank.py` | Tier 1 working memory — JSON/Markdown files in `memory/` |
| `memory_db.py` | Tier 2 long-term memory — SQLite + FTS5 search |
| `tool_registry.py` / `tool_registry.json` | Formal schemas for every execution script |
| `execution_trace.py` | Structured observability for tool calls |
| `confirm_action.py` | Human-in-the-loop approval gates for irreversible actions |

Changes here are covered by `tests/` — the case factories and pipelines are tested
without WSL, gmsh, or OpenFOAM present, so run `pytest` before committing.
