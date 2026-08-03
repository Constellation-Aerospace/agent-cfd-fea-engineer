# agent-data/ — permanent reference data

Curated, non-confidential engineering data the agent reads while scoping and running
studies. Committed to git and versioned deliberately: numbers here end up cited in
reports, so a change is a reviewable event.

**[INDEX.md](INDEX.md) is the authoritative asset table** — every file in this folder
must have a row there describing its purpose and when the agent should read it.

| File | Contents |
| --- | --- |
| `materials_library.json` | Solid + fluid properties (rho, cp, kappa, mu, Pr, emissivity, absorption) keyed by material name; referenced from assembly manifests, per-study `overrides` win |
| `reference_conditions.json` | Representative marine-exhaust study envelope: operating ranges, fluid properties, default composition |
| `validation_references.md` | Literature anchors for validating submerged buoyant jet results |
| `lessons.md` | Self-annealing log — techniques and gotchas captured per project, written by `.github/skills/self_annealing/scripts/anneal.py log` |
| `INDEX.md` | The asset table above, maintained by hand |

## Rules

- **Not for confidential material.** Client CAD, specs, and project documents go to
  `inputs/<project>/`, which is not committed. This folder is public within the repo.
- Add every new asset to `INDEX.md` in the same commit.
- Material properties consumed by a solver run must be traceable: cite the source in
  `validation_references.md` rather than pasting an unattributed number.
