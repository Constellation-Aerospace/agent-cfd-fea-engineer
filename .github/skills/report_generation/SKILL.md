---
name: report_generation
description: >
  Final technical report generation: collates study configuration, methodology, mesh and
  mesh-independence data, CFD results (figures, KPIs, back-pressure, temperature decay),
  FEA results, parametric comparison, and validation methodology into a Markdown + HTML
  report with embedded figures. Use for "generate the report", "technical report",
  "write up the results", "deliverable".
when_to_use: "After runs complete, to produce the final technical report deliverable."
authority: write
cost_tier: 1
version: 0.1.0
---

# Technical Report Generation

Assembles everything a study produced into `outputs/<study>/report/report.md` (+ `.html`).
Sections are included when their source data exists, so the report grows as the study
progresses:

1. Executive summary & problem statement
2. Methodology — solver, multiphase/turbulence models, fluid properties, boundary conditions
3. Geometry & mesh (+ mesh independence table and GCI when available)
4. Results — flow field figures, volume fraction, temperature decay, back-pressure
5. FEA — pipe wall thermal-structural summary (when available)
6. Parametric comparison (when available)
7. Validation methodology & limitations
8. Conclusions and recommendations

The LLM should review `report.md` after generation and refine the narrative text
(executive summary, conclusions) — the script assembles structure + data, the agent
adds engineering judgment.

## Scripts

| Script | Purpose |
| --- | --- |
| `scripts/build_report.py` | Assemble report.md + report.html from study artifacts |

## Usage

```bash
python .github/skills/report_generation/scripts/build_report.py --study baseline \
    --title "Submerged Marine Exhaust Discharge — CFD Investigation" \
    --author "Constellation Space"
```

## Outputs

`outputs/<study>/report/report.md`, `report.html` (self-contained, figures embedded).
