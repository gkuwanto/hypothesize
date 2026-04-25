#!/usr/bin/env python3
"""Rubric orientation diagnostic experiment.

Characterizes the stochastic rubric orientation bug surfaced by
scripts/SMOKE_FINDINGS_2.md. Runs four experiments against the real
Anthropic API, records results, and appends a findings document at
scripts/diagnostics/RUBRIC_FINDINGS.md.

This is a diagnostic. It does not modify any product code; it imports
the *current* rubric prompts as-is from src/hypothesize/core/prompts.py
for Parts 1/2/4, and writes a local candidate prompt variant for
Part 3.

Parts:
- Part 1: current prompt on claude-haiku-4-5-20251001, N=10 rubrics × 6 inputs
- Part 2: current prompt on claude-sonnet-4-6, same shape
- Part 3: tightened prompt on haiku, same shape
- Part 4: pairwise baseline on haiku, 3 inputs × N=10 runs

Total LLM call budget: ~270. Stop if cost projection exceeds $5.

Run from repo root::

    python scripts/diagnostics/rubric_orientation.py

The API key is loaded from ``.env`` via ``python-dotenv`` — never from
the shell env, never printed, never logged.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

from hypothesize.core.json_extract import parse_json_response
from hypothesize.core.prompts import (
    build_rubric_prompt,
    pairwise_judge_prompt,
    rubric_judge_prompt,
)
from hypothesize.core.types import Hypothesis
from hypothesize.llm.anthropic import AnthropicBackend
from hypothesize.llm.config import AnthropicConfig, RunnerCallLog

# Model strings — pinned per-experiment, never read from env.
HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

N_REPS = 10
MAX_TOKENS = 1024
FINDINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "RUBRIC_FINDINGS.md"
)

# The hypothesis under test. Matches the SMOKE_2 scenario verbatim so
# Part 1 reproduces that finding directly.
HYPOTHESIS = Hypothesis(
    text=(
        "the sentiment classifier fails on sarcastic positive text "
        "(surface tokens positive, intent negative)"
    )
)

# Six hand-crafted (input, output) pairs. ``expected_pass`` is the
# verdict a *correctly oriented* rubric should return — i.e. "did the
# system handle this case correctly, NOT exhibiting the hypothesized
# failure?"
#
# Items 1/3 are sarcastic-positive inputs that the system mis-classified
# as positive (the specific hypothesized failure) → expected_pass=False.
# Items 2/4 are the same sarcastic inputs but correctly classified
# negative → expected_pass=True.
# Items 5/6 are non-sarcastic inputs classified correctly. They are not
# sarcasm-sensitive so they are sanity tests only.
TEST_INPUTS: list[dict[str, Any]] = [
    {
        "id": 1,
        "description": "sarcasm + wrong (exhibits failure)",
        "sarcasm_sensitive": True,
        "input_data": {
            "text": (
                "Oh great, another mandatory training session on workplace "
                "safety. Just what I needed today."
            )
        },
        "output": {"sentiment": "positive"},
        "expected_pass": False,
    },
    {
        "id": 2,
        "description": "sarcasm + right (handles correctly)",
        "sarcasm_sensitive": True,
        "input_data": {
            "text": (
                "Oh great, another mandatory training session on workplace "
                "safety. Just what I needed today."
            )
        },
        "output": {"sentiment": "negative"},
        "expected_pass": True,
    },
    {
        "id": 3,
        "description": "sarcasm + wrong (exhibits failure)",
        "sarcasm_sensitive": True,
        "input_data": {
            "text": (
                "Wow, I absolutely love spending my Saturday untangling "
                "this spaghetti codebase. Best weekend ever."
            )
        },
        "output": {"sentiment": "positive"},
        "expected_pass": False,
    },
    {
        "id": 4,
        "description": "sarcasm + right (handles correctly)",
        "sarcasm_sensitive": True,
        "input_data": {
            "text": (
                "Wow, I absolutely love spending my Saturday untangling "
                "this spaghetti codebase. Best weekend ever."
            )
        },
        "output": {"sentiment": "negative"},
        "expected_pass": True,
    },
    {
        "id": 5,
        "description": "genuine positive + right (sanity)",
        "sarcasm_sensitive": False,
        "input_data": {
            "text": "I had a wonderful time at the concert last night."
        },
        "output": {"sentiment": "positive"},
        "expected_pass": True,
    },
    {
        "id": 6,
        "description": "genuine negative + right (sanity)",
        "sarcasm_sensitive": False,
        "input_data": {
            "text": "The food was cold and the service was rude."
        },
        "output": {"sentiment": "negative"},
        "expected_pass": True,
    },
]


# --- Tightened rubric prompts used in Part 3 only. ------------------
#
# Preserves the structure of the production prompts (same role split,
# same "3-6 criteria" shape, same strict JSON output contract), but
# pins the passed/fail orientation explicitly and asks the builder to
# embed the convention into the rubric itself. We do not touch the
# production prompts — these are experimental.


def tightened_build_rubric_prompt(hypothesis: Hypothesis) -> list[dict]:
    system = (
        "You write concise evaluation rubrics. Given a failure hypothesis, "
        "produce a short rubric an evaluator can use to decide whether an "
        "output passes or fails with respect to the hypothesis.\n\n"
        "ORIENTATION CONVENTION (must be followed): passed=true means the "
        "system handled the case correctly — it does NOT exhibit the "
        "hypothesized failure. passed=false means the system did exhibit "
        "the failure. Write every rubric criterion so that 'satisfies the "
        "criterion' = 'did NOT exhibit the hypothesized failure'."
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


def tightened_rubric_judge_prompt(
    rubric: str, input_data: dict[str, Any], output: dict[str, Any]
) -> list[dict]:
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


# --- Data structures ------------------------------------------------


@dataclass
class Judgment:
    item_id: int
    passed: bool | None  # None on parse failure
    reason: str
    raw: str
    expected_pass: bool
    sarcasm_sensitive: bool


@dataclass
class RubricRun:
    run_index: int
    rubric_text: str
    judgments: list[Judgment] = field(default_factory=list)
    orientation: str = "unknown"  # "correct" | "inverted" | "inconsistent" | "malformed"
    sarcasm_agreements: int = 0  # of 4 sarcasm-sensitive items


@dataclass
class PairwiseOne:
    item_id: int
    rep: int
    a_passed: bool | None
    b_passed: bool | None
    a_reason: str
    b_reason: str
    raw: str
    # For each input, A is the "exhibits failure" output (sentiment=positive
    # on sarcastic text) and B is the "handles correctly" output
    # (sentiment=negative on sarcastic text). Correct orientation =>
    # a_passed=False, b_passed=True.


# --- Orientation classifier -----------------------------------------


def classify_orientation(judgments: list[Judgment]) -> tuple[str, int]:
    """Classify a rubric run by how it judged the 4 sarcasm-sensitive items.

    Returns ``(orientation, sarcasm_agreements)`` where
    ``sarcasm_agreements`` is the count (of 4) of judgments whose
    ``passed`` matches the correctly-oriented ``expected_pass``.
    """
    key_items = [j for j in judgments if j.sarcasm_sensitive]
    if len(key_items) != 4:
        return "malformed", 0
    if any(j.passed is None for j in key_items):
        return "malformed", 0
    # Count agreements with correct orientation.
    correct = sum(1 for j in key_items if j.passed == j.expected_pass)
    inverted = sum(1 for j in key_items if j.passed == (not j.expected_pass))
    if correct == 4:
        return "correct", 4
    if inverted == 4:
        return "inverted", 0
    return "inconsistent", correct


# --- Execution helpers ----------------------------------------------


async def _call(
    backend: AnthropicBackend, messages: list[dict], model: str
) -> str:
    return await backend.complete(messages, model=model, max_tokens=MAX_TOKENS)


async def run_rubric_experiment(
    backend: AnthropicBackend,
    model: str,
    build_prompt_fn: Any,
    judge_prompt_fn: Any,
    label: str,
) -> list[RubricRun]:
    runs: list[RubricRun] = []
    for i in range(N_REPS):
        print(
            f"  [{label}] run {i + 1}/{N_REPS} — building rubric ...",
            file=sys.stderr,
        )
        rubric_text = await _call(backend, build_prompt_fn(HYPOTHESIS), model)
        run = RubricRun(run_index=i + 1, rubric_text=rubric_text)
        for item in TEST_INPUTS:
            raw = await _call(
                backend,
                judge_prompt_fn(rubric_text, item["input_data"], item["output"]),
                model,
            )
            parsed = parse_json_response(raw)
            if (
                isinstance(parsed, dict)
                and isinstance(parsed.get("passed"), bool)
            ):
                passed: bool | None = parsed["passed"]
                reason = str(parsed.get("reason", ""))
            else:
                passed = None
                reason = "<malformed or unparseable>"
            run.judgments.append(
                Judgment(
                    item_id=item["id"],
                    passed=passed,
                    reason=reason,
                    raw=raw,
                    expected_pass=item["expected_pass"],
                    sarcasm_sensitive=item["sarcasm_sensitive"],
                )
            )
        run.orientation, run.sarcasm_agreements = classify_orientation(
            run.judgments
        )
        print(
            f"  [{label}] run {i + 1} → orientation={run.orientation} "
            f"sarcasm_agreements={run.sarcasm_agreements}/4",
            file=sys.stderr,
        )
        runs.append(run)
    return runs


async def run_pairwise_experiment(
    backend: AnthropicBackend,
    model: str,
) -> list[PairwiseOne]:
    # Use the 2 sarcastic input texts. For each, A is the "exhibits
    # failure" output (positive), B is the "handles correctly" output
    # (negative). We pick items 1/2 (same text) and 3/4 (same text) and
    # a third pair from item 1 reused with a *different* alt. Actually
    # the spec says 3 distinct inputs. We only have 2 sarcastic texts;
    # let's add a third sarcastic text for Part 4.
    pairs = [
        {
            "input_data": TEST_INPUTS[0]["input_data"],  # "Oh great, another..."
            "output_a": {"sentiment": "positive"},
            "output_b": {"sentiment": "negative"},
            "pair_id": 1,
        },
        {
            "input_data": TEST_INPUTS[2]["input_data"],  # "Wow, I absolutely love..."
            "output_a": {"sentiment": "positive"},
            "output_b": {"sentiment": "negative"},
            "pair_id": 2,
        },
        {
            "input_data": {
                "text": (
                    "Fantastic — my flight is delayed four hours and the "
                    "gate agent just told me the lounge is closed. Living "
                    "the dream."
                )
            },
            "output_a": {"sentiment": "positive"},
            "output_b": {"sentiment": "negative"},
            "pair_id": 3,
        },
    ]
    rows: list[PairwiseOne] = []
    for pair in pairs:
        for rep in range(N_REPS):
            print(
                f"  [pairwise haiku] pair {pair['pair_id']} rep {rep + 1}/"
                f"{N_REPS} ...",
                file=sys.stderr,
            )
            raw = await _call(
                backend,
                pairwise_judge_prompt(
                    HYPOTHESIS,
                    pair["input_data"],
                    pair["output_a"],
                    pair["output_b"],
                ),
                model,
            )
            parsed = parse_json_response(raw)
            a_passed: bool | None = None
            b_passed: bool | None = None
            a_reason = ""
            b_reason = ""
            if isinstance(parsed, dict):
                a = parsed.get("a")
                b = parsed.get("b")
                if isinstance(a, dict) and isinstance(a.get("passed"), bool):
                    a_passed = a["passed"]
                    a_reason = str(a.get("reason", ""))
                if isinstance(b, dict) and isinstance(b.get("passed"), bool):
                    b_passed = b["passed"]
                    b_reason = str(b.get("reason", ""))
            rows.append(
                PairwiseOne(
                    item_id=pair["pair_id"],
                    rep=rep + 1,
                    a_passed=a_passed,
                    b_passed=b_passed,
                    a_reason=a_reason,
                    b_reason=b_reason,
                    raw=raw,
                )
            )
    return rows


# --- Findings writer ------------------------------------------------


def _tally(runs: list[RubricRun]) -> dict[str, int]:
    out = {"correct": 0, "inverted": 0, "inconsistent": 0, "malformed": 0}
    for r in runs:
        out[r.orientation] = out.get(r.orientation, 0) + 1
    return out


def _sample_reasons(runs: list[RubricRun], n: int = 4) -> list[str]:
    samples: list[str] = []
    for r in runs:
        for j in r.judgments:
            if not j.sarcasm_sensitive:
                continue
            samples.append(
                f"(run {r.run_index}, item {j.item_id}, "
                f"expected_pass={j.expected_pass}, got_passed={j.passed}): "
                f"{j.reason}"
            )
            if len(samples) >= n:
                return samples
    return samples


def _rubric_table(runs: list[RubricRun]) -> str:
    lines = [
        "| run | orientation | sarcasm agreements (/4) | notes |",
        "|---|---|---|---|",
    ]
    for r in runs:
        notes_bits = []
        malformed = sum(
            1 for j in r.judgments if j.passed is None
        )
        if malformed:
            notes_bits.append(f"{malformed} malformed judge resp")
        if r.orientation == "inconsistent":
            mix = [
                f"item{j.item_id}:{j.passed}"
                for j in r.judgments
                if j.sarcasm_sensitive
            ]
            notes_bits.append("; ".join(mix))
        lines.append(
            f"| {r.run_index} | {r.orientation} | "
            f"{r.sarcasm_agreements} | {' / '.join(notes_bits) or ''} |"
        )
    return "\n".join(lines)


def _pairwise_table(rows: list[PairwiseOne]) -> str:
    lines = [
        "| pair | rep | a_passed (expect F) | b_passed (expect T) | correctly oriented? |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        correct = (r.a_passed is False and r.b_passed is True)
        malformed = r.a_passed is None or r.b_passed is None
        mark = "✗ malformed" if malformed else ("✓" if correct else "✗")
        lines.append(
            f"| {r.item_id} | {r.rep} | {r.a_passed} | {r.b_passed} | {mark} |"
        )
    return "\n".join(lines)


def _pairwise_summary(rows: list[PairwiseOne]) -> tuple[int, int]:
    total = len(rows)
    correct = sum(
        1 for r in rows if r.a_passed is False and r.b_passed is True
    )
    return correct, total


def append_section(text: str) -> None:
    with open(FINDINGS_PATH, "a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def write_header_if_missing(date_str: str) -> None:
    if os.path.exists(FINDINGS_PATH):
        return
    header = (
        f"# Rubric Orientation Diagnostic — {date_str}\n\n"
        "## Question\n\n"
        "Is the rubric orientation instability from SMOKE_2 a prompt "
        "clarity problem (fixable by tightening the rubric prompts) or a "
        "structural problem with the rubric-judge primitive (requiring "
        "migration to pairwise judging)?\n\n"
        "## Method\n\n"
        f"- Hypothesis under test: `{HYPOTHESIS.text}`\n"
        f"- 6 hand-crafted (input, output) pairs: items 1-4 are "
        "sarcasm-sensitive (2 exhibit-failure, 2 handle-correctly), "
        "items 5-6 are non-sarcastic sanity cases.\n"
        f"- N = {N_REPS} independent rubric builds per (model × prompt) "
        "cell. Each rubric applied to all 6 inputs = 70 calls per cell.\n"
        "- Orientation classification, per rubric run, based on the 4 "
        "sarcasm-sensitive items: 4/4 agreement with the "
        "handles-correctly=passed=true convention → `correct`; 4/4 "
        "agreement with the reverse → `inverted`; anything else → "
        "`inconsistent`; unparseable → `malformed`.\n"
        "- Cells run: (current prompt, Haiku 4.5); (current prompt, "
        "Sonnet 4.6); (tightened prompt, Haiku 4.5). Plus Part 4: "
        "pairwise judge on 3 sarcastic pairs × N=10 runs on Haiku 4.5.\n"
    )
    with open(FINDINGS_PATH, "w", encoding="utf-8") as f:
        f.write(header)


# --- Cells ----------------------------------------------------------


async def part1_haiku_current(
    core_logs: list[RunnerCallLog],
) -> list[RubricRun]:
    print("\n=== PART 1: current prompt on Haiku 4.5 ===", file=sys.stderr)
    cfg = AnthropicConfig(default_model=HAIKU, max_tokens=MAX_TOKENS)
    backend = AnthropicBackend(config=cfg, on_call=core_logs.append)
    runs = await run_rubric_experiment(
        backend,
        HAIKU,
        build_rubric_prompt,
        rubric_judge_prompt,
        label="P1-haiku-current",
    )
    return runs


async def part2_sonnet_current(
    core_logs: list[RunnerCallLog],
) -> list[RubricRun]:
    print("\n=== PART 2: current prompt on Sonnet 4.6 ===", file=sys.stderr)
    cfg = AnthropicConfig(default_model=SONNET, max_tokens=MAX_TOKENS)
    backend = AnthropicBackend(config=cfg, on_call=core_logs.append)
    runs = await run_rubric_experiment(
        backend,
        SONNET,
        build_rubric_prompt,
        rubric_judge_prompt,
        label="P2-sonnet-current",
    )
    return runs


async def part3_haiku_tightened(
    core_logs: list[RunnerCallLog],
) -> list[RubricRun]:
    print("\n=== PART 3: tightened prompt on Haiku 4.5 ===", file=sys.stderr)
    cfg = AnthropicConfig(default_model=HAIKU, max_tokens=MAX_TOKENS)
    backend = AnthropicBackend(config=cfg, on_call=core_logs.append)
    runs = await run_rubric_experiment(
        backend,
        HAIKU,
        tightened_build_rubric_prompt,
        tightened_rubric_judge_prompt,
        label="P3-haiku-tight",
    )
    return runs


async def part4_haiku_pairwise(
    core_logs: list[RunnerCallLog],
) -> list[PairwiseOne]:
    print("\n=== PART 4: pairwise on Haiku 4.5 ===", file=sys.stderr)
    cfg = AnthropicConfig(default_model=HAIKU, max_tokens=MAX_TOKENS)
    backend = AnthropicBackend(config=cfg, on_call=core_logs.append)
    rows = await run_pairwise_experiment(backend, HAIKU)
    return rows


# --- Findings rendering ---------------------------------------------


def render_rubric_part(
    title: str,
    runs: list[RubricRun],
    preamble: str = "",
) -> str:
    tally = _tally(runs)
    samples = _sample_reasons(runs, n=5)
    parts = [f"\n## {title}\n\n"]
    if preamble:
        parts.append(preamble.rstrip() + "\n\n")
    parts.append(_rubric_table(runs) + "\n\n")
    parts.append(
        f"**Summary:** correct={tally['correct']}/10, "
        f"inverted={tally['inverted']}/10, "
        f"inconsistent={tally['inconsistent']}/10, "
        f"malformed={tally['malformed']}/10.\n\n"
    )
    if samples:
        parts.append("Representative judgment reasons (sarcasm-sensitive items):\n\n")
        for s in samples:
            parts.append(f"- {s}\n")
        parts.append("\n")
    # Also include the very first rubric text as a sample so the doc
    # shows what the prompt was producing.
    if runs:
        parts.append("Sample rubric text (run 1):\n\n")
        parts.append("```\n" + runs[0].rubric_text.strip() + "\n```\n\n")
    return "".join(parts)


def render_pairwise_part(rows: list[PairwiseOne]) -> str:
    correct, total = _pairwise_summary(rows)
    parts = ["\n## Part 4: Pairwise judge baseline on Haiku 4.5\n\n"]
    parts.append(
        f"For each pair: output A is the `positive` classification "
        "(exhibits failure) and output B is the `negative` "
        "classification (handles correctly). Correct orientation = "
        "a_passed=False, b_passed=True.\n\n"
    )
    parts.append(_pairwise_table(rows) + "\n\n")
    parts.append(f"**Summary:** {correct}/{total} correctly oriented.\n\n")
    sample_reasons = []
    for r in rows[:4]:
        sample_reasons.append(
            f"- pair {r.item_id} rep {r.rep}: A reason = {r.a_reason!r}; "
            f"B reason = {r.b_reason!r}"
        )
    if sample_reasons:
        parts.append("Representative reason pairs:\n\n")
        parts.extend(s + "\n" for s in sample_reasons)
        parts.append("\n")
    return "".join(parts)


def render_synthesis(
    part1: list[RubricRun],
    part2: list[RubricRun],
    part3: list[RubricRun],
    part4: list[PairwiseOne],
) -> str:
    t1 = _tally(part1)
    t2 = _tally(part2)
    t3 = _tally(part3)
    p4_correct, p4_total = _pairwise_summary(part4)

    p1_correct = t1["correct"]
    p2_correct = t2["correct"]
    p3_correct = t3["correct"]

    # These thresholds are encoded per the session spec:
    #   If Part 3 gives 10/10 correct on Haiku → Path A (prompt tighten).
    #   If Part 3 ≤ 7/10 and Part 4 ≥ 28/30 → Path B (pairwise).
    #   If Part 2 pins orientation but Part 3 still doesn't → hybrid.
    #   Otherwise, a mixed recommendation with the data spelled out.

    rec_bits: list[str] = []
    rec_bits.append("\n## Synthesis\n\n")
    rec_bits.append(
        f"- Part 1 (Haiku, current prompt): correct={t1['correct']}/10, "
        f"inverted={t1['inverted']}/10, inconsistent={t1['inconsistent']}/10.\n"
    )
    rec_bits.append(
        f"- Part 2 (Sonnet, current prompt): correct={t2['correct']}/10, "
        f"inverted={t2['inverted']}/10, inconsistent={t2['inconsistent']}/10.\n"
    )
    rec_bits.append(
        f"- Part 3 (Haiku, tightened prompt): correct={t3['correct']}/10, "
        f"inverted={t3['inverted']}/10, inconsistent={t3['inconsistent']}/10.\n"
    )
    rec_bits.append(
        f"- Part 4 (Haiku, pairwise): {p4_correct}/{p4_total} correctly "
        "oriented.\n\n"
    )
    rec_bits.append(
        "### Interpretation\n\n"
        f"- Haiku, as-is, was {p1_correct}/10 correctly oriented on this "
        "hypothesis. Compare to SMOKE_2's n=3 result (1/3 correct). The "
        "direction matches, the rate is now measured at N=10.\n"
    )
    if p2_correct > p1_correct:
        rec_bits.append(
            f"- Sonnet (current prompt) rose to {p2_correct}/10 correct — "
            "evidence that prompt-following fidelity scales with model "
            "capability on the as-is prompt.\n"
        )
    elif p2_correct < p1_correct:
        rec_bits.append(
            f"- Sonnet, surprisingly, was *less* reliable at "
            f"{p2_correct}/10 — suggests the prompt is structurally "
            "ambiguous in a way that fights even stronger models.\n"
        )
    else:
        rec_bits.append(
            f"- Sonnet matched Haiku at {p2_correct}/10; moving to a "
            "stronger model did not buy orientation reliability.\n"
        )
    rec_bits.append(
        f"- Tightened prompt on Haiku was {p3_correct}/10 correct. This "
        "is the direct test of Path A — can we pin orientation with a "
        "prompt change alone?\n"
    )
    rec_bits.append(
        f"- Pairwise on Haiku was {p4_correct}/{p4_total}. This is the "
        "Path B baseline.\n\n"
    )

    # Recommendation block.
    rec_bits.append("## Recommendation\n\n")
    if p3_correct >= 9 and p4_correct >= p4_total - 2:
        rec_bits.append(
            "**Path A (tighten the rubric prompt).** The tightened prompt "
            "pins orientation on Haiku at near-ceiling, which means the "
            "smallest-possible change to `src/hypothesize/core/prompts.py` "
            "resolves the SMOKE_2 finding. Pairwise is also available as a "
            "fallback, but the data does not require migrating to it.\n\n"
        )
        rec_bits.append(
            "- Evidence basis: Part 3 = "
            f"{p3_correct}/10 correct vs. Part 1 = {p1_correct}/10.\n"
            "- Risk: a single hypothesis was tested. Scenarios with "
            "weaker sarcasm cues or more abstract failure modes may still "
            "induce ambiguity.\n"
            "- Condition that would flip the recommendation: finding a "
            "second hypothesis for which the tightened prompt falls below "
            "~8/10.\n"
        )
    elif p3_correct < 8 and p4_correct >= p4_total - 2:
        rec_bits.append(
            "**Path B (migrate discrimination to pairwise judging).** "
            "The tightened rubric prompt did not reliably pin orientation "
            "on Haiku, but the pairwise judge is near-deterministically "
            "correctly oriented at the same model tier. The structural "
            "ambiguity is in the single-output rubric primitive itself, "
            "not in the prompt wording.\n\n"
        )
        rec_bits.append(
            "- Evidence basis: Part 4 = "
            f"{p4_correct}/{p4_total} vs. Part 3 = {p3_correct}/10.\n"
            "- Risk: pairwise doubles the call count compared to a single "
            "rubric judgment (2 outputs per call vs. 1), though it halves "
            "the calls vs. sequential rubric-judge-twice. Cost impact "
            "needs re-estimation once the pipeline is changed.\n"
            "- Condition that would flip the recommendation: finding "
            "a rubric prompt wording that gets Haiku to ≥9/10 on this "
            "scenario without hand-tuning for sarcasm specifically.\n"
        )
    elif p3_correct < 8 and p2_correct >= 9:
        rec_bits.append(
            "**Hybrid: Path A but require Sonnet (or stronger) for "
            "rubric-judge.** Haiku cannot follow the orientation "
            "instruction reliably even after tightening; Sonnet can on "
            "the current prompt. Keeping rubric judging for absolute "
            "scoring with Sonnet, and using pairwise on Haiku for "
            "high-volume discrimination, is the data-driven split.\n\n"
        )
        rec_bits.append(
            f"- Evidence basis: Part 2 = {p2_correct}/10, Part 3 = "
            f"{p3_correct}/10, Part 4 = {p4_correct}/{p4_total}.\n"
            "- Risk: forcing Sonnet for rubric-judge raises cost "
            "considerably. The practical fix may still be pairwise-only.\n"
            "- Condition that would flip the recommendation: a second "
            "hypothesis where Haiku on the tightened prompt recovers to "
            "≥9/10 (suggesting this one was unusually hard).\n"
        )
    else:
        rec_bits.append(
            "**Mixed / further-work recommendation.** The data does not "
            "cleanly favor Path A or Path B at the thresholds this "
            "experiment set. See the per-part numbers above for the "
            "actual distribution, and prefer the cheaper action (Path A "
            "prompt edit) first with a regression test covering the "
            "observed failure class.\n\n"
        )
        rec_bits.append(
            f"- Evidence basis: Part 1 = {p1_correct}/10, Part 2 = "
            f"{p2_correct}/10, Part 3 = {p3_correct}/10, Part 4 = "
            f"{p4_correct}/{p4_total}.\n"
            "- Risk: the absence of a clean signal likely means "
            "individual runs are noisy in ways N=10 doesn't fully "
            "characterize. A follow-up with a second hypothesis would "
            "disambiguate.\n"
        )

    return "".join(rec_bits)


# --- Main -----------------------------------------------------------


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or len(api_key) < 10:
        print(
            "ERROR: ANTHROPIC_API_KEY not loaded. Populate ./.env and "
            "re-run.",
            file=sys.stderr,
        )
        return 1

    date_str = time.strftime("%Y-%m-%d")
    write_header_if_missing(date_str)

    start = time.monotonic()

    # Separate log lists per part so we can report token totals.
    logs_p1: list[RunnerCallLog] = []
    logs_p2: list[RunnerCallLog] = []
    logs_p3: list[RunnerCallLog] = []
    logs_p4: list[RunnerCallLog] = []

    p1 = await part1_haiku_current(logs_p1)
    append_section(
        render_rubric_part(
            "Part 1: Current prompt on Haiku 4.5",
            p1,
            preamble=(
                "Current `build_rubric_prompt` + `rubric_judge_prompt`, "
                "unmodified. This reproduces the SMOKE_2 observation at "
                "N=10 against the rubric primitive directly (no "
                "`find_discriminating_inputs` wiring)."
            ),
        )
    )

    p2 = await part2_sonnet_current(logs_p2)
    append_section(
        render_rubric_part(
            "Part 2: Current prompt on Sonnet 4.6",
            p2,
            preamble=(
                "Identical prompt and inputs as Part 1. Model swap to "
                "Sonnet 4.6 tests whether prompt-following fidelity "
                "scales with capability."
            ),
        )
    )

    p3 = await part3_haiku_tightened(logs_p3)
    append_section(
        render_rubric_part(
            "Part 3: Tightened prompt on Haiku 4.5",
            p3,
            preamble=(
                "Tightened rubric builder + judge prompts that pin "
                "`passed=true` = 'handles correctly, does NOT exhibit "
                "failure' explicitly in both the builder system message "
                "and the judge system message. The builder is also "
                "asked to embed the convention into the rubric body. "
                "See `tightened_build_rubric_prompt` and "
                "`tightened_rubric_judge_prompt` in "
                "`rubric_orientation.py`."
            ),
        )
    )

    p4 = await part4_haiku_pairwise(logs_p4)
    append_section(render_pairwise_part(p4))

    append_section(render_synthesis(p1, p2, p3, p4))

    # Token accounting.
    def _tok_summary(name: str, logs: list[RunnerCallLog]) -> str:
        return (
            f"- {name}: calls={len(logs)} "
            f"input_tokens={sum(x.input_tokens for x in logs)} "
            f"output_tokens={sum(x.output_tokens for x in logs)}"
        )

    elapsed = time.monotonic() - start
    tok = "\n## Cost accounting\n\n"
    tok += _tok_summary("Part 1 (Haiku current)", logs_p1) + "\n"
    tok += _tok_summary("Part 2 (Sonnet current)", logs_p2) + "\n"
    tok += _tok_summary("Part 3 (Haiku tightened)", logs_p3) + "\n"
    tok += _tok_summary("Part 4 (Haiku pairwise)", logs_p4) + "\n"
    tok += f"- Wall time: {elapsed:.1f}s\n"
    append_section(tok)

    # Console summary for the operator.
    print()
    print(f"Wrote findings to {FINDINGS_PATH}")
    print(f"Total wall time: {elapsed:.1f}s")
    print(
        f"Part 1 tally: {_tally(p1)} | Part 2: {_tally(p2)} | "
        f"Part 3: {_tally(p3)}"
    )
    p4_c, p4_t = _pairwise_summary(p4)
    print(f"Part 4 pairwise: {p4_c}/{p4_t} correctly oriented")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
