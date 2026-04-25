# Design: CLI, Claude Code Skill, and MCP Server

## Architecture overview

Three surfaces share a single core entry point: `run_discrimination` —
a thin async wrapper around `find_discriminating_inputs` that takes a
parsed config dict and a hypothesis string, builds the runners, the
backend, the judge, and the budget, then returns a serialisable
result. Both the CLI's `run` subcommand and the MCP server's
`run_discrimination` tool call it. The skill orchestrates by shelling
out to the CLI; it does not import library code directly. This keeps
the wire-protocol surface narrow.

```
.claude/skills/hypothesize/SKILL.md   shell-out target
        |
        v
   hypothesize CLI (Click)  ──┐
                              ├──>  src/hypothesize/cli/runner.py
   MCP tools (FastMCP)     ──┤            (build runners, judge, backend)
                              └──>  hypothesize.core.find_discriminating_inputs
```

## RunConfig — the top-level YAML model

The CLI consumes a higher-level YAML than `SystemConfig`. We add a new
pydantic model `RunConfig` in `src/hypothesize/cli/config.py` that
composes `SystemConfig` for current/alternative, `Hypothesis`,
`AnthropicConfig`, and `Budget` defaults. `extra="forbid"` so typos
are loud. Lives in `cli/` because its sole consumer is the CLI.

```yaml
# config.yaml
name: sarcasm-sentiment
current:
  adapter: python_module
  module_path: examples/sarcasm/system.py
  entrypoint: run
alternative:
  adapter: auto                     # sentinel — synthesize via make_auto_alternative
  # OR another SystemConfig for an explicit alt
hypothesis:
  text: "the sentiment classifier mislabels sarcastic positive text"
  context_refs: []
llm:
  default_model: claude-haiku-4-5-20251001
  max_tokens: 2048
budget:
  max_llm_calls: 100
defaults:
  target_n: 5
  min_required: 3
```

The `alternative.adapter == "auto"` sentinel is handled at runner
construction; everything else is a regular `SystemConfig`.

The `hypothesis`, `llm`, `budget`, and `defaults` blocks are all
optional with sensible defaults. The CLI's `--hypothesis` flag wins
over the YAML value; same for `--budget` and `--target-n`.

## CLI architecture

`click.Group` at `hypothesize.cli.main:cli`. Subcommands registered as
separate modules:

- `cli/main.py` — group definition, version flag, top-level options
- `cli/run.py` — `hypothesize run`
- `cli/list.py` — `hypothesize list`
- `cli/validate.py` — `hypothesize validate`
- `cli/runner.py` — shared backend/runner construction (testable
  without a Click context)
- `cli/output.py` — YAML serialization of `DiscriminationResult`
- `cli/config.py` — `RunConfig` pydantic model + loader

### `hypothesize run`

```
hypothesize run [OPTIONS]

Options:
  -c, --config PATH      Path to RunConfig YAML  [required]
  -H, --hypothesis TEXT  Override hypothesis text
  -o, --output PATH      Output YAML path (default:
                         tests/discriminating/<slug>_<date>.yaml)
  -n, --target-n INT     Target number of discriminating cases (default: 5)
  -b, --budget INT       Max LLM calls (default: 100)
  --backend [anthropic|mock]
                         Backend selection. 'mock' reads a scripted
                         responses file; for tests only.
  --mock-script PATH     Required when --backend=mock.
  --help                 Show this message and exit.
```

The `--backend` flag is added because the CLI is the only place where
we need a way to test the full subcommand without making API calls.
`--backend=mock` is undocumented in the user-facing README; it's an
escape hatch for the test suite, mentioned only in CLI `--help`. The
sarcasm example's README uses the default (`anthropic`).

Exit codes:
- `0` — discrimination succeeded; YAML written.
- `1` — `insufficient_evidence` from the algorithm. YAML still written
  (with `status: insufficient_evidence`) so users can inspect what
  the algorithm tried.
