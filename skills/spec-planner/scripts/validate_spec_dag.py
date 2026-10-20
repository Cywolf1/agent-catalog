#!/usr/bin/env python3
"""Validate a directory of spec markdown files and their dependency DAG.

Scans ``*.md`` files (non-recursive) under a specs directory, parses a small
YAML front-matter subset by hand (no PyYAML dependency), checks the required
fields and field values, verifies every ``depends_on`` reference resolves, and
detects cycles in the resulting dependency graph.

Usage:
    python3 validate_spec_dag.py <specs_dir> [--json]

Exit codes:
    0  all specs valid and the dependency graph is acyclic
    1  one or more validation errors were found
    2  usage error (wrong number of arguments)
"""

import json
import re
import sys
from pathlib import Path

REQUIRED_SCALARS = (
    "id",
    "phase",
    "status",
    "test_commands.unit",
    "test_commands.functional",
)
REQUIRED_LIST_PATHS = ("scope.allowed_paths", "scope.forbidden_paths")

VALID_STATUSES = {"draft", "ready", "in_progress", "review", "complete"}
ID_RE = re.compile(r"^FEAT-\d{3,}$")
INT_RE = re.compile(r"^-?\d+$")


def strip_comment(value: str) -> str:
    """Remove a trailing `` # comment`` from a scalar, ignoring quoted spans."""
    quote = None  # type: str | None
    for i, ch in enumerate(value):
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "#" and i > 0 and value[i - 1] in (" ", "\t"):
            return value[:i].rstrip()
    return value.rstrip()


def parse_scalar(raw: str) -> object:
    """Convert a raw scalar string into a bool/int/str, stripping quotes."""
    text = strip_comment(raw).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    if INT_RE.match(text):
        return int(text)
    if text == "[]":
        return []
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part) for part in inner.split(",")]
    return text


def parse_front_matter(text):
    # type: (str) -> tuple[dict, str]
    """Parse a YAML front-matter subset from ``text``.

    Returns ``(data, error)`` where ``error`` is a message when the front
    matter is missing or malformed.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "missing YAML front-matter"
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return {}, "unterminated YAML front-matter"

    try:
        data = _parse_body(lines[1:end])
    except ValueError as exc:
        return {}, str(exc)
    return data, ""


def _parse_body(body_lines):
    # type: (list) -> dict
    """Parse front-matter body lines into a nested dict, handling block lists.

    Supports nested mappings by 2-space (or any multiple of 2) indentation,
    block lists (``- item``, either indented under the key or at the key's own
    indent), and inline flow lists. Raises ``ValueError`` on malformed input.
    """
    data = {}
    contexts = {-2: data}  # type: dict
    list_owners = {}  # type: dict

    for raw_line in body_lines:
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()

        # Allow a trailing comment-only line.
        if stripped.startswith("#"):
            continue

        if indent % 2 != 0:
            raise ValueError(
                f"indentation must be a multiple of 2 spaces: {stripped!r}"
            )

        if stripped.startswith("- "):
            owner = None
            best = None
            for ind, candidate in list_owners.items():
                if ind <= indent and (best is None or ind > best):
                    best = ind
                    owner = candidate
            if owner is None:
                raise ValueError(
                    f"list item without a parent key: {stripped!r}"
                )
            container, key = owner
            if isinstance(container[key], dict):
                if container[key]:
                    raise ValueError(
                        f"list item under mapping key {key!r}: {stripped!r}"
                    )
                container[key] = []
            container[key].append(parse_scalar(stripped[2:]))
            continue

        if ":" not in stripped:
            raise ValueError(f"malformed line: {stripped!r}")

        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()

        parent = data
        best = -2
        for ind, ctx in contexts.items():
            if ind < indent and ind > best:
                best = ind
                parent = ctx

        if value == "":
            child = {}
            parent[key] = child
            contexts[indent] = child
            list_owners[indent] = (parent, key)
        else:
            parent[key] = parse_scalar(value)
            contexts.pop(indent, None)
            list_owners.pop(indent, None)

    return data


def get_path(data, dotted):
    # type: (dict, str) -> object
    """Fetch a nested value by dotted path, or ``None`` when absent."""
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def validate_spec(path):
    # type: (Path) -> tuple
    """Validate one spec file. Returns ``(data, errors)``; data is None on parse failure."""
    text = path.read_text(encoding="utf-8")
    data, err = parse_front_matter(text)
    if err:
        return None, [err]

    errors = []  # type: list

    present = set()  # type: set
    for dotted in REQUIRED_SCALARS:
        value = get_path(data, dotted)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            errors.append(f"missing or empty required field '{dotted}'")
        else:
            present.add(dotted)

    allowed = get_path(data, REQUIRED_LIST_PATHS[0])
    if not isinstance(allowed, list) or len(allowed) == 0:
        errors.append(f"{REQUIRED_LIST_PATHS[0]} must be a non-empty list")

    forbidden = get_path(data, REQUIRED_LIST_PATHS[1])
    if not isinstance(forbidden, list):
        errors.append(f"{REQUIRED_LIST_PATHS[1]} must be a list")

    spec_id = data.get("id")
    if "id" in present and isinstance(spec_id, str) and not ID_RE.match(spec_id):
        errors.append(f"invalid id '{spec_id}' (expected FEAT-<digits>)")

    phase = data.get("phase")
    if "phase" in present and (
        not isinstance(phase, int) or isinstance(phase, bool) or phase < 1
    ):
        errors.append(f"phase must be a positive integer, got {phase!r}")

    status = data.get("status")
    if "status" in present and status not in VALID_STATUSES:
        errors.append(f"invalid status '{status}'")

    depends = data.get("depends_on", [])
    if not isinstance(depends, list):
        errors.append("depends_on must be a list")

    return data, errors


def find_cycle(graph):
    # type: (dict) -> list
    """Return a cycle path as a list of ids, or None when acyclic."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in graph}
    stack = []  # type: list

    def visit(node):
        # type: (str) -> list
        color[node] = GRAY
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                start = stack.index(dep)
                return stack[start:] + [dep]
            if color[dep] == WHITE:
                found = visit(dep)
                if found is not None:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for node in graph:
        if color[node] == WHITE:
            found = visit(node)
            if found is not None:
                return found
    return None


