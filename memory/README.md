# memory/ — persistent agent memory

State that survives between sessions. Two tiers, both implemented in
`.tmp/scripts/`:

- **Tier 1 — working memory** (`memory_bank.py`): the JSON/Markdown files below.
  Small, human-readable, committed.
- **Tier 2 — long-term memory** (`memory_db.py`): `agent_memory.db`, SQLite + FTS5
  full-text search. Regenerable local state — gitignored (`memory/*.db*`) and
  currently written to `.tmp/memory/`.

| File | Contents |
| --- | --- |
| `context.json` | Current state: active projects, goals, open challenges |
| `interaction_log.json` | Past conversation summaries — topics, advice given, follow-ups |
| `decision_journal.json` | Decisions with reasoning, expected outcome, and outcome tracking |
| `insights.md` | Accumulated wisdom and lessons learned (append-only) |

Read and written through `memory_bank.py` rather than by hand — it stamps
`_last_updated` and maintains the counters. Custom memory files can be registered
with `--register <name> <filename>`.

## Not to be confused with

- `agent-data/lessons.md` — the **self-annealing** log: reusable techniques and
  gotchas that get folded back into SKILL.md files. Engineering knowledge.
- This folder — conversational and project state. Session continuity.
