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
