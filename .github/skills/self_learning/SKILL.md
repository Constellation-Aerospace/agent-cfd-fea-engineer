---
name: self_learning
description: >
  Data-driven recommender that gets better with every simulation. Every completed
  study (multiphase CFD, conjugate heat transfer, FEA) is automatically harvested —
  its inputs, the solver knobs actually used, and an outcome-quality score — into
  agent-data/learning_history.json. Before setting up a new case, query it for
  solver settings recommended by weighted similarity to past runs of the same
  case type. No separate training step: harvesting a study IS the learning, and
  confidence rises automatically as more studies accumulate.
when_to_use: "Before setup_case.py / setup_cht_case.py / run_pipe_fea.py on a new study, to get data-driven starting settings instead of skill defaults. Harvesting itself is automatic (wired into each run_*.py) — no manual step needed after a run completes."
authority: write
cost_tier: 1
version: 0.1.0
---

# Self-Learning

Quantitative counterpart to `self_annealing`: where annealing captures qualitative
lessons a human/agent must read and integrate, this captures numeric run history and
turns it into recommendations automatically — no judgment call required to benefit
from it.

## How it works

1. **Harvest (automatic).** The moment a study finishes solving, `run_case.py` /
   `run_cht_case.py` / `run_pipe_fea.py` calls `learning_store.harvest(slug)`, which:
   - reads that study's inputs (`params.json` / `assembly/manifest.json` /
     `fea/fea_summary.json`) and flattens them into numeric **features**,
   - pulls out the solver **knobs** actually used (`max_co`, `n_procs`,
     `write_interval_s`, mesh resolution, ...),
   - scores **quality** in [0, 1] from `checkMesh`, convergence/residuals, Courant
     number, and (for CHT) energy-balance closure,
   - upserts the record (keyed by study slug — re-running a study replaces its old
     record) into `agent-data/learning_history.json`.

   Nothing here needs an LLM judgment call, so it runs unconditionally, every time.

2. **Recommend (on demand, before a new case).** Given a case type and a set of
   query features (either pulled from an existing study's own inputs via `--like`,
   or supplied by hand with `--param key=value`), `recommend.py` finds the
   k = 5 most similar past runs — similarity is a normalized-distance weighted by
   each neighbour's quality score — and returns a weighted average of their solver
   knobs plus a confidence score and the nearest examples it drew from:

   ```bash
   python .github/skills/self_learning/scripts/recommend.py \
       --case-type multiphase_cfd --like marine-exhaust-cfd/next-run

   python .github/skills/self_learning/scripts/recommend.py \
       --case-type conjugate_heat_transfer \
       --param n_components=8 --param total_volume_m3=0.0004 --param ambient_T_K=193.15
   ```

   `confidence` is `min(1, n_matches/5) * mean(neighbour quality)` — 0 with no
   history, and it only rises as more relevant, well-converged studies accumulate.
   At `confidence` below ~0.3, treat the recommendation as a hint, not a setting;
   apply engineering judgment and the skill's own documented defaults.

3. **Backfill / re-sync.** `harvest.py --all` sweeps every study currently under
   `outputs/` and (re-)harvests all of them — useful the first time this skill is
   added to a workspace with pre-existing studies, or after manually editing a
   study's artifacts.

## What gets learned, per case type

| Case type | Features (query-time inputs) | Knobs (what's recommended) | Quality signal |
| --- | --- | --- | --- |
| `multiphase_cfd` | flattened `params.json` (U_in, T_exhaust_C, T_water_C, geometry.*, ...) | `max_co`, `n_procs`, `write_interval_s`, `end_time_s` | checkMesh ok, run completed, bounded max Courant |
| `conjugate_heat_transfer` | component/interface/patch counts, total volume, total interface area, radiative-patch count, total incoming heat flux, ambient T/P | `n_procs` | run completed, worst region residual, heat-exchanger energy imbalance % |
| `fea_analysis` | flattened geometry/loads/material from `fea_summary.json` | mesh node/element counts | run completed with parsed results |

Feature keys are stable across studies of the same case type (fixed config schemas
for multiphase/FEA; generic aggregate counts for CHT, which never hardcodes a
component name — assemblies vary study to study).

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/harvest.py --study <slug> [--all]` | Extract + upsert one or every completed study's learning record |
| `scripts/recommend.py --case-type <type> [--like <slug>] [--param k=v ...]` | Weighted-kNN recommendation + confidence + nearest examples |

Core logic lives in `.tmp/scripts/learning_store.py` (feature extraction, quality
scoring, the recommender) so it is unit-testable without WSL or a solver
(`tests/test_learning_store.py`).

## Division of labour with self_annealing and memory

- `self_annealing` — prose lessons a human integrates into a `SKILL.md` or module.
  Use it for *why* something works (a BC gotcha, a modelling trap).
- `self_learning` (this skill) — numeric history a program can already act on.
  Use it for *what setting* worked (mesh density, relaxation-adjacent knobs, ranks).
- `memory/` — session context (what was decided, where a study stands *right now*).

If a lesson could instead be a number harvested automatically from run artifacts,
prefer this skill — it never goes stale and needs no manual integration step.

## Limits

- Recommendations are only as good as the harvested history; a workspace with one
  or two studies will report low confidence by design — that's the signal to fall
  back to skill defaults and engineering judgment, not a bug.
- This is case-based weighted-kNN, not a physics model — it will happily
  extrapolate past bad practice if the harvested history itself contains
  low-quality runs with inflated quality scores. `quality` is heuristic; sanity-check
  a recommendation the way you would sanity-check anything a junior engineer said
  "this is what we did last time" about.
