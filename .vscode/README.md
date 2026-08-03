# .vscode/ — workspace configuration

Committed on purpose (there is an explicit `!.vscode/` un-ignore in `.gitignore`) so
that opening `agent-cfd-fea-engineer.code-workspace` gives every user the same
interpreter, tasks, and extensions.

| File | Contents |
| --- | --- |
| `settings.json` | Python interpreter pinned to `.venv\Scripts\python.exe`, Pylance basic type checking, format-on-save + organise-imports, Copilot enabled for markdown/python, `*.agent.md` mapped to Markdown, PowerShell as the default terminal at the workspace root |
| `tasks.json` | Setup Agent Environment · Activate Virtual Environment · Install Requirements · Check Solver Environment · Run Test Suite · validate-dynamic-skills (Windows/Linux/macOS variants) |
| `extensions.json` | Recommended extensions: Copilot + Copilot Chat, Python/Pylance/debugpy, Prettier, YAML, XML (for `.drawio`) |

Run a task with **Ctrl+Shift+P → Tasks: Run Task**. "Check Solver Environment" is the
quickest way to confirm the WSL solver stack is still reachable; "Run Test Suite" is
the same gate CI uses.

Machine-local preferences do not belong here — put them in your user settings, since
edits to these files show up in everyone's diff.