- `2` — config or invocation error (missing file, validation, etc.).
  No YAML written.
- `3` — runtime error from a runner or backend (e.g. user's
  `system.py` raised). YAML not written; stderr carries the
  exception type and a one-line message.

### `hypothesize list`

```
hypothesize list [PATH]
```

Walks `PATH` (default cwd) for YAML files whose top-level `metadata`
key shape matches a hypothesize benchmark. Prints one line per match:
`<path>\t<hypothesis>\t<status>\t<n_test_cases>`. Empty if none.

### `hypothesize validate`

```
hypothesize validate PATH
```

Loads `PATH` and validates its shape against the documented schema.
Exits 0 on success, 2 on malformed. One-line summary on stdout either
way.

## Output YAML schema

The user-visible artifact. Both human-readable (a sentiment engineer
should be able to scan it) and machine-parseable (tests should be able
to load it back).

```yaml
hypothesis: "the sentiment classifier mislabels sarcastic positive text"
metadata:
  generated_at: "2026-04-25T14:32:11Z"
  model: claude-haiku-4-5-20251001
  budget_used: 44
  budget_max: 100
  status: ok                          # or "insufficient_evidence"
  target_n: 5
  config_name: sarcasm-sentiment
test_cases:
  - input:
      text: "I just LOVE waiting on hold for an hour."
    expected_behavior: |
      The classifier should detect the sarcastic framing and label
      this as negative sentiment, not positive.
    discrimination_evidence:
      current_output: {sentiment: positive}
      alternative_output: {sentiment: negative}
      current_verdict:
        passed: false
        reason: "..."
        judge_type: rubric
      alternative_verdict:
        passed: true
        reason: "..."
        judge_type: rubric
# When status == insufficient_evidence:
insufficient:
  reason: "Found only 1 discriminating input after trying 18 candidates."
  candidates_tried: 18
  discriminating_found: 1
```

`metadata.config_name` is the `name` field from `RunConfig`, threaded
through so consumers can group benchmarks by system. `metadata.model`
is the `default_model` from the resolved `AnthropicConfig`.

The schema is intentionally extensible: unknown keys are tolerated by
`hypothesize validate` and `hypothesize list`. Future fields can be
added without breaking existing consumers.

## Configuration discovery

The CLI does not search for a config — `--config` is required. The
**skill** searches: it inspects the repo for `config.yaml` files
(canonical name) at top level, in `examples/<name>/`, and in
`hypothesize/<name>/`, asks the user which one if multiple match. The
MCP server's `discover_systems` tool implements the same search and
returns the matches.

This keeps the CLI's contract narrow ("you tell me where the config
is") while letting the skill and MCP do the heuristic discovery.

## Skill design

`.claude/skills/hypothesize/SKILL.md` is markdown. The skill is read
by Claude Code when the user's message matches one of the trigger
phrases. It contains:

1. A frontmatter-style header describing the skill: name,
   description, when to invoke.
2. A workflow section: clarify → identify system → run → surface.
3. Concrete example invocations of the CLI showing the shapes
   Claude should pattern-match against.
4. Failure-mode handling: what to do when the algorithm returns
   `insufficient_evidence`, when budget is exhausted, when the
   user's `system.py` fails to load.

Philosophy: SKILL.md is **instructions for Claude**, not Python code.
Iterate on its prose carefully. The full text is reproduced as an
appendix at the end of this design doc.

We do not ship helper scripts under `.claude/skills/hypothesize/` in
this feature. The skill's only side effect is `hypothesize run`.

## MCP server design

Built on `mcp.server.fastmcp.FastMCP`, which is the high-level helper
in the official `mcp` Python SDK. Server module:
`src/hypothesize/mcp/server.py`. Tools live at
`src/hypothesize/mcp/tools.py` so they can be tested as plain async
functions independently of the server wiring.

### Tool list

