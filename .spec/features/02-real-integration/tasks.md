# Tasks: Feature 02 — Real LLM Integration and System Adapters

## Task 2.1: JSON extractor utility

- Status: done
- Depends: none
- Files: `src/hypothesize/core/json_extract.py`,
  `tests/core/test_json_extract.py`,
  `tests/_fixtures/smoke_responses/decompose_haiku_fenced.txt`
- Acceptance:
  - `parse_json_response(raw: str) -> Any | None` implements the
    five-step ladder in `design.md` (clean parse → fence-strip →
    brace-slice → trailing-comma repair → None).
  - ≥ 25 unit tests. The corpus must include, as named cases, each
    of the following — these exercise the state-machine-sensitive
    and framing-sensitive failure modes the algorithm is designed
    to handle:
    - clean JSON object
    - ` ```json ` fenced object
    - bare ` ``` ` fenced object (no language tag)
    - alternate-language-tag fence (e.g. ` ```python `,
      ` ```javascript `)
    - leading prose before the JSON
      ("Sure, here's your JSON: { ... }")
    - trailing prose after the JSON
      ("{ ... }. Let me know if...")
    - both fences and leading prose
      ("Here's the result:\n\\`\\`\\`json\n{...}\n\\`\\`\\`")
    - valid JSON array at root (step 4 must handle `[` as well as
      `{`)
    - trailing comma in object
    - trailing comma in array
    - string value containing an escaped quote character
      (`{"msg": "she said \"hi\""}`) — must not confuse the
      state-machine scanner
    - string value containing a literal `{` or `}` inside the
      string (`{"template": "use {name}"}`) — brackets inside
      strings must not be counted
    - string value ending in `,]` or `,}` as literal characters
      (`{"note": "see list,]"}`) — trailing-comma repair must not
      touch commas inside strings
    - nested JSON-in-string (a string value that itself is a JSON
      blob: `{"payload": "{\"x\": 1}"}`) — scanner must treat the
      inner braces as part of the string
    - double-fenced input (fence inside fence)
    - embedded code-fence inside a string value
    - `null` / None / empty-string input (returns None)
    - whitespace-only input (returns None)
    - malformed JSON — mismatched brackets (returns None)
    - unquoted keys (returns None — do not mask)
    - single-quoted strings (returns None — do not mask)
  - One test loads the saved first-smoke response fixture and
    asserts parse to a dict with `dimensions` of length 3-7.
  - Import is free of side effects.

## Task 2.2: Apply JSON extractor at four parse sites in core

- Status: done
- Depends: 2.1
- Files: `src/hypothesize/core/decompose.py`,
  `src/hypothesize/core/generate.py`,
  `src/hypothesize/core/judge.py`, plus regression additions in
  `tests/core/test_decompose.py`, `tests/core/test_generate.py`,
  `tests/core/test_judge.py`.
- Acceptance:
  - `decompose.py`, `generate.py`, and both sites in `judge.py`
    (`RubricJudge.judge`, `PairwiseJudge.judge_pair`) use
    `parse_json_response` in place of direct `json.loads`.
  - Public signatures unchanged. No new kwargs.
  - Every Feature 01 test passes unmodified.
  - One new test per site feeds a fenced variant of an existing
    fixture and asserts the same behavior as the clean variant.
  - `ruff check` clean.

## Task 2.3: AnthropicConfig and AnthropicBackend

- Status: done
- Depends: none (can run in parallel with 2.1/2.2)
- Files: `src/hypothesize/llm/__init__.py`,
  `src/hypothesize/llm/config.py`,
  `src/hypothesize/llm/anthropic.py`,
  `src/hypothesize/llm/errors.py`,
  `src/hypothesize/llm/prompts.py` (empty module with
  `rewrite_prompt_messages` stub for 2.7),
  `tests/llm/__init__.py`,
  `tests/llm/test_anthropic_backend.py`.
- Acceptance:
  - `AnthropicConfig` and `RunnerCallLog` per design.md, frozen.
  - `AnthropicBackend.__init__(config, client=None, on_call=None)`
    accepts injectable `AsyncAnthropic` for test isolation.
  - `complete` translates `{role, content}` messages into
    `system=` + `messages=` per design.md.
  - Returns `""` on empty / malformed content block (no raise).
  - Calls `on_call(RunnerCallLog(...))` on success when set, with
    model and token counts from `resp.usage`.
  - `budget=` kwarg short-circuits to `""` when exhausted. Does
    not mutate budget.
  - Errors map to `AnthropicAuthError`, `AnthropicRateLimited`,
    `AnthropicTransientError`, `AnthropicClientError`. Rate-limit
    and transient categories retry with exponential backoff
    (1s, 2s, 4s) up to three attempts.
  - Unit tests inject a stub `AsyncAnthropic` — no network.
  - Coverage ≥ 80% on `src/hypothesize/llm/`.

## Task 2.4: SystemAdapter protocol and config loader

- Status: done
- Depends: none
- Files: `src/hypothesize/adapters/__init__.py`,
  `src/hypothesize/adapters/base.py`,
  `src/hypothesize/adapters/config.py`,
  `tests/adapters/__init__.py`,
  `tests/adapters/test_config.py`.
- Acceptance:
  - `SystemAdapter` Protocol with `build_runner(config)` and
    `extract_prompt(config)`. `Runner` type alias re-exported.
  - `SystemConfig` pydantic model per design.md with
    `extra="forbid"`.
  - `load_system_config(path: Path) -> SystemConfig` reads YAML and
    validates.
  - Tests: valid YAML load, unknown-key rejection, invalid-adapter-
    literal rejection, missing-required-field rejection.

