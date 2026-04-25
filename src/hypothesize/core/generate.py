"""Generate candidate inputs for one probing dimension.

One LLM call per dimension. The prompt requests JSON of shape
``{"candidates": [{"input_data": {...}, "rationale": str}, ...]}``. Items
without a non-empty ``input_data`` dict or non-empty ``rationale`` string
are dropped. At most ``n`` valid candidates are returned. Empty list on
any total failure (malformed JSON, missing key, budget exhausted, n == 0).
"""

from __future__ import annotations

from typing import Any

from hypothesize.core.json_extract import parse_json_response
from hypothesize.core.llm import LLMBackend
from hypothesize.core.prompts import generate_candidates_prompt
from hypothesize.core.types import Budget, CandidateInput, Hypothesis, ProbingDimension


def _is_valid_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    input_data = item.get("input_data")
    rationale = item.get("rationale")
    if not isinstance(input_data, dict) or not input_data:
        return False
    if not isinstance(rationale, str) or not rationale.strip():
        return False
    return True


async def generate_candidates(
    hypothesis: Hypothesis,
    dimension: ProbingDimension,
    context: list[str],
    n: int,
    llm: LLMBackend,
    budget: Budget,
) -> list[CandidateInput]:
    """Return up to ``n`` candidate inputs probing ``dimension``."""
    if n <= 0:
        return []
    if budget.exhausted():
        return []

    messages = generate_candidates_prompt(hypothesis, dimension, context, n)
    raw = await llm.complete(messages)
    budget.charge()

    payload = parse_json_response(raw)
    if not isinstance(payload, dict):
        return []
    items = payload.get("candidates")
    if not isinstance(items, list):
        return []

    candidates: list[CandidateInput] = []
    for item in items:
        if not _is_valid_item(item):
            continue
        candidates.append(
            CandidateInput(
                input_data=item["input_data"],
                dimension=dimension.name,
                rationale=item["rationale"],
            )
        )
        if len(candidates) >= n:
            break
    return candidates
