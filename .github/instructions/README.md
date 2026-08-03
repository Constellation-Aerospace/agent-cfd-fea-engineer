# .github/instructions/ — scoped editing rules

Artifact-specific standards the agent applies when it creates or edits a matching
kind of file. Unlike `../copilot-instructions.md` (always loaded), these are read on
demand — use them for rules that only matter while producing one kind of artifact.

| File | Applies to |
| --- | --- |
| `diagram-creation.instructions.md` | draw.io `.drawio`, Mermaid `.mmd`, and inline Mermaid in reports/proposals — format selection (block diagram vs illustration), styling, and layout standards |

## Convention

Name files `<topic>.instructions.md` and open with a blockquote stating exactly when
the rules apply (which file types / which task), so the scope is unambiguous when the
file is loaded on its own.

Related skill: `../skills/diagramming/` (the scripts that emit the files these rules
govern).
