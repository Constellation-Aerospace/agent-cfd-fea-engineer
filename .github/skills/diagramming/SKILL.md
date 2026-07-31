# Skill: diagramming

Create editable, standards-compliant engineering diagrams (domain schematics, BC maps,
workflows, programme charts) as draw.io `.drawio` / Mermaid `.mmd` sources, and export
them for embedding in reports and proposals.

## Goal

Every non-solver figure in a deliverable has an editable source file the client (or a
future session) can open in draw.io / any Mermaid editor — no dead-end inline graphics.

## Inputs

- The figure's content (physics, flow, schedule) from the study or document at hand
- `.github/instructions/diagram-creation.instructions.md` — format selection, palette,
  layout guardrails, pre-save checklist (READ FIRST, follow exactly)

## Scripts

| Script | Purpose |
|---|---|
| `scripts/export_drawio.py` | Export `.drawio` → PNG/SVG via draw.io web API (no local install) |

## Process

1. Pick format per the instructions table (schematic → `.drawio`; flowchart/gantt → `.mmd`).
2. Author the source in `outputs/<study-or-doc>/diagrams/`.
3. For `.drawio`: lay out label boxes with explicit x/y/w/h and verify no overlaps
   numerically (the layout guardrails). For `.mmd`: hub diamonds at splits/merges.
4. Export: `python .github/skills/diagramming/scripts/export_drawio.py --input <f>.drawio --output <f>.png`
5. Visually inspect the export at final embed size (light and dark surround).
6. Embed (data URI in HTML deliverables) and update `diagrams/README.md`.
7. Run the pre-save checklist from the instructions file before calling the figure done.

## Outputs

- `outputs/<study-or-doc>/diagrams/*.drawio|*.mmd` (editable sources)
- `outputs/<study-or-doc>/diagrams/*.png|*.svg` (exports)
- `outputs/<study-or-doc>/diagrams/README.md` (index: diagram → source → export → used in)

## Learnings

- 2026-07-30: Inline hand-authored SVG schematics with floating `<text>` labels caused
  label/dimension collisions in the marine-exhaust SOW (Figure 1). Root cause: no
  bounding-box discipline. Fix: boxed labels + reserved margins + numeric overlap check —
  now codified in the layout guardrails. Physics schematics keep straight anchored
  leaders as a documented exception to the no-anchor flowchart rule.
