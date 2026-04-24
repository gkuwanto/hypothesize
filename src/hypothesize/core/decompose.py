"""Decompose a hypothesis into probing dimensions.

One LLM call. The prompt requests JSON of shape
``{"dimensions": [{"name", "description", "examples"}, ...]}`` with exactly
3-7 entries. Any deviation (bad JSON, missing keys, wrong count) yields an
empty list, which the caller treats as insufficient evidence.
"""

from __future__ import annotations

from pydantic import ValidationError

from hypothesize.core.json_extract import parse_json_response
from hypothesize.core.llm import LLMBackend
from hypothesize.core.prompts import decompose_hypothesis_prompt
from hypothesize.core.types import Budget, Hypothesis, ProbingDimension

MIN_DIMENSIONS = 3
MAX_DIMENSIONS = 7


async def decompose_hypothesis(
    hypothesis: Hypothesis,
    context: list[str],
    llm: LLMBackend,
    budget: Budget,
) -> list[ProbingDimension]:
    """Return 3-7 typed dimensions, or an empty list on any failure."""
    if budget.exhausted():
        return []

    messages = decompose_hypothesis_prompt(hypothesis, context)
    raw = await llm.complete(messages)
    budget.charge()

    payload = parse_json_response(raw)
    if not isinstance(payload, dict):
        return []
    raw_dims = payload.get("dimensions")
    if not isinstance(raw_dims, list):
        return []
    if not (MIN_DIMENSIONS <= len(raw_dims) <= MAX_DIMENSIONS):
        return []

    dimensions: list[ProbingDimension] = []
    for item in raw_dims:
        if not isinstance(item, dict):
            return []
        try:
            dimensions.append(ProbingDimension(**item))
        except (ValidationError, TypeError):
            return []
    return dimensions
