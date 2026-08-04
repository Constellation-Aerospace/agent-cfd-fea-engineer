"""agent-cfd-fea-engineer — MAF Agent definitions.

CFD/FEA engineering simulation agent: multiphase VOF (OpenFOAM), FEA with CalculiX as
the default path and other FEM backends as available, geometry/meshing (Gmsh),
post-processing (PyVista), parametric studies, reporting.

Exports:
    build_agents() -> list[GitHubCopilotAgent]   (Dynamic Agent Loader entry point)

Architecture (DOE v2):
  Layer 1 (Skills)        — .github/skills/*/SKILL.md + .github/skills/*/scripts/
  Layer 2 (Orchestration) — THIS FILE (GitHubCopilotAgent via MAF)
  Layer 3 (Execution)     — .tmp/scripts/ shared utilities + skill scripts
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
AGENT_DIR = Path(__file__).parent.resolve()
PROMPTS_DIR = AGENT_DIR / ".github" / "prompts"
SKILLS_DIR = AGENT_DIR / ".github" / "skills"
SCRIPTS_DIR = AGENT_DIR / ".tmp" / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ── Subprocess helpers ────────────────────────────────────────────────────────

def _run_env() -> dict[str, str]:
    """Add .tmp/scripts/ to PYTHONPATH so skill scripts can import shared utilities."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    scripts = str(SCRIPTS_DIR)
    env["PYTHONPATH"] = f"{scripts}{os.pathsep}{existing}" if existing else scripts
    return env


async def _run(args: list[str], timeout: int | None = None) -> str:
    """Run a script as a subprocess. Raises RuntimeError on non-zero exit."""
    result = await asyncio.to_thread(
        subprocess.run, args,
        capture_output=True, text=True, timeout=timeout,
        cwd=str(AGENT_DIR), env=_run_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or f"Script exited {result.returncode}")
    return result.stdout or "(no output)"


def _skill(name: str, script: str) -> str:
    return str(SKILLS_DIR / name / "scripts" / script)


def _resolve_skill_script(skill: str, script: str) -> Path:
    skill_path = (SKILLS_DIR / skill).resolve()
    scripts_path = (skill_path / "scripts").resolve()
    script_path = (scripts_path / script).resolve()

    if not skill_path.is_dir():
        raise ValueError(f"Unknown skill: {skill}")
    if skill_path.parent != SKILLS_DIR:
        raise ValueError(f"Invalid skill path: {skill}")
    if script_path.suffix != ".py":
        raise ValueError("Only Python skill scripts are supported")
    if script_path.parent != scripts_path or not script_path.is_file():
        raise ValueError(f"Unknown script for skill '{skill}': {script}")
    return script_path


def _available_skill_scripts() -> dict[str, list[str]]:
    inventory: dict[str, list[str]] = {}
    if not SKILLS_DIR.exists():
        return inventory
    for skill_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        scripts_dir = skill_dir / "scripts"
        scripts = sorted(p.name for p in scripts_dir.glob("*.py")) if scripts_dir.exists() else []
        inventory[skill_dir.name] = scripts
    return inventory


