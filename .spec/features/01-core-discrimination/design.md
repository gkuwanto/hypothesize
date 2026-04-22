# Design: Core Discrimination

## Types

```python
# src/hypothesize/core/types.py

from pydantic import BaseModel
from typing import Literal, Any

class Hypothesis(BaseModel):
    text: str
    context_refs: list[str] = []  # file paths or doc ids, optional

class ProbingDimension(BaseModel):
    name: str
    description: str
    examples: list[str] = []

class CandidateInput(BaseModel):
    input_data: dict[str, Any]
    dimension: str  # which ProbingDimension this came from
    rationale: str  # why this input probes the hypothesis

class Verdict(BaseModel):
    passed: bool
    reason: str
    judge_type: Literal["exact_match", "rubric", "pairwise"]

class TestCase(BaseModel):
    input_data: dict[str, Any]
    expected_behavior: str  # natural language description
    hypothesis_tag: str
    discrimination_evidence: dict  # records current vs alternative outputs

class Budget(BaseModel):
    max_llm_calls: int = 200
    calls_used: int = 0

    def charge(self, n: int = 1) -> None: ...
    def remaining(self) -> int: ...
    def exhausted(self) -> bool: ...

class InsufficientEvidence(BaseModel):
    reason: str
    candidates_tried: int
    discriminating_found: int

class DiscriminationResult(BaseModel):
    status: Literal["ok", "insufficient_evidence"]
    test_cases: list[TestCase] = []
    insufficient: InsufficientEvidence | None = None
    budget_used: int
```

## LLM backend protocol

```python
# src/hypothesize/core/llm.py

from typing import Protocol

class LLMBackend(Protocol):
    async def complete(self, messages: list[dict], **kwargs) -> str: ...
```

Production implementations (Anthropic) live in `src/hypothesize/llm/` in
Feature 02. Tests inject a `MockBackend` that records calls and replays
scripted responses.

## Judge protocol

```python
# src/hypothesize/core/judge.py

from typing import Protocol

class Judge(Protocol):
    async def judge(
        self,
        input_data: dict,
        output: dict,
        hypothesis: Hypothesis,
        budget: Budget,
    ) -> Verdict: ...
```

### ExactMatchJudge

Compares a specific output field against an expected value. No LLM call.
Used when ground-truth labels exist.

### RubricJudge

Uses the LLMBackend to evaluate output against a rubric derived from the
hypothesis. The rubric is generated once per hypothesis (not per judgment)
and cached. One LLM call per judgment.

### PairwiseJudge

Compares current vs alternative outputs side by side. One LLM call per
judgment. Used when rubric generation is unreliable.

## The discrimination algorithm

```python
# src/hypothesize/core/discrimination.py (pseudocode)

async def find_discriminating_inputs(
    hypothesis: Hypothesis,
    current_runner: Callable[[dict], Awaitable[dict]],
    alternative_runner: Callable[[dict], Awaitable[dict]],
    context: list[str],
    judge: Judge,
    llm: LLMBackend,
    budget: Budget,
    target_n: int = 10,
    min_required: int = 3,
) -> DiscriminationResult:

    # Step 1: decompose hypothesis into probing dimensions
    dimensions = await decompose_hypothesis(hypothesis, context, llm, budget)

    # Step 2: generate candidate inputs, spread across dimensions
    per_dim = max(3, (target_n * 4) // len(dimensions))  # overgenerate
    candidates: list[CandidateInput] = []
    for dim in dimensions:
        if budget.exhausted(): break
        candidates.extend(
            await generate_candidates(hypothesis, dim, context, per_dim, llm, budget)
        )

    # Step 3: run both systems on each candidate
    discriminating: list[TestCase] = []
    for cand in candidates:
        if budget.exhausted(): break
        current_out = await current_runner(cand.input_data)
        alt_out = await alternative_runner(cand.input_data)

        # Step 4: judge each output against the hypothesis
        current_verdict = await judge.judge(cand.input_data, current_out, hypothesis, budget)
        alt_verdict = await judge.judge(cand.input_data, alt_out, hypothesis, budget)

        # Step 5: keep only discriminating cases
        if not current_verdict.passed and alt_verdict.passed:
            discriminating.append(TestCase(
                input_data=cand.input_data,
                expected_behavior=alt_verdict.reason,
                hypothesis_tag=hypothesis.text,
                discrimination_evidence={
                    "current_output": current_out,
                    "alternative_output": alt_out,
                    "current_verdict": current_verdict.model_dump(),
                    "alternative_verdict": alt_verdict.model_dump(),
                },
            ))

    # Step 6: handle insufficient evidence
    if len(discriminating) < min_required:
        return DiscriminationResult(
            status="insufficient_evidence",
            insufficient=InsufficientEvidence(
                reason=(
                    f"Found only {len(discriminating)} discriminating inputs "
                    f"after trying {len(candidates)} candidates. "
                    f"Hypothesis may be wrong or alternative may not improve."
                ),
                candidates_tried=len(candidates),
                discriminating_found=len(discriminating),
            ),
            budget_used=budget.calls_used,
        )

    # Step 7: if too many, pick a diverse subset
    if len(discriminating) > target_n:
        discriminating = diversify_subset(discriminating, target_n)

    return DiscriminationResult(
        status="ok",
        test_cases=discriminating,
        budget_used=budget.calls_used,
    )
```

## Diversity heuristic (simple version)

For Feature 01, `diversify_subset` uses surface-token Jaccard distance. Pick
the first case, then iteratively pick the case most different from the
already-selected set. Not optimal but cheap and deterministic.

## Prompt design

Prompts live in `src/hypothesize/core/prompts.py`. Each prompt is a function
that takes typed inputs and returns a message list. Keeping them in one file
makes iteration easy and makes prompts grep-able.

Initial prompts needed:
- `decompose_hypothesis_prompt(hypothesis, context) -> messages`
- `generate_candidates_prompt(hypothesis, dimension, context, n) -> messages`
- `build_rubric_prompt(hypothesis) -> messages`
- `rubric_judge_prompt(rubric, input_data, output) -> messages`
- `pairwise_judge_prompt(hypothesis, input_data, output_a, output_b) -> messages`

## Open questions

- [open] Should `decompose_hypothesis` return a fixed number of dimensions
  or let the LLM decide? Leaning: LLM decides between 3 and 7, prompt
  enforces range.
- [open] Should `Budget` raise on exhaustion or return a sentinel? Leaning
  sentinel (return empty list / no verdict), to avoid partial state.
- [resolved] Cache rubric per hypothesis. Do not regenerate per input.
