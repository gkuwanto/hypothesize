# Claude Code Operating Manual

## Read this first

Before doing anything, read in order:

1. `.spec/steering/product.md` — what we're building and why
2. `.spec/steering/structure.md` — file layout rules
3. `.spec/steering/tech.md` — stack and dependency rules
4. `.spec/steering/standards.md` — TDD, budget, scope, and review rules

These files apply to every session. They are not repeated here.

## Current phase

Bootstrap complete. Next: execute Feature 01.

## Working on a feature

Before starting work on any task:

1. Read the feature's `requirements.md`, `design.md`, and `tasks.md`
2. Locate the task assigned to you in `tasks.md`
3. Verify its `Depends:` tasks are marked `done`
4. Follow TDD: failing test first, then implementation

After completing a task:

1. Run the full test suite
2. Update the task's `Status:` to `done`
3. Commit with a message referencing the task id (e.g., `feat(01): task 1.2`)

## When to ask, not act

- If `requirements.md` doesn't cover a decision → append to `design.md`
  under "Open Questions", stop, and await human input
- If a requirement seems wrong → propose an edit to `requirements.md`,
  stop, and await approval
- If tests fail three times in a row → write `STUCK.md`, stop

## Running tests

- `pytest tests/` — full suite
- `pytest tests/core/` — just core layer
- `pytest -x -q` — stop on first failure, quiet
- `pytest --cov=src/hypothesize` — with coverage

The PostToolUse hook runs `pytest -x -q --timeout=30` after every file edit.
If it reports failures, address them before moving on.

## Never do

- Modify tests to make them pass
- Add dependencies not listed in `tech.md`
- Implement features not in the current feature's `requirements.md`
- Mark a task `done` without running the full test suite
- Commit with failing tests
