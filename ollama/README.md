# ollama/ — local-model driver

Runs the agent against a **local Ollama model** instead of Copilot Chat — no API
keys, no cloud. Used to execute the transient-run procedures in
[runbooks/](runbooks/) on a machine with no VS Code agent runtime.

| File / folder | Purpose |
| --- | --- |
| `Modelfile.cfd` | Builds the `cfd-qwen` model — `qwen2.5-coder:7b` at 32 k context, low temperature, with its own tightened `SYSTEM` prompt (one command per turn, never invent numbers, never install anything) |
| `run_agent.ps1` | Driver: seeds a runbook, then loops *model proposes one PowerShell command → it runs → real stdout/stderr is fed back*. Interactive by default (`r`/`s`/`q` approval); `-AutoApprove` runs it fully unattended |
| [runbooks/](runbooks/) | The runbook documents themselves — one per study, each a complete Part A–E procedure. See [runbooks/README.md](runbooks/README.md) for the index |
| `transcripts/` | `-AutoApprove -TranscriptPath ...` output lands here — full turn-by-turn logs of unattended runs, for after-the-fact review |

## Usage

```powershell
ollama create cfd-qwen -f ollama\Modelfile.cfd

# one round trip: server, model, context budget, command extraction — executes nothing
.\ollama\run_agent.ps1 -SelfTest -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md

# interactive: r = run, s = skip, q = quit
.\ollama\run_agent.ps1 -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md

# unattended: every proposed command executes without a keystroke; transcript logged to file
.\ollama\run_agent.ps1 -AutoApprove -Runbook ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK_0_40KM.md `
  -TranscriptPath ollama\transcripts\my-run.log -MaxTurns 150
```

Omit `-Runbook` to use the default (`ollama\runbooks\OLLAMA_QWEN_TRANSIENT_RUNBOOK.md`).

## Safety model

The model never touches the shell. `run_agent.ps1` executes commands — after your `r`
keystroke in interactive mode, or automatically in `-AutoApprove` mode. Either way there
is a **hard block**: anything matching `install_solvers | setup.ps1 | first_run_setup |
apt install | pip install | winget install | choco install` is refused and never
executed, even with approval — a 7b model reliably proposes an installer the moment it
sees something that looks like evidence the stack is missing (typically the stale
`setup_report.json`). Prose in the system prompt does not prevent this; the regex does.
`-SelfTest` includes an adversarial check that this guard holds.

`-AutoApprove` mode also carries three more automated safeguards, added after real
unattended runs hit each failure mode (full history in `agent-data/lessons.md`,
L012–L016):

- **Known-warning injection** — a driver-level note is appended the instant a
  documented, expected non-fatal warning (currently: the `checkMesh` warning common to
  this project's CAD family) appears in a command's output, before the model has a
  chance to misread it as something to fix.
- **Code-fence sanitising** — the model sometimes echoes the bare step id or a plain-
  English sentence *inside* the fenced command block instead of only in prose outside
  it; leading non-code lines are stripped before execution so PowerShell doesn't try to
  run them as commands.
- **Native-argument quote fix** — Windows PowerShell 5.1 itself strips embedded double
  quotes from single-quoted JSON arguments passed to native executables (a
  `--solver '{"mode":...}'`-style argument silently arrives at `python.exe` corrupted);
  the driver auto-escapes these before execution regardless of how the model formatted
  the JSON.
- **Command-cycle guard** — tracks the last several proposed commands; a repeat gets
  skipped with a corrective nudge instead of re-executed, and the run stops cleanly
  (rather than burning the turn budget) if the same command keeps recurring.

**Not yet automated:** the model can still silently skip a required step (e.g. copying
in a prior study's solved state before a restart) without checking its own stated
verification gate. Review `run_summary.json`/`n_steps` against the runbook's stated gate
before trusting an unattended run's downstream results — see `agent-data/lessons.md`
L015 for the concrete case this happened.

Context is the other constraint: a runbook alone is a large prompt, solver output is
fed back trimmed to 6 000 chars, and the driver warns past 28 k tokens against the
32 k limit — restart with a state summary rather than pushing through.