```python
# src/hypothesize/mcp/tools.py

async def discover_systems(repo_path: str) -> list[dict]: ...
    """Find candidate config.yaml files. Returns a list of
    {"path": str, "name": str, "adapter": str} entries."""

async def list_benchmarks(repo_path: str) -> list[dict]: ...
    """Find existing hypothesize-generated benchmark YAMLs.
    Returns {"path", "hypothesis", "status", "n_test_cases"} per entry."""

async def read_benchmark(path: str) -> dict: ...
    """Load a benchmark YAML and return it as a dict."""

async def formulate_hypothesis(
    complaint: str, context: dict | None = None,
    backend: LLMBackend | None = None,
) -> dict: ...
    """Turn a vague complaint into a structured hypothesis dict.
    Default backend is AnthropicBackend; tests inject a MockBackend."""

async def run_discrimination(
    config_path: str,
    hypothesis: str,
    target_n: int = 5,
    budget: int = 100,
    backend: LLMBackend | None = None,
) -> dict: ...
    """Same code path as the CLI's `run` command. Returns the YAML
    payload as a dict."""
```

Tool inputs and outputs are plain JSON-serialisable dicts.
`backend` is a private testing hook — the FastMCP server registers
the tools without a `backend` kwarg, so MCP clients cannot inject
backends. The tool functions accept it for unit-test convenience.

### How tools chain

Typical Claude Code use:

1. `discover_systems(repo_path)` — get candidate configs.
2. `formulate_hypothesis(complaint)` — get a structured hypothesis.
3. `run_discrimination(config_path, hypothesis)` — kick off the run.
4. `list_benchmarks(repo_path)` then `read_benchmark(path)` — review
   the resulting file.

### Server entry point

```python
# src/hypothesize/mcp/server.py

from mcp.server.fastmcp import FastMCP

server = FastMCP("hypothesize")

@server.tool()
async def discover_systems(repo_path: str) -> list[dict]:
    return await tools.discover_systems(repo_path)

# ... register the rest

def main() -> None:
    server.run()  # stdio transport by default

if __name__ == "__main__":
    main()
```

A `hypothesize-mcp` entry point is **not** declared in
`pyproject.toml` for this feature — running `python -m
hypothesize.mcp.server` is enough. Adding the script entry is a
trivial future change if the user finds it desirable.

## `formulate_hypothesis` LLM call

The MCP `formulate_hypothesis` tool is the only Feature-04 surface
that *originates* an LLM call. The CLI does not — it consumes a
hypothesis string. The skill is expected to clarify in conversation
and pass the result to the CLI directly.

Implementation: a small one-shot prompt that takes a complaint and
optional context, and returns `{"text": str, "context_refs": []}`.
Follows the project's prompt-style: prompt lives in
`src/hypothesize/mcp/prompts.py`, parsed via
`parse_json_response`. Mockable via `backend=MockBackend([...])`.

```python
def formulate_hypothesis_messages(complaint: str, context: dict) -> list[dict]:
    system = (
        "You convert vague developer complaints about LLM systems into "
        "testable failure hypotheses. A failure hypothesis names a "
        "specific class of input the system handles incorrectly."
    )
    user = (
        f"Complaint: {complaint}\n\n"
        f"Context: {json.dumps(context)}\n\n"
        "Return STRICT JSON: "
        '{"text": "<hypothesis sentence>", "context_refs": []}. '
        "No prose outside the JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
```

## Examples structure

### `examples/sarcasm/` (full)

```
examples/sarcasm/
├── README.md            run instructions, expected output preview
├── config.yaml          RunConfig pointing at system.py
└── system.py            SYSTEM_PROMPT + make_runner(prompt=None)
```

`system.py` exposes a deliberately weak baseline prompt — a one-line
"Classify sentiment as positive or negative" with no sarcasm
instruction. The `make_runner` factory follows the prompt-factory
convention so `make_auto_alternative` can rewrite the prompt for the
auto-alt path. A `run = make_runner()` line is added so the
`entrypoint: run` field works.

