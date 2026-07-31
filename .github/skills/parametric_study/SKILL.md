---
name: parametric_study
description: >
  Comparative CFD assessment under varying operating parameters: sweeps over exhaust
  temperature (300-550 C), inlet velocity (10-25 m/s), submergence depth, or any solver
  config key. Each sweep point runs the full pipeline (geometry, mesh, case, solve, KPIs)
  and results are collated into a comparison table and trend plots. Use for "parametric
  study", "sweep", "compare operating conditions", "sensitivity", "what if temperature is X".
when_to_use: "Running/comparing multiple operating points; sensitivity and trend analysis."
authority: execute
cost_tier: 3
version: 0.1.0
---

# Parametric Study

Runs N operating points as sibling studies `<base>-p01`, `<base>-p02`, ... and collates
KPIs (back-pressure, peak axis temperature, thermal decay length) into
`outputs/<base>/parametric_results.csv` plus trend plots.

## Sweep definition

JSON list of config overrides (any `params.json` keys — solver or geometry):

```json
[
  {"label": "cold-slow",  "U_in": 10, "T_exhaust_C": 300},
  {"label": "base",       "U_in": 15, "T_exhaust_C": 400},
  {"label": "hot-fast",   "U_in": 25, "T_exhaust_C": 550},
  {"label": "deep", "geometry": {"submergence": 3.5}}
]
```

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/run_sweep.py` | Execute the sweep matrix and collate comparison outputs |

## Usage

```bash
python .github/skills/parametric_study/scripts/run_sweep.py --study baseline \
    --matrix sweep.json --sim-time 2.0 --np 6
# or inline:
python .github/skills/parametric_study/scripts/run_sweep.py --study baseline \
    --matrix '[{"label":"a","U_in":10},{"label":"b","U_in":25}]' --sim-time 1.0
```

Each point is a full transient run — schedule realistic wall-clock time (hours per point)
and prefer `--sim-time` short enough for the comparison purpose.

## Outputs

`outputs/<base>/parametric_results.csv|json`, `figures/parametric_trends.png`,
individual studies under `outputs/<base>-pNN/`.
