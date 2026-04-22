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
