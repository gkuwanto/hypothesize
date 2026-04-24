# Design: Real LLM Integration and System Adapters

## New types

All pydantic v2 models. Frozen where immutability aids reasoning.

```python
# src/hypothesize/llm/config.py

from pydantic import BaseModel, ConfigDict

class AnthropicConfig(BaseModel):
    """Per-backend configuration.

    The backend's default model is used when a specific call does not
    override via a per-call ``model=`` kwarg on ``complete()``.
    """
    model_config = ConfigDict(frozen=True)

    default_model: str = "claude-opus-4-7"
    max_tokens: int = 2048
    timeout_seconds: float = 60.0
    # Environment variable lookup name. When None, the anthropic SDK's
    # own default (ANTHROPIC_API_KEY) is honored.
    api_key_env: str | None = None
```

```python
# src/hypothesize/adapters/config.py

from pathlib import Path
from pydantic import BaseModel, ConfigDict
from typing import Literal

class SystemConfig(BaseModel):
    """Declarative description of a system under test.

    Loaded from YAML for Feature 04's CLI; in Feature 02 it is the
    handoff between ``load_system_config`` and adapter constructors.
    """
    model_config = ConfigDict(frozen=True)

    name: str
    adapter: Literal["python_module", "http", "cli"]
    # Python-module adapter fields
    module_path: Path | None = None
    entrypoint: str = "run"
    # HTTP and CLI adapter fields are declared here but unused
    # by the Python-module adapter; stubs read them where relevant.
    url: str | None = None
    command: list[str] | None = None


class RunnerCallLog(BaseModel):
    """Optional token-accounting record surfaced by AnthropicBackend.

    Not a budget primitive — ``Budget`` still counts calls, not tokens.
    This is informational, collected by a caller-supplied hook.
    """
    model_config = ConfigDict(frozen=True)

    model: str
    input_tokens: int
    output_tokens: int
    phase: str | None = None  # caller-populated
```

No new types are added to `src/hypothesize/core/`. The Feature 01 interface
is frozen.

## AnthropicBackend

```python
# src/hypothesize/llm/anthropic.py

class AnthropicBackend:
    def __init__(
        self,
        config: AnthropicConfig | None = None,
        client: "anthropic.AsyncAnthropic | None" = None,
        on_call: Callable[[RunnerCallLog], None] | None = None,
    ) -> None: ...

    async def complete(self, messages: list[dict], **kwargs: Any) -> str: ...
```

Implementation notes:

- **Model selection.** `default_model` from config; `complete(messages,
  model=...)` overrides per call. The core layer does not pass `model`
  today, so the default wins unless we later teach prompts to select per
  phase. Acceptable; per-phase overrides are a caller concern.
- **Budget.** The backend checks `kwargs.get("budget")` if supplied; if
  that budget is exhausted it returns an empty string without calling
  the API. This is a belt-and-braces guard — the core already checks
  `budget.exhausted()` before calling `complete` in every current site.
  The backend does not charge the budget; the core sites charge after
  `complete` returns, preserving Feature 01's contract.
- **Streaming.** Not used. We parse whole responses and there is no user
  waiting on partial output in-process. If streaming is wanted later,
  it is additive.
- **Message translation.** The core passes
  `[{"role": "system"/"user"/"assistant", "content": str}]`. Anthropic's
  `messages.create` takes `system=` separately. The backend extracts
  any `role == "system"` messages and joins them into the `system`
  kwarg; the rest pass through. Mirrors the smoke script's
  already-validated translation.
- **Response extraction.** `resp.content[0].text`. On missing / empty
  content block, return an empty string; the calling parser handles
  the empty case.
- **Token logging.** On each successful call, if `on_call` was supplied
  at construction, the backend emits a `RunnerCallLog` with model and
  token counts from `resp.usage`. The `phase` field is left None here;
  callers that want per-phase labels can wrap the backend or read from
  the system prompt, as `smoke_test.py` already demonstrates.
- **Error handling.** See the dedicated section below.

## JSON extraction strategy

**Resolved decision: Option 2 — extractor lives in
`src/hypothesize/core/json_extract.py` as a pure utility.**

Rationale, grounded in `structure.md`:

- `core/` "may not import from `adapters/`, `llm/`, `cli/`, or `mcp/`".
  A JSON-parsing helper is pure string manipulation with no I/O, which
  is exactly the kind of thing `core/` is allowed to contain.
- Placing the helper in `llm/` would make "return clean JSON" part of
  the backend contract. Any future backend — the `MockBackend` in
  `tests/`, a hypothetical local-model backend, an HTTP passthrough —
  would have to re-implement extraction or inherit from a base class
  that does. Silent drift is the predictable outcome.
- The contract is clearer at the parser site: "here is a raw string
  from an LLM; tolerate messy framing". That contract does not belong
  to the producer — it belongs to the consumer.
