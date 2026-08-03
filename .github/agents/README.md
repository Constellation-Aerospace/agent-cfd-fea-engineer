# .github/agents/ — chat agent definitions

VS Code / Copilot Chat custom agent definitions. Each `*.agent.md` file becomes an
entry in the Copilot Chat agent dropdown.

| File | Agent |
| --- | --- |
| `cfd-fea-engineer.agent.md` | The CFD/FEA simulation engineer — multiphase VOF, conjugate heat transfer, space/high-altitude thermal, FEA, meshing, parametric sweeps, reporting |

## File format

YAML frontmatter followed by the agent's system prompt in Markdown:

```markdown
---
description: <shown in the agent picker>
name: <dropdown entry, e.g. cfd-fea-engineer>
tools: ["codebase", "editFiles", "runCommands", ...]   # tools the agent may call
---
# <name>

<system prompt: role, solver backend, skills table, pipeline, ground rules>
```

Keep the prompt body in sync with `../prompts/system.md` (same role, used when the
agent runs outside VS Code) and with the skills table in the repo `README.md`.
