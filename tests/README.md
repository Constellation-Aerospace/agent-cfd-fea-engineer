# tests/ — CI gate

pytest suite that runs **without WSL, OpenFOAM, gmsh, or CalculiX**. Everything here
tests the deterministic layer — case factories, manifests, property models, script
contracts — so it stays fast and runnable on any machine. Solver-dependent checks are
skipped when the toolchain is absent rather than failing.

| File | Covers |
| --- | --- |
| `test_agents.py` | `agents.py` imports and registers the agent — the gate for the agent being usable at all |
| `test_toolchain.py` | Contract tests: every skill script path exists, shared utilities in `.tmp/scripts/` import, plus solver checks when the toolchain is available |
| `test_cht.py` | Materials library, assembly-manifest validation, multi-region case factory |
| `test_aerothermal.py` | US Standard Atmosphere 1976, radiative environment math, space/altitude environment BCs |
| `test_annealing.py` | Self-annealing loop: lesson capture/apply round trip and session-end exit semantics |

## Running

```powershell
.venv\Scripts\python.exe -m pytest tests -q
```

Or **Tasks: Run Test Suite** in VS Code. `.github/skills/self_annealing/scripts/anneal.py
check --run-tests` runs the same suite as the session-end gate.

## Adding tests

Tests resolve the repo root themselves and put `.tmp/scripts` on `sys.path`:

```python
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / ".tmp" / "scripts"))
```

New skill → add its script paths to the contract list in `test_toolchain.py`. Keep new
tests WSL-free; if a check genuinely needs a solver, guard it with a skip on
availability so the suite still passes on a bare checkout.
