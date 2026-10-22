#!/usr/bin/env python3
"""Sync the canonical skills into the tech-lead agent bundle.

`omni agent add` uploads ONLY the agent directory, so each canonical
repo-root skill at skills/<name>/ must exist as real files (not symlinks)
under agents/tech-lead/skills/<name>/ for the skill to install with the
agent. This script copies every canonical tree over its bundled tree;
`--check` verifies they are identical without writing.

spec-planner is authored here; fanout, cross-review, and investigate are
verbatim copies of Omnigent's shipped polly example skills
(omnigent/resources/examples/polly/skills/).

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
SRC_ROOT = REPO_ROOT / "skills"
DST_ROOT = REPO_ROOT / "agents" / "tech-lead" / "skills"
SKILL_NAMES = ("spec-planner", "fanout", "cross-review", "investigate")

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
    problems = []  # type: list[str]
    total = 0
    for name in SKILL_NAMES:
        src = SRC_ROOT / name
        dst = DST_ROOT / name
        if not src.is_dir():
            print(f"error: canonical skill dir missing: {src}", file=sys.stderr)
            return 2
        if not dst.is_dir():
            problems.append(f"missing in bundle: agents/tech-lead/skills/{name}/")
            continue

        src_files = _relative_files(src)
        dst_files = _relative_files(dst)
        total += len(src_files)

        for rel in sorted(src_files - dst_files):
            problems.append(f"missing in bundle: agents/tech-lead/skills/{name}/{rel}")
        for rel in sorted(dst_files - src_files):
            problems.append(f"extra in bundle: agents/tech-lead/skills/{name}/{rel}")
        for rel in sorted(src_files & dst_files):
            if not filecmp.cmp(src / rel, dst / rel, shallow=False):
                problems.append(f"content differs: agents/tech-lead/skills/{name}/{rel}")

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        print(
            "FAILED: bundled skills are out of sync; run "
            "`python3 scripts/sync_skills.py` to refresh it.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {total} file(s) in sync across {len(SKILL_NAMES)} skill(s).")
    return 0


def sync():
    # type: () -> int
    """Copy the canonical trees over the bundled trees. Returns the exit code."""
    for name in SKILL_NAMES:
        if not (SRC_ROOT / name).is_dir():
            print(f"error: canonical skill dir missing: {SRC_ROOT / name}", file=sys.stderr)
            return 2
    copied = 0
    for name in SKILL_NAMES:
        dst = DST_ROOT / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(SRC_ROOT / name, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*SKIP_DIRS, "*.pyc", "*.pyo"))
        copied += len(_relative_files(dst))
    print(f"OK: synced {copied} file(s) into agents/tech-lead/skills/.")
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