`config.yaml` declares:
- `current`: the `system.py` Python-module adapter
- `alternative.adapter: auto` — Claude rewrites the prompt
- `hypothesis.text` matching SMOKE_3's tested hypothesis
- Budget 100, target_n 5

`README.md` walks the user through:
- Setting `ANTHROPIC_API_KEY` in `.env`
- `hypothesize run --config examples/sarcasm/config.yaml`
- Inspecting the generated YAML

### `examples/hotpotqa/` (scaffold)

```
examples/hotpotqa/
├── README.md            describes manual setup; lists TODOs
├── config.yaml          template — TODO markers for data path
└── system.py            skeleton with TODO comments
```

`system.py` imports cleanly but raises `NotImplementedError("TODO: ...")`
when called. The README is explicit that this example is not runnable
without manual setup. No tests exercise the runner; one test asserts
the module imports.

## Error handling

CLI behavior on each failure category:

| Condition | CLI exit | Stderr message | YAML written? |
|---|---|---|---|
| Config file missing | 2 | "config not found: PATH" | no |
| Config validation failure | 2 | pydantic error formatted | no |
| `system.py` missing | 2 | adapter's FileNotFoundError | no |
| `system.py` raises during build_runner | 3 | type + message | no |
| Auto-alt unavailable | 2 | AutoAlternativeUnavailable msg | no |
| Budget exhausted before any candidates | 2 | "budget exhausted before discrimination could start" | no |
| `insufficient_evidence` | 1 | one-line summary | yes |
| `ok` | 0 | "wrote N test cases to PATH" | yes |
| Runtime exception during run | 3 | type + message | no |

Errors land on stderr; only the success summary lands on stdout.
This makes the CLI scriptable.

## Resolved design decisions

- **CLI uses Click, not argparse or typer.** Click is already a
  declared dependency (`tech.md`). Typer is not.
- **`RunConfig` lives in `cli/config.py`, not `adapters/config.py`.**
  Its sole consumer is the CLI. Putting it next to `SystemConfig`
  would muddle the layering — `adapters/` exposes pieces, `cli/`
  composes them.
- **MCP server uses FastMCP.** The low-level `mcp.server.Server` is
  more flexible but for five JSON-in / JSON-out tools the high-level
  helper saves boilerplate. Switching later is mechanical.
- **`alternative.adapter == "auto"` sentinel.** Resolves at runner
  construction in `cli/runner.py` by calling `make_auto_alternative`.
  Less surface than introducing a new adapter kind.
- **Output YAML's `metadata.status` mirrors
  `DiscriminationResult.status`.** The two fields stay in sync; the
  YAML never invents a third state.
- **Skill shells out to `hypothesize run` rather than importing
  library code.** Keeps the skill agnostic to Python version
  mismatches between Claude Code's bundled environment and the
  user's project venv. The CLI is the contract.
- **`hypothesize-mcp` script entry not declared.** `python -m
  hypothesize.mcp.server` is the documented invocation. Avoids
  committing to a name that may need to change.
- **`--backend mock --mock-script PATH`** flag is the test seam for
  CLI integration tests. It loads a JSON file of scripted responses
  and constructs a `MockBackend` from them. Documented in `--help`
  but not in the README — users have no reason to invoke it
  directly.
- **Sarcasm example mirrors SMOKE_3's hypothesis and prompts.** The
  demo flow tracks already-validated behavior. Diverging would mean
  the demo could regress without the regression suite catching it.
- **`hotpotqa` is a scaffold, not a full implementation.** The
  acceptance criteria explicitly call this out as out-of-scope for
  this session; the user finishes it manually if desired.
- **No live tests in this session.** All tests use `MockBackend`. The
  manual validation list lives in `DECISIONS.md` after the review
  pass; live verification is the user's job.

## Open questions

None that block implementation. Two parked items for a later session:

- **`hypothesize run --watch`** — re-run when a system file changes.
  Useful in a tight prompt-iteration loop. Out of scope; the CLI is
  one-shot for now.
