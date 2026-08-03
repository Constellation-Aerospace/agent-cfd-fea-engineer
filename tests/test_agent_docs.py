"""Cross-tool entry points stay consistent: AGENTS.md, CLAUDE.md, Copilot, skill proxies."""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / ".tmp" / "scripts"))
SOURCE_SKILLS = REPO / ".github" / "skills"
PROXY_SKILLS = REPO / ".claude" / "skills"

ENTRY_POINTS = [
    "AGENTS.md",
    "CLAUDE.md",
    "instructions.md",
    ".github/copilot-instructions.md",
    ".github/agents/cfd-fea-engineer.agent.md",
    ".github/prompts/system.md",
]


def _skill_names():
    return sorted(d.name for d in SOURCE_SKILLS.iterdir() if (d / "SKILL.md").is_file())


def test_entry_points_exist():
    for rel in ENTRY_POINTS:
        assert (REPO / rel).is_file(), f"missing agent entry point: {rel}"


def test_claude_md_points_at_shared_harness():
    """CLAUDE.md must delegate to AGENTS.md rather than fork the instructions."""
    text = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
    for needle in ("AGENTS.md", ".github/skills", "sync_agent_docs.py"):
        assert needle in text, f"CLAUDE.md does not reference {needle}"


def test_every_skill_has_frontmatter():
    """name/description front-matter is what every tool matches skills on."""
    for name in _skill_names():
        text = (SOURCE_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---"), f"{name}/SKILL.md has no YAML front-matter"
        header = text.split("---", 2)[1]
        assert "name:" in header, f"{name}/SKILL.md front-matter has no name:"
        assert "description:" in header, f"{name}/SKILL.md front-matter has no description:"


def test_claude_skill_proxies_cover_every_skill():
    assert sorted(d.name for d in PROXY_SKILLS.iterdir() if d.is_dir()) == _skill_names()


def test_claude_skill_proxies_are_in_sync():
    """Regenerate with: python .tmp/scripts/sync_agent_docs.py"""
    r = subprocess.run(
        [sys.executable, str(REPO / ".tmp" / "scripts" / "sync_agent_docs.py"), "--check"],
        capture_output=True, text=True, cwd=str(REPO),
    )
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.parametrize("name", _skill_names())
def test_proxy_description_survives_yaml_parsing(name):
    """Descriptions contain ': ' and quotes — the proxy must quote them.

    An unquoted plain scalar silently truncates or corrupts the description, which is
    exactly what every tool matches skills on. Round-trip the generated proxy and
    compare against the canonical skill.
    """
    from sync_agent_docs import parse_frontmatter, skill_metadata

    proxy = (PROXY_SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    parsed = parse_frontmatter(proxy)
    canonical = skill_metadata(SOURCE_SKILLS / name)

    assert parsed.get("name") == canonical["name"]
    assert parsed.get("description") == canonical["description"]
    assert "GENERATED" not in parsed.get("description", "")


def test_agents_md_lists_every_skill():
    text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    for name in _skill_names():
        assert name in text, f"AGENTS.md does not mention the {name} skill"