## Task 2.5: Python module adapter

- Status: done
- Depends: 2.4
- Files: `src/hypothesize/adapters/python_module.py`,
  `tests/adapters/test_python_module.py`,
  `tests/_fixtures/example_systems/` (small `system.py` files, one
  per contract variant).
- Acceptance:
  - `PythonModuleAdapter` satisfies `SystemAdapter` structurally.
  - Loads modules via `importlib.util.spec_from_file_location`;
    caches by absolute path.
  - `build_runner` uses `module.make_runner(prompt=None)` if
    present, else the attribute named by `config.entrypoint`.
  - Sync entrypoints wrapped in an async shim; async pass through.
  - `extract_prompt` returns `SYSTEM_PROMPT` when both
    `SYSTEM_PROMPT` and `make_runner` are exposed; else `None`.
  - `build_runner_with_prompt(config, prompt)` calls
    `module.make_runner(prompt)` and returns the runner; raises
    `AutoAlternativeUnavailable` if `make_runner` is absent.
  - Tests: async entrypoint, sync entrypoint, missing entrypoint,
    missing module path, `make_runner`-based system,
    `SYSTEM_PROMPT`-only system (auto-alt unavailable), bare
    `run`-only system.

## Task 2.6: HTTP and CLI adapter stubs

- Status: done
- Depends: 2.4
- Files: `src/hypothesize/adapters/http.py`,
  `src/hypothesize/adapters/cli.py`,
  `tests/adapters/test_stub_adapters.py`.
- Acceptance:
  - Modules import cleanly at definition time.
  - `HttpAdapter().build_runner(config)` and
    `CliAdapter().build_runner(config)` raise `NotImplementedError`
    with a message naming the future feature.
  - `extract_prompt` returns `None` without raising on both.
  - Tests assert raise behavior and clean-import behavior.

## Task 2.7: Automatic alternative generation

- Status: done
- Depends: 2.3, 2.5
- Files: `src/hypothesize/adapters/auto_alternative.py`,
  `src/hypothesize/adapters/errors.py` (defines
  `AutoAlternativeUnavailable`, `BudgetExhausted`),
  `src/hypothesize/llm/prompts.py` (fill `rewrite_prompt_messages`),
  `tests/adapters/test_auto_alternative.py`.
- Acceptance:
  - `make_auto_alternative(current, hypothesis, llm, budget) ->
    Runner` implements the six-step algorithm in design.md.
  - Parses the rewrite response with `parse_json_response`;
    validates `{"rewritten_prompt": str, "rationale": str}`.
  - Raises `AutoAlternativeUnavailable` when `extract_prompt`
    returns None or the rewrite response fails shape validation.
  - Raises `BudgetExhausted` when the budget is exhausted on entry.
  - Tests: clean rewrite response, fenced rewrite response,
    malformed rewrite response, module without prompt-factory,
    exhausted budget. All use `MockBackend`; no network.

## Task 2.8: Live integration tests

- Status: done
- Depends: 2.3, 2.5, 2.7
- Files: `tests/_live/__init__.py`,
  `tests/_live/conftest.py`,
  `tests/_live/test_anthropic_live.py`,
  `tests/_live/test_pipeline_live.py`,
  `tests/conftest.py` (collection-modifier hook).
- Acceptance:
  - Both files declare `pytestmark = pytest.mark.live`.
  - `test_anthropic_live.py`: one tiny `complete(...)` round trip,
    asserts non-empty response and a logged `RunnerCallLog` with
    positive tokens. Skips when `ANTHROPIC_API_KEY` unset.
  - `test_pipeline_live.py`: `find_discriminating_inputs` with
    `Budget(max_llm_calls=8)`, a toy hypothesis, synthetic
    current/alternative pair, and `AnthropicBackend`. Asserts the
    pipeline reaches the generate phase and the final result is
    either `ok` with ≥ 1 case or `insufficient_evidence` with a
    non-parse reason.
  - `pytest tests/` (no `-m live`) does not execute these.
  - No edits to the PostToolUse hook config.

## Task 2.9: Re-run smoke test and document findings

- Status: pending
- Depends: 2.2, 2.3, 2.7
- Files: `scripts/smoke_test.py` (minimal edit to consume
  `AnthropicBackend`), `scripts/SMOKE_FINDINGS_2.md` (new).
- Acceptance:
  - `ANTHROPIC_API_KEY=... python scripts/smoke_test.py` exits 0
    and progresses past decomposition.
  - `SMOKE_FINDINGS_2.md` mirrors `SMOKE_FINDINGS.md`'s structure
    and covers: end-to-end success, calls per phase, observed
    `input_data` shapes, parse cleanliness with extractor applied,
    token usage per phase, discrimination outcome, any new class
    of failure prioritized for Feature 03.
  - Doc references `SMOKE_FINDINGS.md` for the first run and
    calls out what changed.

## Task 2.10: Feature 02 review pass

- Status: pending
- Depends: 2.1–2.9
- Files: none (review only; appends `DECISIONS.md`, updates task
  statuses).
- Acceptance:
  - Coverage ≥ 80% on each of `src/hypothesize/llm/`,
    `src/hypothesize/adapters/`, `src/hypothesize/core/`.
  - `pytest -m live` passes against the real API (or skips cleanly
    when the key is unset, documented in the review).
  - `ruff check src/ tests/` clean.
  - Every acceptance criterion in `requirements.md` verified and
    noted pass/fail.
  - `DECISIONS.md` gains a "Feature 02 complete" entry recording
    any deviations, any open questions raised by SMOKE_2, and
    confirmation of the JSON-extractor placement decision.
  - Update all Feature 02 task `Status:` fields to `done`.
