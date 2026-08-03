# .github/ — agent definition and skill library

Everything that tells the LLM *what it is* and *what it can run*. Nothing here is
imported by Python at runtime except the skill scripts, which are invoked as
subprocesses from the repo root with the venv interpreter.

| Path | Contents |
| --- | --- |
| `copilot-instructions.md` | Always-on repo context for Copilot Chat: solver stack, pipeline order, ground rules, self-annealing duty. Short by design — the details live in `AGENTS.md` and the SKILL.md files |
| `agents/` | The `cfd-fea-engineer` chat agent definition (name, description, allowed tools, system prompt) |
| `instructions/` | Path/filetype-scoped rules VS Code auto-applies while editing matching files |
| `prompts/` | Standalone system prompt used when the agent is driven outside VS Code |
| `skills/` | The 12 skills — one folder each, `SKILL.md` + `scripts/` |

## How the agent uses this folder

1. `copilot-instructions.md` loads on every turn.
2. The agent picks a skill and reads `skills/<name>/SKILL.md` **before** running any
   of its scripts (the SKILL.md defines inputs, outputs, and guardrails).
3. It executes `skills/<name>/scripts/*.py` with `.venv\Scripts\python.exe` from the
   repo root, writing to `outputs/<project>/<study>/`.

Adding a solver or capability = adding a `skills/<name>/SKILL.md` + `scripts/`, then
committing. No change to `agents.py` is required — discovery is dynamic.
