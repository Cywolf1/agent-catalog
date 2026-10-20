#!/usr/bin/env python3
"""Sync the canonical spec-planner skill into the tech-lead agent bundle.

`omni agent add` uploads ONLY the agent directory, so the canonical
repo-root skill at skills/spec-planner/ must exist as real files (not
symlinks) under agents/tech-lead/skills/spec-planner/ for the skill to
install with the agent. This script copies the canonical tree over the
bundled tree; `--check` verifies they are identical without writing.

Usage:
    python3 scripts/sync_skills.py          # copy canonical -> bundled
    python3 scripts/sync_skills.py --check  # exit 1 if they differ

Exit codes:
    0  (check) trees are identical, or (copy) sync completed
    1  (check) trees differ
    2  usage / filesystem error
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "skills" / "spec-planner"
DST = REPO_ROOT / "agents" / "tech-lead" / "skills" / "spec-planner"

SKIP_SUFFIXES = {".pyc", ".pyo"}
SKIP_DIRS = {"__pycache__"}


def _relative_files(root):
    # type: (Path) -> set[str]
    """POSIX-relative paths of every syncable file under *root*."""
    files = set()  # type: set[str]
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        files.add(rel.as_posix())
    return files


def check():
    # type: () -> int
    """Compare canonical and bundled trees. Returns the process exit code."""
    if not SRC.is_dir():
        print(f"error: canonical skill dir missing: {SRC}", file=sys.stderr)
        return 2
    if not DST.is_dir():
        print(f"error: bundled skill dir missing: {DST}", file=sys.stderr)
        return 1

    src_files = _relative_files(SRC)
    dst_files = _relative_files(DST)
    problems = []  # type: list[str]

    for rel in sorted(src_files - dst_files):
        problems.append(f"missing in bundle: agents/tech-lead/skills/spec-planner/{rel}")
    for rel in sorted(dst_files - src_files):
        problems.append(f"extra in bundle: agents/tech-lead/skills/spec-planner/{rel}")
    for rel in sorted(src_files & dst_files):
        if not filecmp.cmp(SRC / rel, DST / rel, shallow=False):
            problems.append(f"content differs: agents/tech-lead/skills/spec-planner/{rel}")

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(
            "FAILED: bundled skill is out of sync; run "
            "`python3 scripts/sync_skills.py` to refresh it.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(src_files)} file(s) in sync.")
    return 0


def sync():
    # type: () -> int
    """Copy the canonical tree over the bundled tree. Returns the exit code."""
    if not SRC.is_dir():
        print(f"error: canonical skill dir missing: {SRC}", file=sys.stderr)
        return 2
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SRC, DST, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc", "*.pyo"))
    copied = len(_relative_files(DST))
    print(f"OK: synced {copied} file(s) into agents/tech-lead/skills/spec-planner/.")
    return 0


def main():
    # type: () -> int
    args = [a for a in sys.argv[1:] if a != "--check"]
    if len(args) > 0 or len(sys.argv) > 2:
        print("usage: sync_skills.py [--check]", file=sys.stderr)
        return 2
    if "--check" in sys.argv:
        return check()
    return sync()


if __name__ == "__main__":
    sys.exit(main())
