"""Tests for the Jaccard-based diversity heuristic (Task 1.6)."""

from __future__ import annotations

from hypothesize.core.diversity import diversify_subset
from hypothesize.core.types import TestCase


def _case(text: str, tag: str = "h") -> TestCase:
    return TestCase(
        input_data={"text": text},
        expected_behavior="",
        hypothesis_tag=tag,
        discrimination_evidence={},
    )


def test_returns_all_when_fewer_than_target() -> None:
    cases = [_case("alpha"), _case("beta")]
    assert diversify_subset(cases, 3) == cases


def test_returns_all_when_equal_to_target() -> None:
    cases = [_case("alpha"), _case("beta"), _case("gamma")]
    assert diversify_subset(cases, 3) == cases


def test_picks_distinct_case_over_near_duplicates() -> None:
    near_dup_a = _case("apple banana cherry date")
    near_dup_b = _case("apple banana cherry fig")
    near_dup_c = _case("apple banana cherry grape")
    distinct = _case("xenon yttrium zinc")
    cases = [near_dup_a, near_dup_b, near_dup_c, distinct]
    result = diversify_subset(cases, 2)
    assert len(result) == 2
    assert near_dup_a in result  # seed is first case
    assert distinct in result  # must beat the near-duplicates


def test_is_deterministic_given_same_inputs() -> None:
    cases = [_case(f"tok_{i} other") for i in range(8)]
    r1 = diversify_subset(cases, 4)
    r2 = diversify_subset(cases, 4)
    assert r1 == r2


def test_ties_broken_by_original_order() -> None:
    # Three cases, all equally far from each other → the second selection
    # should be the earliest non-seed case among those tied.
    cases = [_case("alpha"), _case("bravo"), _case("charlie")]
    result = diversify_subset(cases, 2)
    assert result[0] == cases[0]
    assert result[1] == cases[1]


def test_handles_non_string_input_values() -> None:
    def _mixed_case(n: int, text: str) -> TestCase:
        return TestCase(
            input_data={"n": n, "text": text},
            expected_behavior="",
            hypothesis_tag="h",
            discrimination_evidence={},
        )

    cases = [
        _mixed_case(1, "apple"),
        _mixed_case(2, "apple"),
        _mixed_case(3, "orange"),
    ]
    result = diversify_subset(cases, 2)
    assert len(result) == 2


def test_seed_is_always_first_case() -> None:
    cases = [_case("unique seed"), _case("a b"), _case("c d"), _case("e f")]
    result = diversify_subset(cases, 3)
    assert result[0] == cases[0]


def test_empty_input_list_returns_empty() -> None:
    assert diversify_subset([], 5) == []
