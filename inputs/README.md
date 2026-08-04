# inputs/ — user-supplied CAD and specifications

Organised project-wise, mirroring `outputs/`. This is where confidential material
enters the workspace: STEP assemblies, client specs, datasheets, requirement
documents.

```
inputs/
  <project-slug>/          same slug as outputs/<project-slug>/
    assembly.step          multi-part STEP for CHT / step_assembly studies
    <specs, datasheets, requirement docs>
```

## Rules

- **Treat as confidential.** Client material is meant to stay local. Note that this
  folder is *not* currently in `.gitignore` and `balloon-ttp/assembly.step` is tracked
  — check `git status` before committing new CAD, or add an ignore rule. Committed
  reference data belongs in `agent-data/`, results and reports in `outputs/`.
- Slugs are kebab-case and **contain no spaces** (OpenFOAM rejects spaced paths), and
  must match the project slug used for `--study <project>/<study>`.
- Inputs are read-only to the pipeline: scripts never write here. Derived geometry,
  meshes, and manifests land in `outputs/<project>/<study>/`.

## Typical use

```powershell
.venv\Scripts\python.exe .github/skills/step_assembly/scripts/inspect_step.py `
    --study <project>/<study> --step inputs\<project>\assembly.step
```

## Current projects

| Project | Contents |
| --- | --- |
| `balloon-ttp/` | `assembly.step` (original geometry) plus `spaced out rad+box.step` / `Spaced out radiators.step` (radiator-spacing revision) — stratospheric balloon payload assembly (see `outputs/balloon-ttp/PROJECT.md`) |