# ── System prompt ─────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    """Load .github/prompts/system.md + append each .github/skills/*/SKILL.md as a tool block."""
    parts: list[str] = []
    system_md = PROMPTS_DIR / "system.md"
    if system_md.exists():
        parts.append(system_md.read_text(encoding="utf-8", errors="replace"))
        if SKILLS_DIR.exists():
            skill_sections: list[str] = []
            for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
                content = skill_md.read_text(encoding="utf-8", errors="replace")
                skill_sections.append(f"\n### Tool: {skill_md.parent.name}\n\n{content}")
            if skill_sections:
                parts.append("\n\n---\n\n## Registered Skill Tool Descriptions\n")
                parts.extend(skill_sections)
    else:
        agents_md = AGENT_DIR / "AGENTS.md"
        if agents_md.exists():
            parts.append(agents_md.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


SYSTEM_PROMPT = _build_system_prompt()


# ── Tool functions ────────────────────────────────────────────────────────────

async def check_solver_environment() -> str:
    """Verify the CFD/FEA toolchain (WSL, OpenFOAM, CalculiX, Gmsh, Python packages).
    Use at session start, after solver errors, or when asked if solvers are installed."""
    return await _run([sys.executable, _skill("solver_environment", "check_environment.py")])


async def install_solvers(force: bool = False) -> str:
    """Install OpenFOAM 2412 + CalculiX + Gmsh into WSL Ubuntu (idempotent, ~2 GB).
    Use when check_solver_environment reports missing solvers."""
    args = [sys.executable, _skill("solver_environment", "install_solvers.py")]
    if force:
        args.append("--force")
    return await _run(args, timeout=2400)


async def build_geometry(study: str, overrides: str = "", export_step: bool = False) -> str:
    """Define/validate the parametric exhaust-discharge geometry for a study.
    Use when the user changes pipe diameter, submergence, domain size, or starts a study.
    overrides: space-separated KEY=VALUE pairs, e.g. 'pipe_diameter=0.35 submergence=3.0'."""
    args = [sys.executable, _skill("geometry_domain", "build_geometry.py"), "--study", study]
    for spec in overrides.split():
        args += ["--set", spec]
    if export_step:
        args.append("--export-step")
    return await _run(args, timeout=600)


async def generate_mesh(study: str, level: str = "medium") -> str:
    """Generate the CFD mesh at a refinement level (coarse|medium|fine).
    Use for 'mesh the domain' or before setting up a case with a specific resolution."""
    return await _run([sys.executable, _skill("meshing", "generate_mesh.py"),
                       "--study", study, "--level", level], timeout=1800)


async def run_mesh_independence(study: str, sim_time: float = 1.0, n_procs: int = 6) -> str:
    """Run the 3-level mesh independence study with GCI reporting. Long-running (hours).
    Use when the user asks for mesh independence / grid convergence verification."""
    return await _run([sys.executable, _skill("meshing", "mesh_independence.py"),
                       "--study", study, "--sim-time", str(sim_time), "--np", str(n_procs)],
                      timeout=12 * 3600)


async def setup_cfd_case(study: str, config_json: str = "{}", mesh_factor: float = 1.0) -> str:
    """Set up the full multiphase CFD case: geometry, mesh, OpenFOAM case, field init.
    config_json: solver overrides, e.g. '{"U_in": 25, "T_exhaust_C": 550, "end_time_s": 4}'.
    Use for 'set up the simulation' or after changing operating conditions."""
    return await _run([sys.executable, _skill("multiphase_cfd", "setup_case.py"),
                       "--study", study, "--config", config_json,
                       "--mesh-factor", str(mesh_factor)], timeout=3600)


async def run_cfd_case(study: str, n_procs: int = 6, end_time: float = 0.0) -> str:
    """Run compressibleInterFoam for a prepared study (parallel, in WSL). Long-running.
    end_time > 0 overrides the configured physical end time (use 0.2 for smoke runs).
    Use for 'run the simulation'."""
    args = [sys.executable, _skill("multiphase_cfd", "run_case.py"),
            "--study", study, "--np", str(n_procs)]
    if end_time > 0:
        args += ["--end-time", str(end_time)]
    return await _run(args, timeout=12 * 3600)


async def run_fea(study: str, t_inner: float = -1, t_outer: float = -1) -> str:
    """FEA: steady thermal-structural analysis of the exhaust pipe wall.
    CalculiX is the default implementation in this repo; Temperatures are in Celsius;
    -1 uses the study's exhaust/water temperatures. Use for 'FEA', 'thermal stress',
    'structural check'."""
    args = [sys.executable, _skill("fea_analysis", "run_pipe_fea.py"), "--study", study]
    if t_inner >= 0:
        args += ["--t-inner", str(t_inner)]
    if t_outer >= 0:
        args += ["--t-outer", str(t_outer)]
    return await _run(args, timeout=3600)


async def plot_results(study: str) -> str:
    """Generate all post-processing figures: field contours, streamlines, temperature
    decay curves, and back-pressure history. Use after a CFD run completes."""
    out = []
    for script in ("plot_fields.py", "temperature_decay.py", "back_pressure.py"):
        out.append(await _run([sys.executable, _skill("post_processing", script),
                               "--study", study], timeout=1200))
    return "\n\n".join(out)


async def run_parametric_sweep(study: str, matrix_json: str, sim_time: float = 2.0,
                               n_procs: int = 6) -> str:
    """Comparative assessment across operating points. Very long-running (hours/point).
    matrix_json: JSON list of overrides, e.g.
    '[{"label":"cold","U_in":10,"T_exhaust_C":300},{"label":"hot","U_in":25,"T_exhaust_C":550}]'.
    Use for 'parametric study', 'compare operating conditions', 'sensitivity'."""
    return await _run([sys.executable, _skill("parametric_study", "run_sweep.py"),
                       "--study", study, "--matrix", matrix_json,
                       "--sim-time", str(sim_time), "--np", str(n_procs)],
                      timeout=24 * 3600)


async def build_report(study: str, title: str = "") -> str:
    """Assemble the final technical report (Markdown + HTML) from all study artifacts.
    Use for 'generate the report' / 'write up the results'. After generation, refine the
    executive summary and conclusions sections with engineering judgment."""
    args = [sys.executable, _skill("report_generation", "build_report.py"), "--study", study]
    if title:
        args += ["--title", title]
    return await _run(args, timeout=600)


async def list_available_skill_scripts() -> str:
    """List repository skill scripts that can be executed dynamically.
    Use when checking which uploaded solver skills or helper scripts are available."""
    lines: list[str] = []
    for skill, scripts in _available_skill_scripts().items():
        lines.append(f"{skill}: {', '.join(scripts) if scripts else '(no scripts)'}")
    return "\n".join(lines) if lines else "No skills found under .github/skills"


async def run_skill_script(skill: str, script: str, arguments: str = "",
                           timeout: int = 3600) -> str:
    """Run any repository skill script by skill name, script file, and raw CLI arguments.
    Use this for newly uploaded solver skills so they become executable without editing
    the agent factory. Example: skill='solver_environment', script='check_environment.py',
    arguments='--help'."""
    script_path = _resolve_skill_script(skill, script)
    args = [sys.executable, str(script_path)]
    if arguments:
        args.extend(arguments.split())
    return await _run(args, timeout=timeout)


# ── LiteLLM provider (CommandCenter mode) ────────────────────────────────────

def _llm_provider() -> dict[str, Any]:
    base_url = os.environ.get("LITELLM_BASE_URL", "http://127.0.0.1:8080")
    api_key = os.environ.get("LITELLM_MASTER_KEY", "sk-local")
    return {"type": "openai", "base_url": f"{base_url}/v1", "api_key": api_key}


# ── Agent factory ─────────────────────────────────────────────────────────────

def build_agent() -> "GitHubCopilotAgent":
    from agent_framework_github_copilot import GitHubCopilotAgent  # type: ignore[import]
    from copilot.types import PermissionHandler                     # type: ignore[import]

    return GitHubCopilotAgent(
        name="cfd-fea-engineer",
        description="CFD/FEA simulation agent: multiphase VOF exhaust discharge, thermal "
                    "mixing, back-pressure, mesh independence, FEA, parametric studies, reports.",
        instructions=SYSTEM_PROMPT,
        tools=[
            check_solver_environment,
            install_solvers,
            build_geometry,
            generate_mesh,
            run_mesh_independence,
            setup_cfd_case,
            run_cfd_case,
            run_fea,
            plot_results,
            run_parametric_sweep,
            build_report,
            list_available_skill_scripts,
            run_skill_script,
        ],
        default_options={
            "model": "tier-balanced",
            "provider": _llm_provider(),
            "mcp_servers": {},
            "on_permission_request": PermissionHandler.approve_all,
        },
    )


def build_agents() -> list:
    """Dynamic Agent Loader entry point. Synchronous, zero-argument, pure."""
    return [build_agent()]


__all__ = ["build_agents", "build_agent", "SYSTEM_PROMPT"]
