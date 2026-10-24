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

# Declared sub-agents, in polly's order. ``sys_session_send``'s ``agent`` enum
# is built from the bundle's ``agents/<dir>/config.yaml`` children, so each
# name here must also be a real worker config.
WORKERS = ("claude_code", "codex", "opencode", "cursor", "hermes", "agy", "pi")
WORKER_HARNESSES = {
    "claude_code": "claude-native",
    "codex": "codex-native",
    "opencode": "opencode-native",
    "cursor": "cursor-native",
    "hermes": "hermes-native",
    "agy": "antigravity-native",
    "pi": "pi",
}


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
    assert executor["config"]["harness"] == "claude-sdk"
    assert executor["model"] == "claude-sonnet-4-6"


def test_config_yaml_orchestrator_flags():
    config = _load_config()
    # spawn registers sys_session_create; async registers sys_read_inbox and
    # friends; cancellable/timers mirror polly's orchestrator surface.
    for flag in ("spawn", "async", "cancellable", "timers"):
        assert config.get(flag) is True, "config.yaml %s must be true" % flag


def test_config_yaml_declares_seven_workers():
    agents = _load_config()["tools"]["agents"]
    assert list(agents) == list(WORKERS)


def test_worker_configs_exist_and_parse():
    for name in WORKERS:
        path = AGENT_DIR / "agents" / name / "config.yaml"
        assert path.is_file() and not path.is_symlink(), path
        worker = _load_yaml(path)
        assert worker["spec_version"] == 1, path
        assert worker["name"] == name, path
        assert isinstance(worker["description"], str) and worker["description"].strip()
        assert worker["executor"]["type"] == "omnigent", path
        assert worker["executor"]["config"]["harness"] == WORKER_HARNESSES[name], path
        prompt = worker["prompt"]
        assert "tech-lead" in prompt, "%s prompt must name its dispatcher" % path
        assert "polly" not in prompt, "%s prompt still names polly" % path
        for token in (".specs/feat-", "Gherkin", "RED", "GREEN", "allowed_paths",
                      "forbidden_paths", "Reserved Anti-Scope", "gh pr create"):
            assert token in prompt, "%s prompt must mention %r" % (path, token)
        blast = worker["guardrails"]["policies"]["blast_radius"]["function"]
        assert blast["arguments"]["gate_pushes"] is False, path


def test_worker_dirs_match_declared_workers():
    dirs = sorted(p.name for p in (AGENT_DIR / "agents").iterdir() if p.is_dir())
    assert dirs == sorted(WORKERS)


def test_config_yaml_declares_required_skills():
    skills = _load_config()["skills"]
    for name in REQUIRED_SKILLS:
        assert name in skills, "config.yaml skills: missing %r" % name


def test_config_yaml_policies():
    guardrails = _load_config()["guardrails"]
    assert guardrails["ask_timeout"] == 86400
    policies = guardrails["policies"]
    spawn = policies["spawn_bounds"]["function"]
    assert policies["spawn_bounds"]["type"] == "function"
    assert spawn["arguments"]["max_dispatches_per_turn"] == 5
    assert spawn["path"] == "omnigent.inner.nessie.policies.spawn_bounds"
    assert "sys_session_create" in spawn["arguments"]["dispatch_tools"]
    blast = policies["blast_radius"]["function"]
    assert blast["path"] == "omnigent.inner.nessie.policies.blast_radius"
    guard = policies["headless_subagent_purpose_guard"]["function"]
    assert guard["path"] == "omnigent.inner.nessie.policies.headless_subagent_purpose_guard"
    assert set(guard["arguments"]["allowed_purposes"]) == {
        "implement", "review", "explore", "search"
    }
    gate = policies["human_gate_implement"]
    assert gate.get("on", gate.get(True)) == ["tool_call"]
    assert gate["function"]["path"] == "omnigent.policies.builtins.cel.cel_policy"
    assert "ASK" in gate["function"]["arguments"]["expression"]
    thrash = policies["detect_thrashing"]["function"]
    assert policies["detect_thrashing"]["type"] == "function"
    assert thrash["arguments"]["consecutive_threshold"] == 4
    assert thrash["arguments"]["action"] == "DENY"
    assert thrash["path"] == "omnigent.policies.builtins.context.detect_thrashing"


