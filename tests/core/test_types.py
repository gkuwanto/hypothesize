"""Tests for core types (Task 1.1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hypothesize.core.types import (
    Budget,
    CandidateInput,
    DiscriminationResult,
    Hypothesis,
    InsufficientEvidence,
    ProbingDimension,
    TestCase,
    Verdict,
)


def test_hypothesis_instantiates_with_defaults() -> None:
    h = Hypothesis(text="system fails on negation")
    assert h.text == "system fails on negation"
    assert h.context_refs == []


def test_hypothesis_is_frozen() -> None:
    h = Hypothesis(text="x")
    with pytest.raises(ValidationError):
        h.text = "y"  # type: ignore[misc]


def test_probing_dimension_defaults_examples_to_empty() -> None:
    d = ProbingDimension(name="negation", description="probes negated queries")
    assert d.name == "negation"
    assert d.description == "probes negated queries"
    assert d.examples == []


def test_candidate_input_requires_fields() -> None:
    c = CandidateInput(
        input_data={"text": "foo"},
        dimension="negation",
        rationale="probes negated handling",
    )
    assert c.input_data == {"text": "foo"}
    assert c.dimension == "negation"
    assert c.rationale == "probes negated handling"


def test_verdict_judge_type_literal_enforced() -> None:
    v = Verdict(passed=False, reason="missed negation", judge_type="rubric")
    assert v.passed is False
    assert v.judge_type == "rubric"
    with pytest.raises(ValidationError):
        Verdict(passed=True, reason="ok", judge_type="not_a_judge")  # type: ignore[arg-type]


def test_verdict_is_frozen() -> None:
    v = Verdict(passed=True, reason="ok", judge_type="exact_match")
    with pytest.raises(ValidationError):
        v.passed = False  # type: ignore[misc]


def test_testcase_roundtrips_through_serialization() -> None:
    tc = TestCase(
        input_data={"q": "which products are NOT organic?"},
        expected_behavior="answers with non-organic products",
        hypothesis_tag="negation handling",
        discrimination_evidence={
            "current_output": {"answer": "organic list"},
            "alternative_output": {"answer": "non-organic list"},
        },
    )
    data = tc.model_dump()
    restored = TestCase.model_validate(data)
    assert restored == tc


def test_testcase_is_frozen() -> None:
    tc = TestCase(
        input_data={"q": "x"},
        expected_behavior="y",
        hypothesis_tag="z",
        discrimination_evidence={},
    )
    with pytest.raises(ValidationError):
        tc.expected_behavior = "changed"  # type: ignore[misc]


def test_budget_defaults_to_two_hundred_max_calls() -> None:
    b = Budget()
    assert b.max_llm_calls == 200
    assert b.calls_used == 0


def test_budget_charge_increments_calls_used() -> None:
    b = Budget(max_llm_calls=10)
    b.charge()
    assert b.calls_used == 1
    b.charge(3)
    assert b.calls_used == 4


def test_budget_remaining_clamped_at_zero() -> None:
    b = Budget(max_llm_calls=5)
    b.charge(3)
    assert b.remaining() == 2
    b.charge(10)
    assert b.remaining() == 0


def test_budget_exhausted_when_used_reaches_cap() -> None:
    b = Budget(max_llm_calls=2)
    assert not b.exhausted()
    b.charge()
    assert not b.exhausted()
    b.charge()
    assert b.exhausted()
    b.charge()
    assert b.exhausted()


def test_budget_charge_never_raises_on_exhaustion() -> None:
    b = Budget(max_llm_calls=1)
    b.charge(1)
    b.charge(100)
    assert b.exhausted()
    assert b.calls_used == 101


def test_budget_is_mutable() -> None:
    b = Budget(max_llm_calls=5)
    b.calls_used = 2
    assert b.calls_used == 2


def test_insufficient_evidence_carries_counts() -> None:
    ie = InsufficientEvidence(
        reason="only 1 discriminating found",
        candidates_tried=12,
        discriminating_found=1,
    )
    assert ie.candidates_tried == 12
    assert ie.discriminating_found == 1


def test_discrimination_result_ok_status() -> None:
    tc = TestCase(
        input_data={"q": "x"},
        expected_behavior="b",
        hypothesis_tag="h",
        discrimination_evidence={},
    )
    r = DiscriminationResult(status="ok", test_cases=[tc], budget_used=5)
    assert r.status == "ok"
    assert r.test_cases == [tc]
    assert r.insufficient is None
    assert r.budget_used == 5


def test_discrimination_result_insufficient_evidence_branch() -> None:
    ie = InsufficientEvidence(
        reason="not enough",
        candidates_tried=3,
        discriminating_found=1,
    )
    r = DiscriminationResult(
        status="insufficient_evidence",
        insufficient=ie,
        budget_used=17,
    )
    assert r.status == "insufficient_evidence"
    assert r.test_cases == []
    assert r.insufficient == ie


def test_discrimination_result_roundtrips() -> None:
    ie = InsufficientEvidence(
        reason="x",
        candidates_tried=5,
        discriminating_found=2,
    )
    r = DiscriminationResult(
        status="insufficient_evidence",
        insufficient=ie,
        budget_used=9,
    )
    restored = DiscriminationResult.model_validate(r.model_dump())
    assert restored == r
