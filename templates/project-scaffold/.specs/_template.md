---
id: FEAT-XXX
title: "Feature Title"
phase: 1
status: draft # [draft, ready, in_progress, review, complete]
depends_on: []
scope:
  allowed_paths:
    - "src/..."
    - "tests/..."
  forbidden_paths:
    - "src/reserved_future_module/**"
test_commands:
  unit: "pytest tests/unit/test_feature.py -v"
  functional: "pytest tests/functional/test_feature_flow.py -v"
---

## Executive Summary & Objective

One paragraph: what ships in this phase and why it is the smallest
shippable increment. State the user-visible outcome and the measurable
definition of done. Example: "Expose a `/api/session` GET endpoint that
returns the active session summary (id, title, status) as JSON. Done
means an authenticated client can call it and the unit + functional suites
below pass green."

## In-Scope Contract (Phase X)

Everything Phase X implements, expressed as contracts, not vibes. One
bullet per behavior. Each bullet must be testable by the commands in the
front-matter and covered by at least one Gherkin scenario below. Example:

- The endpoint accepts a valid bearer token and returns 200 with
  `{id, title, status}`.
- An unknown session id returns 404 with an RFC7807 `type`/`title` body.
- Empty or missing auth returns 401 without leaking whether the session
  exists.

## Reserved Anti-Scope (DO NOT IMPLEMENT - Reserved for Phase X+1)

Named follow-on work that is explicitly OUT of bounds here. Editing any
of it — even "while we're in the file" — fails cross-review. Every path
listed here must also appear in front-matter `scope.forbidden_paths`.
Example:

- Pagination and filtering of the session list — Reserved for Phase 2
  (`src/reserved_future_module/**`).
- Webhook emission on status change — Reserved for Phase 2.
- Admin-only destructive actions — Reserved for Phase 3.

## Architectural Invariants & Constraints

Non-negotiable properties the implementation must preserve. Example:

- Handlers stay thin: validation in `src/validation/`, persistence behind
  the repository interface; no SQL in route modules.
- No new runtime dependencies; stdlib or already-declared packages only.
- All I/O funnels through the existing clock and id providers so tests
  stay deterministic.
- Public function signatures in `scope.allowed_paths` are frozen — extend
  by addition, never by breaking change.

## Acceptance Criteria (Gherkin Scenarios)

Every scenario maps to at least one test in the verification matrix; the
worker's test files must cover all of them before implementation starts.

```gherkin
Feature: Session summary endpoint
  Scenario: Happy path returns the summary
    Given a session "auth-refactor" with status "running"
    And a valid bearer token
    When the client requests GET /api/session/sess_123
    Then the response status is 200
    And the response body contains id "sess_123", title "auth-refactor", status "running"

  Scenario: Unknown session id
    Given a valid bearer token
    When the client requests GET /api/session/does-not-exist
    Then the response status is 404
    And the response body has type "about:blank" and title "Session not found"

  Scenario: Missing authentication
    Given no authorization header
    When the client requests GET /api/session/sess_123
    Then the response status is 401
```

## Unit & Functional Verification Matrix

Maps each scenario group to its exact test file and command. The unit
layer tests the logic in isolation (mocked I/O); the functional layer
exercises the real route + store path end to end. The worker authors BOTH
files, runs both commands to confirm RED, implements, then drives both to
GREEN (exit 0).

| Scenario group | Unit test file | Unit command | Functional test file | Functional command |
|----------------|----------------|--------------|----------------------|--------------------|
| Happy path | `tests/unit/test_feature.py::test_session_summary_ok` | `pytest tests/unit/test_feature.py -v` | `tests/functional/test_feature_flow.py::test_get_session_summary` | `pytest tests/functional/test_feature_flow.py -v` |
| Unknown id → 404 | `tests/unit/test_feature.py::test_session_summary_unknown_404` | `pytest tests/unit/test_feature.py -v` | `tests/functional/test_feature_flow.py::test_get_session_unknown_404` | `pytest tests/functional/test_feature_flow.py -v` |
| Missing auth → 401 | `tests/unit/test_feature.py::test_session_summary_unauthorized` | `pytest tests/unit/test_feature.py -v` | `tests/functional/test_feature_flow.py::test_get_session_unauthorized` | `pytest tests/functional/test_feature_flow.py -v` |