- The four parse sites can update in a mechanical, grep-able way:
  `json.loads(raw)` becomes `parse_json_response(raw)`. Signature of
  `decompose_hypothesis`, `generate_candidates`, and the judge methods
  is unchanged.

Signature:

```python
# src/hypothesize/core/json_extract.py

def parse_json_response(raw: str) -> Any | None:
    """Attempt to parse a JSON value from an LLM response.

    Returns the parsed value on success; ``None`` on any failure. Callers
    handle ``None`` the same way they handled ``json.JSONDecodeError`` in
    Feature 01 — by returning an empty list / malformed-verdict signal.

    Tolerates:
    - markdown code fences: ``` ```json ... ``` ```, ``` ``` ... ``` ```,
      ``` ```python ... ``` ```, ``` ```javascript ... ``` ```,
      and other language tags (treated as opaque language hints).
    - leading prose ("Here is the JSON:\\n", "Sure, here's the answer:",
      etc.).
    - trailing prose after the closing brace.
    - trailing commas inside objects or arrays (best-effort; applied
      only if a strict parse fails first).
    - leading/trailing whitespace.
    - an empty string or pure whitespace (returns None).

    Does not tolerate:
    - actually malformed JSON (mismatched brackets, unquoted keys,
      single-quoted strings). These remain parse failures — masking
      them would lose signal we need.
    """
```

Algorithm:

1. If `raw` is empty or whitespace, return None.
2. Try `json.loads(raw.strip())`. On success, return.
3. Try fence-stripping: find the first ``` ``` ``` fence line; if
   present, slice between it and the next ``` ``` ``` fence line.
   Strip an optional language tag on the opening fence. Try
   `json.loads` on the extracted body. On success, return.
4. Try brace-slicing: find the first `{` or `[`; find the matching
   closer by state-machine bracket counting that correctly handles
   JSON string literals, including escape sequences (`\"`, `\\`,
   `\u....`). Try `json.loads` on that substring. On success, return.
5. Trailing-comma repair: operate on the best candidate string from
   prior steps — step 4's brace-slice if it found one, else step 3's
   fence-body if that succeeded, else the original raw input. Using
   the same state-machine scanner from step 4, remove commas that
   precede `}` or `]` when outside a string literal. Attempt the
   repair and call `json.loads` one final time. On success, return.
6. Return None.

The five-step ladder is defensive in depth. Step 2 covers clean
responses; step 3 covers the exact smoke-test failure; step 4 covers
"Sure, here's your JSON: { ... }. Let me know if..."; step 5 covers a
common tool-use artifact; None covers genuinely malformed output.

Testing target: ≥ 25 cases in `tests/core/test_json_extract.py`, with a
named fixture capturing the first smoke run's exact response and
similar real-world shapes.

## SystemAdapter protocol

```python
# src/hypothesize/adapters/base.py

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

Runner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class SystemAdapter(Protocol):
    """Build a runnable function from a SystemConfig.

    Every adapter takes a ``SystemConfig`` and returns a ``Runner``
    shaped to satisfy ``find_discriminating_inputs``'s
    ``current_runner`` / ``alternative_runner`` arguments.
    """

    def build_runner(self, config: SystemConfig) -> Runner: ...

    def extract_prompt(self, config: SystemConfig) -> str | None:
        """Optional: return the system prompt for auto-alt rewriting.

        Adapters that cannot introspect their system's prompt return
        None. Auto-alt then raises a clear error pointing the user at
        the prompt-factory convention.
        """
```

Adapters are stateless where possible; `build_runner` returns a new
closure per call, and the `extract_prompt` method is a pure read.

## Python module adapter

```python
# src/hypothesize/adapters/python_module.py

class PythonModuleAdapter:
    def build_runner(self, config: SystemConfig) -> Runner: ...
    def extract_prompt(self, config: SystemConfig) -> str | None: ...
```

Loading protocol:

1. `config.adapter == "python_module"` and `config.module_path` points
   at a file.
2. `importlib.util.spec_from_file_location` loads the module. The
   module is cached per absolute path so repeated `build_runner`
   calls (e.g., current + auto-alt) do not re-execute module body.
3. The entrypoint is `getattr(module, config.entrypoint)`. If it is
   async, it is used directly; if sync, the adapter wraps it in a
   thin `async def` that calls the sync function on the current
   thread (acceptable for hackathon scale; a thread-pool variant is
   a future optimization).

Prompt-factory convention (opt-in, enables auto-alt):

