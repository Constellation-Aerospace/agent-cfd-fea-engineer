---
name: self_annealing
description: >
  Continuous self-improvement loop for this agent workspace. As projects accumulate,
  every new technique, fix, gotcha, or validated setting is captured as a lesson the
  moment it is learned, integrated into the harness (SKILL.md files, core modules,
  materials library, docs, tests), and the session is gated on a git commit prompt so
  improvements are never lost. Use during EVERY project session: log lessons as they
  surface; run the annealing check before ending any session that changed the harness.
when_to_use: "Whenever something new is learned mid-project (solver settings that worked, BC gotchas, meshing tricks, workflow fixes); ALWAYS at session end before signing off."
authority: write
cost_tier: 1
version: 0.1.0
---

# Self-Annealing

The harness is a living system: skills encode what the agent knows, and projects keep
teaching things the skills don't know yet. This skill turns that learning into a loop
with a hard gate, so knowledge lands in git instead of evaporating with the session.

## The loop

1. **Capture (during work, zero friction).** The moment something is learned — a
   relaxation factor that stabilised a solver, a BC combination that worked, a CAD
   import trap, a wrong assumption in a SKILL.md — log it:

   ```bash
   python .github/skills/self_annealing/scripts/anneal.py log \
       --title "short name" --lesson "what was learned and why it matters" \
       --target <skill-or-module> --project <project-slug>
   ```

   Log liberally. An un-logged lesson is a repeat mistake scheduled for the next
   project. Lessons live in `agent-data/lessons.md` (tracked in git — the backlog
   itself is part of the harness history).

2. **Integrate (same session when cheap, next annealing pass when not).** Place each
   lesson in its architectural home *before* writing — wrong-layer lessons drift:

   | Lesson kind | Home |
   | --- | --- |
   | Reusable computation, BC type, property model | core module in `.tmp/scripts/` **+ a test** |
   | Process rule, gotcha, validated setting | the target skill's `SKILL.md` |
   | Material / property data | `agent-data/materials_library.json` |
   | Capability description (routing/triggers) | `AGENTS.md`, `agent.md`, `config.json`, `README.md` — all of them |
   | One-off project fact | the project's `PROJECT.md` (NOT the harness) |

   A capability is only integrated when every surface that routes or describes it is
   updated, and behaviour-changing lessons ship with a test — prose-only lessons
   regress silently. Then mark it:

   ```bash
   python .github/skills/self_annealing/scripts/anneal.py apply L007 --note "added to meshing SKILL gotchas"
   ```

3. **Gate (every session end).** Before signing off any session that touched the
   harness or produced lessons:

   ```bash
   python .github/skills/self_annealing/scripts/anneal.py check --run-tests
   ```

   Exit 1 means action is needed: OPEN lessons to integrate (or explicitly defer to
   the user), failing tests, or uncommitted changes. When changes are uncommitted the
   check prints a suggested commit — **present it to the user and ask them to commit
   (or approve committing) before ending the session.** Never leave harness
   improvements sitting untracked; never commit without the user's go-ahead.

## What counts as a lesson

- Solver/numerics settings that fixed divergence or sped up convergence
- BC/material/property combinations validated against data or references
- Meshing strategies (sizing, refinement, quality thresholds) that worked
- CAD/import gotchas, unit traps, naming constraints
- Workflow inefficiencies where the skill's documented path lost to a better one
- Wrong or missing statements found in any SKILL.md
- Per-project physics envelopes worth generalising (new materials, new regimes)

Not lessons: one-off project facts with no reuse value (keep those in the project's
PROJECT.md), and anything already documented (verify before logging).

## Harness disciplines (adopted from vjvarada/coding-agent-setup)

- **Fail-closed on outward actions.** Committing/pushing is outward-facing: the gate
  *suggests* the commit and asks the user — it never auto-commits. Long/destructive
  runs (production solves, installs) likewise get an explicit go-ahead; read-only
  checks flow freely.
- **Compress solver output.** Never paste raw solver logs into the conversation —
  pipelines already return JSON summaries and 30-line log tails; use those. Full
  logs stay on disk (`case/log.<tool>`) and are quoted only as failing tails.
- **Verify before you trust.** A green offline suite is necessary, not sufficient:
  behaviour that only shows up in a live solve (BC combinations, convergence) gets a
  smoke run before being recorded as a validated lesson.

## Division of labour with memory

`memory_bank.py` / `insights.md` hold *session context* (what was decided, where a
study stands). Lessons hold *transferable technique* destined for the harness. If a
memory entry starts sounding like advice for future projects, it is a lesson — log it.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/anneal.py log/list/apply` | Capture, review, and close lessons |
| `scripts/anneal.py check [--run-tests]` | Session-end gate: OPEN lessons + pytest + git status → suggested commit + user prompt |
