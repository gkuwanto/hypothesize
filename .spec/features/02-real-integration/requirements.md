# Feature 02: Real LLM Integration and System Adapters

## Goal

Connect Feature 01's algorithmic core to the real world. Ship an
`AnthropicBackend` that satisfies the `LLMBackend` protocol against the live
Anthropic API, a permissive JSON extraction helper that absorbs the
response-framing variance observed in the Feature 01 smoke test, and a
`SystemAdapter` abstraction with a working Python-module implementation so
users can plug their own system under test into `find_discriminating_inputs`.
Also ship the automatic alternative-system generator that was deferred from
Feature 01. After this feature, a human can run `scripts/smoke_test.py`
end-to-end against real Claude and obtain real discriminating test cases.

## Acceptance criteria

- `src/hypothesize/llm/anthropic.py` defines `AnthropicBackend` that
  implements the `LLMBackend` protocol from `src/hypothesize/core/llm.py`
  using the `anthropic` SDK's `AsyncAnthropic` client. Model is
  configurable; defaults follow `tech.md` (`claude-opus-4-7` for reasoning
  calls, `claude-haiku-4-5-20251001` for rubric-judging, selectable per
  call via a kwarg).
- `AnthropicBackend` is budget-aware: it never calls the API when the
  supplied `Budget` is exhausted, and it exposes per-call input/output
  token counts via a structured log hook or return-side callback (shape
  specified in `design.md`). It does not mutate `Budget`; charging stays
  the responsibility of the core caller, matching the Feature 01 contract.
- All four JSON-expecting parse sites in `src/hypothesize/core/` —
  `decompose.py`, `generate.py`, and the two sites in `judge.py` (rubric
  judge, pairwise judge) — accept fenced JSON (```` ```json ````, bare
  ```` ``` ````, other language tags), leading or trailing prose, and
  trailing commas, without any signature change. Mechanism is specified
  in `design.md` (a `parse_json_response` utility, placement resolved
  there).
- A `SystemAdapter` protocol and a `Runner` type are defined in
  `src/hypothesize/adapters/base.py`. Adapters produce a `Runner` — a
  `Callable[[dict], Awaitable[dict]]` — that matches the
  `current_runner` / `alternative_runner` arguments to
  `find_discriminating_inputs`.
- `src/hypothesize/adapters/python_module.py` implements a Python-module
  adapter: given a path to a user-written module and the name of its
  entrypoint, returns a `Runner`. Supports both sync and async
  entrypoints. Supports the prompt-factory convention that enables
  automatic alternative generation (see below).
- `src/hypothesize/adapters/http.py` and
  `src/hypothesize/adapters/cli.py` are scaffolded as stubs. Each exposes
  a class implementing the same protocol whose `build_runner()` method
  raises `NotImplementedError` with a message that names the feature the
  implementation belongs to (Feature 03 or later). Stubs import cleanly
  and do not crash at definition time.
- Automatic alternative generation exists as a utility function
  `make_auto_alternative(current_config, hypothesis, llm) -> Runner`
  (signature and location resolved in `design.md`). Given a system
  config whose module exposes the prompt-factory convention, it uses
  `llm` to rewrite the system prompt targeting the hypothesis, then
  returns a runner bound to the rewritten prompt. Given a system whose
  module does not expose the convention, it raises a clear error naming
  what the user must add.
- A `SystemConfig` pydantic model (in
  `src/hypothesize/adapters/config.py`) describes a system in
  YAML-loadable form. A `load_system_config(path: Path) -> SystemConfig`
  helper reads YAML. The CLI that consumes this is out of scope
  (Feature 04); this feature only ships the loader and the model.
- `scripts/smoke_test.py` runs end-to-end against the real Anthropic API
  using `AnthropicBackend`, successfully parses Haiku's fenced output,
  progresses past decomposition into generate / judge, and either
  produces discriminating cases or reports a well-formed
  `insufficient_evidence` result with a reason that is not about
  parsing. A new `scripts/SMOKE_FINDINGS_2.md` documents the second-run
  results, including observed `input_data` shapes from the generate
  phase, rubric-judge JSON cleanliness, token usage per phase, and any
  new class of failure the run surfaces.
- Test coverage on `src/hypothesize/llm/` and
  `src/hypothesize/adapters/` is at least 80%, measured with
  `pytest --cov`. Unit tests mock the Anthropic SDK at the
  `AsyncAnthropic` client boundary; no live network calls in the unit
  suite.
- The JSON extractor is covered by at least 25 unit tests exercising a
  corpus of realistic messy responses (fenced, double-fenced, prose-
  prefixed, prose-suffixed, trailing-comma, mixed-language fence, empty,
  whitespace, bare object, nested object, array root, near-miss with
  unescaped quotes). Behavior on the first smoke run's exact observed
  response is captured as a named fixture.
- Integration tests marked `@pytest.mark.live` exercise (a) the
  `AnthropicBackend` against the live API with a tiny payload, and (b)
  the full `find_discriminating_inputs` pipeline against a small
  fixture hypothesis. These are excluded from the PostToolUse hook
  (which runs `pytest -x -q --timeout=30`) by default and run only on
  explicit `pytest -m live` invocation.

## Non-goals

- CLI entry point, Claude Code skill, MCP server — all Feature 04.
- Dataset-specific examples (GoEmotions, HotpotQA, etc.) — all Feature 03.
- HTTP and CLI adapter implementations — scaffold only in this feature.
- Any changes to protocol signatures in `src/hypothesize/core/`.
  Feature 01's interface is frozen; additions are permitted only at the
  adapter/backend boundary or as new pure utilities inside core.
- Any changes to judge, decompose, generate, or discrimination
  algorithms in core. Feature 02 only adds a JSON-parsing helper and
  rewires the existing parse sites to call it.
- Multi-provider support (OpenAI, Bedrock, etc.). Anthropic only.
- Automatic retry on parse failure. Extraction must be robust enough
  that a one-shot retry is not required. If Feature 02's smoke run
  shows residual parse failures after extraction, a retry mechanism
  becomes a Feature 03 consideration.

## Dependencies

- Feature 01 complete and merged. All types, protocols, and the
  discrimination pipeline in `src/hypothesize/core/` are in place and
  frozen.
