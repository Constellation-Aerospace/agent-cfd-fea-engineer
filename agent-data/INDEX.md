# agent-data Index

Permanent reference assets for the CFD/FEA engineer agent.

| Asset | Purpose | Usage |
| --- | --- | --- |
| `reference_conditions.json` | Representative marine exhaust study envelope: operating ranges, fluid properties, default composition | Loaded by the agent when scoping a new study; cite in reports |
| `validation_references.md` | Literature anchors for validating submerged buoyant jet results | Read when building the validation section of a report |
| `materials_library.json` | Solid + fluid property library (rho, cp, kappa, mu, Pr, emissivity, absorption) for CHT studies | Referenced by component `material` names in assembly manifests; override per-study via `overrides` |

Notes:

- Confidential CAD and project-specific documents must go to `inputs/<project>/`,
  NOT here — this folder is committed to git.
- Add every new asset to this table.
