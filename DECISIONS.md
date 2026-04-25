# Decision Log

This file records decisions made during development, especially deviations
from the original design documents. Appended to by Claude Code at the end
of each feature and at any point where a non-trivial decision is made that
future sessions should know about.

## Format

```
## YYYY-MM-DD — Feature NN (title)

- Decision: <what was decided>
- Rationale: <why>
- Spec impact: <any spec files updated>
```

## Entries

## 2026-04-25 — HotpotQA example complete

- Closed-book multi-hop QA with `DIRECT_PROMPT` and `DECOMPOSE_PROMPT`
  variants. `examples/hotpotqa/system.py` is now real (no longer
  scaffolded), exposes the prompt-factory convention, and parses
  multi-line model responses by extracting the trailing `Final
  answer: <X>` line that both prompts instruct Claude to emit.
- 50-item dataset built reproducibly from HotpotQA distractor /
  validation, filtered to bridge questions with question ≤25 words,
  answer ≤5 words, and an "interesting-entity" keyword filter
  (film / album / city / actor / etc.). Source script
  `examples/hotpotqa/build_dataset.py` (seeded with 20260425).
- Filter run found **3 discriminating cases** out of 50 (DIRECT
  fails, DECOMPOSE passes). Also surfaced a 3-case reverse-
  discriminating set (DIRECT passes, DECOMPOSE fails — over-
  caution / speculative intermediate steps), which is itself a
  finding the video should not paper over.
- 3 curated for video; brief asked for 4 but the natural set was 3.
  Curating a fourth would have meant lowering the quality bar or
  re-rolling randomness. Stuck with 3, surfaced the count clearly
  in `CURATED.md`.
- Total cost incurred this session: ~$0.10 (≈100 Haiku 4.5 calls
  at the live filter pass; a small amount on the live sanity
  check). Well under the $2 hard cap.
- Mechanism: filter over a fixed eval, `ExactMatchJudge`-style
  containment match against gold answers. Implemented as a
  standalone script (`run_filter.py`), not via the CLI.

### Option B chosen over Option A

The brief offered (A) adding a `--candidates-from <path>` CLI flag
and (B) writing a standalone `run_filter.py`. Inspecting the code
showed Option A would not be the "~50 lines additive" the brief
estimated:

- The CLI's `run_discrimination` always wires `RubricJudge`. To
  use `ExactMatchJudge` we would need a second judge selector.
- `core/discrimination.py` (frozen — Feature 01) always calls
  `decompose_hypothesis` and `generate_candidates`. A "user-
  supplied candidate pool" path would have to bypass this entry
  point entirely, i.e. a parallel pipeline in CLI code rather
  than a small flag.

That is a CLI refactor, not an additive flag. Option B contains
the change to `examples/hotpotqa/`, leaves frozen layers alone, and
is honest about the example's narrow scope. The `config.yaml` still
loads cleanly via `load_run_config` so the example surfaces in
`hypothesize list` and `discover_systems`.

### Surprises

- Haiku 4.5 ignored "Provide only the final answer, no explanation"
  on hard bridge questions — it produced multi-line reasoning even
  with the DIRECT prompt. Fixed by appending an explicit "End your
  response with a single line of the form: `Final answer: <X>`"
  instruction to both prompts and parsing the last `Final answer:`
  line in `_normalize_answer`. This is a plausible, real-world
  prompt convention; not a strawman or test-only hack.
