# Unified Memory Strategy for Tech Lead Agent

## The Registry is Memory

`.tech-lead/registry.json` tracks **everything**:
- Spec workflow state ✅
- Patterns from completed work ✅
- Lessons learned ✅
- Session history ✅

**No separate memory file needed.**

---

## Structure

```json
{
  "version": "1.0",
  "specs": {
    "FEAT-001": { "status": "ready", "worktree": ".worktrees/feat-001", ... }
  },
  "memory_entries": {
    "patterns": [
      {
        "name": "unity-catalog-endpoint",
        "description": "Adding UC-backed API endpoint",
        "solution": "1. Create route 2. Add test 3. Update spec",
        "verified_pr": "https://github.com/org/repo/pull/123",
        "cost_savings": "~30min re-investigation"
      }
    ],
    "architectural_decisions": [
      {
        "title": "Model Selection: glm-5-3-flash for most work",
        "rationale": "Cost-optimal, 95% success rate on tests",
        "date": "2026-01-15"
      }
    ],
    "lessons_learned": [
      {
        "from_spec": "FEAT-001",
        "issue": "Missing type annotations caused rework",
        "fix": "Peach spec to include type requirement"
      }
    ]
  }
}
```

---

## Usage (Standard Omnigent Tools)

### Read Memory Before Dispatch

```bash
# Agent reads registry to get patterns
REGISTRY=$(sys_os_read(".tech-lead/registry.json"))

# Extract relevant patterns (using shell jq if available)
PATTERNS=$(jq '.memory_entries.patterns[:3]' <<EOF
$REGISTRY
EOF
)

# Inject into sub-agent dispatch
sys_session_send(
  agent="claude_code",
  title="feature-xyz",
  args={
    "input": """
EXISTING PATTERNS:
$PATTERNS

TASK:
{spec_content}
""",
    "purpose": "implement"
  }
)
```

### Store After Success

After human confirms PR merged:

```bash
# Append pattern to registry
sys_os_edit(
  path=".tech-lead/registry.json",
  edits=[{
    "oldText": "\"patterns\": []",
    "newText": "\"patterns\": [{\"name\": \"...\", \"solution\": \"...\"}]"
  }]
)

# Or update spec status
sys_os_edit(
  path=".tech-lead/registry.json",
  edits=[{
    "oldText": "\"status\": \"in-review\"",
    "newText": "\"status\": \"merged\",\"merged_at\": \"2026-01-XX\"}"
  }]
)
```

---

## Cost Breakdown

| Operation | Cost | Tool |
|-----------|------|------|
| Read registry | $0 | `sys_os_read` |
| Write registry | $0 | `sys_os_write` |
| Edit registry | $0 | `sys_os_edit` |
| **Total** | **$0/month** | Just disk space (~50KB max) |

---

## Why This Works

1. **Single source of truth** — One JSON file, no synchronization needed
2. **Omnigent-native** — Uses standard `sys_os_*` tools
3. **Human-readable** — Editable by hand if needed
4. **Version-controllable** — Registry can be in Git (or just .tech-lead/)
5. **Scales cheaply** — 1000 patterns = ~50KB, still instant to load

---

## Migration Path

Current state → Unified:

1. Keep registry.json for spec workflow (already working)
2. Add `memory_entries` section (new)
3. Agents read `memory_entries.patterns` before dispatch
4. Aftermerge, append pattern to `memory_entries.patterns`

**No separate files, no Python code, just JSON editing.**

---

## When to Escalate

If memory grows beyond what file-based JSON can handle:

- **10K+ entries** → Consider Databricks Vector Search (UC table)
- **Team-wide sharing** → Central registry in shared workspace
- **Semantic search needed** → Add embeddings via Databricks model

Until then: **registry.json is sufficient.**
