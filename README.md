# agent-catalog — Tech Lead (Spec-Driven) for Omnigent

An [Omnigent](https://omnigent.ai) **Agents-as-Code** repository. Everything
needed to install and run the `tech-lead` supervisor agent lives in this
repo as plain files: its config, its prompt, its bundled skills, and the
project scaffold its workflow is built around. Install it into any Omnigent
deployment with:

```sh
omni agent add <git-repo-url>
# or pin a branch/path/agent:
omni agent add <git-repo-url>/tree/main@tech-lead
```

`omni agent add` shallow-clones the repo, discovers every agent directory
(the outermost directories containing a `config.yaml` — here
`agents/tech-lead/`), bundles **only that directory**, and installs it under
your account. It appears in the new-session picker on every host you use,
no restart needed.

## How this repo fits Omnigent's architecture

Omnigent agents are described by code, not configured in a UI:

- **Agent bundle** — `agents/tech-lead/config.yaml` is an Omnigent
  `spec_version: 1` agent spec: name, display name, instructions
  (`PROMPT.md`), executor (`type: omnigent`, harness `claude`, model
  `claude-sonnet-4-6`), the skill list, and guardrail policies. Omnigent
  parses and validates this shape (`omnigent.spec.parser` +
  `omnigent.spec.validator`) at install time.
- **Instructions** — `agents/tech-lead/PROMPT.md` is the supervisor's
  system prompt: role invariant (pure supervisor, never edits `src/`)
  plus the four protocols (intake/decomposition, human APPROVE gate,
  TDD dispatch, cross-review & presentation).
- **Bundled skills** — `agents/tech-lead/skills/<dir>/SKILL.md` files are
  skills that ship with the agent and surface as slash commands in its
  sessions. The catalog keeps the canonical `spec-planner` skill at
  repo-root `skills/spec-planner/` and ships a real copy inside the agent
  bundle (see [Skills bundling](#skills-bundling--why-there-are-two-copies)).
- **Policies** — `guardrails.policies` in the agent config wires real
  Omnigent policy factories: `spawn_bounds` (at most **5** worker
  dispatches per supervisor turn) and `detect_thrashing` (**4**
  consecutive erroring tool results, e.g. repeated test failures, escalate
  with `DENY` so an unattended run stops the worker instead of looping).
- **Smart Routing** — tech-lead routes work smartly (free/cheap first) with
  per-harness caps enforced by the prompt (claude_code 3, codex 3,
  opencode 3 on big-pickle, pi 5 on qwen/cheap models, 3 for expensive
  models). It uses `sys_advise_models` if available, else a static tier
  table, always passes explicit `args.model` and `reasoning_effort`, spreads
  across vendors, avoids `gpt-*`/OpenAI models (403 in this workspace), and
- **Model Retry & Failure Policy** — before dispatch, call `sys_list_models` and pick from models actually listed for that worker; on boot/403/429/rate_limit/model-not-found/empty output, retry the same task on the same harness with a different non-gpt-* model (up to 3 distinct models, no reuse). After 3 failures, drop the harness for the session and re-route to another harness (up to 3 attempts). Cancel stuck sessions with `sys_cancel_task`; keep a per-spec attempt ledger and show it on escalation. Real task failures (tests red, scope violation) are not model failures and don't count toward the 3.
  re-routes on 403/429/rate_limit.
- **Workers via worktrees** — at run time the supervisor dispatches coding
  sub-agents (Claude Code, Codex, Pi, …) each in its own git worktree,
  driven by the bundled `fanout` / `cross-review` / `investigate` skills.
- **Project scaffold** — `templates/project-scaffold/` carries the
  `.specs/_template.md` contract template and the `.agent/SYSTEM_RULES.md`
  worker rules that make each dispatch a self-enforcing TDD contract.

## Repository layout

```
agents/tech-lead/                 # the installable agent bundle
  config.yaml                     # spec_version: 1 agent spec
  PROMPT.md                       # supervisor system prompt (4 protocols)
  skills/                         # REAL copies bundled with the agent
    spec-planner/SKILL.md
    spec-planner/scripts/validate_spec_dag.py
    fanout/SKILL.md               # from Omnigent's shipped polly example
    cross-review/SKILL.md
    investigate/SKILL.md
skills/spec-planner/              # canonical skill source (synced into the bundle)
  SKILL.md
  scripts/validate_spec_dag.py
scripts/sync_skills.py            # canonical -> bundle copy, --check gate
templates/project-scaffold/       # drop into your own repo
  .specs/_template.md
  .agent/SYSTEM_RULES.md
tests/test_repo_layout.py         # packaging contract tests
```

## Install

```sh
omni agent add <git-repo-url>
```

Confirm the install; list what a repo offers first with
`omni agent add <git-repo-url> --list`. The `tech-lead` agent shows up in
the new-session picker as **Tech Lead (Spec-Driven)**.

## Initialize your project

Copy the scaffold into the repo `tech-lead` will supervise (it includes
hidden `.specs/` and `.agent/` directories — note the trailing `/.`, NOT
`/*`, because the `/*` glob silently skips dot-directories like `.specs/`
and `.agent/`):

```sh
cp -r templates/project-scaffold/. /path/to/my-repo/
```

This gives your repo:

- `.specs/_template.md` — the spec contract template every feature spec is
  cloned from (front-matter id/phase/status/scope/test_commands + six body
  sections);
- `.agent/SYSTEM_RULES.md` — the rules injected into every worker: `.specs/`
  is the single source of truth, test-first (red then green) is mandatory,
  and edits outside `scope.allowed_paths` or into forbidden/reserved
  anti-scope paths are rejected at review.

Commit those files to your repo so every worktree starts with them.

## Full walkthrough (Omnigent UI)

1. **Start a Tech Lead session.** Open the Omnigent UI, start a new
   session, pick **Tech Lead (Spec-Driven)** in the session picker.
2. **Plan.** Type your goal, e.g.
   `/spec-plan Add a GET /api/session endpoint returning the active session summary`.
   The supervisor loads the `spec-planner` skill, inspects existing
   `.specs/*.md` for ID/dependency consistency, decomposes the goal into
   atomic phase-separated specs, writes each as `.specs/feat-<name>.md`
   with `status: draft`, runs the bundled DAG validator
   (`validate_spec_dag.py`) on `.specs/`, and presents a summary table
   (ID, phase, scope, anti-scope, unit/functional test commands) ending
   with: *Type [APPROVE] to mark status: ready and dispatch, or
   [EDIT <ID>] to refine.*
3. **The human gate.** Nothing dispatches until you type `APPROVE`. The
   supervisor then flips the approved specs to `status: ready`. `[EDIT
   FEAT-XXX]` re-opens one spec instead.
4. **Worktree fan-out.** The supervisor loads `fanout`, creates one git
   worktree per parallel-safe spec (`git worktree add .worktrees/<task>`
   -b tech-lead/<task>`), and dispatches one coding sub-agent per spec via
   `sys_session_send` — capped at 5 dispatches per turn by the
   `spawn_bounds` policy; bigger plans run in waves. Each worker receives
   ONLY the path to its `.specs/feat-*.md` contract, authors unit AND
   functional tests for every Gherkin scenario, confirms they fail (RED),
   implements strictly inside `scope.allowed_paths`, and drives both test
   commands to GREEN. A worker hitting 4 consecutive test-run errors is
   stopped by the `detect_thrashing` policy instead of looping.
5. **Cross-review.** The supervisor loads `cross-review`, snapshots each
   worker's diff, re-runs the deterministic gates, and dispatches a
   reviewer on an ALTERNATE harness (e.g. Codex or Pi for a Claude-built
   diff). The reviewer verifies 100% Gherkin coverage and zero edits to
   `scope.forbidden_paths` or reserved anti-scope; blocking issues loop
   back to the implementer.
6. **Human merge.** The supervisor presents the final branch per spec,
   unit/functional test status with exact commands and counts, and diff
   stats. You review and merge — the supervisor never merges.

## Skills bundling — why there are two copies

`omni agent add` uploads **only the agent directory**
(`agents/tech-lead/`), refuses symlinks from remote repos, and a bundled
skill must be a real file at `<agent_dir>/skills/<dir>/SKILL.md` (the
directory name is the slash command). So the canonical `spec-planner`
skill lives at repo-root `skills/spec-planner/` and an identical real copy
ships at `agents/tech-lead/skills/spec-planner/`. Polly's `fanout`,
`cross-review`, and `investigate` skills are copied into the agent bundle
directly so those names resolve. Keep the two `spec-planner` copies in
lockstep with the sync script:

```sh
python3 scripts/sync_skills.py          # refresh the bundled copy
python3 scripts/sync_skills.py --check  # CI gate: exit 1 if they differ
```

## Tests

```sh
python3 -m pytest -q tests
python3 scripts/sync_skills.py --check
```

The suite pins the packaging contract: every required file exists, the
agent bundle contains no symlinks, `config.yaml` carries the required
fields/skills/policies, the bundled validator accepts the scaffold
template, and the sync check is green.