def test_smart_routing_config():
    config = _load_config()
    # spawn_bounds increased
    spawn = config["guardrails"]["policies"]["spawn_bounds"]["function"]
    assert spawn["arguments"]["max_dispatches_per_turn"] == 5
    # prompt must mention smart routing
    prompt = (AGENT_DIR / "PROMPT.md").read_text(encoding="utf-8")
    assert "Smart Routing" in prompt
    assert "sys_advise_models" in prompt
    assert "args.model" in prompt
    assert "reasoning_effort" in prompt
    # per-harness caps mentioned
    assert "claude_code" in prompt and "3" in prompt
    assert "codex" in prompt and "3" in prompt
    assert "opencode" in prompt
    assert "pi" in prompt and "5" in prompt
    # gpt forbidden
    assert "gpt-" in prompt or "OpenAI" in prompt


def test_worker_models_not_priciest():
    # Check no worker defaults to opus/priciest
    for name in WORKERS:
        path = AGENT_DIR / "agents" / name / "config.yaml"
        worker = _load_yaml(path)
        exec_cfg = worker.get("executor", {})
        model = exec_cfg.get("model") or exec_cfg.get("config", {}).get("model") or ""
        # Should have explicit model set
        assert model, f"{name} should have a model set"
        # Should not be opus
        assert "opus" not in str(model).lower(), f"{name} should not default to opus"
        # Check reasoning_effort
        reasoning = exec_cfg.get("reasoning_effort") or exec_cfg.get("config", {}).get("reasoning_effort")
        assert reasoning is not None, f"{name} should have reasoning_effort set"


def test_readme_smart_routing():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "5" in readme
    assert "smart routing" in readme.lower() or "Smart Routing" in readme
    assert "per-harness" in readme.lower()


def test_model_retry_failure_policy():
    prompt = (AGENT_DIR / "PROMPT.md").read_text(encoding="utf-8")
    assert "Model Retry & Failure Policy" in prompt
    assert "sys_list_models" in prompt
    assert "403" in prompt and "429" in prompt
    assert "rate_limit" in prompt
    assert "model-not-found" in prompt
    assert "empty output" in prompt
    assert "3 distinct models" in prompt
    assert "never reusing a model that already failed" in prompt
    assert "never any gpt-" in prompt
    assert "mark that harness failed for the session" in prompt
    assert "drop it from the roster" in prompt
    assert "re-route the spec to a different harness" in prompt
    assert "sys_cancel_task" in prompt
    assert "never leave duplicates running" in prompt
    assert "per-spec attempt ledger" in prompt
    assert "show it to the human when escalating" in prompt
    assert "Real task failures" in prompt
    assert "tests red" in prompt
    assert "fix-task on same harness" in prompt
    assert "don't count toward the 3" in prompt
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Model Retry & Failure Policy" in readme


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


def test_root_skills_mirror_every_bundled_skill():
    for name in REQUIRED_SKILLS:
        root = REPO_ROOT / "skills" / name
        bundled = AGENT_SKILLS_DIR / name
        root_files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                            if p.is_file() and "__pycache__" not in p.parts)
        bundled_files = sorted(p.relative_to(bundled).as_posix() for p in bundled.rglob("*")
                               if p.is_file() and "__pycache__" not in p.parts)
        assert root_files and root_files == bundled_files, name
        for rel in root_files:
            assert (root / rel).read_bytes() == (bundled / rel).read_bytes(), "%s/%s" % (name, rel)


def test_sync_skills_covers_every_required_skill():
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import sync_skills  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)
    assert set(sync_skills.SKILL_NAMES) == set(REQUIRED_SKILLS)


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
    for token in ("/spec-plan", "/fanout", "/cross-review", "APPROVE",
                  "sys_session_get_info", "sys_session_send", "sys_read_inbox",
                  "/goal", "depends_on", "validate_spec_dag.py"):
        assert token in prompt, "PROMPT.md must reference %r" % token
    assert "You are tech-lead" in prompt, "PROMPT.md must establish tech-lead's identity"
    assert "you are polly" not in prompt.lower(), "PROMPT.md must not keep polly's identity"


def test_spec_planner_skill_mentions_validate_script():
    skill = (CANONICAL_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "validate_spec_dag.py" in skill
    assert "[APPROVE]" in skill
