# CLAUDE.md

Entry point for Claude Code / Claude Agent SDK in this workspace.

## Read this first

**[AGENTS.md](AGENTS.md) is the single source of truth** for how this agent operates —
architecture, skill catalogue, solver backend, file organisation, standard study
pipeline, and operating principles. Read it at the start of every session; everything
below is Claude-specific plumbing on top of it, not a replacement.

The same harness is shared by every tool that works on this repo:

| Tool | Entry point | Skills it sees |
| --- | --- | --- |
| Claude Code / Agent SDK | `CLAUDE.md` → `AGENTS.md` | `.claude/skills/*/SKILL.md` (proxies) → `.github/skills/` |
| GitHub Copilot / Copilot Chat | `.github/copilot-instructions.md` | `.github/skills/*/SKILL.md` |
| Copilot custom agent | `.github/agents/cfd-fea-engineer.agent.md` | `.github/skills/*/SKILL.md` |
| Other AGENTS.md-aware agents | `AGENTS.md` | `.github/skills/*/SKILL.md` |
| Hosted / API runs | `.github/prompts/system.md` + `instructions.md` | `.github/skills/*/SKILL.md` |

Keep it that way: **skill content and workspace rules are authored once, under
`.github/`.** Never fork instructions into a Claude-only copy — fix the canonical file
and let every tool pick up the change.

## Skills

The twelve skills live in `.github/skills/<name>/SKILL.md` (goals, inputs, scripts,
outputs, gotchas). `.claude/skills/<name>/SKILL.md` holds **generated proxies** so
Claude Code's skill discovery and `/<skill-name>` invocation work — each proxy carries
the canonical name/description and tells you to read the real SKILL.md.

- Proxies are generated — do not hand-edit them, and do not add Claude-only skills there.
- After adding, renaming, or re-describing a skill under `.github/skills/`, run:

  ```bash
  python .tmp/scripts/sync_agent_docs.py          # regenerate proxies
  python .tmp/scripts/sync_agent_docs.py --check  # CI gate: fails when stale
  ```

  `tests/test_agent_docs.py` enforces this, so a drifted proxy fails the pytest gate.
- A new skill needs YAML front-matter (`name`, `description`, optional `when_to_use`) in
  its `.github/skills/<name>/SKILL.md`; that is what every tool matches on.

Always read the canonical `SKILL.md` before running any of its scripts — the proxy is a
pointer, not the instructions.

## Working in this repo (Claude-specific)

- **Shell:** the primary working shell is PowerShell on Windows 11; a Bash (Git Bash)
  tool is also available. Solvers do **not** run on Windows — OpenFOAM and CalculiX live
  in WSL Ubuntu and are driven through `.tmp/scripts/wsl_bridge.py`. Do not try to invoke
  `simpleFoam`, `chtMultiRegion*Foam`, or `ccx` directly from the Windows shell.
- **Python:** run every script from the repo root with the venv interpreter
  (`.venv\Scripts\python.exe` / `.venv/bin/python`), so `.tmp/scripts/` stays on
  `PYTHONPATH`. On a new or broken machine run `python first_run_setup.py` (see
  [SETUP.md](SETUP.md)) instead of fixing pieces by hand.
- **Long runs:** production solves take hours. Smoke-run every new configuration first
  (`--end-time 0.2` / `--smoke`), and start production runs as background commands rather
  than blocking the session on them.
- **Output discipline:** solver logs are enormous. Quote JSON summaries and log tails
  only — never paste a full log into the conversation.
- **Outputs are project-wise:** `outputs/<project>/<study-slug>/`; pass nested slugs
  (`--study marine-exhaust-cfd/baseline`). A new project gets a folder and a `PROJECT.md`
  (see `outputs/README.md`).
- **Never fabricate results.** Report only numbers that came out of tool output or
  generated artifacts, and show the log tail when something fails.

## Memory

This workspace has its own cross-session memory, separate from any harness-level memory:

```bash
python .tmp/scripts/memory_bank.py --read all      # session start
python .tmp/scripts/memory_bank.py --log-decision  # after milestones
```

Log mesh choices, model settings, and validated configurations there so the next
session — in any tool — inherits them.

## Self-annealing (session-end gate)

The moment a technique, fix, or gotcha is learned, log it and integrate it into the
skill it belongs to:

```bash
python .github/skills/self_annealing/scripts/anneal.py log
python .github/skills/self_annealing/scripts/anneal.py check --run-tests   # before ending
```

When `check` reports uncommitted harness changes, present the suggested commit and ask
the user before committing. Never end a session with harness improvements untracked, and
never commit without the user's go-ahead.

## Tests

```bash
python -m pytest tests -q
```

`tests/test_toolchain.py` (script contracts), `test_cht.py`, `test_aerothermal.py`,
`test_annealing.py`, `test_agents.py`, and `test_agent_docs.py` (cross-tool entry-point
and skill-proxy integrity).
