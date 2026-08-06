# Runbook — Local Ollama (`qwen2.5-coder`) driving the 0→20 km Transient Thermal Simulation

**Audience:** an operator setting up a fully local LLM agent, and the `qwen2.5-coder`
model itself. Everything below is executable — no step requires a cloud API key.

## How to use this file with Ollama

Use this document as the complete instruction bundle for an Ollama session. The model
should read it, follow the operating contract in Part A, and execute Part C end to end
in order. For a hand-driven session, paste the full runbook first, then paste the
prompt in Part E. The agent must:

1. Work only from the repository in `D:\Github\agent-cfd-fea-engineer`.
2. Execute exactly one PowerShell command per turn and wait for the real output.
3. Stop on any verification gate failure instead of guessing.
4. Never install the solver stack; C0 is a read-only environment check and must report
   `READY: full CFD/FEA toolchain available.`

**Target study:** stratospheric balloon payload (60 W Jetson + copper straps + twin
radiators inside an EPS foam box), transient conduction/radiation from ground to
20 km over 1200 s.

**Two things are being set up, and they are independent:**

| Layer | What it is | Status | Needs the LLM? |
| --- | --- | --- | --- |
| Solver stack | OpenFOAM v2412 `chtMultiRegionFoam` + CalculiX 2.21 + Gmsh in WSL Ubuntu, Python on Windows | **Installed and verified — nothing to set up** | No |
| Orchestration | `qwen2.5-coder` served by Ollama, reading this runbook and issuing the commands | Part A below | Yes |

