# outputs/ — organised project-wise

One folder per **project** (client engagement / SOW), containing that project's
studies, proposals, diagrams, and delivered documents:

```
outputs/
  <project-slug>/               e.g. marine-exhaust-cfd/
    PROJECT.md                  what this project is, reference number, status
    <study-slug>/               one folder per simulation study
      params.json               (or assembly/manifest.json for CHT studies)
      mesh/  case/  figures/  fea/  report/
    <proposal / SOW / deliverable files>
```

Conventions:

- Pass project-scoped slugs to every pipeline script:
  `--study marine-exhaust-cfd/baseline` (the tools accept nested slugs; the
  WSL-side scratch name is flattened automatically).
- New project → new folder with a short kebab-case slug **without spaces**
  (OpenFOAM rejects spaced paths) + a `PROJECT.md`.
- Confidential inputs (CAD, client specs) go to `inputs/<project>/`, not here —
  this folder is committed to git (heavy solver artifacts are gitignored).

## Projects

| Project | What | Status |
| --- | --- | --- |
| _(none yet)_ | Add a row per project folder | — |
