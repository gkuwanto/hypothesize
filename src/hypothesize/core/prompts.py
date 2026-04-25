"""Prompt builders used by the core algorithm.

Prompts are kept together here so iteration is easy and every LLM-shaped
string in the core layer is grep-able from one file.

Each builder takes typed inputs and returns a list of chat messages in the
``{"role": ..., "content": ...}`` shape expected by ``LLMBackend.complete``.
"""

from __future__ import annotations

import json
from typing import Any

from hypothesize.core.types import Hypothesis, ProbingDimension


def _context_block(context: list[str]) -> str:
    if not context:
        return "(no additional context provided)"
    return "\n".join(f"- {line}" for line in context)


def decompose_hypothesis_prompt(
    hypothesis: Hypothesis, context: list[str]
) -> list[dict]:
    """Ask the LLM to split a hypothesis into 3-7 probing dimensions."""
    system = (
        "You decompose a failure hypothesis about an LLM-powered system into "
        "between 3 and 7 orthogonal probing dimensions. Each dimension names "
        "a distinct axis along which inputs can vary to test the hypothesis."
    )
    user = (
        f"Hypothesis: {hypothesis.text}\n\n"
        f"Context:\n{_context_block(context)}\n\n"
        "Return STRICT JSON with the schema:\n"
        '{"dimensions": ['
        '{"name": str, "description": str, "examples": [str, ...]}'
        ", ...]}\n"
        "Return between 3 and 7 dimensions. No prose outside the JSON object."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def generate_candidates_prompt(
    hypothesis: Hypothesis,
    dimension: ProbingDimension,
    context: list[str],
    n: int,
) -> list[dict]:
    """Ask the LLM to produce n candidate inputs for one probing dimension."""
    system = (
        "You design inputs that probe a specific dimension of a failure "
        "hypothesis about an LLM-powered system. The inputs should be "
        "realistic, varied, and likely to expose the hypothesized failure."
    )
    user = (
        f"Hypothesis: {hypothesis.text}\n\n"
        f"Probing dimension: {dimension.name}\n"
        f"Description: {dimension.description}\n"
        f"Dimension examples: {json.dumps(dimension.examples)}\n\n"
        f"Context:\n{_context_block(context)}\n\n"
        f"Produce exactly {n} candidate inputs. Return STRICT JSON:\n"
        '{"candidates": ['
        '{"input_data": {...}, "rationale": str}'
        ", ...]}\n"
        "Each input_data must be a non-empty JSON object whose shape is "
        "appropriate to the hypothesis (e.g. {\"text\": ...} for a classifier "
        "or {\"question\": ...} for a RAG system). "
        "No prose outside the JSON object."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_rubric_prompt(hypothesis: Hypothesis) -> list[dict]:
    """Ask the LLM to produce a rubric for judging outputs against a hypothesis.

    The prompt pins a fixed orientation convention: ``passed=true`` means
    the system handled the case correctly (did NOT exhibit the hypothesized
    failure). Criteria are required to be success-descriptors — properties
    of a correctly-handling output — so that "satisfies all criteria" lines
    up with "did NOT exhibit the failure" on the downstream judge.
    """
    system = (
        "You write concise evaluation rubrics. Given a failure hypothesis, "
        "produce a short rubric an evaluator can use to decide whether an "
        "output passes or fails with respect to the hypothesis.\n\n"
        "ORIENTATION CONVENTION (must be followed): passed=true means the "
        "system handled the case correctly — it does NOT exhibit the "
        "hypothesized failure. passed=false means the system did exhibit "
        "the failure. Write every rubric criterion as a success-descriptor "
        "— a property of a correctly-handling output — so that 'satisfies "
        "the criterion' = 'did NOT exhibit the hypothesized failure'. Do "
        "NOT write criteria as failure-descriptors (e.g. 'output "
        "contradicts true sentiment'); write the positive form instead "
        "(e.g. 'output correctly identifies the sentiment despite "
        "surface-positive tokens indicating sarcasm')."
    )
    user = (
        f"Hypothesis: {hypothesis.text}\n\n"
        "Write a rubric (3-6 bullet criteria). An output passes only if it "
        "satisfies all criteria, where 'passes' means the output does NOT "
        "exhibit the hypothesized failure. State the convention explicitly "
        "in the rubric header so a downstream evaluator cannot misread it. "
        "Plain text, no JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def rubric_judge_prompt(
    rubric: str, input_data: dict[str, Any], output: dict[str, Any]
) -> list[dict]:
    """Ask the LLM to score an output against a rubric.

    Repeats the orientation convention as a belt-and-suspenders safeguard —
    even if the rubric body omits the convention header, the judge itself
    is instructed to interpret ``passed=true`` as "handles correctly, does
    NOT exhibit the failure".
    """
    system = (
        "You apply a rubric to an input/output pair. Return a strict JSON "
        'object: {"passed": bool, "reason": str}. "reason" is one short '
        "sentence. No prose outside the JSON.\n\n"
        "CRITICAL: passed=true means the system handled the case correctly "
        "— it does NOT exhibit the hypothesized failure described in the "
        "rubric. passed=false means the system DID exhibit the failure. "
        "Apply this orientation on every judgment regardless of how the "
        "rubric is phrased."
    )
    user = (
        f"Rubric:\n{rubric}\n\n"
        f"Input: {json.dumps(input_data)}\n"
        f"Output: {json.dumps(output)}\n\n"
        'Respond with {"passed": ..., "reason": ...}.'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def pairwise_judge_prompt(
    hypothesis: Hypothesis,
    input_data: dict[str, Any],
    output_a: dict[str, Any],
    output_b: dict[str, Any],
) -> list[dict]:
    """Ask the LLM to judge two outputs side-by-side against a hypothesis."""
    system = (
        "You evaluate two candidate outputs against a failure hypothesis. "
        "For each output, decide whether it passes (does NOT exhibit the "
        'failure). Return strict JSON of shape {"a": {"passed": bool, '
        '"reason": str}, "b": {"passed": bool, "reason": str}}.'
    )
    user = (
        f"Hypothesis: {hypothesis.text}\n\n"
        f"Input: {json.dumps(input_data)}\n"
        f"Output A: {json.dumps(output_a)}\n"
        f"Output B: {json.dumps(output_b)}\n\n"
        "Respond with strict JSON only."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