def main():
    # type: () -> int
    """Entry point. Returns the process exit code."""
    args = sys.argv[1:]
    json_mode = "--json" in args
    positional = [a for a in args if a != "--json"]

    if len(positional) != 1:
        print(
            "usage: validate_spec_dag.py <specs_dir> [--json]",
            file=sys.stderr,
        )
        return 2

    specs_dir = Path(positional[0])
    errors = []  # type: list

    if not specs_dir.is_dir():
        errors.append((str(specs_dir), "specs directory does not exist"))
        return _report(json_mode, [], errors)

    files = sorted(
        p for p in specs_dir.glob("*.md") if not p.name.startswith("_")
    )

    parsed = {}  # type: dict
    file_for_id = {}  # type: dict
    graph = {}  # type: dict
    ids = []  # type: list

    for path in files:
        data, spec_errors = validate_spec(path)
        if data is None:
            errors.extend((path.name, e) for e in spec_errors)
            continue

        spec_id = data.get("id")
        if isinstance(spec_id, str) and ID_RE.match(spec_id):
            if spec_id in parsed:
                errors.append(
                    (path.name, f"duplicate id '{spec_id}'")
                )
            else:
                parsed[spec_id] = data
                file_for_id[spec_id] = path.name
                ids.append(spec_id)

        for e in spec_errors:
            errors.append((path.name, e))

    # Resolve dependencies (only among successfully parsed, valid-id specs).
    for spec_id, data in parsed.items():
        depends = data.get("depends_on", [])
        if not isinstance(depends, list):
            continue
        resolved = []  # type: list
        for dep in depends:
            if not isinstance(dep, str):
                errors.append((file_for_id[spec_id], f"invalid dependency {dep!r}"))
                continue
            if dep == spec_id:
                errors.append(
                    (file_for_id[spec_id], f"spec depends on itself ('{spec_id}')")
                )
                resolved.append(dep)
                continue
            if dep not in parsed:
                errors.append(
                    (file_for_id[spec_id], f"unknown dependency '{dep}'")
                )
                continue
            resolved.append(dep)
        graph[spec_id] = resolved

    cycle = find_cycle(graph)
    if cycle is not None:
        errors.append(("<dag>", "dependency cycle: " + " -> ".join(cycle)))

    return _report(json_mode, ids, errors)


def _report(json_mode, ids, errors):
    # type: (bool, list, list) -> int
    """Print results in the requested format and return the exit code."""
    if json_mode:
        payload = {
            "ok": not errors,
            "specs": ids,
            "errors": [{"file": f, "message": m} for f, m in errors],
        }
        print(json.dumps(payload))
        return 0 if not errors else 1

    if errors:
        for fname, message in errors:
            print(f"[ERROR] {fname}: {message}", file=sys.stderr)
        print(f"FAILED: {len(errors)} error(s).", file=sys.stderr)
        return 1

    print(f"OK: {len(ids)} spec(s) validated, dependency graph is acyclic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
