"""Judge strategies.

Three judges satisfy (or nearly satisfy) a common ``Judge`` protocol. All
three share the same ``Verdict`` return type, charge the injected
``Budget`` for every live LLM call, and degrade to
``Verdict(passed=False, reason="budget_exhausted", ...)`` when the budget
is exhausted before a call is made.

- ``ExactMatchJudge`` makes no LLM call. It compares a field in ``output``
  against an expected value taken from ``input_data``.
- ``RubricJudge`` builds a rubric once per hypothesis and caches it, then
  judges each output against that rubric.
- ``PairwiseJudge`` compares two outputs in a single LLM call. Its method
  is named ``judge_pair`` because the pairwise shape does not fit the
  single-output ``Judge`` protocol; it is offered alongside rubric judging
  for callers that prefer head-to-head comparison.
"""

from __future__ import annotations

from typing import Any, Protocol

from hypothesize.core.json_extract import parse_json_response
from hypothesize.core.llm import LLMBackend
from hypothesize.core.prompts import (
    build_rubric_prompt,
    pairwise_judge_prompt,
    rubric_judge_prompt,
)
from hypothesize.core.types import Budget, Hypothesis, Verdict


class Judge(Protocol):
    """Single-output judge protocol."""

    async def judge(
        self,
        input_data: dict[str, Any],
        output: dict[str, Any],
        hypothesis: Hypothesis,
        budget: Budget,
    ) -> Verdict: ...


def _budget_exhausted_verdict(judge_type: str) -> Verdict:
    return Verdict(
        passed=False,
        reason="budget_exhausted",
        judge_type=judge_type,  # type: ignore[arg-type]
    )


def _parse_verdict_payload(text: str) -> dict[str, Any] | None:
    data = parse_json_response(text)
    if not isinstance(data, dict):
        return None
    return data


class ExactMatchJudge:
    """Pass iff ``output[output_key] == input_data[expected_key]``.

    Used when the input carries a ground-truth label and the output has a
    specific prediction field. No LLM call.
    """

    def __init__(self, expected_key: str, output_key: str) -> None:
        self.expected_key = expected_key
        self.output_key = output_key

    async def judge(
        self,
        input_data: dict[str, Any],
        output: dict[str, Any],
        hypothesis: Hypothesis,
        budget: Budget,
    ) -> Verdict:
        if budget.exhausted():
            return _budget_exhausted_verdict("exact_match")
        if self.expected_key not in input_data:
            return Verdict(
                passed=False,
                reason=f"missing expected field {self.expected_key!r} in input",
                judge_type="exact_match",
            )
        if self.output_key not in output:
            return Verdict(
                passed=False,
                reason=f"missing output field {self.output_key!r}",
                judge_type="exact_match",
            )
        expected = input_data[self.expected_key]
        actual = output[self.output_key]
        if expected == actual:
            return Verdict(
                passed=True,
                reason=f"{self.output_key}={actual!r} matches expected",
                judge_type="exact_match",
            )
        return Verdict(
            passed=False,
            reason=f"mismatch: expected {expected!r}, got {actual!r}",
            judge_type="exact_match",
        )


class RubricJudge:
    """Generate a rubric once per hypothesis; judge each output against it."""

    def __init__(self, llm: LLMBackend) -> None:
        self.llm = llm
        self._rubric_cache: dict[str, str] = {}

    async def _build_rubric(
        self, hypothesis: Hypothesis, budget: Budget
    ) -> str | None:
        if budget.exhausted():
            return None
        messages = build_rubric_prompt(hypothesis)
        rubric = await self.llm.complete(messages)
        budget.charge()
        return rubric

    async def judge(
        self,
        input_data: dict[str, Any],
        output: dict[str, Any],
        hypothesis: Hypothesis,
        budget: Budget,
    ) -> Verdict:
        if budget.exhausted():
            return _budget_exhausted_verdict("rubric")

        rubric = self._rubric_cache.get(hypothesis.text)
        if rubric is None:
            rubric = await self._build_rubric(hypothesis, budget)
            if rubric is None:
                return _budget_exhausted_verdict("rubric")
            self._rubric_cache[hypothesis.text] = rubric

        if budget.exhausted():
            return _budget_exhausted_verdict("rubric")

        messages = rubric_judge_prompt(rubric, input_data, output)
        raw = await self.llm.complete(messages)
        budget.charge()

        payload = _parse_verdict_payload(raw)
        if (
            payload is None
            or "passed" not in payload
            or not isinstance(payload["passed"], bool)
        ):
            return Verdict(
                passed=False,
                reason="malformed judge response",
                judge_type="rubric",
            )
        return Verdict(
            passed=payload["passed"],
            reason=str(payload.get("reason", "")),
            judge_type="rubric",
        )


class PairwiseJudge:
    """Compare two outputs side-by-side in one LLM call."""

    def __init__(self, llm: LLMBackend) -> None:
        self.llm = llm

    async def judge_pair(
        self,
        input_data: dict[str, Any],
        output_a: dict[str, Any],
        output_b: dict[str, Any],
        hypothesis: Hypothesis,
        budget: Budget,
    ) -> tuple[Verdict, Verdict]:
        if budget.exhausted():
            v = _budget_exhausted_verdict("pairwise")
            return v, v

        messages = pairwise_judge_prompt(hypothesis, input_data, output_a, output_b)
        raw = await self.llm.complete(messages)
        budget.charge()

        payload = _parse_verdict_payload(raw)
        if payload is None or "a" not in payload or "b" not in payload:
            fail = Verdict(
                passed=False,
                reason="malformed pairwise response",
                judge_type="pairwise",
            )
            return fail, fail

        def _one(side: dict[str, Any]) -> Verdict:
            if not isinstance(side, dict) or not isinstance(
                side.get("passed"), bool
            ):
                return Verdict(
                    passed=False,
                    reason="malformed pairwise response",
                    judge_type="pairwise",
                )
            return Verdict(
                passed=side["passed"],
                reason=str(side.get("reason", "")),
                judge_type="pairwise",
            )

        return _one(payload["a"]), _one(payload["b"])
