"""Top-level discrimination algorithm.

Composes decomposition, candidate generation, dual-system execution,
judging, and diversity pruning into a single ``find_discriminating_inputs``
entry point. The algorithm returns either a ``DiscriminationResult`` with
up to ``target_n`` ``TestCase`` objects, or an ``insufficient_evidence``
result carrying counts and a reason.

Budget is charged only for internal LLM calls (decompose, generate,
judge). Calls to the user-supplied ``current_runner`` and
``alternative_runner`` are opaque to the budget.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from hypothesize.core.decompose import decompose_hypothesis
from hypothesize.core.diversity import diversify_subset
from hypothesize.core.generate import generate_candidates
from hypothesize.core.judge import Judge
from hypothesize.core.llm import LLMBackend
from hypothesize.core.types import (
    Budget,
    CandidateInput,
    DiscriminationResult,
    Hypothesis,
    InsufficientEvidence,
    TestCase,
)

SystemRunner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _per_dimension_count(target_n: int, n_dims: int) -> int:
    return max(3, min(5, (target_n * 2) // n_dims))


async def find_discriminating_inputs(
    hypothesis: Hypothesis,
    current_runner: SystemRunner,
    alternative_runner: SystemRunner,
    context: list[str],
    judge: Judge,
    llm: LLMBackend,
    budget: Budget,
    target_n: int = 10,
    min_required: int = 3,
) -> DiscriminationResult:
    """Return the minimum set of inputs that discriminate current vs alternative."""
    # Step 1: decompose
    dimensions = await decompose_hypothesis(hypothesis, context, llm, budget)
    if not dimensions:
        return DiscriminationResult(
            status="insufficient_evidence",
            insufficient=InsufficientEvidence(
                reason=(
                    "decomposition failed: expected 3-7 probing dimensions "
                    "from the LLM"
                ),
                candidates_tried=0,
                discriminating_found=0,
            ),
            budget_used=budget.calls_used,
        )

    # Step 2: generate candidates across dimensions
    per_dim = _per_dimension_count(target_n, len(dimensions))
    candidates: list[CandidateInput] = []
    for dim in dimensions:
        if budget.exhausted():
            break
        batch = await generate_candidates(
            hypothesis, dim, context, per_dim, llm, budget
        )
        candidates.extend(batch)

    # Steps 3-5: run both systems and judge each output
    discriminating: list[TestCase] = []
    for cand in candidates:
        if budget.exhausted():
            break
        current_out = await current_runner(cand.input_data)
        alt_out = await alternative_runner(cand.input_data)
        current_verdict = await judge.judge(
            cand.input_data, current_out, hypothesis, budget
        )
        alt_verdict = await judge.judge(
            cand.input_data, alt_out, hypothesis, budget
        )
        if not current_verdict.passed and alt_verdict.passed:
            discriminating.append(
                TestCase(
                    input_data=cand.input_data,
                    expected_behavior=alt_verdict.reason,
                    hypothesis_tag=hypothesis.text,
                    discrimination_evidence={
                        "current_output": current_out,
                        "alternative_output": alt_out,
                        "current_verdict": current_verdict.model_dump(),
                        "alternative_verdict": alt_verdict.model_dump(),
                    },
                )
            )

    # Step 6: insufficient evidence
    if len(discriminating) < min_required:
        return DiscriminationResult(
            status="insufficient_evidence",
            insufficient=InsufficientEvidence(
                reason=(
                    f"Found only {len(discriminating)} discriminating inputs "
                    f"after trying {len(candidates)} candidates. "
                    "Hypothesis may be wrong or alternative may not improve."
                ),
                candidates_tried=len(candidates),
                discriminating_found=len(discriminating),
            ),
            budget_used=budget.calls_used,
        )

    # Step 7: diversify if we have too many
    if len(discriminating) > target_n:
        discriminating = diversify_subset(discriminating, target_n)

    return DiscriminationResult(
        status="ok",
        test_cases=discriminating,
        budget_used=budget.calls_used,
    )
