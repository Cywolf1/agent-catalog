# Unified Memory System (Cost: $0)

## Overview

`.tech-lead/registry.json` serves as **both** workflow state AND cross-session memory. No separate storage needed.

## Memory Structure

```json
{
  "specs": { "FEAT-001": { ... } },
  "memory_entries": {
    "patterns": [
      {
        "name": "unity-catalog-integration",
        "solution": "Add uc_volume mount + Databricks synthetic auth for testing",
        "tags": ["unity-catalog", "testing", "databricks"],
        "cost_savings": "Avoided $8 re-investigation",
        "validated_build": "abc123",
        "created": "2026-01-XX"
      }
    ],
    "architectural_decisions": [
      {
        "decision": "Use opencode/big-pickle for all exploring",
        "rationale": "Zero cost, 90% accuracy for read-only tasks",
        "reverted": false
      }
    ],
    "lessons_learned": [
      {
        "scenario": "claude_code failed with 403 on model X",
        "solution": "Fallback to databricks-glm-5-3-flash via codex",
        "timestamp": "2026-01-XX"
      }
    ]
  }
}
```

## Usage Patterns

### Before Dispatch (Memory Injection)

Read registry, extract relevant patterns, inject into prompt:

```python
# tech-lead does this:
REGISTRY = sys_os_read(".tech-lead/registry.json")
existing_patterns = json.loads(REGISTRY)["memory_entries"]["patterns"]

# Inject into dispatch prompt:
args.input = f"""
### CONTEXT FROM EXISTING PATTERNS
{existing_patterns}

### YOUR TASK
{original_task}
"""
```

### After Task Success (Store Pattern)

After PR passes cross-review and merges (human confirms):

```python
# tech-lead does this:
REGISTRY = sys_os_edit(
    path=".tech-lead/registry.json",
    edits=[{
        "oldText": '"patterns": []',
        "newText": f'"patterns": [{json.dumps(pattern)}]'
    }]
)
```

Example pattern to store:
```json
{
  "name": "unity-catalog-integration",
  "solution": "Created uc_volume mount, added Databricks synthetic auth for testing, configured ~\/.databricks\/config for local dev",
  "affected_paths": ["src/unity_catalog/", "tests/integration/"],
  "test_command": "python -m pytest tests/integration/test_uc_volume.py",
  "cost_savings": "~$5 avoided re-investigation",
  "tags": ["unity-catalog", "databricks", "testing"],
  "validated_in": "PR #123",
  "created": "2026-01-XX"
}
```

### Search Patterns (Simple Grep)

```bash
# tech-lead can find relevant patterns:
cat .tech-lead/registry.json | grep -A5 "unity-catalog"

# Or use Python (if registered tool):
python3 -c "import json; r=json.load(open('.tech-lead/registry.json')); print([p for p in r['memory_entries']['patterns'] if 'unity' in str(p)])"
```

## Cost Breakdown

| Component | Cost |
|-----------|------|
| JSON file (10KB) | $0 (disk) |
| sys_os_read/write | $0 (built-in tool) |
| **Total** | **$0/month** |

## Why This Works

1. **Same toolset** - Uses `sys_os_read` / `sys_os_edit`, already available
2. **No infrastructure** - Just a file, no databases or APIs
3. **Atomic updates** - `sys_os_edit` ensures no corrupt state
4. **Human-readable** - Easy to inspect and debug

## Best Practices

- **Keep it lean** - Max ~50 pattern entries (~100KB file)
- **Tag aggressively** - `["unity-catalog", "testing"]` for easy grep
- **Validate before storing** - Only add patterns from merged PRs
- **Prune rarely** - Manual cleanup if file grows too large

## Integration Points

Where to inject memory in the workflow:

1. **/spec-plan** - Before authoring specs, read patterns to avoid past mistakes
2. **/fanout dispatch** - Include relevant patterns in `args.input`
3. **/cross-review** - Reviewer checks if pattern standards were followed
4. **Post-merge** - Extract new pattern from completed spec, append to registry
