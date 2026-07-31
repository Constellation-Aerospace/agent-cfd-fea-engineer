"""Contract tests: script paths, shared utilities, and (when available) solver toolchain."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / ".tmp" / "scripts"

SKILL_SCRIPTS = [
    ".github/skills/solver_environment/scripts/check_environment.py",
    ".github/skills/solver_environment/scripts/install_solvers.py",
    ".github/skills/geometry_domain/scripts/build_geometry.py",
    ".github/skills/meshing/scripts/generate_mesh.py",
    ".github/skills/meshing/scripts/mesh_independence.py",
    ".github/skills/multiphase_cfd/scripts/setup_case.py",
    ".github/skills/multiphase_cfd/scripts/run_case.py",
    ".github/skills/fea_analysis/scripts/run_pipe_fea.py",
    ".github/skills/post_processing/scripts/plot_fields.py",
    ".github/skills/post_processing/scripts/temperature_decay.py",
    ".github/skills/post_processing/scripts/back_pressure.py",
    ".github/skills/parametric_study/scripts/run_sweep.py",
    ".github/skills/report_generation/scripts/build_report.py",
]


def _run(args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=str(REPO))


def test_all_skill_scripts_have_help():
    """Every skill script must at least parse --help (catches import/path breakage)."""
    for rel in SKILL_SCRIPTS:
        r = _run([str(REPO / rel), "--help"])
        assert r.returncode == 0, f"{rel} --help failed:\n{r.stderr[:500]}"


def test_every_skill_has_skillmd():
    for d in (REPO / ".github" / "skills").iterdir():
        if d.is_dir():
            assert (d / "SKILL.md").exists(), f"missing SKILL.md in {d.name}"


def test_exhaust_properties_mixture():
    """Mixture property calculator: sane molar mass and cp for diesel exhaust."""
    sys.path.insert(0, str(SCRIPTS))
    from exhaust_properties import mixture_properties, DEFAULT_MOLE_FRACTIONS
    props = mixture_properties(DEFAULT_MOLE_FRACTIONS)
    assert 28.0 < props["molar_mass_kg_per_kmol"] < 30.5
    assert 950 < props["cp_at_25C_J_per_kgK"] < 1150
    assert 1050 < props["cp_at_400C_J_per_kgK"] < 1250


def test_foam_case_writer(tmp_path):
    """Case factory writes a complete OpenFOAM case skeleton."""
    sys.path.insert(0, str(SCRIPTS))
    from foam_case import write_case
    cfg = write_case(tmp_path / "case", {"U_in": 20, "T_exhaust_C": 500})
    assert cfg["U_in"] == 20
    for rel in ("0.orig/U", "0.orig/T", "0.orig/alpha.water", "0.orig/p_rgh",
                "constant/g", "constant/thermophysicalProperties.gas",
                "constant/turbulenceProperties", "system/controlDict",
                "system/fvSolution", "system/setFieldsDict"):
        assert (tmp_path / "case" / rel).exists(), f"missing {rel}"
    gas = (tmp_path / "case" / "constant" / "thermophysicalProperties.gas").read_text()
    assert "janaf" in gas and "perfectGas" in gas


def test_wsl_bridge_path_translation():
    sys.path.insert(0, str(SCRIPTS))
    from wsl_bridge import win_to_wsl
    assert win_to_wsl("C:\\Users\\x\\case") == "/mnt/c/Users/x/case"


@pytest.mark.skipif(subprocess.run(["wsl", "-l", "-q"], capture_output=True).returncode != 0,
                    reason="WSL not available")
def test_solver_environment_ready():
    """Full toolchain check — skipped on machines without WSL."""
    r = _run([str(REPO / ".github/skills/solver_environment/scripts/check_environment.py")])
    assert r.returncode == 0, f"solver environment not ready:\n{r.stdout[-800:]}"
    status = json.loads(r.stdout[: r.stdout.rindex("}") + 1])
    assert status["openfoam"], "OpenFOAM missing"
    assert status["calculix"], "CalculiX missing"
