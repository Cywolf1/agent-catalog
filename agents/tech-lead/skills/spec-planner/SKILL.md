---
name: spec-planner
description: Decompose a feature request into atomic, dependency-ordered spec contracts under .specs/, separate Phase 1 immediate scope from reserved anti-scope, validate the dependency DAG, and present a roadmap for the human APPROVE gate.
---

# spec-plan — spec-driven decomposition

Invoked as `/spec-plan <prompt>`. Turns the prompt into one or more atomic
spec contracts at `.specs/feat-<name>.md`, each a self-contained TDD hand-off
workers execute in their own Omnigent worktree. The Tech Lead never writes
production code — the spec IS the deliverable of this skill.

## Procedure

1. **Inspect existing specs.** Read every existing `.specs/*.md` in the
   project. Record their IDs (`FEAT-<digits>`), phases, `status`, and
   `depends_on` edges. New specs must not reuse an ID, must not contradict an
   existing spec's scope boundaries, and must list any existing spec they
   depend on in `depends_on`. Pick the next free ID (zero-padded to three
   digits, e.g. `FEAT-007`).
2. **Decompose into atomic specs.** One spec = one independently mergeable
   unit of work with a single owner. Split by feature seam, not by file
   count. Each spec gets:
   - an `Executive Summary & Objective`,
   - an `In-Scope Contract` listing exactly what Phase implements,
   - a `Reserved Anti-Scope` section naming the follow-on phase work that is
     explicitly OUT of bounds for this spec,
   - `Architectural Invariants & Constraints`,
   - `Acceptance Criteria` written as Gherkin scenarios covering every
     stated behavior (happy path, edge, and failure),
   - a `Unit & Functional Verification Matrix` naming the exact unit and
     functional test commands.
3. **Separate Phase 1 from Reserved Anti-Scope.** Phase 1 is the immediate
   scope: the smallest shippable increment. Everything adjacent, speculative,
   or deferred goes into Phase 2/3 Reserved Anti-Scope with the header
   `## Reserved Anti-Scope (DO NOT IMPLEMENT - Reserved for Phase X+1)`.
   Reserved paths also land in the front-matter `scope.forbidden_paths` so
   the reviewer can reject edits there mechanically.
4. **Write each spec file.** Start from the template at
   `templates/project-scaffold/.specs/_template.md`. Write the file to
   `.specs/feat-<name>.md` with front-matter `status: draft`, the concrete
   `id`, `phase`, `depends_on`, `scope.allowed_paths`,
   `scope.forbidden_paths`, and `test_commands.unit` / `test_commands.functional`.
   Fill every body section with real guidance — no placeholders, no TODOs.
5. **Validate the DAG.** Run the validator that ships inside this skill's own
   directory — resolve it relative to this SKILL.md, never from the shell's
   cwd:
   `python3 <skill_dir>/scripts/validate_spec_dag.py .specs/`
   (where `<skill_dir>` is this SKILL.md's parent directory, e.g.
   `agents/tech-lead/skills/spec-planner`). It checks required front-matter
   fields, ID format, dependency resolution, and cycle-freedom. Fix any
   reported error before presenting; the skill does not proceed on a red DAG.
6. **Present the roadmap.** Output a summary table with one row per spec:

   | ID | Phase | Scope (allowed_paths) | Anti-Scope (forbidden_paths) | Unit test command | Functional test command |
   |----|-------|-----------------------|------------------------------|-------------------|-------------------------|

   Then list the dependency order (topological) and which specs are
   parallel-safe (disjoint `allowed_paths`).

## The gate

End every `/spec-plan` run with exactly this closing line, nothing after it:

Type [APPROVE] to mark status: ready and dispatch, or [EDIT <ID>] to refine.

- `[APPROVE]` — flip every presented spec's front-matter `status: draft` to
  `status: ready`, then proceed to Protocol 3 (dispatch via `/fanout`).
- `[EDIT FEAT-XXX]` — re-open only that spec, apply the human's refinement,
  re-run the DAG validator, and re-present the updated table.

NEVER dispatch workers before the human has typed APPROVE. Never flip a
spec to `ready` without the explicit gate — the draft/ready boundary is
the human's decision, not the agent's.

## Notes

- Keep each spec's `scope.allowed_paths` minimal and disjoint across
  parallel-safe specs; that is what keeps a multi-spec fan-out conflict-free.
- Every acceptance criterion in the Gherkin section must be reachable by the
  spec's test commands — the verification matrix maps each scenario group to
  its unit and functional test files.
- Anti-scope is a contract, not a suggestion: workers that edit a
  `forbidden_paths` entry or any reserved anti-scope path fail cross-review.