- The user's module may expose a `make_runner(prompt: str | None = None)
  -> Runner` callable. When present, `build_runner` calls it with
  `prompt=None` to obtain the default runner; `make_auto_alternative`
  calls it with a rewritten prompt.
- The user's module may also expose a module-level `SYSTEM_PROMPT: str`
  attribute. `extract_prompt` reads it when `make_runner` is present.
  If only `SYSTEM_PROMPT` is present without `make_runner`, auto-alt
  raises (see below).
- If neither is present, the module is treated as prompt-opaque:
  `build_runner` still works (uses the bare entrypoint), but
  `extract_prompt` returns None and auto-alt is unavailable for this
  system.

Minimal user-side example (documented in adapter module docstring):

```python
# user's system.py
SYSTEM_PROMPT = "You are a helpful assistant..."

def make_runner(prompt: str | None = None):
    p = prompt or SYSTEM_PROMPT
    async def run(input_data: dict) -> dict:
        return {"output": await _call_my_llm(p, input_data)}
    return run

# fallback entrypoint when auto-alt is not used
run = make_runner()
```

## Automatic alternative generation

**Resolved decision: utility function, not adapter subclass.**

```python
# src/hypothesize/adapters/auto_alternative.py

async def make_auto_alternative(
    current: SystemConfig,
    hypothesis: Hypothesis,
    llm: LLMBackend,
    budget: Budget,
) -> Runner: ...
```

Rationale for utility over subclass:

- The operation "rewrite this prompt, rebuild the runner" is
  orthogonal to adapter type — in principle HTTP and CLI adapters
  could also expose an `extract_prompt` hook in the future, and the
  same utility would work against all three.
- A subclass (`AutoAlternativeAdapter(PythonModuleAdapter)`) would
  force a new class per adapter type. The utility collapses that to
  one function that reads `extract_prompt` from whichever adapter
  matches `current.adapter`.
- `build_runner` + `extract_prompt` is all the utility needs.
  Composition is cleaner than inheritance here.

Algorithm:

1. Resolve the adapter implied by `current.adapter` (Python-module in
   scope; HTTP / CLI raise `NotImplementedError` from their stub).
2. Call `adapter.extract_prompt(current)`. If None, raise a
   `AutoAlternativeUnavailable` exception with a message naming the
   prompt-factory convention and pointing the user at the docs.
3. Charge one LLM call. If `budget.exhausted()`, raise
   `BudgetExhausted` — auto-alt is a pre-pipeline setup step, not a
   mid-pipeline step, so exceptions are appropriate here rather than
   the core's sentinel-return pattern.
4. Call `llm.complete(rewrite_prompt_messages(current_prompt,
   hypothesis))` using the prompt-rewrite prompt (below). Parse the
   response with `parse_json_response`. Validate shape
   `{"rewritten_prompt": str, "rationale": str}`.
5. Rebuild the runner:
   `adapter.build_runner_with_prompt(current, rewritten)` — a new
   method on `PythonModuleAdapter` that calls `module.make_runner(
   rewritten)`.
6. Return the resulting `Runner`.

Prompt-rewrite prompt (new entry in `src/hypothesize/llm/prompts.py`,
parallel to `core/prompts.py` — kept out of core because its consumer
is specifically the adapter layer):

```python
def rewrite_prompt_messages(current_prompt: str, hypothesis: Hypothesis) -> list[dict]:
    system = (
        "You rewrite an LLM system prompt to specifically mitigate a "
        "stated failure hypothesis while preserving the prompt's "
        "original task and tone. You do not rewrite the prompt from "
        "scratch; you add targeted guidance."
    )
    user = (
        f"Current system prompt:\n---\n{current_prompt}\n---\n\n"
        f"Failure hypothesis the rewrite should address:\n"
        f"{hypothesis.text}\n\n"
        'Return STRICT JSON: {"rewritten_prompt": str, '
        '"rationale": str}. The rewritten_prompt should be a '
        "drop-in replacement. The rationale is one sentence "
        "explaining the change you made. No prose outside the JSON."
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]
```

## HTTP and CLI adapters (stubs)

Both live in Feature 02 only as import-safe stubs.

```python
# src/hypothesize/adapters/http.py

class HttpAdapter:
    def build_runner(self, config: SystemConfig) -> Runner:
        raise NotImplementedError(
            "HTTP adapter is not implemented in Feature 02. "
            "Planned for a future feature."
        )

    def extract_prompt(self, config: SystemConfig) -> str | None:
        return None