- **Skill helper scripts.** A small Python helper that does config
  discovery (so the skill doesn't have to teach Claude how to glob)
  could simplify SKILL.md. Park until the skill is field-tested; if
  Claude Code consistently fumbles the discovery step, add a
  `discover.py` helper.

## Appendix A: SKILL.md content

```markdown
---
name: hypothesize
description: |
  Turn a developer's vague complaint about an LLM-backed system into a
  set of failing regression tests. Invoke when the user describes a
  system that "seems to fail at" something, mentions a stakeholder
  complaint, or asks for help building tests for a known failure
  mode.
---

# hypothesize

Hypothesize generates **discriminating** test cases — inputs where the
user's current system fails and a plausibly-better alternative
succeeds. The output is a YAML file that lives in the user's repo as
a regression suite.

## When to invoke

Trigger phrases:
- "my classifier gets X wrong"
- "the model fails when..."
- "stakeholder is complaining that..."
- "I want regression tests for..."
- "help me catch when the system breaks on..."

If the user describes a complaint about an LLM-backed system in
their repo, this skill is probably the right answer.

## Workflow

### 1. Clarify the complaint into a hypothesis

A hypothesis is a single sentence naming a specific class of input
the system handles incorrectly. Examples:

- "the classifier mislabels sarcastic positive text as positive"
- "the summarizer drops named entities in favor of generic nouns"
- "the QA agent answers from the first retrieved doc and ignores
  the second"

If the user's complaint is already this specific, use it. If not,
ask one or two clarifying questions:

- "What should the system do correctly that it's failing at?"
- "Do you have a small example that triggers the failure?"

Do not invent specifics the user has not given you.

### 2. Identify the system

Look for a `config.yaml` in the repo:

- Top level (`./config.yaml`)
- `examples/<name>/config.yaml`
- `hypothesize/<name>/config.yaml`

If you find one, confirm with the user before proceeding. If you
find several, ask which.

If no config exists, tell the user that hypothesize needs a config
pointing at their system, and offer to draft one based on their
existing code.

### 3. Run the discrimination

Invoke the CLI:

```
hypothesize run \\
  --config <path> \\
  --hypothesis "<hypothesis text>"
```

Default budget is 100 calls and target-n is 5 — fine for most
cases. Pass `--budget 200` if the user wants more thorough
exploration. Wall time is typically 60-90 seconds.

### 4. Surface the results

When the run completes, tell the user:

- How many discriminating cases were found
- Where the YAML was written
- One representative case (input + why it discriminates)

If the run returned `insufficient_evidence`, do not silently treat
it as a failure of the tool. Tell the user: "Hypothesize tried N
candidates but found only M discriminating ones. The hypothesis may
be wrong, or the alternative may not actually be better. Want to
revise the hypothesis?"

### 5. Optional follow-up: draft a fix

The user may ask you to draft a fixed system prompt based on the
discriminating cases. This is an extension, not part of
hypothesize itself. Read the test cases, propose a prompt edit,
and offer to test it by re-running hypothesize.

## Example invocations

```
hypothesize run \\
  --config examples/sarcasm/config.yaml \\
  --hypothesis "the sentiment classifier mislabels sarcastic positive text"
```

```
hypothesize list .                  # find existing benchmarks
hypothesize validate tests/discriminating/sarcasm_2026_04_26.yaml
```

## Failure modes

- **Config not found**: Show the user the search paths and ask
  where their config lives.
- **`system.py` raises during load**: Surface the exception. The
  user has a bug in their system.py — they fix it, you re-run.
- **`insufficient_evidence`**: See workflow step 4. This is a
  signal, not a tool failure.
- **Budget exhausted**: Re-invoke with `--budget 200`.
- **`AutoAlternativeUnavailable`**: The user's `system.py` doesn't
  expose `make_runner(prompt=None)`. Either ask them to add it, or
  explicitly point `alternative` at another system in the config.
```
