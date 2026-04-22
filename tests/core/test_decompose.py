"""Tests for decompose_hypothesis (Task 1.4)."""

from __future__ import annotations

import json

import pytest

from hypothesize.core.decompose import decompose_hypothesis
from hypothesize.core.types import Budget, Hypothesis, ProbingDimension
from tests._fixtures.mock_backend import MockBackend


@pytest.fixture
def hypothesis() -> Hypothesis:
    return Hypothesis(text="system mishandles negated queries")


def _dims_payload(dims: list[dict]) -> str:
    return json.dumps({"dimensions": dims})


def _make_dims(n: int) -> list[dict]:
    return [
        {
            "name": f"dim_{i}",
            "description": f"description {i}",
            "examples": [f"ex{i}"],
        }
        for i in range(n)
    ]


async def test_happy_path_returns_typed_dimensions(hypothesis: Hypothesis) -> None:
    backend = MockBackend(responses=[_dims_payload(_make_dims(4))])
    budget = Budget(max_llm_calls=10)
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert len(dims) == 4
    assert all(isinstance(d, ProbingDimension) for d in dims)
    assert dims[0].name == "dim_0"
    assert dims[0].description == "description 0"
    assert dims[0].examples == ["ex0"]
    assert budget.calls_used == 1


async def test_accepts_three_dimensions(hypothesis: Hypothesis) -> None:
    backend = MockBackend(responses=[_dims_payload(_make_dims(3))])
    budget = Budget(max_llm_calls=5)
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert len(dims) == 3


async def test_accepts_seven_dimensions(hypothesis: Hypothesis) -> None:
    backend = MockBackend(responses=[_dims_payload(_make_dims(7))])
    budget = Budget(max_llm_calls=5)
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert len(dims) == 7


async def test_rejects_too_few_dimensions(hypothesis: Hypothesis) -> None:
    backend = MockBackend(responses=[_dims_payload(_make_dims(2))])
    budget = Budget(max_llm_calls=5)
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert dims == []


async def test_rejects_too_many_dimensions(hypothesis: Hypothesis) -> None:
    backend = MockBackend(responses=[_dims_payload(_make_dims(8))])
    budget = Budget(max_llm_calls=5)
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert dims == []


async def test_malformed_json_returns_empty_list(hypothesis: Hypothesis) -> None:
    backend = MockBackend(responses=["totally not json"])
    budget = Budget(max_llm_calls=5)
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert dims == []


async def test_missing_dimensions_key_returns_empty_list(
    hypothesis: Hypothesis,
) -> None:
    backend = MockBackend(responses=[json.dumps({"wrong_key": []})])
    budget = Budget(max_llm_calls=5)
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert dims == []


async def test_dimension_missing_required_field_returns_empty_list(
    hypothesis: Hypothesis,
) -> None:
    broken = _make_dims(4)
    del broken[1]["description"]
    backend = MockBackend(responses=[_dims_payload(broken)])
    budget = Budget(max_llm_calls=5)
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert dims == []


async def test_budget_exhausted_short_circuits(hypothesis: Hypothesis) -> None:
    backend = MockBackend()  # no responses scripted
    budget = Budget(max_llm_calls=0)
    assert budget.exhausted()
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert dims == []
    assert len(backend.calls) == 0  # no LLM call attempted


async def test_empty_context_still_sends_request(hypothesis: Hypothesis) -> None:
    backend = MockBackend(responses=[_dims_payload(_make_dims(3))])
    budget = Budget(max_llm_calls=5)
    dims = await decompose_hypothesis(hypothesis, [], backend, budget)
    assert len(dims) == 3
    assert len(backend.calls) == 1


async def test_context_included_in_prompt(hypothesis: Hypothesis) -> None:
    backend = MockBackend(responses=[_dims_payload(_make_dims(3))])
    budget = Budget(max_llm_calls=5)
    await decompose_hypothesis(
        hypothesis, ["context line one", "context line two"], backend, budget
    )
    joined = "\n".join(
        msg["content"]
        for call in backend.calls
        for msg in call["messages"]
    )
    assert "context line one" in joined
    assert "context line two" in joined
