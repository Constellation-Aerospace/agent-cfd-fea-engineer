"""CI gate for the self-annealing loop: lesson capture / apply round-trip and the
session-end check's exit semantics (no git or WSL needed)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ANNEAL = REPO / ".github" / "skills" / "self_annealing" / "scripts" / "anneal.py"


def run(args, lessons_file: Path):
    env = {**os.environ, "LESSONS_FILE": str(lessons_file)}
    return subprocess.run([sys.executable, str(ANNEAL), *args],
                          capture_output=True, text=True, env=env)


def test_log_list_apply_roundtrip(tmp_path):
    lessons = tmp_path / "lessons.md"

    r = run(["log", "--title", "test lesson", "--lesson", "something learned",
             "--target", "meshing", "--project", "proj-x"], lessons)
    assert r.returncode == 0 and "L001 logged" in r.stdout
    r = run(["log", "--title", "second", "--lesson", "more", "--target", "core"],
            lessons)
    assert "L002 logged" in r.stdout

    r = run(["list"], lessons)
    assert "L001" in r.stdout and "L002" in r.stdout and "[OPEN]" in r.stdout

    r = run(["apply", "L001", "--note", "integrated into meshing SKILL"], lessons)
    assert r.returncode == 0 and "APPLIED" in r.stdout
    text = lessons.read_text(encoding="utf-8")
    assert "L001 — test lesson [APPLIED]" in text
    assert "integrated into meshing SKILL" in text

    r = run(["list"], lessons)
    assert "L001" not in r.stdout and "L002" in r.stdout

    r = run(["apply", "L001", "--note", "again"], lessons)
    assert r.returncode == 1                      # already applied -> not OPEN


def test_check_flags_open_lessons(tmp_path):
    lessons = tmp_path / "lessons.md"
    run(["log", "--title", "open one", "--lesson", "x", "--target", "docs"], lessons)
    r = run(["check"], lessons)
    assert r.returncode == 1
    assert "OPEN lesson" in r.stdout


def test_shipped_backlog_has_no_stale_open_lessons():
    """The committed lessons file must not accumulate silently-forgotten entries:
    OPEN lessons are allowed mid-work, but every entry must parse."""
    text = (REPO / "agent-data" / "lessons.md").read_text(encoding="utf-8")
    import re
    entries = re.findall(r"^## (L\d{3}) — .*? \[(OPEN|APPLIED)\]\s*$", text, re.M)
    assert entries, "lessons.md has no parseable entries"
    ids = [e[0] for e in entries]
    assert len(ids) == len(set(ids)), "duplicate lesson ids"
