"""Factories for the typed objects defined in Feature 01's design.md.

Each factory sets sensible defaults and allows overrides. They are thin
wrappers; tests that need the real objects can construct them directly.

Until Feature 01 task 1.1 lands ``src/hypothesize/core/types.py``, the
imports below fail and each factory raises ``NotImplementedError`` with a
pointer to the task that will unblock it.
"""

from __future__ import annotations

from typing import Any

try:
    from hypothesize.core.types import (
        Budget,
        CandidateInput,
        Hypothesis,
        ProbingDimension,
        Verdict,
    )

    _TYPES_AVAILABLE = True
except ImportError:
    _TYPES_AVAILABLE = False


def _require_types() -> None:
    if not _TYPES_AVAILABLE:
        raise NotImplementedError(
            "hypothesize.core.types is not yet implemented. "
            "See .spec/features/01-core-discrimination/tasks.md task 1.1."
        )


def make_hypothesis(
    text: str = "test hypothesis",
    context_refs: list[str] | None = None,
) -> Hypothesis:
    _require_types()
    return Hypothesis(text=text, context_refs=context_refs or [])


def make_dimension(
    name: str = "dim1",
    description: str = "probe",
    examples: list[str] | None = None,
) -> ProbingDimension:
    _require_types()
    return ProbingDimension(name=name, description=description, examples=examples or [])


def make_candidate(
    input_data: dict[str, Any] | None = None,
    dimension: str = "dim1",
    rationale: str = "because",
) -> CandidateInput:
    _require_types()
    return CandidateInput(
        input_data=input_data if input_data is not None else {"q": "sample"},
        dimension=dimension,
        rationale=rationale,
    )


def make_verdict(
    passed: bool = True,
    reason: str = "ok",
    judge_type: str = "rubric",
) -> Verdict:
    _require_types()
    return Verdict(passed=passed, reason=reason, judge_type=judge_type)


def make_budget(max_llm_calls: int = 200) -> Budget:
    _require_types()
    return Budget(max_llm_calls=max_llm_calls)
