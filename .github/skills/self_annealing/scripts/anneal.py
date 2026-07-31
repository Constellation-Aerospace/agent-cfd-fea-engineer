#!/usr/bin/env python3
"""Self-annealing loop: capture lessons during project work, track them until they
are integrated into the harness (skills/scripts/materials/docs), and gate session
end on a commit prompt.

Commands:
    # capture a lesson the moment it is learned (cheap, no interruption)
    python anneal.py log --title "P1 diverges on coarse tets" \\
        --lesson "P1 radiation needs relaxation 0.5 below 100k cells" \\
        --target conjugate_heat_transfer --project acme-hx

    python anneal.py list            # OPEN lessons (the annealing backlog)
    python anneal.py list --all      # full history
    python anneal.py apply L003 --note "relaxation table added to SKILL.md"

    # session end: OPEN lessons + uncommitted changes -> suggested commit
    python anneal.py check
    python anneal.py check --run-tests

Exit codes for `check`: 0 = annealed & committed; 1 = action needed (open lessons
or uncommitted harness changes — integrate, then prompt the user to commit).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
LESSONS = Path(os.getenv("LESSONS_FILE", REPO / "agent-data" / "lessons.md"))

HEADER = """# Lessons — the annealing backlog

Techniques, fixes, and gotchas learned during project work, captured the moment
they surface and tracked until integrated into the harness (a SKILL.md, a core
module, the materials library, or docs). `anneal.py check` refuses to sign off a
session while lessons are OPEN or harness changes are uncommitted.

Format per entry: `## L<nnn> — <title> [OPEN|APPLIED]` + date/project/target/
lesson lines (+ applied note once integrated).
"""

_ENTRY = re.compile(r"^## (L\d{3}) — (.\S.*?) \[(OPEN|APPLIED)\]\s*$", re.M)


def _read() -> str:
    return LESSONS.read_text(encoding="utf-8") if LESSONS.exists() else HEADER


def _entries(text: str) -> list[dict]:
    out = []
    for m in _ENTRY.finditer(text):
        out.append({"id": m.group(1), "title": m.group(2), "status": m.group(3),
                    "start": m.start()})
    return out


def cmd_log(args) -> int:
    text = _read()
    ids = [int(e["id"][1:]) for e in _entries(text)]
    new_id = f"L{(max(ids) + 1 if ids else 1):03d}"
    entry = (f"\n## {new_id} — {args.title} [OPEN]\n"
             f"- date: {_dt.date.today().isoformat()}\n"
             f"- project: {args.project or '-'}\n"
             f"- target: {args.target}\n"
             f"- lesson: {args.lesson}\n")
    LESSONS.parent.mkdir(parents=True, exist_ok=True)
    LESSONS.write_text(text + entry, encoding="utf-8")
    print(f"{new_id} logged (target: {args.target}). Integrate before session end "
          f"or leave OPEN for the next annealing pass.")
    return 0


def cmd_list(args) -> int:
    text = _read()
    entries = _entries(text)
    shown = entries if args.all else [e for e in entries if e["status"] == "OPEN"]
    if not shown:
        print("No OPEN lessons — backlog is annealed.")
        return 0
    for e in shown:
        block_end = min((n["start"] for n in entries if n["start"] > e["start"]),
                        default=len(text))
        block = text[e["start"]:block_end].strip()
        print(block + "\n")
    return 0


def cmd_apply(args) -> int:
    text = _read()
    if not re.search(rf"^## {args.id} — .* \[OPEN\]\s*$", text, re.M):
        print(f"{args.id} not found or not OPEN.")
        return 1
    text = re.sub(rf"^(## {args.id} — .*) \[OPEN\]\s*$", r"\1 [APPLIED]", text,
                  count=1, flags=re.M)
    entries = _entries(text)
    e = next(x for x in entries if x["id"] == args.id)
    block_end = min((n["start"] for n in entries if n["start"] > e["start"]),
                    default=len(text))
    applied = f"- applied: {_dt.date.today().isoformat()} — {args.note}\n"
    text = text[:block_end].rstrip("\n") + "\n" + applied + text[block_end:]
    LESSONS.write_text(text, encoding="utf-8")
    print(f"{args.id} marked APPLIED.")
    return 0


def _suggest_commit(changed: list[str]) -> str:
    areas = set()
    for path in changed:
        p = path.replace("\\", "/")
        if p.startswith(".github/skills/"):
            areas.add(p.split("/")[2])
        elif p.startswith(".tmp/scripts/"):
            areas.add("core")
        elif p.startswith("agent-data/"):
            areas.add("data")
        elif p.startswith("tests/"):
            areas.add("tests")
        else:
            areas.add("docs")
    return f"anneal: update {', '.join(sorted(areas))}"


def cmd_check(args) -> int:
    problems = 0
    open_lessons = [e for e in _entries(_read()) if e["status"] == "OPEN"]
    if open_lessons:
        problems += 1
        print(f"[!!] {len(open_lessons)} OPEN lesson(s) — integrate into their targets "
              f"and `anneal.py apply <id>`, or explicitly defer:")
        for e in open_lessons:
            print(f"     {e['id']} — {e['title']}")
    else:
        print("[ok] no OPEN lessons")

    if args.run_tests:
        r = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"],
                           cwd=str(REPO), capture_output=True, text=True)
        tail = (r.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
        print(f"[{'ok' if r.returncode == 0 else '!!'}] pytest: {tail[0]}")
        problems += 0 if r.returncode == 0 else 1

    r = subprocess.run(["git", "status", "--porcelain"], cwd=str(REPO),
                       capture_output=True, text=True)
    changed = [ln[3:] for ln in (r.stdout or "").splitlines() if ln.strip()]
    if changed:
        problems += 1
        print(f"[!!] {len(changed)} uncommitted change(s) — PROMPT THE USER TO COMMIT:")
        for c in changed[:15]:
            print(f"     {c}")
        print(f'\n     suggested: git add -A && git commit -m "{_suggest_commit(changed)}" '
              "&& git push")
    else:
        print("[ok] working tree clean — harness state is committed")

    if problems == 0:
        print("\nSession annealed: lessons integrated, tree committed.")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("log", help="Capture a new lesson")
    p.add_argument("--title", required=True)
    p.add_argument("--lesson", required=True)
    p.add_argument("--target", required=True,
                   help="Skill/module/doc the lesson should update")
    p.add_argument("--project", default=None)
    p.set_defaults(fn=cmd_log)
    p = sub.add_parser("list", help="Show lessons")
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("apply", help="Mark a lesson integrated")
    p.add_argument("id")
    p.add_argument("--note", required=True)
    p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("check", help="Session-end annealing gate")
    p.add_argument("--run-tests", action="store_true")
    p.set_defaults(fn=cmd_check)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
