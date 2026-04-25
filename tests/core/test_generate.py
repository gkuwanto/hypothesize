"""Tests for generate_candidates (Task 1.5)."""

from __future__ import annotations

import json

import pytest

from hypothesize.core.generate import generate_candidates
from hypothesize.core.types import Budget, CandidateInput, Hypothesis, ProbingDimension
from tests._fixtures.mock_backend import MockBackend


@pytest.fixture
def hypothesis() -> Hypothesis:
    return Hypothesis(text="system mishandles negated queries")


@pytest.fixture
def dimension() -> ProbingDimension:
    return ProbingDimension(
        name="explicit_negation",
        description="inputs containing 'not', 'no', 'never'",
        examples=["which products are NOT organic?"],
    )


def _candidates_payload(items: list[dict]) -> str:
    return json.dumps({"candidates": items})


def _make_items(n: int) -> list[dict]:
    return [
        {
            "input_data": {"question": f"not-case {i}"},
            "rationale": f"probes negation variant {i}",
        }
        for i in range(n)
    ]


async def test_happy_path_returns_typed_candidates(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    backend = MockBackend(responses=[_candidates_payload(_make_items(3))])
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 3, backend, budget)
    assert len(cands) == 3
    assert all(isinstance(c, CandidateInput) for c in cands)
    assert cands[0].dimension == dimension.name
    assert cands[0].input_data == {"question": "not-case 0"}
    assert cands[0].rationale == "probes negation variant 0"
    assert budget.calls_used == 1


async def test_truncates_when_llm_returns_more_than_n(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    backend = MockBackend(responses=[_candidates_payload(_make_items(5))])
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 3, backend, budget)
    assert len(cands) == 3


async def test_returns_fewer_when_llm_returns_fewer(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    backend = MockBackend(responses=[_candidates_payload(_make_items(2))])
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 5, backend, budget)
    assert len(cands) == 2


async def test_n_zero_skips_llm_call(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    backend = MockBackend()  # no script
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 0, backend, budget)
    assert cands == []
    assert len(backend.calls) == 0
    assert budget.calls_used == 0


async def test_budget_pre_exhausted_returns_empty(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    backend = MockBackend()
    budget = Budget(max_llm_calls=0)
    assert budget.exhausted()
    cands = await generate_candidates(hypothesis, dimension, [], 3, backend, budget)
    assert cands == []
    assert len(backend.calls) == 0


async def test_malformed_json_returns_empty(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    backend = MockBackend(responses=["garbage"])
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 3, backend, budget)
    assert cands == []


async def test_missing_candidates_key_returns_empty(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    backend = MockBackend(responses=[json.dumps({"other": []})])
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 3, backend, budget)
    assert cands == []


async def test_drops_items_with_empty_input_data(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    items = _make_items(3)
    items[1]["input_data"] = {}  # invalid
    backend = MockBackend(responses=[_candidates_payload(items)])
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 3, backend, budget)
    assert len(cands) == 2
    assert all(c.input_data for c in cands)


async def test_drops_items_with_empty_rationale(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    items = _make_items(3)
    items[0]["rationale"] = ""
    backend = MockBackend(responses=[_candidates_payload(items)])
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 3, backend, budget)
    assert len(cands) == 2


async def test_fenced_json_response_parses_like_clean(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    """Regression: fenced JSON from the LLM must parse identically."""
    clean = _candidates_payload(_make_items(3))
    fenced = f"```json\n{clean}\n```"
    backend = MockBackend(responses=[fenced])
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 3, backend, budget)
    assert len(cands) == 3
    assert all(isinstance(c, CandidateInput) for c in cands)


async def test_every_candidate_tagged_with_dimension_name(
    hypothesis: Hypothesis, dimension: ProbingDimension
) -> None:
    backend = MockBackend(responses=[_candidates_payload(_make_items(2))])
    budget = Budget(max_llm_calls=10)
    cands = await generate_candidates(hypothesis, dimension, [], 2, backend, budget)
    assert all(c.dimension == dimension.name for c in cands)
