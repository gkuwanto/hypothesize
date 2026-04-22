# Tasks: Feature 01 — Core Discrimination

## Task 1.1: Define core types

- Status: done
- Depends: none
- Files: `src/hypothesize/core/types.py`, `tests/core/test_types.py`
- Acceptance:
  - All types from design.md instantiate and validate with pydantic
  - `Budget.charge`, `.remaining`, `.exhausted` behave correctly
  - Basic round-trip serialization test passes
  - Types are frozen where appropriate (TestCase, Verdict, Hypothesis frozen;
    Budget mutable)

## Task 1.2: Define LLM backend protocol and mock

- Status: done
- Depends: 1.1
- Files: `src/hypothesize/core/llm.py`, `tests/_fixtures/mock_backend.py`,
  `tests/core/test_llm_mock.py`
- Acceptance:
  - `LLMBackend` protocol defined with `complete` method
  - `MockBackend` records calls in order and replays scripted responses in
    order
  - `MockBackend` raises a clear error on unexpected call
  - Tests cover: script-replay, call recording, error on exhausted script

## Task 1.3: Implement judge strategies

- Status: done
- Depends: 1.1, 1.2
- Files: `src/hypothesize/core/judge.py`, `src/hypothesize/core/prompts.py`,
  `tests/core/test_judge.py`
- Acceptance:
  - `Judge` protocol defined
  - `ExactMatchJudge` works without LLM, compares specified output field
  - `RubricJudge` generates rubric once, caches, judges against it
  - `PairwiseJudge` compares two outputs in one LLM call
  - All three tested with MockBackend returning scripted responses
  - Edge cases: empty output, malformed LLM response, budget exhausted

## Task 1.4: Implement hypothesis decomposer

- Status: done
- Depends: 1.1, 1.2
- Files: `src/hypothesize/core/decompose.py`, `tests/core/test_decompose.py`
- Acceptance:
  - `decompose_hypothesis(hypothesis, context, llm, budget)` returns a list
    of `ProbingDimension` with 3-7 items
  - Parses LLM output, validates structure, returns typed objects
  - On malformed LLM output, returns `InsufficientEvidence` rather than
    raising
  - Tests: happy path, malformed response, budget exhaustion, empty context

## Task 1.5: Implement candidate input generator

- Status: pending
- Depends: 1.4
- Files: `src/hypothesize/core/generate.py`, `tests/core/test_generate.py`
- Acceptance:
  - `generate_candidates(hypothesis, dimension, context, n, llm, budget)`
    returns up to n `CandidateInput` objects
  - Each candidate has a non-empty `input_data` dict and a rationale
  - Budget-aware: stops early if budget low
  - Tests: happy path, n=0, budget pre-exhausted, malformed LLM output

## Task 1.6: Implement discrimination filter with diversity heuristic

- Status: pending
- Depends: 1.3, 1.5
- Files: `src/hypothesize/core/discrimination.py`,
  `src/hypothesize/core/diversity.py`,
  `tests/core/test_discrimination.py`, `tests/core/test_diversity.py`
- Acceptance:
  - `find_discriminating_inputs` composes the full pipeline as in design.md
  - Returns `InsufficientEvidence` when fewer than 3 discriminating
  - Returns at most `target_n` test cases when more than that qualify
  - `diversify_subset` uses Jaccard distance on tokenized input_data values
  - Deterministic given same inputs and MockBackend script
  - Tests cover: full pipeline happy path, insufficient evidence, budget
    exhaustion mid-run, diversity pruning from oversized set

## Task 1.7: Feature review pass

- Status: pending
- Depends: 1.1-1.6
- Files: none (review only, no code changes)
- Acceptance:
  - Run `pytest --cov=src/hypothesize/core tests/core/` — coverage ≥ 80%
  - Run `ruff check src/ tests/` — clean
  - Read `requirements.md` and confirm every acceptance criterion is met
  - Append a summary to `DECISIONS.md` under a "Feature 01 complete" heading
    listing any deviations from the design doc
  - Update all task `Status:` fields to `done`
