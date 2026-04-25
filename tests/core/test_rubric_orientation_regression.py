"""Offline regression tests pinning the rubric orientation contract.

Background: the SMOKE_2 run on 2026-04-24 exposed a stochastic rubric
semantic inversion — `build_rubric_prompt` / `rubric_judge_prompt` did not
constrain whether `passed=true` meant "system handles the case correctly"
or "system exhibits the failure", and real Haiku coin-flipped the
orientation from run to run. The rubric orientation diagnostic
(`scripts/diagnostics/RUBRIC_FINDINGS.md`) nailed down the fix: tighten
the prompts to pin `passed=true = handles correctly, does NOT exhibit
failure`. These tests pin that contract so any future regression in the
prompts, in `RubricJudge`, or in `find_discriminating_inputs`'
discrimination predicate is caught offline by the suite.

The contract under test:

    `discrimination.py` appends a ``TestCase`` for a candidate iff
        ``not current_verdict.passed and alt_verdict.passed``

    which, combined with the orientation convention, means "current
    exhibits the failure AND alternative handles correctly". With a
    correctly-oriented judge, a current-fails / alt-passes pair must
    trigger that predicate; with both-pass or both-fail pairs, it must
    not.

These tests do not touch a real LLM — they use ``MockBackend`` to script
exactly the rubric-build and rubric-judge payloads the algorithm will
receive, and assert on the shape of the resulting
``DiscriminationResult``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from hypothesize.core.discrimination import find_discriminating_inputs
from hypothesize.core.judge import RubricJudge
from hypothesize.core.types import Budget, Hypothesis
from tests._fixtures.mock_backend import MockBackend

# Success-descriptor rubric text — this is the kind of rubric the tightened
# `build_rubric_prompt` should produce. The literal text does not matter
# for these tests; what matters is that the downstream judge payloads are
# correctly oriented.
SUCCESS_DESCRIPTOR_RUBRIC = (
    "# Rubric: Sarcasm Handling\n"
    "**PASSING CONVENTION: passed=true means the classifier correctly "
    "handled the sarcastic input (did NOT exhibit the failure). "
    "passed=false means the classifier exhibited the failure.**\n"
    "- The classifier correctly identifies the sentiment despite "
    "surface-positive tokens indicating sarcasm.\n"
    "- The classifier's label matches the speaker's true negative intent.\n"
)


def _dims_payload(n: int) -> str:
    return json.dumps(
        {
            "dimensions": [
                {
                    "name": f"d{i}",
                    "description": f"description {i}",
                    "examples": [f"ex{i}"],
                }
                for i in range(n)
            ]
        }
    )


def _candidates_payload(inputs: list[dict[str, Any]]) -> str:
    return json.dumps(
        {
            "candidates": [
                {"input_data": inp, "rationale": "probes sarcasm"}
                for inp in inputs
            ]
        }
    )


def _judgment(passed: bool, reason: str) -> str:
    return json.dumps({"passed": passed, "reason": reason})


@pytest.fixture
def hypothesis() -> Hypothesis:
    return Hypothesis(
        text=(
            "the sentiment classifier fails on sarcastic positive text "
            "(surface tokens positive, intent negative)"
        )
    )


async def _current_runner_positive(input_data: dict[str, Any]) -> dict[str, Any]:
    """Stand-in for the broken classifier under test."""
    return {"sentiment": "positive"}


async def _alt_runner_negative(input_data: dict[str, Any]) -> dict[str, Any]:
    """Stand-in for a sarcasm-aware alternative classifier."""
    return {"sentiment": "negative"}


# ---------- Case 1: correctly-oriented, current fails, alt passes -> fires


async def test_discrimination_fires_on_correct_orientation(
    hypothesis: Hypothesis,
) -> None:
    """With a correctly-oriented judge, a current-fails / alt-passes pair
    must trigger the discrimination predicate. This is the headline
    regression for SMOKE_2's silent inversion bug.
    """
    # 3 dims, 3 candidates each (the minimum per_dim_count)
    backend = MockBackend(
        responses=[
            _dims_payload(3),
            _candidates_payload(
                [{"text": f"sarc {i} dim0"} for i in range(3)]
            ),
            _candidates_payload(
                [{"text": f"sarc {i} dim1"} for i in range(3)]
            ),
            _candidates_payload(
                [{"text": f"sarc {i} dim2"} for i in range(3)]
            ),
            SUCCESS_DESCRIPTOR_RUBRIC,  # rubric_build
            # 9 candidates × 2 judge calls each = 18 judgments.
            # Orientation is correct: current=positive (wrong) → passed=False,
            # alt=negative (right) → passed=True.
            *(
                payload
                for _ in range(9)
                for payload in (
                    _judgment(False, "current exhibited the failure"),
                    _judgment(True, "alternative handled correctly"),
                )
            ),
        ]
    )
    budget = Budget(max_llm_calls=100)
    judge = RubricJudge(llm=backend)

    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_current_runner_positive,
        alternative_runner=_alt_runner_negative,
        context=[],
        judge=judge,
        llm=backend,
        budget=budget,
        target_n=5,
        min_required=3,
    )

    assert result.status == "ok"
    assert len(result.test_cases) >= 3
    # Every discriminating case must have captured both outputs in evidence.
    for tc in result.test_cases:
        evidence = tc.discrimination_evidence
        assert evidence["current_output"] == {"sentiment": "positive"}
        assert evidence["alternative_output"] == {"sentiment": "negative"}
        assert evidence["current_verdict"]["passed"] is False
        assert evidence["alternative_verdict"]["passed"] is True


# ---------- Case 2: both pass -> does NOT discriminate


async def test_no_discrimination_when_both_pass(
    hypothesis: Hypothesis,
) -> None:
    """Neither system exhibits the failure — nothing to discriminate on."""
    backend = MockBackend(
        responses=[
            _dims_payload(3),
            _candidates_payload([{"text": f"sarc {i}"} for i in range(3)]),
            _candidates_payload([{"text": f"sarc {i} b"} for i in range(3)]),
            _candidates_payload([{"text": f"sarc {i} c"} for i in range(3)]),
            SUCCESS_DESCRIPTOR_RUBRIC,
            *(
                payload
                for _ in range(9)
                for payload in (
                    _judgment(True, "current also handles correctly"),
                    _judgment(True, "alternative handles correctly"),
                )
            ),
        ]
    )
    budget = Budget(max_llm_calls=100)
    judge = RubricJudge(llm=backend)

    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_current_runner_positive,
        alternative_runner=_alt_runner_negative,
        context=[],
        judge=judge,
        llm=backend,
        budget=budget,
        target_n=5,
        min_required=3,
    )

    assert result.status == "insufficient_evidence"
    assert result.insufficient is not None
    assert result.insufficient.discriminating_found == 0
    assert result.insufficient.candidates_tried == 9


# ---------- Case 3: both fail -> does NOT discriminate


async def test_no_discrimination_when_both_fail(
    hypothesis: Hypothesis,
) -> None:
    """Both systems exhibit the failure — also no discrimination signal."""
    backend = MockBackend(
        responses=[
            _dims_payload(3),
            _candidates_payload([{"text": f"sarc {i}"} for i in range(3)]),
            _candidates_payload([{"text": f"sarc {i} b"} for i in range(3)]),
            _candidates_payload([{"text": f"sarc {i} c"} for i in range(3)]),
            SUCCESS_DESCRIPTOR_RUBRIC,
            *(
                payload
                for _ in range(9)
                for payload in (
                    _judgment(False, "current exhibits the failure"),
                    _judgment(False, "alternative also exhibits the failure"),
                )
            ),
        ]
    )
    budget = Budget(max_llm_calls=100)
    judge = RubricJudge(llm=backend)

    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_current_runner_positive,
        alternative_runner=_alt_runner_negative,
        context=[],
        judge=judge,
        llm=backend,
        budget=budget,
        target_n=5,
        min_required=3,
    )

    assert result.status == "insufficient_evidence"
    assert result.insufficient is not None
    assert result.insufficient.discriminating_found == 0


# ---------- Case 4: inverted-orientation mock -> predicate stays silent


async def test_no_discrimination_under_inverted_mock(
    hypothesis: Hypothesis,
) -> None:
    """Sanity: the discrimination predicate is on the right side of polarity.

    If the judge were returning the inverted convention — passed=true for
    "current exhibits the failure", passed=false for "alternative handles
    correctly" — the predicate `not current.passed AND alt.passed` would
    evaluate to `not True AND False = False` for every candidate. This
    test pins that expectation so a future change to the predicate that
    re-inverts it (e.g. "pass iff current.passed and not alt.passed")
    doesn't silently slip through.
    """
    backend = MockBackend(
        responses=[
            _dims_payload(3),
            _candidates_payload([{"text": f"sarc {i}"} for i in range(3)]),
            _candidates_payload([{"text": f"sarc {i} b"} for i in range(3)]),
            _candidates_payload([{"text": f"sarc {i} c"} for i in range(3)]),
            SUCCESS_DESCRIPTOR_RUBRIC,
            *(
                payload
                for _ in range(9)
                for payload in (
                    # Inverted mock: current flagged passed=True (exhibits
                    # failure under the wrong convention), alt flagged
                    # passed=False.
                    _judgment(True, "inverted: current 'satisfies' rubric"),
                    _judgment(False, "inverted: alt 'does not satisfy' rubric"),
                )
            ),
        ]
    )
    budget = Budget(max_llm_calls=100)
    judge = RubricJudge(llm=backend)

    result = await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=_current_runner_positive,
        alternative_runner=_alt_runner_negative,
        context=[],
        judge=judge,
        llm=backend,
        budget=budget,
        target_n=5,
        min_required=3,
    )

    assert result.status == "insufficient_evidence"
    assert result.insufficient is not None
    assert result.insufficient.discriminating_found == 0
