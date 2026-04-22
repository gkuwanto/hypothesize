# Development Standards

These rules apply to every feature and every task. Violations require
explicit approval before proceeding.

## TDD is strict

- Write the failing test first. Run it. Confirm it fails for the right
  reason. Then implement until it passes.
- Red, green, refactor. No exceptions.
- Do not modify a test to make it pass. If a test is wrong, flag it
  explicitly in the task output and get approval before editing.
- Tests must assert behavior, not implementation detail.

## Budget awareness

- Any code path that makes live LLM calls must respect a budget.
- `MAX_LLM_CALLS_PER_HYPOTHESIS = 200` is the hard cap.
- Log token usage per run.
- Tests must use mocked backends. Live LLM calls are only for integration
  tests explicitly marked `@pytest.mark.live`.

## Scope discipline

- If a task is not in the current feature's `tasks.md`, stop and flag.
- Never add CLI flags, config options, public API surface, or features not
  in the current feature's `requirements.md`.
- If you believe a requirement is wrong, edit `requirements.md` first,
  stop, and request confirmation before writing code.
- Non-goals in `requirements.md` are enforceable. Do not violate them.

## When blocked

- If `requirements.md` doesn't cover a decision, append the question to the
  feature's `design.md` under an "Open Questions" section and stop the task.
- If tests fail three edits in a row without progress, stop and write
  `STUCK.md` at the repo root describing what you tried and why each
  attempt failed.

## Task execution (Kiro-style)

- Tasks in `tasks.md` have a `Status:` field. Update it as you work:
  `pending` → `in_progress` → `done`.
- After each task: run the full test suite, update status, commit with a
  message referencing the task id.
- Each task should, where possible, be executable in a fresh Claude Code
  context given only the steering files, the feature's three spec
  documents, and the previously completed tasks' outputs.

## Review passes

- At the end of each feature, a review pass reads `requirements.md` and
  verifies every acceptance criterion against the code. The reviewer does
  not modify code; it produces a pass/fail report per criterion.

## Commits

- Commit after each completed task. Reference the task id.
- Example: `feat(01): implement task 1.2 — LLM backend protocol and mock`
- Never commit with failing tests.