```

`cli.py` mirrors this shape with a CLI-specific message. Both classes
satisfy the `SystemAdapter` protocol structurally so that dispatch code
in `make_auto_alternative` and the Feature 04 CLI compiles without
special-casing.

## Budget tracking integration

- Feature 01's contract stands: `Budget` counts LLM calls, not tokens.
  Every core caller increments the budget after `llm.complete` returns.
- `AnthropicBackend` does not mutate `Budget`. It accepts an optional
  `budget=` kwarg on `complete`; if passed and exhausted, the backend
  short-circuits to an empty string without calling the API. This is a
  safety net, not the primary control.
- Token counts are surfaced via the `on_call` callback. Callers that
  want per-phase accounting register a callback that appends to a list
  of `RunnerCallLog` entries. `scripts/smoke_test.py` and the Feature
  02 smoke refresh both rely on this.
- `MAX_LLM_CALLS_PER_HYPOTHESIS = 200` (from `standards.md`) remains
  the hard cap enforced by whoever constructs the `Budget`.

## Error handling

`AnthropicBackend` must distinguish four categories:

1. **Auth failures** (`anthropic.AuthenticationError`). Re-raise as
   `AnthropicAuthError` with a message pointing the user at
   `ANTHROPIC_API_KEY`. Never retry.
2. **Rate limits** (`anthropic.RateLimitError`). Sleep with exponential
   backoff (1s, 2s, 4s) up to three attempts, then re-raise as
   `AnthropicRateLimited`. Caller may catch or let it propagate.
3. **Transient server errors** (5xx, `anthropic.APIConnectionError`).
   Exponential backoff, three attempts, then re-raise as
   `AnthropicTransientError`.
4. **Client errors** (4xx other than 401/429). Re-raise as
   `AnthropicClientError` with status and response body included.

Response-shape failures (empty content, unexpected content block type)
return an empty string. The parser at the core site will treat it as a
parse failure and cascade to the existing malformed-payload branches.

`parse_json_response` does not raise. Returning None is the entire
failure contract.

`make_auto_alternative` raises `AutoAlternativeUnavailable` when the
user's module does not expose the prompt-factory convention, or when
`parse_json_response` returns None on the rewrite response. These are
pre-pipeline setup errors; bubbling them up gives the user actionable
feedback.

## Configuration

Preview of the YAML shape that Feature 04's CLI will consume. Feature 02
ships `SystemConfig` and a `load_system_config` helper; the CLI
glue-code is Feature 04.

```yaml
name: sarcasm-sentiment
current:
  adapter: python_module
  module_path: examples/sentiment/system.py
  entrypoint: run
alternative:
  adapter: auto   # synthesize via make_auto_alternative
hypothesis:
  text: "the sentiment classifier fails on sarcastic positive text"
  context_refs: []
llm:
  default_model: claude-opus-4-7
  max_tokens: 2048
budget:
  max_llm_calls: 50
```

`load_system_config` returns a root model composed of `SystemConfig`
(for `current`), an optional `SystemConfig` for `alternative` (with a
special `adapter: auto` sentinel handled by the CLI in Feature 04),
`Hypothesis`, `AnthropicConfig`, and `Budget`. Unknown keys are
rejected by pydantic `extra="forbid"` so typos are loud.

## Resolved design decisions

- **JSON extractor lives in `core/` as a utility (Option 2).**
  Parser-side responsibility. See JSON extraction strategy for full
  rationale.
- **Auto-alternative is a utility function, not an adapter subclass.**
  Composition over inheritance; one function works against any future
  adapter that implements `extract_prompt`.
- **`AnthropicBackend` does not mutate `Budget`.** Matches the
  Feature 01 contract: callers charge.
- **Tool-use / structured-output not used in Feature 02.** The smoke
  findings note that JSON-mode-via-tool-use would eliminate the parse
  class of bug entirely. In practice it requires per-phase schema
  definitions and a matching parse layer, which is a larger surface
  than a string helper. The extractor is defence in depth regardless,
  so the cheap thing wins for now. Revisit in Feature 03 if SMOKE_2
  shows residual failures.
- **Sync `run` entrypoints are wrapped on the calling thread.** Good
  enough for the hackathon-scale examples. A thread-pool wrapper is a
  future optimization, not a Feature 02 concern.
- **Stub adapters implement `SystemAdapter` structurally.** They raise
  only from `build_runner`, not at definition time, so the module
  imports cleanly and the structural `Protocol` check passes for
  dispatch code.
- **Prompt-rewrite prompt lives in `llm/prompts.py`, not
  `core/prompts.py`.** Its consumer is the adapter layer, not the
  core algorithm. Keeping core-only prompts in `core/prompts.py`
  preserves the Feature 01 "every core LLM call is grep-able from one
  file" property.

## Open questions

None that block implementation. Two items to revisit if SMOKE_2
surfaces new signal:

- Whether `parse_json_response` should gain a sixth repair step
  (unquoted-key or single-quote-to-double-quote) if we see those in
  the wild. Current position: no; they mask deeper prompt bugs.
- Whether `AnthropicBackend` should auto-retry on parse failure with a
  corrective prompt, per SMOKE_FINDINGS.md item 2. Current position:
  no; the extractor is the first line of defence and a retry is worth
  considering only if SMOKE_2 shows it firing frequently.
