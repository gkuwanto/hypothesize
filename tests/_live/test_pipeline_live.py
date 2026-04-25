"""End-to-end live tests of the discrimination pipeline against Haiku.

Covers two paths:

- ``decompose_hypothesis`` against real Claude — asserts 3-7 typed
  ``ProbingDimension`` objects come back, parse-clean.
- ``find_discriminating_inputs`` over a tiny budget — asserts the
  pipeline progresses past decomposition and the final result is
  either ``ok`` with at least one discriminating case or
  ``insufficient_evidence`` with a reason that is *not* about parsing.

Run:    pytest tests/_live -m live -v
"""

from __future__ import annotations

from typing import Any

import pytest

from hypothesize.core.decompose import decompose_hypothesis
from hypothesize.core.discrimination import find_discriminating_inputs
from hypothesize.core.json_extract import parse_json_response
from hypothesize.core.judge import RubricJudge
from hypothesize.core.llm import LLMBackend
from hypothesize.core.types import Budget, Hypothesis

pytestmark = pytest.mark.live


class _RecordingBackend:
    """Wraps an ``LLMBackend`` and records every raw response.

    Lets a live test inspect what Haiku actually returned without
    teaching the production backend to expose responses on a hook.
    """

    def __init__(self, inner: LLMBackend) -> None:
        self._inner = inner
        self.responses: list[str] = []

    async def complete(self, messages: list[dict], **kwargs: Any) -> str:
        text = await self._inner.complete(messages, **kwargs)
        self.responses.append(text)
        return text


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_decompose_against_real_claude(anthropic_backend) -> None:
    """Real Claude must produce 3-7 well-typed dimensions for a toy hyp."""
    hypothesis = Hypothesis(
        text=(
            "the sentiment classifier fails on sarcastic positive text "
            "(surface tokens positive, intent negative)"
        )
    )
    context = [
        "Current system: a naive sentiment classifier that always says positive.",
        "Alternative: a sarcasm-aware classifier.",
    ]
    budget = Budget(max_llm_calls=4)

    dimensions = await decompose_hypothesis(
        hypothesis, context, anthropic_backend, budget
    )

    assert 3 <= len(dimensions) <= 7, (
        "decompose returned an empty list — likely a parse failure; "
        "check parse_json_response against the live response"
    )
    for dim in dimensions:
        assert dim.name
        assert dim.description
    assert budget.calls_used == 1


async def _always_positive(input_data: dict[str, Any]) -> dict[str, Any]:
    return {"sentiment": "positive"}


async def _always_negative(input_data: dict[str, Any]) -> dict[str, Any]:
    return {"sentiment": "negative"}


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_full_discrimination_pipeline_smoke(anthropic_backend) -> None:
    """Tiny end-to-end run — must clear decomposition, no parse-class failures."""
    hypothesis = Hypothesis(
        text=(
            "the sentiment classifier fails on sarcastic positive text "
            "(surface tokens positive, intent negative)"
        )
    )
    context = [
        "Current system always returns 'positive'.",
        "Alternative system always returns 'negative' as a stand-in for "
        "an actually sarcasm-aware system.",
    ]
    budget = Budget(max_llm_calls=8)
    backend = _RecordingBackend(anthropic_backend)
    judge = RubricJudge(llm=backend)

    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_always_positive,
        alternative_runner=_always_negative,
        context=context,
        judge=judge,
        llm=backend,
        budget=budget,
        target_n=3,
        min_required=1,
    )

    assert result.budget_used >= 1
    assert backend.responses, "expected at least one LLM call to have been made"

    # The decompose response is always first. The parse-class regression
    # this test guards against is a malformed *extraction* — Haiku's
    # framing breaking parse_json_response. We assert that separately
    # from any algorithmic outcome: parse must succeed and produce a
    # dict with a 'dimensions' key. If Haiku returned the wrong count
    # of dimensions (a model-quality failure, not a parse failure) the
    # pipeline can still legitimately report insufficient_evidence.
    decompose_raw = backend.responses[0]
    decompose_parsed = parse_json_response(decompose_raw)
    assert isinstance(decompose_parsed, dict), (
        "parse_json_response failed on the decompose response; "
        f"raw response (first 500 chars): {decompose_raw[:500]!r}"
    )
    assert "dimensions" in decompose_parsed, (
        "decompose response did not include a 'dimensions' key; "
        f"raw response (first 500 chars): {decompose_raw[:500]!r}"
    )

    if result.status == "ok":
        assert len(result.test_cases) >= 1
    else:
        assert result.status == "insufficient_evidence"
        assert result.insufficient is not None
