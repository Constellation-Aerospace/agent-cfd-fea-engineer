---
name: post_processing
description: >
  CFD/FEA post-processing and visualization with PyVista + matplotlib: velocity contours,
  temperature fields, pressure distribution, volume fraction (gas plume), streamlines,
  temperature decay curves along the jet axis, and exhaust back-pressure history. Use for
  "plot the results", "show contours/streamlines", "temperature decay", "back-pressure",
  "volume fraction", or generating figures for the report.
when_to_use: "After a CFD/FEA run to generate figures, decay curves, and back-pressure metrics."
authority: write
cost_tier: 1
version: 0.1.0
---

# Post-Processing & Visualization

Consumes `outputs/<study>/case/VTK/` (written by run_case.py via foamToVTK) and the
function-object histories in `case/postProcessing/`. All figures land in
`outputs/<study>/figures/` as PNG (headless rendering — no GUI needed).

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/plot_fields.py` | Mid-plane (y=0) contours: U magnitude, T, p, alpha.water + streamlines |
| `scripts/temperature_decay.py` | Jet-axis & plume-rise temperature decay curves over time + decay length |
| `scripts/back_pressure.py` | Inlet back-pressure history, mean value, hydrostatic decomposition |

## Usage

```bash
python .github/skills/post_processing/scripts/plot_fields.py --study baseline
python .github/skills/post_processing/scripts/plot_fields.py --study baseline --time 2.0
python .github/skills/post_processing/scripts/temperature_decay.py --study baseline
python .github/skills/post_processing/scripts/back_pressure.py --study baseline
```

## Outputs

- `figures/slice_<field>_t<time>.png` — contour maps on the vertical mid-plane
- `figures/streamlines_t<time>.png` — jet streamlines colored by temperature
- `figures/temperature_decay.png`, `figures/plume_rise.png` + `decay_metrics.json`
- `figures/back_pressure.png` + back-pressure numbers merged into `kpis.json`
