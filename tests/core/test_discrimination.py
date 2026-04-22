"""Tests for find_discriminating_inputs (Task 1.6)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from hypothesize.core.discrimination import find_discriminating_inputs
from hypothesize.core.judge import ExactMatchJudge
from hypothesize.core.types import Budget, Hypothesis
from tests._fixtures.mock_backend import MockBackend


@pytest.fixture
def hypothesis() -> Hypothesis:
    return Hypothesis(text="system mishandles negated queries")


def _decompose(n_dims: int) -> str:
    return json.dumps(
        {
            "dimensions": [
                {
                    "name": f"d{i}",
                    "description": f"desc {i}",
                    "examples": [],
                }
                for i in range(n_dims)
            ]
        }
    )


def _candidates(items: list[dict]) -> str:
    return json.dumps({"candidates": items})


def _candidate_item(text: str, expected: str) -> dict:
    return {
        "input_data": {"text": text, "expected": expected},
        "rationale": f"probes {text}",
    }


async def _current_runner_always_wrong(input_data: dict[str, Any]) -> dict:
    return {"prediction": "wrong"}


async def _alt_runner_mirrors_expected(input_data: dict[str, Any]) -> dict:
    return {"prediction": input_data.get("expected", "wrong")}


# ---------------- happy path ----------------


async def test_happy_path_returns_ok_with_target_n_cases(
    hypothesis: Hypothesis,
) -> None:
    """3 dims × 3 candidates each, all 9 discriminate; diversify to target_n=3."""
    n_dims = 3
    per_dim = 3  # max(3, min(5, (6*2)//3)) == 3 for target_n=3, 3 dims

    all_items_per_dim = [
        [_candidate_item(f"d{d}_c{c}_unique_tok_{d}{c}", "correct") for c in range(per_dim)]
        for d in range(n_dims)
    ]
    backend = MockBackend(
        responses=[
            _decompose(n_dims),
            *(_candidates(items) for items in all_items_per_dim),
        ]
    )
    budget = Budget(max_llm_calls=20)
    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_current_runner_always_wrong,
        alternative_runner=_alt_runner_mirrors_expected,
        context=[],
        judge=ExactMatchJudge(expected_key="expected", output_key="prediction"),
        llm=backend,
        budget=budget,
        target_n=3,
        min_required=3,
    )
    assert result.status == "ok"
    assert len(result.test_cases) == 3
    assert all(tc.hypothesis_tag == hypothesis.text for tc in result.test_cases)
    assert result.budget_used == 4  # decompose + 3 generate; no judge calls
    # Evidence captured
    evidence = result.test_cases[0].discrimination_evidence
    assert "current_output" in evidence
    assert "alternative_output" in evidence


# ---------------- insufficient evidence: too few discriminating ----------------


async def test_insufficient_evidence_when_not_enough_discriminate(
    hypothesis: Hypothesis,
) -> None:
    """Only 2 of 9 candidates actually discriminate → insufficient_evidence."""
    n_dims = 3
    per_dim = 3
    items = [
        [_candidate_item(f"d{d}_c{c}", "wrong") for c in range(per_dim)]
        for d in range(n_dims)
    ]
    # Mark the first two as "correct" so they discriminate
    items[0][0] = _candidate_item("d0_c0", "correct")
    items[1][0] = _candidate_item("d1_c0", "correct")
    backend = MockBackend(
        responses=[
            _decompose(n_dims),
            *(_candidates(batch) for batch in items),
        ]
    )
    budget = Budget(max_llm_calls=20)
    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_current_runner_always_wrong,
        alternative_runner=_alt_runner_mirrors_expected,
        context=[],
        judge=ExactMatchJudge(expected_key="expected", output_key="prediction"),
        llm=backend,
        budget=budget,
        target_n=10,
        min_required=3,
    )
    assert result.status == "insufficient_evidence"
    assert result.insufficient is not None
    assert result.insufficient.discriminating_found == 2
    assert result.insufficient.candidates_tried == 9
    assert result.test_cases == []


# ---------------- insufficient evidence: decomposition failed ----------------


async def test_insufficient_evidence_when_decomposition_fails(
    hypothesis: Hypothesis,
) -> None:
    backend = MockBackend(responses=["not valid json"])
    budget = Budget(max_llm_calls=20)
    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_current_runner_always_wrong,
        alternative_runner=_alt_runner_mirrors_expected,
        context=[],
        judge=ExactMatchJudge(expected_key="expected", output_key="prediction"),
        llm=backend,
        budget=budget,
        target_n=3,
        min_required=3,
    )
    assert result.status == "insufficient_evidence"
    assert result.insufficient is not None
    assert "decomposition" in result.insufficient.reason.lower()
    assert result.insufficient.candidates_tried == 0
    assert result.insufficient.discriminating_found == 0


# ---------------- budget exhaustion mid-run ----------------


async def test_budget_exhaustion_during_generate_phase(
    hypothesis: Hypothesis,
) -> None:
    """Budget runs out after decompose + 1 generate call → only 3 candidates."""
    n_dims = 3
    per_dim = 3
    items = [
        [_candidate_item(f"d{d}_c{c}", "correct") for c in range(per_dim)]
        for d in range(n_dims)
    ]
    backend = MockBackend(
        responses=[
            _decompose(n_dims),
            *(_candidates(batch) for batch in items),
        ]
    )
    # Budget of 2 allows decompose (1) + one generate (1); third call sees
    # exhausted budget and breaks the generate loop.
    budget = Budget(max_llm_calls=2)
    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_current_runner_always_wrong,
        alternative_runner=_alt_runner_mirrors_expected,
        context=[],
        judge=ExactMatchJudge(expected_key="expected", output_key="prediction"),
        llm=backend,
        budget=budget,
        target_n=10,
        min_required=5,  # 3 candidates < min_required → insufficient
    )
    assert result.status == "insufficient_evidence"
    assert result.insufficient is not None
    assert result.insufficient.candidates_tried == 3
    assert result.budget_used == 2


# ---------------- diversity pruning ----------------


async def test_diversity_pruning_from_oversized_set(
    hypothesis: Hypothesis,
) -> None:
    """9 discriminating candidates, target_n=3 → diversify picks 3."""
    n_dims = 3
    per_dim = 3

    # Give each candidate distinct tokens so diversity selection is meaningful
    items = [
        [
            _candidate_item(
                f"unique_dim_{d}_case_{c}_token_{d * 100 + c}",
                "correct",
            )
            for c in range(per_dim)
        ]
        for d in range(n_dims)
    ]
    backend = MockBackend(
        responses=[
            _decompose(n_dims),
            *(_candidates(batch) for batch in items),
        ]
    )
    budget = Budget(max_llm_calls=20)
    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_current_runner_always_wrong,
        alternative_runner=_alt_runner_mirrors_expected,
        context=[],
        judge=ExactMatchJudge(expected_key="expected", output_key="prediction"),
        llm=backend,
        budget=budget,
        target_n=3,
        min_required=3,
    )
    assert result.status == "ok"
    assert len(result.test_cases) == 3
    # All 3 should have distinct input_data
    texts = {tc.input_data["text"] for tc in result.test_cases}
    assert len(texts) == 3


# ---------------- determinism ----------------


async def test_deterministic_given_same_script(hypothesis: Hypothesis) -> None:
    n_dims = 3
    per_dim = 3
    items = [
        [_candidate_item(f"d{d}_c{c}_tok{d}{c}", "correct") for c in range(per_dim)]
        for d in range(n_dims)
    ]
    script = [
        _decompose(n_dims),
        *(_candidates(batch) for batch in items),
    ]

    async def _run() -> list[str]:
        backend = MockBackend(responses=list(script))
        budget = Budget(max_llm_calls=20)
        result = await find_discriminating_inputs(
            hypothesis=hypothesis,
            current_runner=_current_runner_always_wrong,
            alternative_runner=_alt_runner_mirrors_expected,
            context=[],
            judge=ExactMatchJudge(
                expected_key="expected", output_key="prediction"
            ),
            llm=backend,
            budget=budget,
            target_n=3,
            min_required=3,
        )
        assert result.status == "ok"
        return [tc.input_data["text"] for tc in result.test_cases]

    first = await _run()
    second = await _run()
    assert first == second
