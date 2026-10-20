"""Tests for the spec DAG validator script.

The validator is a standalone, stdlib-only script invoked via subprocess so
that it is exercised exactly the way the skill calls it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "spec-planner"
    / "scripts"
    / "validate_spec_dag.py"
)


def run_validator(specs_dir: Path, *extra: str) -> subprocess.CompletedProcess:
    """Invoke the validator script against ``specs_dir``."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(specs_dir), *extra],
        capture_output=True,
        text=True,
    )


SPEC_TEMPLATE = """---
id: {id}
phase: {phase}
status: {status}
test_commands:
  unit: "pytest tests/unit"
  functional: "pytest tests/functional"
scope:
  allowed_paths:
    - src/{id_lower}
  forbidden_paths: []
{depends_block}
---
# {id}
"""


def write_spec(
    directory: Path,
    spec_id: str,
    *,
    phase: str = "1",
    status: str = "draft",
    depends_on: list[str] | None = None,
    name: str | None = None,
) -> Path:
    """Write a valid spec file named ``{spec_id}.md`` (unless overridden)."""
    depends_block = ""
    if depends_on is not None:
        deps = ", ".join(f'"{d}"' for d in depends_on)
        depends_block = f"depends_on: [{deps}]\n"
    content = SPEC_TEMPLATE.format(
        id=spec_id,
        phase=phase,
        status=status,
        id_lower=spec_id.lower().replace("-", "_"),
        depends_block=depends_block,
    )
    path = directory / (name or f"{spec_id}.md")
    path.write_text(content)
    return path


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_valid_single_spec(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001")
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "OK: 1 spec(s) validated, dependency graph is acyclic."
    )
    assert result.stderr == ""


