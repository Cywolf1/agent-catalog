"""Repo-layout contract tests for the tech-lead agent catalog bundle.

These tests pin the packaging invariants ``omni agent add`` depends on:
the agent directory is self-contained (real files, no symlinks), the
canonical repo-root skill stays byte-identical to the bundled copy via
``scripts/sync_skills.py``, and the spec-DAG validator accepts the
shipped project-scaffold template.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = REPO_ROOT / "agents" / "tech-lead"
AGENT_SKILLS_DIR = AGENT_DIR / "skills"
CANONICAL_SKILL_DIR = REPO_ROOT / "skills" / "spec-planner"
VALIDATOR = AGENT_SKILLS_DIR / "spec-planner" / "scripts" / "validate_spec_dag.py"
TEMPLATE = REPO_ROOT / "templates" / "project-scaffold" / ".specs" / "_template.md"

try:  # PyYAML when available; a minimal parser covers the fallback case.
    import yaml  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only without PyYAML
    yaml = None  # type: ignore[assignment]

REQUIRED_FILES = (
    AGENT_DIR / "config.yaml",
    AGENT_DIR / "PROMPT.md",
    AGENT_SKILLS_DIR / "spec-planner" / "SKILL.md",
    AGENT_SKILLS_DIR / "spec-planner" / "scripts" / "validate_spec_dag.py",
    AGENT_SKILLS_DIR / "fanout" / "SKILL.md",
    AGENT_SKILLS_DIR / "cross-review" / "SKILL.md",
    AGENT_SKILLS_DIR / "investigate" / "SKILL.md",
    CANONICAL_SKILL_DIR / "SKILL.md",
    CANONICAL_SKILL_DIR / "scripts" / "validate_spec_dag.py",
    REPO_ROOT / "scripts" / "sync_skills.py",
    TEMPLATE,
    REPO_ROOT / "templates" / "project-scaffold" / ".agent" / "SYSTEM_RULES.md",
    REPO_ROOT / "README.md",
)

REQUIRED_SKILLS = ("spec-planner", "fanout", "cross-review", "investigate")


def _parse_minimal_yaml(text):
    # type: (str) -> dict
    """Parse the 2-space-indented mapping/list subset this repo's YAML uses."""
    root = {}  # type: dict
    stack = [(-2, root, None)]  # type: list
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        _, parent, last_key = stack[-1]
        if stripped.startswith("- "):
            assert last_key is not None, "list item without a parent key: %r" % stripped
            if not isinstance(parent.get(last_key), list):
                parent[last_key] = []
            parent[last_key].append(_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            raise ValueError("unsupported line: %r" % stripped)
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if value == "":
            child = {}  # type: dict
            parent[key] = child
            stack.append((indent, child, key))
        else:
            parent[key] = _scalar(value)
    return root


def _scalar(raw):
    # type: (str) -> object
    text = raw.split(" #", 1)[0].strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    if text == "[]":
        return []
    if text.startswith("[") and text.endswith("]"):
        return [_scalar(p) for p in text[1:-1].split(",")]
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def _load_yaml(path):
    # type: (Path) -> dict
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
    else:  # pragma: no cover - exercised only without PyYAML
        data = _parse_minimal_yaml(text)
    assert isinstance(data, dict), "%s must parse to a mapping" % path
    return data


def _load_config():
    # type: () -> dict
    return _load_yaml(AGENT_DIR / "config.yaml")


def _load_front_matter(path):
    # type: (Path) -> dict
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "%s must start with front-matter" % path
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    body = "\n".join(lines[1:end])
    if yaml is not None:
        data = yaml.safe_load(body)
    else:  # pragma: no cover - exercised only without PyYAML
        data = _parse_minimal_yaml(body)
    assert isinstance(data, dict), "%s front-matter must be a mapping" % path
    return data


def test_required_files_exist():
    missing = [str(p.relative_to(REPO_ROOT)) for p in REQUIRED_FILES if not p.is_file()]
    assert missing == [], "missing files: %s" % missing


def test_no_symlinks_in_agent_bundle():
    symlinks = [
        str(p.relative_to(REPO_ROOT))
        for p in sorted(AGENT_DIR.rglob("*"))
        if p.is_symlink()
    ]
    assert symlinks == [], "omni agent add refuses symlinked agent files: %s" % symlinks


def test_config_yaml_required_fields():
    config = _load_config()
    assert config["spec_version"] == 1
    assert config["name"] == "tech-lead"
    assert config["display_name"] == "Tech Lead (Spec-Driven)"
    assert isinstance(config["description"], str) and config["description"].strip()
    assert config["instructions"] == "PROMPT.md"
    executor = config["executor"]
    assert executor["type"] == "omnigent"
    assert executor["config"]["harness"] == "claude"
    assert executor["model"] == "claude-sonnet-4-6"


def test_config_yaml_declares_required_skills():
    skills = _load_config()["skills"]
    for name in REQUIRED_SKILLS:
        assert name in skills, "config.yaml skills: missing %r" % name


def test_config_yaml_policies():
    policies = _load_config()["guardrails"]["policies"]
    spawn = policies["spawn_bounds"]["function"]
    assert policies["spawn_bounds"]["type"] == "function"
    assert spawn["arguments"]["max_dispatches_per_turn"] == 3
    assert "spawn_bounds" in spawn["path"]
    thrash = policies["detect_thrashing"]["function"]
    assert policies["detect_thrashing"]["type"] == "function"
    assert thrash["arguments"]["consecutive_threshold"] == 4
    assert thrash["arguments"]["action"] == "DENY"
    assert "detect_thrashing" in thrash["path"]


def test_bundled_skills_ship_real_copies():
    for name in REQUIRED_SKILLS:
        skill_md = AGENT_SKILLS_DIR / name / "SKILL.md"
        assert skill_md.is_file() and not skill_md.is_symlink(), skill_md
        data = _load_front_matter(skill_md)
        assert data.get("name"), "%s front-matter needs a name" % skill_md
        assert data.get("description"), "%s front-matter needs a description" % skill_md
    bundled_validator = AGENT_SKILLS_DIR / "spec-planner" / "scripts" / "validate_spec_dag.py"
    canonical_validator = CANONICAL_SKILL_DIR / "scripts" / "validate_spec_dag.py"
    assert bundled_validator.read_bytes() == canonical_validator.read_bytes()
    assert (
        (AGENT_SKILLS_DIR / "spec-planner" / "SKILL.md").read_bytes()
        == (CANONICAL_SKILL_DIR / "SKILL.md").read_bytes()
    )


def test_sync_skills_check_passes():
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "sync_skills.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_validator_accepts_project_scaffold_template(tmp_path):
    spec_text = TEMPLATE.read_text(encoding="utf-8")
    spec_path = tmp_path / "feat-template-check.md"
    # The placeholder id FEAT-XXX is not a valid FEAT-<digits> id; the
    # scaffold copy gets a concrete id exactly as a real spec would.
    spec_path.write_text(spec_text.replace("FEAT-XXX", "FEAT-001"), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_prompt_mentions_protocols_and_gate():
    prompt = (AGENT_DIR / "PROMPT.md").read_text(encoding="utf-8")
    for token in ("/spec-plan", "/fanout", "/cross-review", "APPROVE"):
        assert token in prompt, "PROMPT.md must reference %r" % token


def test_spec_planner_skill_mentions_validate_script():
    skill = (CANONICAL_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "validate_spec_dag.py" in skill
    assert "[APPROVE]" in skill