- Many gold answers in HotpotQA are noisy (the question asks for
  the "name of the biography" but the gold is the biographer's
  name). The filter pass therefore uses bidirectional containment
  on case- and punctuation-normalised forms rather than strict
  equality. This both papers over the noisy gold answers and
  accepts model answers that are slightly more verbose than the
  span (e.g. "Queen Margrethe II of Denmark" vs gold "Queen
  Margrethe II"). Documented in `run_filter.py::_exact_match`.
- The 3-vs-3 only-DECOMPOSE-right vs only-DIRECT-right split was
  unexpected. Decomposition isn't a strict win on bridge
  questions; it sometimes induces analytical refusals ("I cannot
  determine this with certainty") on items DIRECT confidently
  nails. Worth noting in any video framing.
- Closed-book recall is the dominant bottleneck — 27/50 are wrong
  on both prompts. Most of those are obscure entities (Faruk
  Halibegovic, Cordyline ruba, Eighth Wonder lead singer); no
  prompt change rescues recall. The discriminating zone is
  narrower than the 5-15 the brief estimated.

### Files added / modified

- `examples/hotpotqa/system.py` — finished closed-book QA runner.
- `examples/hotpotqa/config.yaml` — finalised, validates via
  `load_run_config`.
- `examples/hotpotqa/build_dataset.py` — new, reproducibly seeds
  the 50-item subset.
- `examples/hotpotqa/run_filter.py` — new, the filter-pass entry
  point.
- `examples/hotpotqa/data/multi_hop_50.jsonl` — new, 50 items.
- `examples/hotpotqa/data/README.md` — new, documents source.
- `examples/hotpotqa/output/multi_hop_filter_run1.yaml` — run
  artefact, 3 discriminating cases + 50 raw rows.
- `examples/hotpotqa/CURATED.md`, `CURATED.yaml` — 3 cases.
- `examples/hotpotqa/README.md` — rewritten for runnable status.
- `tests/examples/test_hotpotqa.py` — extended from scaffold-mode
  tests (NotImplementedError) to 26 tests covering the runner
  factory, prompt selection, answer normalisation including
  multi-line "Final answer:" extraction, and config validation.
- `DECISIONS.md` — this entry.

No source files in `src/hypothesize/core/`, `src/hypothesize/llm/`,
`src/hypothesize/adapters/python_module.py`, `src/hypothesize/mcp/`,
or `examples/sarcasm/` were touched. `pyproject.toml` and
`tech.md` were not modified — `datasets` was already declared.

## 2026-04-24 — Feature 04 complete

- Decision: Feature 04 (developer-facing surface — CLI, Claude Code
  skill, MCP server, sarcasm + hotpotqa examples) shipped end to end
  using mocks-only testing. Live validation deferred to the user's
  manual run after merge.
- Coverage: 90% project-wide. Feature 04 modules at 85% (cli/ 87%,
  mcp/ 80%). Above the 80% floor declared in `requirements.md`.
- Test counts: 328 non-live tests passing in ~3s on 4 workers; 4
  live tests still gated on `-m live`. 87 of those are new in
  Feature 04 (CLI 33, MCP 21, examples 19, skill 7, harness 7).
- Surfaces shipped:
  - `hypothesize` CLI with `run`, `list`, `validate` subcommands.
    Entry point in `pyproject.toml` fixed to `cli:cli` (was the
    bootstrap-era `cli:main`).
  - `.claude/skills/hypothesize/SKILL.md` describing the
    complaint → discrimination → surface workflow.
  - `src/hypothesize/mcp/server.py` (FastMCP) with five tools:
    discover_systems, list_benchmarks, read_benchmark,
    formulate_hypothesis, run_discrimination.
  - `examples/sarcasm/` complete (system.py with the
    prompt-factory convention, config.yaml using
    alternative.adapter=auto, runnable README).
  - `examples/hotpotqa/` scaffold (system.py with TODO body
    raising NotImplementedError; README documenting manual
    setup).
  - README.md Quickstart section.

### Resolved design decisions worth noting

- **`RunConfig.alternative.adapter == "auto"`** is the auto-alt
  sentinel. Resolved in `cli/runner.py` by calling
  `make_auto_alternative` rather than introducing a new adapter
  kind. Keeps `SystemConfig` (frozen by Feature 02) untouched.
- **CLI's `--backend mock --mock-script PATH`** is a private test
  seam. Reads a JSON list of strings, builds a `_ScriptedBackend`
  inside `cli/run.py`. Documented in `--help` but not in the user
  README. We did not import `MockBackend` from `tests/` — that
  would invert the layering.
- **Output YAML schema**: `hypothesis`, `metadata` (with
  generated_at, model, budget_used, budget_max, status, target_n,
  config_name), and `test_cases[]` with `input`,
  `expected_behavior`, `discrimination_evidence`. When
  insufficient, an `insufficient` block is appended.
- **Skill philosophy**: SKILL.md is instructions to Claude, not
  Python. The skill shells out to `hypothesize run` rather than
  importing library code, so it stays agnostic to environment
  mismatches between Claude Code's bundled venv and the user's
  project venv.
- **MCP uses FastMCP**, not the low-level `mcp.server.Server`.
  Five JSON-in / JSON-out tools fit the high-level helper
  cleanly; the low-level server is more flexible but unnecessary
  here.
- **`hypothesize-mcp` script entry not declared.** Documented
  invocation is `python -m hypothesize.mcp.server`. Avoids
  committing to a name that may need to change.

### Deviations from `design.md` / `tasks.md`

- The `cli/list.py` filename was changed to `cli/list_cmd.py` to
  avoid shadowing the builtin `list`; tasks.md already calls this
  out. Same pattern was used for `validate.py` (no shadowing
  issue, but kept consistency with how the command function is
  named `list_cmd` / `validate_cmd`).
- A small `_ScriptedBackend` class was added inside
  `src/hypothesize/cli/run.py` rather than re-using or re-locating
  `tests/_fixtures/mock_backend.py::MockBackend`. The `tasks.md`
  spec said "build a `MockBackend`"; the deviation is the
  layering-clean realization. Functionally equivalent.
- Tasks.md said tests/cli/test_run.py would have ~12 tests; we
  wrote 6 (which cover all the documented exit codes and the
  hypothesis-override-flag case). Plus 14 in test_config.py, 5 in
  test_runner.py, 3 in test_output.py, 5 in test_main.py — 33
  CLI tests total, comfortably above the spec target.

### Manual validation steps for the user (after merge)

These cannot be tested with mocks; live verification is the
user's job.

1. **Install + sanity-check the CLI**:

   ```bash
   pip install -e ".[dev]"
   hypothesize --help
   hypothesize --version
   ```

2. **Set the API key**:

   ```bash
   echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
   ```

3. **Run the sarcasm example**:

   ```bash
   hypothesize run \
     --config examples/sarcasm/config.yaml \
     --hypothesis "the sentiment classifier mislabels sarcastic positive text"
   ```

   Expect: 60-90s wall time, $0.10-$0.20 in tokens, a YAML in
   `tests/discriminating/` with `metadata.status: ok` and 5
   discriminating cases.

4. **Inspect the output**:

   ```bash
   hypothesize list .
   hypothesize validate tests/discriminating/<your_file>.yaml
   ```

5. **Skill smoke**: in Claude Code, paste a sarcasm-shaped
   complaint ("my sentiment classifier seems to mislabel
   sarcastic reviews"). Confirm the hypothesize skill triggers,
   asks at most one clarifying question, identifies the sarcasm
   config, runs the CLI, and surfaces a representative case.

6. **MCP smoke**: in another terminal,

   ```bash
   python -m hypothesize.mcp.server
   ```

   The server starts on stdio. Connect from Claude Desktop or any
   MCP client and exercise at least one tool — `list_benchmarks .`
   is the cheapest end-to-end check; `discover_systems .` and
   `read_benchmark <path>` next.

### Concerns to double-check during validation

- `system.py`'s lazy backend construction uses
  `claude-haiku-4-5-20251001` by default. Verify that survives a
  real run; if Haiku occasionally fails to follow the
  one-word-only constraint, the `_normalize_label` helper has to
  carry the load. Mocked tests cover the normalization, but the
  production prompt's adherence is empirical.
- The MCP `formulate_hypothesis` tool calls Claude; with default
  config, that is `claude-opus-4-7` (the AnthropicConfig default).
  This may be slow / expensive for a single tool call. If the
  user finds it sluggish, override `default_model` to Haiku in a
  later spec.
- `examples/hotpotqa/` deliberately raises `NotImplementedError`.
  `discover_systems` will surface it as a candidate config; that
  is fine because `RunConfig` validates without invoking the
  runner. A user who picks the hotpotqa config and runs
  `hypothesize run` without finishing the TODOs will see exit
  code 3 and a runtime error message — by design.

## 2026-04-24 — Feature 02 complete

- Decision: Feature 02 (real LLM integration + adapters) shipped end to end.
- Coverage: 93% project-wide, 90%+ on every Feature 02 module
  (`src/hypothesize/llm/`, `src/hypothesize/adapters/`, and all
  Feature 02 additions to `src/hypothesize/core/`). Above the 80% floor.
- Test counts: 237 non-live tests, ~0.95s on 4 workers; 4 live tests
  (`pytest -m live`), ~44s end-to-end against Haiku 4.5.
- Smoke result: pipeline runs end to end with zero parse failures.
  See "Open question" below — the discrimination outcome itself is
  stochastic across runs because of an unrelated rubric issue that
  belongs to Feature 03.
- Confirmed: `parse_json_response` lives in `core/json_extract.py` per
  the design's Option-2 placement decision — none of the four parse
  sites needed signature changes, and the helper is import-free of any
  adapter / llm code. `AnthropicBackend` continues not to mutate
  `Budget`; charging stays the core caller's responsibility.

### Deviations from `design.md` / `tasks.md`

- Live tests live in `tests/_live/` (leading underscore) rather than
  `tests/live/` as written in `tasks.md`. The session-B instructions
  explicitly call for `_live`; the underscore matches the existing
  `tests/_fixtures/` convention (private, not a discoverable test
  package). `python_files = ["test_*.py"]` still picks up tests
  inside it. No functional impact.
- A `pytest_collection_modifyitems` hook was added in
  `tests/conftest.py` to default-skip `live` tests unless `-m live` is
  set. The acceptance criterion ("`pytest tests/` does not execute
  these") required it; without the hook, pytest's marker machinery
  collects marked tests by default.
- Live tests carry per-test `@pytest.mark.timeout(120-180)` overrides.
  The project's global `--timeout=30` is too tight for any multi-call
  pipeline run against Haiku.

### Open question raised by SMOKE_2 — rubric semantic stochasticity

Three smoke runs on the same scenario produced 0, 4, 0 discriminating
cases respectively. Wiring is correct; the variance comes from
ambiguity in `build_rubric_prompt` / `rubric_judge_prompt`: neither
prompt pins whether `passed=true` means "system handles correctly" or
"system exhibits the failure". Haiku resolves the ambiguity
differently across runs. `pairwise_judge_prompt` is correctly oriented
already — its system text says explicitly "passes (does NOT exhibit
the failure)". `discrimination.py` assumes the pairwise convention.

This is a Feature 01 / Feature 03 prompt-design issue, not a Feature
02 issue. Per session-B scope rules, core was not modified to fix it.
Feature 03 should:

1. Tighten `build_rubric_prompt` to encode the convention explicitly,
   or move discrimination to pairwise judging entirely.
2. Add a regression test (offline, mocked rubric_judge) that pins the
   discrimination predicate's expected orientation.
3. Run the smoke against a non-classifier scenario to verify the
   stochasticity isn't peculiar to sentiment.

Full evidence: `scripts/SMOKE_FINDINGS_2.md`.

### Surprises

- `parse_json_response` handled 100% of fenced and prose-prefixed
  responses across ~125 LLM calls in the live test suite plus three
  smoke runs. The defence-in-depth case for Anthropic's structured-
  output / tool-use JSON mode is now weaker; park that work unless a
  later run produces a contrary signal.
- The auto-alternative generator's prompt-rewrite call is the most
  consequential prompt in the project, but it is small in this
  feature's footprint — one builder, one utility, one error type.
  Most of the session's value came from end-to-end exercise, not
  net-new code.
- The rubric finding is silent. The rubric_judge response is well-
  formed JSON with coherent `reason` text, no exception path is hit,
  no parse failure, and `discriminating_found = 0` is the only
  signal. A more ambiguous scenario could mask this entirely. Feature
  03 should treat "produces something but produces zero
  discriminations" as a first-class failure category in its review
  pass.

## 2026-04-22 — Smoke test findings (pre-Feature 02)

- Haiku returns JSON wrapped in markdown code fences despite prompt instructions.
  This breaks all four json.loads sites in src/hypothesize/core/.
- Decision: Feature 02 will add a JSONExtractor helper, wrap parse sites.
  Core code signatures unchanged; fix is additive.
- See scripts/SMOKE_FINDINGS.md for full evidence.
- Smoke test should be re-run as part of Feature 02 review.


## 2026-04-22 — Feature 01 complete

- Decision: Feature 01 (core discrimination) shipped end to end.
- Coverage: 93% on `src/hypothesize/core/` (320 stmts, 13 missing), well
  above the 80% floor. Remaining uncovered lines are defensive branches
  (malformed payload guards and budget-exhaustion fall-throughs that the
  outer loop also handles).
- Test counts: 128 tests total; 73 under `tests/core/`, 50 harness
  parallel smoke, 5 harness mock. Suite runs in ~0.7s on 4 workers with
  no network.

### Deviations from `design.md` / `requirements.md`

- `requirements.md` text says `generate_candidates` "takes a hypothesis,
  a list of dimensions". The resolved design (`design.md` pseudocode and
  `tasks.md` 1.5) takes a single `ProbingDimension`; the top-level
  discrimination loop iterates dimensions and calls
  `generate_candidates` once per dimension. Implementation follows the
  design+tasks shape, not the requirements phrasing, because the
  per-dimension budget math and candidate tagging assume one call per
  dimension. No blocker — flagged here so Feature 02 knows to update the
  requirements wording on a future pass.

- `PairwiseJudge.judge_pair(input_data, output_a, output_b, hypothesis,
  budget)` does not satisfy the `Judge` protocol (which is
  single-output). This matches the design note that pairwise judgment is
  "one LLM call per judgment" comparing two outputs — the shape is
  intrinsically different. The discrimination pipeline in Feature 01
  uses only single-output judges; `PairwiseJudge` is a parallel API for
  callers that want head-to-head comparisons.

- `TestCase` carries `__test__ = False` to prevent pytest from treating
  a pydantic model as a test class (its name starts with "Test"). This
  is a mechanical workaround, not a design change.

### Prompt design observations for Feature 02

- Every LLM-facing prompt in `core/prompts.py` requests STRICT JSON with
  an inline schema. The rubric builder is the single exception — it
  returns free-form rubric text that is fed back into a subsequent
  strict-JSON rubric-judge call. Feature 02 (real Anthropic integration)
  should verify that Claude actually adheres to "no prose outside the
  JSON" on all of these, and consider requesting `response_format`
  JSON-mode if the provider exposes one.

- Candidate generation asks the model to produce `input_data` shapes
  that are "appropriate to the hypothesis" (e.g. `{"text": ...}` for a
  classifier, `{"question": ...}` for a RAG system). This shape
  inference is delegated to the LLM for Feature 01; a real run will
  surface whether that works or whether we need to pass an input
  template.

### Surprises

- None of substance. Coverage came out higher than expected because the
  "empty list on any failure" pattern in decompose/generate collapses
  many error shapes into the same path.

- The diversity heuristic had the cleanest implementation when written
  as a plain greedy k-center over pre-computed token sets, rather than
  the online variant hinted at in `design.md`. Deterministic tie-break
  falls out of a strict `>` comparison.

- Spec impact: `tasks.md` all seven tasks marked `done`. No other spec
  files touched.

## 2026-04-24 — Rubric orientation diagnostic complete

- Experiment ran in `scripts/diagnostics/`. See
  `scripts/diagnostics/RUBRIC_FINDINGS.md` for full evidence (N=10 per
  cell, four cells, ~$1.50 in API spend on Haiku 4.5 + Sonnet 4.6).
- Recommendation: **Path A** — tighten `build_rubric_prompt` and
  `rubric_judge_prompt` in `src/hypothesize/core/prompts.py` to pin
  `passed=true = handles correctly, does NOT exhibit failure`
  explicitly, and rewrite the builder to embed the convention into
  the rubric body rather than describing what failure looks like.
- Key evidence: tightened prompt on Haiku 4.5 was 10/10 correctly
  oriented vs. 0/10 on the unmodified prompt — same model, same
  inputs, the prompt is the only delta. Pairwise is also 30/30 on
  Haiku, so Path B is viable but unnecessary.
- Surprise: SMOKE_2 reported Haiku as 1/3 correctly oriented
  (stochastic). The diagnostic at N=10 finds 0/10 correct (9 cleanly
  inverted, 1 inconsistent). The current prompt is not a coin flip on
  Haiku — it is reliably read backwards. Most likely SMOKE_2's 1/3 was
  sample variance over a true rate near zero.
- Open question: only one hypothesis (sarcasm classifier) and one
  model below Sonnet (Haiku 4.5) were exercised. A weaker-signal
  failure mode could re-introduce ambiguity. Re-run smoke against a
  non-classifier scenario after the fix lands.
- Action: a fix session will implement Path A against
  `src/hypothesize/core/prompts.py` and add the offline regression
  test for the discrimination-predicate orientation. Not done in this
  session.

## 2026-04-24 — Rubric orientation fix complete

- Tightened `build_rubric_prompt` and `rubric_judge_prompt` per Path A
  (`scripts/diagnostics/RUBRIC_FINDINGS.md` recommendation). The
  convention `passed=true = handles correctly, does NOT exhibit failure`
  is now stated explicitly in both the builder and judge system
  messages, and the builder is additionally required to write criteria
  as success-descriptors rather than failure-descriptors.
- Added offline regression test
  (`tests/core/test_rubric_orientation_regression.py`, 4 cases) that
  pins the discrimination predicate against a fixed-orientation
  `MockBackend` contract. Guards against future re-inversion in either
  the prompts, the judge, or the discrimination predicate itself.
- Refactored `scripts/smoke_test.py` into a `Scenario` dataclass and
  added a non-classifier scenario (summarization: named-entity
  preservation) alongside the existing sarcasm scenario. Each scenario
  runs with its own 100-call core budget.
- Verified end-to-end with SMOKE_3 across two back-to-back sessions and
  two scenarios each. All four scenario-runs returned `status=ok` with
  5/5 discriminating cases, zero parse failures, and zero inverted
  verdicts across 168 `rubric_judge` calls and 4 rubric builds.
  Orientation: **correct**.
- Total cost incurred this session: ~$0.26 in live API spend (in
  addition to the diagnostic's ~$1.50). Cumulative bug investigation +
  fix cost ≈ $1.80.
- See `scripts/SMOKE_FINDINGS_3.md` for detailed per-run verification,
  per-phase token accounting, and quoted verdict reasons.
