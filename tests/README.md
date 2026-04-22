# Test Harness

Reference notes on how the test suite is wired together. For what to
build, see `.spec/features/`.

## How to run tests

- `pytest` — full suite, parallel, skipping `live` tests (per `pyproject.toml`
  defaults plus the commands below).
- `pytest -n auto` — run in parallel across available cores.
- `pytest tests/core/` — scope to the `core/` layer.
- `pytest -x -q` — stop on first failure, quiet.
- `pytest -m live` — run only tests that hit a real LLM (requires API keys).
- `pytest --cov=src/hypothesize` — with coverage.

## Fixtures available (from `tests/conftest.py`)

- `mock_llm` — empty-scripted `MockBackend`; use when the test does not
  expect LLM calls, or construct `MockBackend(responses=[...])` directly.
- `fresh_budget` — `Budget(max_llm_calls=200)`; parameterize to override.
- `tight_budget` — `Budget(max_llm_calls=3)` for exhaustion paths.
- `sample_hypothesis` — representative `Hypothesis` for generic tests.
- `sample_context` — a list of short context strings.
- `record_calls` — wraps `mock_llm` with `assert_call_count(n)` and
  `assert_called_with_substring(s)` helpers.

## Factories available (from `tests/_fixtures/factories.py`)

- `make_hypothesis(text, context_refs)`
- `make_dimension(name, description, examples)`
- `make_candidate(input_data, dimension, rationale)`
- `make_verdict(passed, reason, judge_type)`
- `make_budget(max_llm_calls)`

Use factories in place of inline object construction so defaults stay in one
place.

## Custom assertions (from `tests/_fixtures/assertions.py`)

- `assert_budget_respected(budget, max_expected)`
- `assert_call_pattern(mock_backend, expected_substrings)`

## Markers

- `@pytest.mark.live` — test makes real LLM API calls. Skipped by default.
- `@pytest.mark.slow` — test takes more than 5 seconds.

Unregistered markers fail the suite (`--strict-markers`). Register new
markers in `pyproject.toml` under `[tool.pytest.ini_options].markers`.

## Parallel execution

CI and the local PostToolUse hook both use `pytest -n auto`. Tests must be
isolated: no shared global state, no writes to shared filesystem paths, no
reliance on execution order. Fixtures are function-scoped by default;
upgrade to session scope only if the fixture is genuinely read-only.

## Adding new tests

- Mirror the `src/` layout: `tests/core/test_foo.py` for `src/hypothesize/core/foo.py`.
- Use factories for default objects; override only what the test asserts on.
- Use `mock_llm` (or a hand-built `MockBackend`) rather than real backends.
  Live tests are the only exception and must be marked `@pytest.mark.live`.
- Mark long tests `@pytest.mark.slow` so they can be deselected when
  iterating.
- Keep test functions under ~15 lines where possible; factor setup into
  fixtures or factories rather than growing the test body.
