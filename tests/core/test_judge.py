"""Tests for judge strategies (Task 1.3)."""

from __future__ import annotations

import json

import pytest

from hypothesize.core.judge import (
    ExactMatchJudge,
    Judge,
    PairwiseJudge,
    RubricJudge,
)
from hypothesize.core.types import Budget, Hypothesis
from tests._fixtures.mock_backend import MockBackend


@pytest.fixture
def hypothesis() -> Hypothesis:
    return Hypothesis(text="system mishandles negated queries")


@pytest.fixture
def budget() -> Budget:
    return Budget(max_llm_calls=20)


def test_judge_protocol_has_judge_method() -> None:
    assert hasattr(Judge, "judge")


# ---------- ExactMatchJudge ----------


async def test_exact_match_judge_passes_when_fields_equal(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    j = ExactMatchJudge(expected_key="label", output_key="prediction")
    v = await j.judge(
        input_data={"text": "foo", "label": "positive"},
        output={"prediction": "positive"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert v.passed is True
    assert v.judge_type == "exact_match"
    assert budget.calls_used == 0  # no LLM call


async def test_exact_match_judge_fails_on_mismatch(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    j = ExactMatchJudge(expected_key="label", output_key="prediction")
    v = await j.judge(
        input_data={"label": "positive"},
        output={"prediction": "negative"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert v.passed is False
    assert "mismatch" in v.reason.lower() or "expected" in v.reason.lower()
    assert v.judge_type == "exact_match"


async def test_exact_match_judge_fails_on_missing_field(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    j = ExactMatchJudge(expected_key="label", output_key="prediction")
    v = await j.judge(
        input_data={"text": "no label here"},
        output={"prediction": "anything"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert v.passed is False
    assert v.judge_type == "exact_match"


async def test_exact_match_judge_respects_budget_exhaustion(
    hypothesis: Hypothesis,
) -> None:
    """Even though ExactMatch makes no LLM call, design says exhausted → budget_exhausted verdict."""
    b = Budget(max_llm_calls=1)
    b.charge()
    assert b.exhausted()
    j = ExactMatchJudge(expected_key="label", output_key="prediction")
    v = await j.judge(
        input_data={"label": "positive"},
        output={"prediction": "positive"},
        hypothesis=hypothesis,
        budget=b,
    )
    assert v.passed is False
    assert v.reason == "budget_exhausted"
    assert v.judge_type == "exact_match"


# ---------- RubricJudge ----------


async def test_rubric_judge_generates_rubric_once_and_reuses(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    backend = MockBackend(
        responses=[
            "RUBRIC: answer must mention non-organic items",
            json.dumps({"passed": True, "reason": "mentions non-organic"}),
            json.dumps({"passed": False, "reason": "missed non-organic"}),
        ]
    )
    j = RubricJudge(llm=backend)
    v1 = await j.judge(
        input_data={"q": "not organic?"},
        output={"answer": "apples are not organic"},
        hypothesis=hypothesis,
        budget=budget,
    )
    v2 = await j.judge(
        input_data={"q": "non-organic?"},
        output={"answer": "all organic"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert v1.passed is True
    assert v2.passed is False
    assert len(backend.calls) == 3  # rubric + two judgments
    assert budget.calls_used == 3


async def test_rubric_judge_cache_keyed_on_hypothesis_text(budget: Budget) -> None:
    backend = MockBackend(
        responses=[
            "RUBRIC A",
            json.dumps({"passed": True, "reason": "rA"}),
            "RUBRIC B",
            json.dumps({"passed": False, "reason": "rB"}),
        ]
    )
    j = RubricJudge(llm=backend)
    h1 = Hypothesis(text="hypothesis A")
    h2 = Hypothesis(text="hypothesis B")
    v1 = await j.judge(input_data={}, output={"o": "x"}, hypothesis=h1, budget=budget)
    v2 = await j.judge(input_data={}, output={"o": "y"}, hypothesis=h2, budget=budget)
    assert v1.reason == "rA"
    assert v2.reason == "rB"
    assert len(backend.calls) == 4


async def test_rubric_judge_malformed_response_returns_failing_verdict(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    backend = MockBackend(
        responses=[
            "RUBRIC",
            "not valid json at all",
        ]
    )
    j = RubricJudge(llm=backend)
    v = await j.judge(
        input_data={"q": "x"},
        output={"o": "y"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert v.passed is False
    assert v.judge_type == "rubric"
    assert "malformed" in v.reason.lower() or "parse" in v.reason.lower()


async def test_rubric_judge_budget_exhausted_returns_sentinel_verdict(
    hypothesis: Hypothesis,
) -> None:
    backend = MockBackend()
    b = Budget(max_llm_calls=0)
    assert b.exhausted()
    j = RubricJudge(llm=backend)
    v = await j.judge(
        input_data={}, output={}, hypothesis=hypothesis, budget=b
    )
    assert v.passed is False
    assert v.reason == "budget_exhausted"
    assert v.judge_type == "rubric"
    assert len(backend.calls) == 0  # no LLM call made


async def test_rubric_judge_fenced_json_response_parses_like_clean(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    """Regression: fenced rubric-judge JSON must parse identically."""
    verdict = json.dumps({"passed": True, "reason": "ok"})
    fenced = f"```json\n{verdict}\n```"
    backend = MockBackend(responses=["RUBRIC", fenced])
    j = RubricJudge(llm=backend)
    v = await j.judge(
        input_data={"q": "x"},
        output={"o": "y"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert v.passed is True
    assert v.reason == "ok"
    assert v.judge_type == "rubric"


async def test_rubric_judge_empty_output_still_judged(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    backend = MockBackend(
        responses=[
            "RUBRIC",
            json.dumps({"passed": False, "reason": "empty output"}),
        ]
    )
    j = RubricJudge(llm=backend)
    v = await j.judge(
        input_data={"q": "x"},
        output={},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert v.passed is False
    assert v.reason == "empty output"


# ---------- PairwiseJudge ----------


async def test_pairwise_judge_returns_two_verdicts_in_one_call(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    backend = MockBackend(
        responses=[
            json.dumps(
                {
                    "a": {"passed": False, "reason": "missed negation"},
                    "b": {"passed": True, "reason": "handled negation"},
                }
            ),
        ]
    )
    j = PairwiseJudge(llm=backend)
    va, vb = await j.judge_pair(
        input_data={"q": "not organic?"},
        output_a={"answer": "organic list"},
        output_b={"answer": "non-organic list"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert va.passed is False
    assert vb.passed is True
    assert va.judge_type == "pairwise"
    assert vb.judge_type == "pairwise"
    assert len(backend.calls) == 1
    assert budget.calls_used == 1


async def test_pairwise_judge_malformed_response_returns_failing_verdicts(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    backend = MockBackend(responses=["not json"])
    j = PairwiseJudge(llm=backend)
    va, vb = await j.judge_pair(
        input_data={"q": "x"},
        output_a={"o": "a"},
        output_b={"o": "b"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert va.passed is False
    assert vb.passed is False
    assert va.judge_type == "pairwise"
    assert vb.judge_type == "pairwise"


async def test_pairwise_judge_fenced_json_response_parses_like_clean(
    hypothesis: Hypothesis, budget: Budget
) -> None:
    """Regression: fenced pairwise-judge JSON must parse identically."""
    verdict = json.dumps(
        {
            "a": {"passed": False, "reason": "rA"},
            "b": {"passed": True, "reason": "rB"},
        }
    )
    fenced = f"```json\n{verdict}\n```"
    backend = MockBackend(responses=[fenced])
    j = PairwiseJudge(llm=backend)
    va, vb = await j.judge_pair(
        input_data={"q": "x"},
        output_a={"o": "a"},
        output_b={"o": "b"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert va.passed is False
    assert vb.passed is True
    assert va.reason == "rA"
    assert vb.reason == "rB"


async def test_pairwise_judge_budget_exhausted(hypothesis: Hypothesis) -> None:
    b = Budget(max_llm_calls=0)
    backend = MockBackend()
    j = PairwiseJudge(llm=backend)
    va, vb = await j.judge_pair(
        input_data={}, output_a={}, output_b={}, hypothesis=hypothesis, budget=b
    )
    assert va.passed is False
    assert vb.passed is False
    assert va.reason == "budget_exhausted"
    assert vb.reason == "budget_exhausted"
    assert len(backend.calls) == 0
