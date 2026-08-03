# .github/prompts/ — standalone system prompt

The agent's system prompt in a host-independent form, for driving it outside VS Code
Copilot Chat (local Ollama runs, API harnesses, evaluation scripts).

| File | Purpose |
| --- | --- |
| `system.md` | Full system prompt: role and reference workload, solver backend, available tools, skills, pipeline order, engineering ground rules |

Consumers: any harness that needs the agent's behaviour without the VS Code agent
runtime. Note that `../../ollama/Modelfile.cfd` does **not** load this file — it
carries its own much tighter `SYSTEM` prompt suited to a 7b model on a 32 k context.

Inside VS Code the equivalent is `../agents/cfd-fea-engineer.agent.md` (same role,
plus the `tools:` allow-list). Edit both together — a drift between them means the
agent behaves differently depending on how it was launched.
