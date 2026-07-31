# Diagram Creation Standards — CFD/FEA Engineer

> Auto-applied when creating or editing draw.io `.drawio` files, Mermaid `.mmd` files, or
> inline Mermaid in reports/proposals. Adapted from the sales-prospector diagram standard
> (`sales-prospector/.github/instructions/diagram-creation.instructions.md`).

## Format Selection

First split: **block diagram or illustration?**

- **Block diagrams, flowcharts, physics schematics, architecture, Gantt** — draw.io /
  Mermaid per the table below (editable node-and-edge sources).
- **Everything else — illustrations, images, pictorial figures** (hero graphics,
  concept art, stylised renders of hardware, decorative document visuals) —
  **hand-authored inline SVG/CSS**, written directly into the HTML deliverable (or a
  standalone `.svg` next to it). Do NOT force draw.io/Mermaid onto pictorial content;
  their primitives fight free-form artwork. Keep the SVG source readable (grouped,
  commented, palette from the table below) so it stays editable by hand.

| Diagram type | Use | Routing |
|---|---|---|
| Physics schematics (domains, BCs, cross-sections) | XML `.drawio` | Absolute canvas placement + straight leader lines |
| Flowcharts / pipelines / decision gates | Mermaid `.mmd` | Auto-routing + hub diamonds |
| Gantt / programme charts | Mermaid `.mmd` (gantt) | n/a |
| Architecture / swimlanes | XML `.drawio` | Linear top-to-bottom stack |
| Illustrations / images / pictorial figures | Hand-authored inline SVG/CSS | n/a (free-form) |

Save the editable source for EVERY figure that is not solver output:
`.drawio` for canvas diagrams, `.mmd` for Mermaid — in `outputs/<study-or-doc>/diagrams/`
with a `README.md` listing each diagram and its export.

## Edge Rules (NON-NEGOTIABLE for flowcharts/architecture)

- `edgeStyle=orthogonalEdgeStyle;rounded=1;` for ALL flow edges
- Every edge cell MUST contain `<mxGeometry relative="1" as="geometry"/>`
- NEVER add `<Array as="points">` waypoints
- NEVER set `exitX`/`exitY`/`entryX`/`entryY`
- Hub diamond at every split/merge point

**Physics-schematic exception:** leader lines from a label box to the feature it annotates
use straight thin edges (`edgeStyle=none;endArrow=none;`) and MAY anchor with
`exitX/exitY/entryX/entryY` — a leader that wanders ruins a schematic. Everything else
(no waypoints, geometry cell) still applies.

## Layout Guardrails (the anti-overlap rules)

1. **Labels live in boxes, never as floating text.** Every annotation is an `mxCell` with
   a filled (or white) rounded rectangle so its extent is explicit and editable.
2. **Reserve margins.** Boundary-condition callouts go in a dedicated right-hand label
   column outside the drawing; in-domain callouts go only in verified empty regions.
3. **No two label boxes may overlap** and no label box may cross a dimension line —
   check bounding boxes numerically (x, y, w, h) before saving, not by eye.
4. **Dimension lines get their own corridor**: nothing else may be placed within 20 px
   of a dimension line's span.
5. **Rigid grid for flow diagrams**: col x = `col*180 + 40`, row y = `row*120 + 40`,
   nodes 140×60 (rect) / 140×80 (diamond).

## Palette (match the document design system)

| Role | Hex | Usage |
|------|-----|-------|
| Deep marine | `#0f4c68` | Headers, boundary/BC accents, water outlines |
| Thermal | `#b5501f` | Exhaust/heat features, inlet markers |
| Water fill | `#d7e7f0` | Water regions |
| Air fill | `#eef6fb` | Air/atmosphere regions |
| Ink | `#16232d` | Primary text, arrows |
| Muted | `#7b8790` | Leader lines, secondary text, dimensions |
| Panel | `#ffffff` stroke `#b9c3cb` | Label boxes |
| Steel | `#e8edf1` stroke `#4a5a66` | Solid structures (hull, pipe walls) |

## Export

Primary: `python .github/skills/diagramming/scripts/export_drawio.py --input <d.drawio> --output <d.png>`
(draw.io web export API, scale 2; `--format svg` also supported).
Fallbacks: VS Code draw.io extension right-click → Export; draw.io desktop CLI.
Embed the exported PNG in HTML deliverables as a base64 data URI (CSP-safe); ship the
`.drawio` source alongside the deliverable so the client can edit it.

## Pre-Save Checklist

- [ ] Every annotation is a boxed label; zero floating text overlaps (verified numerically)
- [ ] Dimension corridors clear of labels and leaders
- [ ] Flow edges orthogonal rounded, zero waypoints; leaders straight and short
- [ ] Palette matches the table above
- [ ] `.drawio`/`.mmd` source saved next to the export + diagrams `README.md` updated
- [ ] Exported PNG visually inspected at final embed size (and in dark-mode surround)
