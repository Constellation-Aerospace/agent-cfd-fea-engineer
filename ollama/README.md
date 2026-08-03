# ollama/ — local-model driver

Runs the agent against a **local Ollama model** instead of Copilot Chat — no API
keys, no cloud. Used to execute the transient-run procedure in
`../OLLAMA_QWEN_TRANSIENT_RUNBOOK.md` on a machine with no VS Code agent runtime.

| File | Purpose |
| --- | --- |
| `Modelfile.cfd` | Builds the `cfd-qwen` model — `qwen2.5-coder:7b` at 32 k context, low temperature, with its own tightened `SYSTEM` prompt (one command per turn, never invent numbers, never install anything) |
| `run_agent.ps1` | Interactive driver: seeds the runbook, then loops *model proposes one PowerShell command → you approve → it runs → real stdout/stderr is fed back* |

## Usage

```powershell
ollama create cfd-qwen -f ollama\Modelfile.cfd
.\ollama\run_agent.ps1 -SelfTest    # one round trip: server, model, context budget, command extraction — executes nothing
.\ollama\run_agent.ps1              # interactive: r = run, s = skip, q = quit
```

## Safety model

The model never touches the shell. `run_agent.ps1` executes commands, and only after
you type `r`. On top of that there is a **hard block**: anything matching
`install_solvers | setup.ps1 | first_run_setup | apt install | pip install |
winget install | choco install` is refused and never executed, even with approval — a
7b model reliably proposes an installer the moment it sees something that looks like
evidence the stack is missing (typically the stale `setup_report.json`). Prose in the
system prompt does not prevent this; the regex does. `-SelfTest` includes an
adversarial check that this guard holds.

Context is the other constraint: the runbook alone is a large prompt, solver output is
fed back trimmed to 6 000 chars, and the driver warns past 28 k tokens against the
32 k limit — restart with a state summary rather than pushing through.