def test_valid_multi_spec_chain(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001")
    write_spec(tmp_path, "FEAT-002", depends_on=["FEAT-001"])
    write_spec(tmp_path, "FEAT-003", depends_on=["FEAT-002"])
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "3 spec(s) validated" in result.stdout


def test_template_file_is_skipped(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001")
    # A template with deliberately invalid content must be ignored.
    (tmp_path / "_template.md").write_text("---\nid: not-a-feature\n---\n")
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "1 spec(s) validated" in result.stdout


# ---------------------------------------------------------------------------
# Missing / empty required fields
# ---------------------------------------------------------------------------


def _valid_body() -> str:
    return (
        "id: FEAT-001\n"
        "phase: 1\n"
        "status: draft\n"
        "test_commands:\n"
        '  unit: "pytest tests/unit"\n'
        '  functional: "pytest tests/functional"\n'
        "scope:\n"
        "  allowed_paths:\n"
        "    - src/foo\n"
        "  forbidden_paths: []\n"
    )


@pytest.mark.parametrize(
    "drop_line",
    [
        "id: FEAT-001\n",
        "phase: 1\n",
        "status: draft\n",
        '  unit: "pytest tests/unit"\n',
        '  functional: "pytest tests/functional"\n',
        "    - src/foo\n",
    ],
)
def test_missing_required_field(tmp_path: Path, drop_line: str) -> None:
    body = _valid_body().replace(drop_line, "")
    (tmp_path / "FEAT-001.md").write_text(f"---\n{body}---\n")
    result = run_validator(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "[ERROR]" in result.stderr
    assert "FAILED: 1 error(s)." in result.stderr


def test_empty_required_string_is_error(tmp_path: Path) -> None:
    body = _valid_body().replace("id: FEAT-001\n", 'id: ""\n')
    (tmp_path / "FEAT-001.md").write_text(f"---\n{body}---\n")
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "id" in result.stderr


def test_empty_allowed_paths_is_error(tmp_path: Path) -> None:
    body = _valid_body().replace(
        "  allowed_paths:\n    - src/foo\n", "  allowed_paths: []\n"
    )
    (tmp_path / "FEAT-001.md").write_text(f"---\n{body}---\n")
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "allowed_paths" in result.stderr


# ---------------------------------------------------------------------------
# Field-value validation
# ---------------------------------------------------------------------------


def test_bad_status(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001", status="banana")
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "status" in result.stderr


def test_bad_id(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-1")
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "id" in result.stderr


def test_bad_phase_non_positive(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001", phase="0")
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "phase" in result.stderr


def test_duplicate_id(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001", name="a.md")
    write_spec(tmp_path, "FEAT-001", name="b.md")
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "duplicate" in result.stderr.lower()


def test_unknown_dependency(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001", depends_on=["FEAT-999"])
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "FEAT-999" in result.stderr


def test_self_dependency(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001", depends_on=["FEAT-001"])
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "self" in result.stderr.lower() or "cycle" in result.stderr.lower()


def test_two_node_cycle(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001", depends_on=["FEAT-002"])
    write_spec(tmp_path, "FEAT-002", depends_on=["FEAT-001"])
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "FEAT-001" in result.stderr and "FEAT-002" in result.stderr
    assert "->" in result.stderr


def test_three_node_cycle(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001", depends_on=["FEAT-002"])
    write_spec(tmp_path, "FEAT-002", depends_on=["FEAT-003"])
    write_spec(tmp_path, "FEAT-003", depends_on=["FEAT-001"])
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "->" in result.stderr


# ---------------------------------------------------------------------------
# Front-matter / directory handling
# ---------------------------------------------------------------------------


def test_missing_front_matter(tmp_path: Path) -> None:
    (tmp_path / "FEAT-001.md").write_text("# Just a heading\nNo front matter.\n")
    result = run_validator(tmp_path)
    assert result.returncode == 1
    assert "front" in result.stderr.lower()


def test_unterminated_front_matter(tmp_path: Path) -> None:
    (tmp_path / "FEAT-001.md").write_text("---\nid: FEAT-001\nphase: 1\n")
    result = run_validator(tmp_path)
    assert result.returncode == 1


def test_nonexistent_directory(tmp_path: Path) -> None:
    result = run_validator(tmp_path / "does-not-exist")
    assert result.returncode == 1
    assert "[ERROR]" in result.stderr


# ---------------------------------------------------------------------------
# Inline comment / quote handling
# ---------------------------------------------------------------------------


def test_inline_comment_stripping(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001", status="draft")
    path = tmp_path / "FEAT-001.md"
    text = path.read_text().replace(
        "status: draft", "status: draft # [draft, ready]"
    )
    path.write_text(text)
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stderr


def test_quoted_value_preserves_comment_like_text(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001")
    path = tmp_path / "FEAT-001.md"
    text = path.read_text().replace(
        'unit: "pytest tests/unit"', 'unit: "pytest # not a comment"'
    )
    path.write_text(text)
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# --json output & usage errors
# ---------------------------------------------------------------------------


def test_json_output_success(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001")
    write_spec(tmp_path, "FEAT-002", depends_on=["FEAT-001"])
    result = run_validator(tmp_path, "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["specs"] == ["FEAT-001", "FEAT-002"]
    assert payload["errors"] == []


def test_json_output_failure(tmp_path: Path) -> None:
    write_spec(tmp_path, "FEAT-001", status="banana")
    result = run_validator(tmp_path, "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"]


def test_usage_error_no_args() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_usage_error_too_many_args(tmp_path: Path) -> None:
    result = run_validator(tmp_path, "extra-arg")
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Indentation robustness
# ---------------------------------------------------------------------------


def test_same_indent_list_items_parse(tmp_path: Path) -> None:
    """A list item may sit at the same indent as its parent key."""
    (tmp_path / "FEAT-001.md").write_text(
        "---\n"
        "id: FEAT-001\n"
        "phase: 1\n"
        "status: draft\n"
        "test_commands:\n"
        '  unit: "pytest tests/unit"\n'
        '  functional: "pytest tests/functional"\n'
        "scope:\n"
        "  allowed_paths:\n"
        '  - "src/x"\n'
        "  forbidden_paths: []\n"
        "---\n"
    )
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "1 spec(s) validated" in result.stdout


def test_four_space_nesting_parses(tmp_path: Path) -> None:
    """Nested mappings indented by four spaces parse correctly."""
    (tmp_path / "FEAT-001.md").write_text(
        "---\n"
        "id: FEAT-001\n"
        "phase: 1\n"
        "status: draft\n"
        "test_commands:\n"
        '    unit: "pytest tests/unit"\n'
        '    functional: "pytest tests/functional"\n'
        "scope:\n"
        "    allowed_paths:\n"
        '        - "src/x"\n'
        "    forbidden_paths: []\n"
        "---\n"
    )
    result = run_validator(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "1 spec(s) validated" in result.stdout


def test_ragged_indentation_errors_not_silently(tmp_path: Path) -> None:
    """A nested key at an ambiguous indent must error, never misparse silently."""
    (tmp_path / "FEAT-001.md").write_text(
        "---\n"
        "id: FEAT-001\n"
        "phase: 1\n"
        "status: draft\n"
        "test_commands:\n"
        '  unit: "pytest tests/unit"\n'
        '   functional: "pytest tests/functional"\n'
        "scope:\n"
        "  allowed_paths: [src/x]\n"
        "  forbidden_paths: []\n"
        "---\n"
    )
    result = run_validator(tmp_path)
    assert result.returncode == 1, result.stdout
    assert "[ERROR]" in result.stderr
    assert "FAILED:" in result.stderr


def test_script_imports_only_allowed_stdlib_modules() -> None:
    """The validator must import only sys, pathlib, re, and json."""
    source = SCRIPT.read_text()
    imported: set[str] = set()
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            imported.add(stripped[len("import "):].split()[0].split(".")[0])
        elif stripped.startswith("from "):
            imported.add(stripped[len("from "):].split()[0].split(".")[0])
    assert imported == {"sys", "pathlib", "re", "json"}, imported