> Only Ollama needs installing. The simulation toolchain is already in place; C0 just
> confirms it. See [C0](#c0--environment-gate-already-satisfied--do-not-install-anything).

If Ollama ever misbehaves, **Part C alone is a complete manual procedure.** Run the
commands yourself and you get the same simulation.

---

# Part A — Ollama + `qwen2.5-coder`

> ## Readiness: verified 2026-08-02 — Part A is **already done** on this machine
>
> | Check | Measured |
> | --- | --- |
> | Ollama | 0.32.5, serving on `127.0.0.1:11434` |
> | Base model | `qwen2.5-coder:7b` (Q4_K_M, capabilities: completion, **tools**, insert) |
> | Task model | `cfd-qwen` built from [ollama/Modelfile.cfd](ollama/Modelfile.cfd) — `num_ctx 32768`, temp 0.1 |
> | GPU residency | 6.6 GB, **100 % GPU** on an RTX 3060 12 GB (`ollama ps`) |
> | Throughput | ~54–62 tok/s eval |
> | Runbook in context | **15 789 tokens** of 32 768 — ~17 k headroom for the run |
> | Behaviour | Turn 1 → correct C0 command, nothing else. Turn 2 → "C0 is satisfied. Proceed to C1" + the exact C1 block |
> | Install guard | Fed the stale `setup_report.json`, the model replies "that is the stale setup_report.json, ignoring it" and re-issues the read-only check. The driver additionally **refuses to execute** any installer |
> | Driver | [ollama/run_agent.ps1](ollama/run_agent.ps1) `-SelfTest` → **PASS** (both checks) |
>
> Re-verify any time, in one command, executing nothing:
>
> ```powershell
> .\ollama\run_agent.ps1 -SelfTest
> ```
>
> A.1–A.3 below are kept for rebuilding on a fresh machine. If the self-test passes,
> skip straight to [A.4](#a4-two-ways-to-drive-the-simulation).

## A.1 Install Ollama (Windows 11)

Already installed here (0.32.5). On a fresh machine:

```powershell
winget install --id Ollama.Ollama -e
```

Or download the installer from <https://ollama.com/download/windows>.

Verify the server is up (it runs as a background service on `127.0.0.1:11434`):

```powershell
ollama --version
curl.exe http://127.0.0.1:11434/api/tags
```

A JSON body (even `{"models":[]}`) means the daemon is alive. If `curl` refuses the
connection, start it manually in its own terminal with `ollama serve`.

## A.2 Where to pull the model from

Canonical source — the Ollama model library:

* Model page: <https://ollama.com/library/qwen2.5-coder>
* Pull command:

```powershell
ollama pull qwen2.5-coder:7b
```

**Already present on this machine — no download needed.**

Available size tags: `0.5b`, `1.5b`, `3b`, `7b`, `14b`, `32b`. A bare
`qwen2.5-coder` resolves to `7b`. Explicit quantisation tags exist too, e.g.
`qwen2.5-coder:14b-instruct-q4_K_M` or `qwen2.5-coder:32b-instruct-q8_0`.

### Sizing for *this* GPU (RTX 3060, 12 GB — 9.5 GB free, 16 GB system RAM)

The runbook needs a 32 k context, and KV cache at 32 k is what decides the fit, not
the weights alone:

| Tag | Weights (Q4_K_M) | KV @ 32 k ctx | Total | Verdict on this machine |
| --- | --- | --- | --- | --- |
| `qwen2.5-coder:7b` | 4.7 GB | ~1.8 GB | **6.6 GB measured, 100 % GPU** | ✅ **Use this** |
| `qwen2.5-coder:14b` | ~9 GB | ~6 GB | ~15 GB | ❌ Will not fit; spills to CPU and crawls. Viable only at `num_ctx ≤ 8192`, which truncates the runbook |
| `qwen2.5-coder:32b` | ~20 GB | ~6 GB | ~26 GB | ❌ Needs a 24 GB+ card |

7b is the right call here for a second reason: this runbook spells out every command,
so the model is doing transcription and state-tracking, not open-ended reasoning.
Context headroom matters more than parameter count. Measured behaviour confirms it —
see the readiness box above.

> **Do not use `qwen2.5-coder:1.5b-base`,** which is also present on this machine. It
> is a *base* completion model: no chat template, no tool support, no instruction
> following. It will not obey the operating contract. Check with `ollama show <name>` —
> the base model's capabilities list lacks `tools`.

Alternative source (same weights, direct from Hugging Face — useful if you need a
specific quantisation Ollama does not tag):

```powershell
ollama pull hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q4_K_M
```

CPU-only is possible but slow. Confirm what actually loaded:

```powershell
ollama list
ollama show qwen2.5-coder:7b
ollama ps          # shows GPU vs CPU placement once the model is resident
```

## A.3 Build a task-tuned variant (required — the default context is too small)

**Already built on this machine as `cfd-qwen`** from
[ollama/Modelfile.cfd](ollama/Modelfile.cfd). This section documents how, and how to
rebuild it.

Ollama defaults to a 4096-token context. This runbook measures **15 789 tokens** when
loaded — it would be truncated to about a quarter of itself, silently, and the model
would lose the environment guard and the staging table. Raising `num_ctx` is not
optional.

The file is `ollama/Modelfile.cfd`:

```dockerfile
FROM qwen2.5-coder:7b

PARAMETER num_ctx 32768
PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.05
PARAMETER num_predict 2048

SYSTEM """
You are the CFD/FEA execution agent for the repository agent-cfd-fea-engineer.
You run a local open-source solver stack: OpenFOAM 2412 + Gmsh + CalculiX in WSL
Ubuntu, orchestrated by Python scripts on Windows. You have no cloud access.

ENVIRONMENT IS ALREADY BUILT. WSL Ubuntu, OpenFOAM v2412 including the
chtMultiRegion solvers, CalculiX 2.21, Gmsh 4.14.0-git and every required Python
package are installed and verified. You must NEVER run install_solvers.py,
setup.ps1, first_run_setup.py, apt, pip install, or any other installer. If a file
such as setup_report.json claims the solvers are missing, that file is stale --
check_environment.py is the only authority, and it reports READY.

Operating contract:
1. Emit ONE command per turn, in a fenced powershell block, and nothing else.
   Wait for the operator to paste back stdout/stderr before continuing.
2. Never invent numbers. Every temperature, heat flux, residual or runtime you
   report must be quoted from tool output that you have actually seen.
3. If a command fails, do not retry it verbatim. Read the error, state the cause
   in one sentence, then issue a corrected command.
4. Follow OLLAMA_QWEN_TRANSIENT_RUNBOOK.md Part C exactly and in order. Do not
   skip a verification gate; if a gate fails, stop and report.
5. Use SI units internally. Report temperatures in degC and state whether a
   pressure is gauge or absolute.
6. Paths are Windows paths. The Python interpreter is always
   .venv\\Scripts\\python.exe run from D:\\Github\\agent-cfd-fea-engineer.
"""
```

```powershell
ollama create cfd-qwen -f ollama\Modelfile.cfd
ollama show cfd-qwen
```

`ollama show` must report `num_ctx 32768` and a `Capabilities` list containing
`tools`. Verified output on this machine:

```
  Model
    architecture        qwen2      parameters      7.6B
    context length      32768      quantization    Q4_K_M
  Capabilities
    completion   tools   insert
  Parameters
    num_ctx 32768   num_predict 2048   repeat_penalty 1.05
    temperature 0.1   top_p 0.9
```

**Environment variables — none are required.** `num_ctx` is baked into the model by
the Modelfile (confirmed by `ollama ps` reporting `CONTEXT 32768`), and
[run_agent.ps1](ollama/run_agent.ps1) sends `keep_alive: 30m` on every request, so the
model does not unload during a long solver stage. Set these only if you drive the
model by hand with bare `ollama run`:

| Variable | Value | Why |
| --- | --- | --- |
| `OLLAMA_KEEP_ALIVE` | `30m` | Default is 5 min — the model unloads mid-stage and reloads on the next turn |
| `OLLAMA_NUM_PARALLEL` | `1` | Free VRAM for a single long context |
| `OLLAMA_HOST` | `127.0.0.1:11434` | Keep it loopback-only |

Changing these requires restarting the Ollama service to take effect.

## A.4 Two ways to drive the simulation

### Path 1 (recommended) — the driver script

[ollama/run_agent.ps1](ollama/run_agent.ps1) seeds the conversation with this entire
runbook, then loops: the model proposes **one** command → you approve it → the script
runs it → the **real** stdout/stderr goes back as the next message.

```powershell
.\ollama\run_agent.ps1 -SelfTest     # verify readiness, executes nothing
.\ollama\run_agent.ps1               # start the run
```

At each step you get `[r]un / [s]kip / [q]uit`. **Nothing executes without your
explicit `r`.** Choosing `s` lets you send your own message instead — use it to
correct the model or to hand it output you gathered another way.

What the driver handles that a raw chat cannot:

* Loads the runbook from disk, so the model always has the current version.
* Sends `keep_alive: 30m`, so the model stays resident across a 20-minute solver stage
  instead of unloading after the default 5 minutes.
* Truncates any command output over 6000 characters (keeping head and tail) so a
  verbose solver log cannot blow the context window.
* **Refuses to execute installers**, with no approval prompt offered — `install_solvers.py`,
  `setup.ps1`, `first_run_setup.py`, `apt install`, `pip install`, `winget`, `choco`.
  It replies to the model explaining why and lets it continue. This is a hard block,
  not a warning: a 7b model *will* propose an installer if it is shown something that
  looks like evidence the stack is missing, and prose alone does not reliably stop it.
* Warns at 28 k tokens that the context is filling.
* `-SelfTest` does two round trips and asserts (a) the model starts at C0 with the
  read-only environment check, and (b) the install guard holds when the model is fed
  the stale `setup_report.json`. This is the readiness gate for all of Part A.

> **Context budget.** The runbook seeds 15.8 k of the 32.8 k window, leaving ~17 k for
> roughly 25–35 command/output exchanges. Part C has ~25 steps, so a single session
> normally suffices. If the driver warns you are near the limit — most likely partway
> through the six stages of C8 — quit, restart it, and paste a short state summary
> ("stages 1–4 complete, currently at t = 800 s, next is stage 5 at 15000 m, h = 0.775")
> as your first `s` message.

### Path 2 — OpenAI-compatible endpoint

Ollama exposes `http://127.0.0.1:11434/v1` with the OpenAI schema (any string works
as the API key). This repo's `agents.py::_llm_provider()` builds its provider from
`LITELLM_BASE_URL`:

```powershell
$env:LITELLM_BASE_URL = "http://127.0.0.1:11434"
$env:LITELLM_MASTER_KEY = "ollama"
```

That makes the base URL `http://127.0.0.1:11434/v1`. You must **also** change the
hardcoded model name in [agents.py:278](agents.py#L278) from `"tier-balanced"` to
`"cfd-qwen"`. Note that `build_agent()` instantiates `GitHubCopilotAgent` from
`agent_framework_github_copilot`; that runtime is not part of the local solver stack
and is not required to run the simulation. If it is not installed, use Path 1.

Minimal sanity check of the endpoint:

```powershell
curl.exe http://127.0.0.1:11434/v1/chat/completions -H "Content-Type: application/json" -d '{\"model\":\"cfd-qwen\",\"messages\":[{\"role\":\"user\",\"content\":\"say ok\"}]}'
```

---

# Part B — What to pull onto the machine

| Item | Location | Notes |
| --- | --- | --- |
| Repository | `D:\Github\agent-cfd-fea-engineer` | Already present. Fresh clones: see the DOE Framework link at the bottom of [README.md](README.md) |
| CAD assembly | [inputs/balloon-ttp/assembly.step](inputs/balloon-ttp/assembly.step) | 12-body STEP: 2 radiators, 2 copper straps, 4 Al brackets, TTP stack, EPS foam box |
| Reference steady study | [outputs/balloon-ttp/cht-30km/](outputs/balloon-ttp/cht-30km/) | Validated manifest, mesh, converged 30 km solid-only CHT run — **copy its manifest, do not start from scratch** |
| Steady BC spec | [simulation_summary_report.md](simulation_summary_report.md) | Source of materials + contact list |
| Transient BC spec | `Transient_Thermal_Analysis_0_to_20km_final.md` | Source of the flight profile; every number from it is transcribed into Part C below |
| Solvers | **Already installed** in WSL Ubuntu: OpenFOAM v2412 (+ CHT solvers), CalculiX 2.21, Gmsh 4.14.0-git | Nothing to download. C0 only confirms |

Model files live in `%LOCALAPPDATA%\Ollama\models` (or `%OLLAMA_MODELS%`); they are
not part of the repository.

---

# Part C — Conducting the simulation

Run every command from `D:\Github\agent-cfd-fea-engineer`. The interpreter is always
`.venv\Scripts\python.exe`.

Study slug for this work: **`balloon-ttp/transient-0-20km`**
(outputs land in `outputs\balloon-ttp\transient-0-20km\`).

> ## Verified end-to-end 2026-08-03 — C0 → C9 have all been executed
>
> The complete 0→20 km flight was run on this machine following these steps. Results
> to expect, so you can tell a correct run from a broken one:
>
> | Quantity | Result |
> | --- | --- |
> | Flight | 6 stages × 400 steps, t = 0 → 1200 s, every stage `completed: true` |
> | Wall clock | ~17 min total (see the pruning note in C8 — solve time is only ~4 min) |
> | Jetson TTP peak | **40.13 °C at t = 1200 s**, still rising |
> | Copper strap / radiator at t = 1200 s | 37.79 °C / 29.54 °C |
> | Foam box outer | −51.65 °C |
> | Heat input (gate 1) | **60.20 W** vs 60 W target — 0.33 % |
> | Restart continuity (gate 4) | Smooth across every boundary (e.g. 22.4646 °C at t=20 → 22.7424 at t=25) |
> | Crossing point (gate 6) | **Confirmed.** TTP heating rate decelerates to +0.99 K/100 s at t ≈ 700 s, then re-accelerates to +1.39 K/100 s by t = 1200 s as convection collapses |
> | Final balance | in 60.20 W, out 30.39 W, net +29.81 W stored — still warming at burnout |
>
> Remember the contact-resistance caveat from C3: add ~43 K to the Jetson-to-radiator
> ΔT. That puts the die near ~83 °C, which is *not* comfortable against a typical
> 85–100 °C limit. This is the headline engineering finding, and it comes entirely from
> the term the solver does not model.

## C0 — Environment gate (already satisfied — **do not install anything**)

> **The solver stack on this machine is fully installed and verified.**
> Do **not** run `install_solvers.py`. Do **not** run `setup.ps1`. Do **not** install
> WSL, OpenFOAM, CalculiX or Gmsh. Nothing in Part C needs a download.

Verified state (`check_environment.py`, 2026-08-02):

```json
{
  "wsl": true,
  "distro": "Ubuntu",
  "openfoam": "v2412",
  "openfoam_cht": "installed",
  "calculix": "2.21",
  "gmsh_wsl": "4.14.0-git",
  "python_packages": {
    "gmsh": true, "pyvista": true, "meshio": true,
    "numpy": true, "matplotlib": true, "fluidfoam": true
  }
}

READY: full CFD/FEA toolchain available.
```

C0 is therefore a single read-only confirmation. It changes nothing and takes seconds:

```powershell
.venv\Scripts\python.exe .github\skills\solver_environment\scripts\check_environment.py
```

**Gate:** the output ends with `READY: full CFD/FEA toolchain available.` Then go
straight to C1.

> **Ignore `setup_report.json`.** That file is a stale artifact of an earlier
> `setup.ps1 -SkipSolvers` run and still records `openfoam: null`, `calculix: null`,
> `ready: false`. It is contradicted by the live check above. `check_environment.py`
> is the authority; the JSON file is not.

Only if the live check unexpectedly reports a missing component — and only then —
install just that component with
`.venv\Scripts\python.exe .github\skills\solver_environment\scripts\install_solvers.py`
(idempotent, ~2 GB, 10–40 min). Report the failing check output before doing so.

## C1 — Create the study and seed the manifest

Copy the validated 30 km manifest rather than re-inspecting the STEP file — the
component typing, material assignment and patch selectors in it are already correct
and geometry-matched.

```powershell
$new = "outputs\balloon-ttp\transient-0-20km\assembly"
New-Item -ItemType Directory -Force $new | Out-Null
Copy-Item outputs\balloon-ttp\cht-30km\assembly\manifest.json  $new\manifest.json
Copy-Item outputs\balloon-ttp\cht-30km\assembly\surfaces.json  $new\surfaces.json
```

Component → hardware map (memorise this; the CAD names are opaque):

| Component | Hardware | Material |
| --- | --- | --- |
| `radiator_plate`, `radiator_plate_2` | Twin external radiators, white paint | `white_paint_aluminum`, ε override 0.85 |
| `component1` | Jetson thermal transfer plate (TTP) — **heat is injected here** | `aluminum_6061` |
| `jetson_ttp2`, `component18` | TTP stack / mounting block | `aluminum_6061` |
| `part_6`, `part_9` | Al brackets, TTP end of each strap | `aluminum_6061` |
| `part_7`, `part_10` | OFHC copper thermal straps | `copper` |
| `part_8`, `part_11` | Al brackets, radiator end of each strap | `aluminum_6061` |
| `component11` | EPS foam insulation box | `eps_foam` |

Confirm the copy loaded:

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --list
```

## C2 — Transient material properties

Steady-state only needed κ. Transient needs ρ and cₚ as well — they set the thermal
inertia, which is the entire point of this study. Reconcile the library against the
transient spec:

| Material | Spec (ρ, cₚ, κ) | `agent-data/materials_library.json` | Action |
| --- | --- | --- | --- |
| OFHC copper | 8940, 385, 390 | 8960, 385, 401 | Override to spec |
| Aluminium 6061 | 2700, 896, 167 | 2700, 896, 167 | Matches — no action |
| EPS foam | 30, 1300, 0.033 | 25, 1450, 0.033 | Override to spec |
| Jetson / FR4 | 1900, 1200, ~15 | `fr4_pcb` = 1850, 1100, 0.3 | **Not used** — see note |

> **Note on the FR4 row.** The STEP assembly contains no PCB body. Heat enters the
> model as a surface flux on the TTP top face, so the PCB's own thermal mass is not
> represented. That makes the predicted Jetson-side temperature rise slightly *faster*
> than reality (conservative). State this in the report. If a PCB body is added to the
> CAD later, type it `solid`, material `fr4_pcb`, overrides
> `{"rho":1900,"cp":1200,"kappa":15}`.

Note the report's EPS density of 1021 kg/m³ is wrong for expanded polystyrene by a
factor of ~34 and must not be used; 30 kg/m³ is correct.

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --component part_7  --overrides '{"rho":8940,"cp":385,"kappa":390}'
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --component part_10 --overrides '{"rho":8940,"cp":385,"kappa":390}'
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --component component11 --overrides '{"rho":30,"cp":1300,"kappa":0.033}'
```

Then set the launch-pad initial condition — 293.15 K everywhere (the copied manifest
has a mix of 15/20/22/25 °C):

```powershell
.venv\Scripts\python.exe -c "import json,pathlib; p=pathlib.Path('outputs/balloon-ttp/transient-0-20km/assembly/manifest.json'); m=json.loads(p.read_text()); [c.__setitem__('T_init_C',20.0) for c in m['components'].values()]; p.write_text(json.dumps(m,indent=2)); print({k:v['T_init_C'] for k,v in m['components'].items()})"
```

## C3 — Solver block: transient

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --solver '{"mode":"transient","end_time_s":1200,"write_interval_s":20,"max_di":10,"n_procs":4,"p_ref_Pa":101325,"T_init_C":20}'
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --radiation none
```

Why `--radiation none`: every region in this assembly is a solid, and
`cht_case.py` only writes `radiationProperties` for **fluid** regions. The `fvDOM`
setting inherited from the 30 km manifest is therefore inert. Radiation to the sky
*is* modelled — it is folded into the `altitude_environment` film coefficient (see
`atmosphere.combined_film`). Leaving `fvDOM` in the manifest would misdescribe the
model in the report.

What this produces: `chtMultiRegionFoam`, `endTime 1200`, `deltaT 1e-3` start,
`adjustTimeStep yes`, `maxDi 10`, `maxDeltaT 1`, outputs every 20 s
([cht_case.py:152-169](.tmp/scripts/cht_case.py#L152-L169)).

**Known limitation — thermal contact resistance is not implemented.** The manifest
carries a `thermal_contact_resistances` block (PTM7950 die interface 0.2 K/W, indium
foil joints 0.5/0.54 K/W), but no code reads it: interfaces are written as
`compressible::turbulentTemperatureRadCoupledMixed` with perfect contact. The run
will therefore **under-predict the Jetson-to-radiator ΔT**. Options, in order of
preference:

1. Report the result as a lower bound and add the resistance analytically. The path is
   die → TTP (0.2 K/W in series), then two identical strap branches in parallel, each
   (0.5 + 0.54) = 1.04 K/W → 0.52 K/W combined:
   R_total = 0.2 + 0.52 = 0.72 K/W → ΔT_extra = 60 W × 0.72 = **43 K** on top of the
   simulated Jetson-to-radiator ΔT. State it explicitly.
2. Implement it properly by adding `thicknessLayers`/`kappaLayers` entries to the
   interface patches in `0/<region>/T` after C6 (`kappaLayers` = t/R″; R″ = R·A with
   A the interface area from the manifest). This is a code change to
   `cht_case.py::_solid_T_field` if it is to survive a re-`prepare`.

Do not silently ignore this.

## C4 — Heat load: 60 W

The transient spec calls for 60 W (0 W at t=0, 60 W from t=1 s to 1200 s). The 1 s
ramp is negligible against a 1200 s flight and a multi-minute thermal time constant —
apply 60 W from t=0 and record the assumption.

The BC is a *flux*, so the value depends on the actual meshed patch area, **not** the
CAD contact area. Read the real area after meshing:

```powershell
.venv\Scripts\python.exe -c "import json;print(json.load(open('outputs/balloon-ttp/cht-30km/mesh/assembly.stats.json'))['patches']['jetson_heat_source'])"
```

For the current mesh this is `0.003666837` m², so

**q = 60 / 0.003666837 = 16362.88 W/m²**

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --patch jetson_heat_source --component component1 --select ymax --bc '{"type":"heat_flux","q_W_m2":16362.88,"description":"60 W over the meshed TTP top face (0.003666837 m2)"}'
```

> **Carry-over defect worth flagging.** The 30 km study used
> `q = 17943.23 W/m²`, derived from the CAD *interface* area 0.002089925 m². The
> meshed patch is 0.003666837 m², so that run actually injected
> 17943.23 × 0.003666837 = **65.8 W**, not the 37.5 W stated in
> [simulation_summary_report.md](simulation_summary_report.md). Verify the new value
> against the run's own `wallHeatFlux` output in C9 rather than trusting the arithmetic.

If C6 regenerates the mesh with a different cell size, recompute q from the **new**
`outputs/balloon-ttp/transient-0-20km/mesh/assembly.stats.json` and re-issue this
command before running.

## C5 — Environment BCs (initial segment)

Three patches see the atmosphere: `radiator_plate_outer`, `radiator_plate_2_outer`
(ε = 0.85, L_char 0.15 m) and `foam_box_outer` (ε = 0.90, L_char 0.30 m). They are
already present in the copied manifest at `altitude_m: 30000` — retarget them to
ground level, which is where the flight starts:

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --patch radiator_plate_outer   --component radiator_plate   --select remaining --bc '{"type":"altitude_environment","altitude_m":1667,"emissivity":0.85,"absorbed_flux_W_m2":0.0,"L_char_m":0.15,"h_W_m2K":13.0}'
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --patch radiator_plate_2_outer --component radiator_plate_2 --select remaining --bc '{"type":"altitude_environment","altitude_m":1667,"emissivity":0.85,"absorbed_flux_W_m2":0.0,"L_char_m":0.15,"h_W_m2K":13.0}'
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --patch foam_box_outer         --component component11     --select remaining --bc '{"type":"altitude_environment","altitude_m":1667,"emissivity":0.90,"absorbed_flux_W_m2":0.0,"L_char_m":0.30,"h_W_m2K":13.0}'
```

`absorbed_flux_W_m2: 0` = night / no-sun cold case, consistent with the 30 km study.
For a hot case, re-run the whole flight with the solar term:

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\environment.py --altitude 20000 --emissivity 0.85 --alpha-solar 0.2 --L-char 0.15
```

and paste the printed `absorbed_flux_W_m2` into the BCs.

**Validate before meshing:**

```powershell
.venv\Scripts\python.exe .github\skills\step_assembly\scripts\assign_materials.py --study balloon-ttp/transient-0-20km --validate
```

Must print `Manifest is ready for meshing/case setup.`

## C6 — Build the case

> **Prerequisite — two transient-mode fixes to the case factory.** Before this study,
> the repository had only ever run `chtMultiRegionSimpleFoam` (steady). Transient mode
> was generated but had never been executed, and it did not start. Two things the
> steady solver tolerates and `chtMultiRegionFoam` does not:
>
> | Missing | Symptom | Fix |
> | --- | --- | --- |
> | `p` field in every **solid** region | `cannot find file ".../0/<region>/p"`, 0 time steps | [cht_case.py](.tmp/scripts/cht_case.py) `write_regions()` writes a uniform placeholder `p` for solids when `mode != steady` (solid density is constant, so the field is inert) |
> | Top-level `PIMPLE` dict in `system/fvSolution` | `Entry 'PIMPLE' not found in dictionary`, 0 time steps | `write_skeleton()` appends `PIMPLE { nOuterCorrectors 1; }` when `mode != steady` |
> | **Usable time stepping** | Runs, but the step collapses: **8144 steps to reach t = 1.8 µs**. At that rate 1200 s takes ~10⁹ s of wall clock | `_write_controldict()` switches to a **fixed** step (`adjustTimeStep no; deltaT 0.5;`) for solid-only transient cases, and writes `ascii` so C8 can rewrite BCs |
>
> The third one is the subtle one. `adjustTimeStep yes` scales the step from the
> Courant number, but a solid-only assembly has **no fluid regions**, so
> `setMultiRegionDeltaT` has nothing valid to scale against and drives the step to
> zero — `maxDi 10` never becomes the active limit. Solid conduction with Euler
> implicit is unconditionally stable, so a fixed step is both correct and far faster.
>
> All three are applied in this repository. Verify before building — each must print `1`:
>
> ```powershell
> (Select-String -Path .tmp\scripts\cht_case.py -Pattern 'nOuterCorrectors 1').Count
> (Select-String -Path .tmp\scripts\cht_case.py -Pattern 'requires p in every solid').Count
> (Select-String -Path .tmp\scripts\cht_case.py -Pattern 'adjustTimeStep  no').Count
> ```
>
> If any prints `0`, the transient case will build but either die at startup with 0
> steps or never finish.

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\setup_cht_case.py --study balloon-ttp/transient-0-20km
```

After it completes, confirm the transient extras actually landed — **12 and 1**:

```powershell
(Get-ChildItem outputs\balloon-ttp\transient-0-20km\case\0\*\p).Count
(Select-String -Path outputs\balloon-ttp\transient-0-20km\case\system\fvSolution -Pattern 'PIMPLE').Count
```

Expect ~19 300 nodes / ~73 800 cells / 12 solid regions and `fluid_regions: []`.
`checkMesh` on this geometry reports `max_non_ortho ≈ 90`, `max_skewness ≈ 4.0` — the
script will flag it. That is the same mesh the 30 km run converged on, so proceed, but
say so in the report. `nNonOrthogonalCorrectors 1` is already set for solids
([cht_case.py:430](.tmp/scripts/cht_case.py#L430)).

**Confirm the time-stepping and write format.** No hand editing is needed — the
factory emits these for a solid-only transient case. Check them anyway, because
every one of them is load-bearing:

```powershell
Select-String -Path outputs\balloon-ttp\transient-0-20km\case\system\controlDict -Pattern 'application|endTime|deltaT|adjustTimeStep|writeControl|writeInterval|writeFormat' | Select-Object -First 8
```

Expected — and **verified on this machine**:

```
application     chtMultiRegionFoam;
endTime         1200;
deltaT          0.5;
writeControl    adjustable;
writeInterval   20;
adjustTimeStep  no;
writeFormat     ascii;
```

`adjustTimeStep no` is mandatory (see the prerequisite box). `writeFormat ascii` is
what lets the C8 staging script rewrite boundary values in written time directories;
with `binary` the script stops with an explicit error rather than corrupting the case.

Verify the generated BC before spending solver time — open
`outputs\balloon-ttp\transient-0-20km\case\0\radiator_plate\T`. The
`radiator_plate_outer` block must read approximately:

```
    radiator_plate_outer
    {
        type            externalWallHeatFluxTemperature;
        mode            coefficient;
        Ta              uniform 264.36;
        h               uniform 16.29;
        kappaMethod     solidThermo;
        value           uniform 293.15;
    }
```

(`h` = 13.0 convective + ~3.3 linearised radiative; `Ta` = the flux-weighted blend of
277.3 K air and the 213.2 K sky sink. If you see `Ta uniform 213.35 / h uniform 3.044`
you are still on the 30 km BC — C5 did not take.)

## C7 — Smoke run

```powershell
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-20km --smoke
```

With `deltaT 0.5` a `--smoke` run is a single time step — enough to prove the case
starts, which is exactly what killed three earlier attempts. **Gate:**
`"completed": true`.

**Measured runtime on this machine** (RTX 3060 box, 4 processors, 73 800 cells,
12 solid regions), so you do not have to guess:

| Run | Steps | Wall clock |
| --- | --- | --- |
| Stage 1, 0 → 200 s | 400 | **41.7 s** |
| Per time step | — | **0.104 s** |
| Full 1200 s flight, all six stages | 2400 | **~5 min** |

Each `run_cht_case.py` call also pays a fixed overhead — copy the case into WSL-native
storage, `decomposePar` over 12 regions, `reconstructPar`, `foamToVTK`, copy back —
of roughly 20 s. Six stages therefore cost ~2 min of overhead on top of ~4 min of
solving.

> **Accuracy note.** A 0.5 s step gives a solid Diffusion Number of ~2 500 in the
> finest copper cells (their diffusive time scale is ~0.012 s). Euler implicit is
> unconditionally stable so this is not a stability problem, but sub-second transients
> inside the straps are smoothed. The physics of interest here evolves over minutes,
> so this is acceptable. If you need to defend it, re-run stage 1 at
> `"deltaT_s": 0.25` and confirm the region temperatures at t = 200 s agree to better
> than 0.5 K.

Reset the case to a clean t=0 before the real run:

```powershell
Remove-Item -Recurse -Force outputs\balloon-ttp\transient-0-20km\case\0.5 -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force outputs\balloon-ttp\transient-0-20km\case\postProcessing -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force outputs\balloon-ttp\transient-0-20km\case\VTK -ErrorAction SilentlyContinue
```

## C8 — The staged ascent

### Why staging is necessary

The flight profile makes both the ambient temperature **and** the film coefficient
functions of time. In `externalWallHeatFluxTemperature`, `Ta` can be a time function
but `h` is a plain field — there is no way to ramp `h` inside a single run. The
toolchain writes both as constants
([cht_case.py:532-534](.tmp/scripts/cht_case.py#L532-L534)).

So the flight is run as **six 200 s segments**, each restarting from the previous
segment's final state (`controlDict` has `startFrom latestTime`) with the environment
re-evaluated at the segment's mid-altitude. Piecewise-constant over 200 s is a fine
approximation here: the payload's thermal time constant is minutes, and the segment-to-
segment change in the *combined* film is small above 10 km.

### The profile

Ascent rate 20 000 m / 1200 s = **16.667 m/s**. `h_conv` follows the transient spec:
linear 15.0 → 3.0 W/m²K over 0–10 km, then exponential 3.0 → 0.2 W/m²K over 10–20 km.

| Stage | t [s] | Altitude at mid-segment [m] | US76 T_air [K] | p [Pa] | h_conv [W/m²K] |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 0 → 200 | 1 667 | 277.32 | 82 845 | 13.000 |
| 2 | 200 → 400 | 5 000 | 255.68 | 54 048 | 9.000 |
| 3 | 400 → 600 | 8 333 | 234.05 | 33 970 | 5.000 |
| 4 | 600 → 800 | 11 667 | 216.65 | 20 442 | 1.910 |
| 5 | 800 → 1000 | 15 000 | 216.65 | 12 112 | 0.775 |
| 6 | 1000 → 1200 | 18 333 | 216.65 | 7 180 | 0.314 |

Two deliberate deviations from the transient spec, both to be stated in the report:

* **Air temperature** comes from US Standard Atmosphere 1976 (15 °C at sea level), not
  the spec's 20 °C sea-level ramp. Difference is ~5 K in the first two minutes and
  zero above 10 km, where both give 216.65 K. Using US76 keeps the air temperature,
  density and sky sink mutually consistent — the BC derives all three from one
  altitude.
* **h above 10 km**: the spec's exponential decay (0.31 W/m²K at 18 km) is *lower*
  than this repo's own Churchill/rarefied estimate (1.44 W/m²K at 18 km). The spec
  value is used, which is the conservative (hotter) choice. Both numbers are printed
  by the staging script so the delta is auditable.

### The staging tool

Save this as `stage_transient_bcs.py` **in the repository root**. It reuses exactly the
physics the case factory uses (`atmosphere.combined_film`), and it picks the
linearisation reference temperature from the surface temperature the payload actually
reached in the previous segment — so each segment is exact at its own operating point.

```python
#!/usr/bin/env python3
"""Retarget the altitude_environment BCs of a CHT case to a new flight altitude,
in the latest time directory, so chtMultiRegionFoam can be restarted for the next
segment of an ascent profile.

Usage:
    python stage_transient_bcs.py --study balloon-ttp/transient-0-20km \
        --altitude 1667 --h 13.0
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / ".tmp" / "scripts"))

from atmosphere import (atmosphere, sky_sink_temperature,  # noqa: E402
                        equivalent_sink_temperature, natural_convection_h,
                        combined_film)


def latest_time_dir(case: Path) -> Path:
    times = []
    for p in case.iterdir():
        if not p.is_dir():
            continue
        try:
            times.append((float(p.name), p))
        except ValueError:
            continue
    if not times:
        raise SystemExit(f"No time directories in {case}")
    return max(times, key=lambda t: t[0])[1]


def patch_block(text: str, patch: str) -> tuple[int, int] | None:
    """Return (start, end) char offsets of the { ... } body of a patch entry."""
    m = re.search(rf"^\s*{re.escape(patch)}\s*$", text, re.M)
    if not m:
        return None
    open_idx = text.find("{", m.end())
    if open_idx < 0:
        return None
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return open_idx, i
    return None


def surface_T_from_block(body: str) -> float | None:
    """Mean of the patch `value` entry: 'uniform X' or 'nonuniform List<scalar> ...'."""
    m = re.search(r"\bvalue\s+uniform\s+([\d.eE+-]+)\s*;", body)
    if m:
        return float(m.group(1))
    m = re.search(r"\bvalue\s+nonuniform\s+List<scalar>\s*\d*\s*\((.*?)\)\s*;", body, re.S)
    if m:
        vals = [float(v) for v in m.group(1).split()]
        return sum(vals) / len(vals) if vals else None
    return None


def set_entry(body: str, key: str, value: str) -> tuple[str, bool]:
    new, n = re.subn(rf"(\b{key}\s+)[^;]*;", rf"\g<1>{value};", body, count=1)
    return new, bool(n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True, help="Study slug under outputs/")
    ap.add_argument("--altitude", type=float, required=True, help="Segment altitude [m]")
    ap.add_argument("--h", type=float, default=None,
                    help="Convective film coefficient [W/m2K]; default = US76 "
                         "Churchill estimate from the manifest L_char_m")
    ap.add_argument("--t-surface-est-C", type=float, default=None,
                    help="Linearisation reference temperature [C]; default = the "
                         "surface temperature read back from the field file")
    ap.add_argument("--time", default=None, help="Time directory to patch (default: latest)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    study = REPO_ROOT / "outputs" / args.study
    case = study / "case"
    manifest = json.loads((study / "assembly" / "manifest.json").read_text(encoding="utf-8"))
    tdir = case / args.time if args.time else latest_time_dir(case)
    if not tdir.is_dir():
        raise SystemExit(f"Time directory not found: {tdir}")

    air = atmosphere(args.altitude)
    t_sky_base = sky_sink_temperature(args.altitude)
    report = {"study": args.study, "time_dir": tdir.name, "altitude_m": args.altitude,
              "T_air_K": round(air["T_K"], 2), "p_Pa": round(air["p_Pa"], 1),
              "patches": {}}

    targets = [(n, p) for n, p in manifest.get("patches", {}).items()
               if p.get("bc", {}).get("type") == "altitude_environment"]
    if not targets:
        raise SystemExit("No altitude_environment patches in the manifest.")

    for pname, patch in targets:
        region = patch["component"]
        bc = patch["bc"]
        eps = float(bc["emissivity"])
        q_abs = float(bc.get("absorbed_flux_W_m2", 0.0))
        L = float(bc.get("L_char_m", 1.0))
        f = tdir / region / "T"
        if not f.exists():
            raise SystemExit(f"Missing field file: {f}")
        text = f.read_text(encoding="utf-8", errors="replace")
        if "binary" in text[:400]:
            raise SystemExit(
                f"{f} is in binary format — set 'writeFormat ascii;' in "
                f"{case/'system'/'controlDict'} and re-run the previous segment.")
        span = patch_block(text, pname)
        if span is None:
            raise SystemExit(f"Patch '{pname}' not found in {f}")
        a, b = span
        body = text[a:b + 1]

        t_ref = (args.t_surface_est_C + 273.15 if args.t_surface_est_C is not None
                 else surface_T_from_block(body))
        if t_ref is None:
            t_ref = air["T_K"] + 20.0
        h_conv = args.h if args.h is not None else natural_convection_h(
            args.altitude, L, max(abs(t_ref - air["T_K"]), 1.0))
        t_sink = equivalent_sink_temperature(eps, q_abs, t_sky_base)
        film = combined_film(h_conv, air["T_K"], eps, t_sink, t_ref)

        body, ok_ta = set_entry(body, "Ta", f"uniform {film['Ta_K']:.2f}")
        body, ok_h = set_entry(body, "h", f"uniform {film['h_W_m2K']:.4g}")
        if not (ok_ta and ok_h):
            raise SystemExit(f"Patch '{pname}' in {f} has no Ta/h entries — "
                             "is it an externalWallHeatFluxTemperature patch?")
        if not args.dry_run:
            f.write_text(text[:a] + body + text[b + 1:], encoding="utf-8")
        report["patches"][f"{region}/{pname}"] = {
            "T_ref_K": round(t_ref, 2), "h_conv_W_m2K": round(h_conv, 4),
            "h_rad_W_m2K": round(film["h_rad_W_m2K"], 4),
            "h_total_W_m2K": round(film["h_W_m2K"], 4),
            "Ta_K": round(film["Ta_K"], 2), "T_sink_K": round(t_sink, 2),
        }

    print(json.dumps(report, indent=2))
    if args.dry_run:
        print("\n(dry run — no files written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Smoke-test it without writing anything:

```powershell
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-20km --altitude 1667 --h 13.0 --dry-run
```

It should list all three environment patches with `h_total_W_m2K` ≈ 16.2–16.3 and
`Ta_K` ≈ 264.

### The six segments

Stage 1 needs no staging call — C5 already set the ground BCs in `0/`.

```powershell

# stage 1 : 0 -> 200 s   (BCs already at 1667 m from C5)
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-20km --end-time 200

# stage 2 : 200 -> 400 s
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-20km --altitude 5000 --h 9.0
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-20km --end-time 400

# stage 3 : 400 -> 600 s
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-20km --altitude 8333 --h 5.0
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-20km --end-time 600

# stage 4 : 600 -> 800 s   (tropopause; convection starts collapsing)
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-20km --altitude 11667 --h 1.910
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-20km --end-time 800

# stage 5 : 800 -> 1000 s
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-20km --altitude 15000 --h 0.775
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-20km --end-time 1000

# stage 6 : 1000 -> 1200 s  (radiation-dominated)
.venv\Scripts\python.exe stage_transient_bcs.py --study balloon-ttp/transient-0-20km --altitude 18333 --h 0.314
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\run_cht_case.py --study balloon-ttp/transient-0-20km --end-time 1200
```

**Per-stage gate — check all four before starting the next stage:**

1. `run_summary.json` shows `"completed": true` and `final_time` equal to the segment
   end (200, 400, …).
2. The solver log's first `Time =` line for that segment is the previous segment's end
   time, not 0 — that proves the restart picked up state rather than reinitialising:
   `Select-String -Path outputs\balloon-ttp\transient-0-20km\case\log.chtMultiRegionFoam -Pattern "^Time = " | Select-Object -First 3`
3. No `FOAM FATAL` or `bounding` messages in the log.
4. The staging script's printed `T_ref_K` for the radiators is close to the radiators'
   actual temperature. If it drifted more than ~15 K during the segment just run,
   re-run that segment with `--t-surface-est-C <observed °C>`; the film linearisation
   is only exact at `T_ref`.

### Per-stage cost grows — prune between stages

Each `run_cht_case.py` call runs `decomposePar`, `reconstructPar` and `foamToVTK` over
**every stored time directory**, not just the new ones. The function objects write
every 10 steps (every 5 s), so directories accumulate fast — 241 of them by the end of
this flight. Measured cost per stage, each doing an identical 400 steps:

| Stage | 1 | 2 | 3 | 4 | 5 |
| --- | --- | --- | --- | --- | --- |
| Wall clock | 41.7 s | 105.4 s | 162.0 s | 217.8 s | 269.4 s |

Solve time is constant at ~42 s; everything above that is re-processing history. The
full flight took ~17 min instead of the ~5 min the solve time alone implies.

To keep stages flat, delete time directories **older than the latest** before
restarting (the latest is the restart point — never delete it):

```powershell
$case = "outputs\balloon-ttp\transient-0-20km\case"
$keep = (Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' } |
         Sort-Object { [double]$_.Name } | Select-Object -Last 1).Name
Get-ChildItem $case -Directory | Where-Object { $_.Name -match '^[\d.]+$' -and $_.Name -ne $keep -and $_.Name -ne '0' } | Remove-Item -Recurse -Force
"kept: $keep"
```

`postProcessing/` feeds the C9 plots and is untouched by this — you only lose field
snapshots for the pruned times, not the temperature history.

## C9 — Post-processing and verification

Save this as `transient_history.py` in the repository root:

```python
#!/usr/bin/env python3
"""Assemble the transient histories of a staged CHT run into CSV + PNG.

Reads every function-object output written across all restart segments and
de-duplicates overlapping times.

Usage:
    python transient_history.py --study balloon-ttp/transient-0-20km
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent


def read_minmax(case: Path) -> dict[str, dict[float, tuple[float, float]]]:
    """region -> {time: (T_min_K, T_max_K)}"""
    out: dict[str, dict[float, tuple[float, float]]] = {}
    for f in sorted(case.glob("postProcessing/*/minMaxT_*/*/fieldMinMax*.dat")):
        region = f.parents[2].name
        series = out.setdefault(region, {})
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            if len(p) >= 3:
                try:
                    series[float(p[0])] = (float(p[1]), float(p[2]))
                except ValueError:
                    continue
    return out


def read_heatflux(case: Path) -> dict[str, dict[float, float]]:
    """'<region>:<patch>' -> {time: integral_W}"""
    out: dict[str, dict[float, float]] = {}
    for f in sorted(case.glob("postProcessing/*/wallHeatFlux_*/*/wallHeatFlux*.dat")):
        region = f.parents[2].name
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            p = line.split()
            if len(p) >= 5:
                try:
                    out.setdefault(f"{region}:{p[1]}", {})[float(p[0])] = float(p[4])
                except ValueError:
                    continue
    return out


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--study", required=True)
    ap.add_argument("--highlight", default="",
                    help="Comma-separated regions to emphasise in the T plot")
    args = ap.parse_args()

    study = REPO_ROOT / "outputs" / args.study
    case = study / "case"
    figs = study / "figures"

    temps = read_minmax(case)
    fluxes = read_heatflux(case)
    if not temps:
        raise SystemExit(f"No fieldMinMax output under {case/'postProcessing'}")

    times = sorted({t for s in temps.values() for t in s})
    regions = sorted(temps)
    rows = []
    for t in times:
        row: list = [t]
        for r in regions:
            v = temps[r].get(t)
            row += ["" if v is None else round(v[0] - 273.15, 4),
                    "" if v is None else round(v[1] - 273.15, 4)]
        rows.append(row)
    header = ["time_s"] + [f"{r}_{k}_C" for r in regions for k in ("Tmin", "Tmax")]
    write_csv(figs / "transient_T_history.csv", header, rows)

    if fluxes:
        ftimes = sorted({t for s in fluxes.values() for t in s})
        patches = sorted(fluxes)
        frows = [[t] + [fluxes[p].get(t, "") for p in patches] for t in ftimes]
        write_csv(figs / "transient_Q_history.csv", ["time_s"] + patches, frows)

    hi = {s.strip() for s in args.highlight.split(",") if s.strip()}
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for r in regions:
        ts = sorted(temps[r])
        ys = [temps[r][t][1] - 273.15 for t in ts]
        ax.plot(ts, ys, lw=2.2 if r in hi else 1.0,
                alpha=1.0 if (r in hi or not hi) else 0.45, label=r)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("region maximum temperature [degC]")
    ax.set_title(f"Transient region temperatures — {args.study}")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(figs / "transient_temperatures.png", dpi=150)

    ext = {p: s for p, s in fluxes.items() if "_to_" not in p.split(":", 1)[1]}
    if ext:
        fig2, ax2 = plt.subplots(figsize=(9, 5))
        for p, s in sorted(ext.items()):
            ts = sorted(s)
            ax2.plot(ts, [s[t] for t in ts], lw=1.4, label=p)
        ax2.set_xlabel("time [s]")
        ax2.set_ylabel("integrated wall heat flux [W]")
        ax2.set_title(f"External heat exchange — {args.study}")
        ax2.grid(alpha=0.3)
        ax2.legend(fontsize=7)
        fig2.tight_layout()
        fig2.savefig(figs / "transient_heat_balance.png", dpi=150)

    print(f"regions: {len(regions)}   time samples: {len(times)}   "
          f"t_end: {times[-1] if times else 0}")
    print(f"wrote {figs/'transient_T_history.csv'}")
    if fluxes:
        print(f"wrote {figs/'transient_Q_history.csv'}")
    print(f"wrote {figs/'transient_temperatures.png'}")
    if ext:
        print(f"wrote {figs/'transient_heat_balance.png'}")
    for r in regions:
        last = max(temps[r])
        print(f"  {r:<20} T_max({last:g}s) = {temps[r][last][1]-273.15:8.3f} C")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```powershell
.venv\Scripts\python.exe transient_history.py --study balloon-ttp/transient-0-20km --highlight component1,part_7,radiator_plate
.venv\Scripts\python.exe .github\skills\conjugate_heat_transfer\scripts\cht_kpis.py --study balloon-ttp/transient-0-20km
```

`cht_kpis.py` reports the *final-time* state only; the `streams`/`effectiveness`/`LMTD`
block will be empty because there are no fluid regions. That is expected — the
meaningful outputs here are `regions` (T extremes), `external_W` (radiator rejection)
and `interfaces_W` (strap conduction).

### Verification gates (do not report results until all pass)

| # | Check | Pass criterion |
| --- | --- | --- |
| 1 | Heat actually injected | `transient_Q_history.csv`, `component1:jetson_heat_source` ≈ ±60 W (sign convention: check it, do not assume). More than a few percent off means the flux/area calculation in C4 is wrong |
| 2 | Temperatures bounded | Every region between the sky sink (≈ −60 °C) and the Jetson max. No region below −70 °C, none above 150 °C |
| 3 | Energy closure | At each output time, `Q_in − Σ external_W` should equal the rate of stored energy `Σ(ρ·V·cₚ·dT/dt)` (volumes are in `assembly/manifest.json`). Agreement within ~10 % during the ramp is acceptable; a persistent offset means the flux BC or a material property is wrong |
| 4 | Restart continuity | No temperature discontinuity across a segment boundary in `transient_T_history.csv` (t = 200, 400, 600, 800, 1000). A jump > 1 K means a stage restarted from the wrong time |
| 5 | Thermal lag present | The TTP (`component1`) rises smoothly over the first ~300 s rather than jumping — confirms ρ and cₚ took effect. A step change means the transient properties are missing |
| 6 | Crossing point visible | An upward inflection in `component1` T_max around t ≈ 600–800 s as convection collapses. This is the headline result the transient spec asks for |
| 7 | Interface balance | For each interface, the two sides in `interfaces_W` agree within a few percent |

## C10 — Report

```powershell
.venv\Scripts\python.exe .github\skills\report_generation\scripts\build_report.py --study balloon-ttp/transient-0-20km --title "Stratospheric Payload Transient Thermal Analysis: 0-20 km"
```

Then edit the executive summary and conclusions by hand. The report **must** state:

* Peak Jetson TTP temperature, the time it occurs, and the margin to the Jetson limit.
* Radiator temperature at t = 1200 s and total radiative rejection there.
* Thermal contact resistance is **not** in the model; quote the analytic ΔT adder from
  C3 and present the CFD result as a lower bound.
* Material and BC deviations from the two spec documents (C2 and C8 lists).
* `checkMesh` quality: max non-orthogonality ≈ 90°, max skewness ≈ 4.0.
* Mesh independence was **not** performed. To do it: re-run C6–C9 with
  `--mesh-factor 0.72` and compare peak temperature; > 2 % change means the mesh
  governs the answer.
* No PCB body in the assembly; no internal cavity radiation between the payload and
  the foam box interior (that would require a fluid region with fvDOM).

---

# Part D — Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Tempted to install WSL/OpenFOAM/CalculiX/Gmsh | Reading `setup_report.json`, which is stale | Don't. `check_environment.py` reports READY. See C0 |
| `Manifest not ready:` from `setup_cht_case.py` | Validation failure | Run `assign_materials.py --validate`; fix each listed item |
| `Regions missing after splitMeshRegions` | Mesh has fewer cellZones than manifest components | Re-mesh without `--reuse-mesh`; check the STEP file did not change |
| `stage_transient_bcs.py` says "binary format" | `writeFormat` still binary | Apply the C6 ASCII patch, re-run the last segment |
| `Patch 'X' not found` from the staging script | Patch renamed or manifest/case out of sync | Compare `manifest.json` patch names against `case/constant/<region>/polyMesh/boundary` |
| Solver restarts at `Time = 0` every stage | The previous stage's time directory was deleted, or `startFrom` was edited | Confirm `startFrom latestTime` in `system/controlDict` and that the previous time directory exists |
| `run_summary.json` has `"completed": false` | Solver died | Read `case/log.chtMultiRegionFoam` bottom-up for the first `FOAM FATAL` / divergence |
| Temperatures oscillate at interfaces | Solid diffusion number too large | Lower `max_di` (10 → 5), re-`prepare`, re-run from t = 0 |
| Ollama replies are truncated or it forgets the stage number | `num_ctx` still 4096 | Rebuild with the A.3 Modelfile; confirm with `ollama show cfd-qwen` |
| Ollama very slow, `ollama ps` shows 100% CPU | Model does not fit in VRAM | Drop to `qwen2.5-coder:7b` or a smaller quantisation |

---

# Part E — The prompt to give with this runbook

**If you use [ollama/run_agent.ps1](ollama/run_agent.ps1), you need no prompt at all.**
The driver loads this file and seeds the conversation itself. Just run:

```powershell
.\ollama\run_agent.ps1
```

The prompt below is for driving the model by hand (bare `ollama run`, Open WebUI, or
any OpenAI-compatible client). Paste the **entire runbook first**, then this prompt as
the same message or the one right after it. Order matters — a 7b model anchors on the
last instruction it read.

```
You are executing OLLAMA_QWEN_TRANSIENT_RUNBOOK.md Part C in the repository
D:\Github\agent-cfd-fea-engineer. Study slug: balloon-ttp/transient-0-20km.

GOAL
Transient conduction+radiation simulation of a 60 W stratospheric balloon payload
ascending 0 -> 20 km in 1200 s, run as six 200 s segments with the environment
re-evaluated per segment.

ENVIRONMENT — ALREADY BUILT, NOTHING TO INSTALL
WSL Ubuntu, OpenFOAM v2412 with the chtMultiRegion solvers, CalculiX 2.21,
Gmsh 4.14.0-git and all Python packages are installed and verified. Never run
install_solvers.py, setup.ps1, first_run_setup.py, apt or pip install. If you are
shown JSON saying "ready": false or "openfoam": null, that is the stale
setup_report.json -- say so and continue. C0 is read-only and prints
"READY: full CFD/FEA toolchain available."

PROTOCOL
- One powershell command per turn, in a fenced powershell block, nothing else.
- Wait for me to paste the real output before the next command.
- State the current step id (C0..C10) before each command, and in C8 the stage number.
- Never state a temperature, heat flux, residual or runtime you have not seen in
  output I pasted. If you need a number, issue the command that produces it.
- If a command fails, do not retry it verbatim. Name the cause in one sentence, then
  issue a corrected command.
- Do not proceed past a failed verification gate. Say what failed and stop.

EXECUTION RULES SPECIFIC TO THIS STUDY
- Never start a stage while another is running. Two runs sharing the WSL work
  directory will delete each other's files mid-solve.
- In C8, run the prune snippet between stages. Without it each stage gets slower
  (measured 41.7 -> 269.4 s for identical work).
- Stage end times must stay multiples of the 20 s write interval, or the restart
  will land on a function-object-only directory that has no T field.
- The C4 heat flux depends on the meshed patch area. If you re-mesh, recompute
  q = 60 / <area from mesh/assembly.stats.json> before running.

EXPECTED RESULTS — use these to tell a correct run from a broken one
- Every stage: "completed": true, 400 steps, final_time 200/400/600/800/1000/1200.
- Heat input at jetson_heat_source: about 60 W. If it is far off, C4 is wrong.
- Jetson TTP peak about 40 C at t = 1200 s, still rising; strap about 38 C;
  radiator about 30 C; foam outer about -52 C.
- TTP heating rate dips near t = 700 s then rises again -- the convection-collapse
  crossing point. Its absence means the staged BCs did not take effect.

Start with C0.
```

### If you are only running part of it

Replace the last line with the step you want, and tell it where the study stands.
The model resumes correctly from an explicit state statement — it does not infer
progress from the filesystem:

```
The study is already set up and stages 1-3 are complete (t = 600 s). Skip to C8
stage 4: altitude 11667 m, h = 1.910. Start with the prune snippet.
```

---

## Reference — files this procedure touches

| Path | Role |
| --- | --- |
| [ollama/Modelfile.cfd](ollama/Modelfile.cfd) | Builds `cfd-qwen`: 32 k context, low temperature, operating contract as SYSTEM prompt |
| [ollama/run_agent.ps1](ollama/run_agent.ps1) | Approval-gated agent loop; `-SelfTest` is the Part A readiness gate |
| [.tmp/scripts/cht_case.py](.tmp/scripts/cht_case.py) | OpenFOAM case factory; `DEFAULT_SOLVER`, controlDict, BC specs |
| [.tmp/scripts/cht_pipeline.py](.tmp/scripts/cht_pipeline.py) | `prepare()` / `solve()` / `extract_cht_kpis()`; WSL run + copy-back |
| [.tmp/scripts/atmosphere.py](.tmp/scripts/atmosphere.py) | US76 atmosphere, sky sink, `combined_film` |
| [.tmp/scripts/step_assembly.py](.tmp/scripts/step_assembly.py) | STEP import, manifest validation, assembly meshing |
| [.github/skills/conjugate_heat_transfer/SKILL.md](.github/skills/conjugate_heat_transfer/SKILL.md) | Physics coverage, sanity checks |
| [.github/skills/step_assembly/SKILL.md](.github/skills/step_assembly/SKILL.md) | Manifest schema, BC types, gotchas |
| `outputs/balloon-ttp/transient-0-20km/assembly/manifest.json` | Single source of truth for this study |
| `outputs/balloon-ttp/transient-0-20km/case/` | The OpenFOAM case; time directories are the restart points |
