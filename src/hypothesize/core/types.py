"""Core types for the discrimination algorithm.

All types are pydantic v2 models. Frozen where immutability aids reasoning
(Hypothesis, ProbingDimension, CandidateInput, Verdict, TestCase,
InsufficientEvidence, DiscriminationResult). Budget is mutable because it
accumulates charges across an async pipeline.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

JudgeType = Literal["exact_match", "rubric", "pairwise"]
DiscriminationStatus = Literal["ok", "insufficient_evidence"]


class Hypothesis(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    context_refs: list[str] = Field(default_factory=list)


class ProbingDimension(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    examples: list[str] = Field(default_factory=list)


class CandidateInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_data: dict[str, Any]
    dimension: str
    rationale: str


class Verdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    passed: bool
    reason: str
    judge_type: JudgeType


class TestCase(BaseModel):
    __test__ = False  # prevent pytest from collecting this as a test class

    model_config = ConfigDict(frozen=True)

    input_data: dict[str, Any]
    expected_behavior: str
    hypothesis_tag: str
    discrimination_evidence: dict[str, Any]


class Budget(BaseModel):
    max_llm_calls: int = 200
    calls_used: int = 0

    def charge(self, n: int = 1) -> None:
        self.calls_used += n

    def remaining(self) -> int:
        return max(0, self.max_llm_calls - self.calls_used)

    def exhausted(self) -> bool:
        return self.calls_used >= self.max_llm_calls


class InsufficientEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str
    candidates_tried: int
    discriminating_found: int


class DiscriminationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: DiscriminationStatus
    test_cases: list[TestCase] = Field(default_factory=list)
    insufficient: InsufficientEvidence | None = None
    budget_used: int
