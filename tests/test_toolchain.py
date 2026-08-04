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


def test_wsl_bridge_status_has_elmer_key():
    """elmer must be a first-class (if optional) status key, like calculix/gmsh_wsl."""
    sys.path.insert(0, str(SCRIPTS))
    import wsl_bridge
    import inspect
    assert '"elmer"' in inspect.getsource(wsl_bridge.check_environment)


def test_fea_pipe_surface_classification():
    """Elmer needs gmsh physical groups on the tube's 4 boundary surfaces (inner/outer/
    fixed-end/far-end) so ElmerGrid can carry boundary IDs into the Elmer mesh; this must
    keep classifying correctly regardless of gmsh's internal surface tag ordering."""
    fea_scripts = REPO / ".github" / "skills" / "fea_analysis" / "scripts"
    sys.path.insert(0, str(fea_scripts))
    import gmsh
    from run_pipe_fea import _classify_surfaces

    R, Ro, L = 0.15, 0.162, 1.0
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("test_tube")
        occ = gmsh.model.occ
        outer = occ.addCylinder(0, 0, 0, L, 0, 0, Ro)
        inner = occ.addCylinder(0, 0, 0, L, 0, 0, R)
        occ.cut([(3, outer)], [(3, inner)])
        occ.synchronize()
        tags = _classify_surfaces(R, Ro, L)
    finally:
        gmsh.finalize()

    assert len(tags["INNER"]) == 1
    assert len(tags["OUTER"]) == 1
    assert len(tags["FIXED"]) == 1
    assert len(tags["FAR"]) == 1


def test_run_pipe_fea_solver_flag():
    """--solver must accept both FEM backends (contract for the fea_analysis skill)."""
    r = _run([str(REPO / ".github/skills/fea_analysis/scripts/run_pipe_fea.py"), "--help"])
    assert r.returncode == 0
    assert "--solver" in r.stdout
    assert "elmer" in r.stdout


@pytest.mark.skipif(subprocess.run(["wsl", "-l", "-q"], capture_output=True).returncode != 0,
                    reason="WSL not available")
def test_solver_environment_ready():
    """Full toolchain check — skipped on machines without WSL."""
    r = _run([str(REPO / ".github/skills/solver_environment/scripts/check_environment.py")])
    assert r.returncode == 0, f"solver environment not ready:\n{r.stdout[-800:]}"
    status = json.loads(r.stdout[: r.stdout.rindex("}") + 1])
    assert status["openfoam"], "OpenFOAM missing"
    assert status["calculix"], "CalculiX missing"
