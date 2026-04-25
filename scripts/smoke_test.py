#!/usr/bin/env python3
"""Smoke test: run find_discriminating_inputs against the real Anthropic API.

This is a one-off diagnostic, not product code and not part of the pytest
suite. It exists to surface the gap between MockBackend (which always
returns well-formed scripted JSON) and real Claude (which may or may not).
Findings are written to scripts/SMOKE_FINDINGS_{1,2,3}.md and inform
later-feature design.

Two scenarios are exercised back-to-back, each with its own 100-call
core-backend budget:

1. ``SARCASM_SCENARIO`` — a deliberately broken sentiment classifier that
   always predicts "positive", pitted against a sarcasm-aware alternative
   built on Claude Haiku. This is the SMOKE_1 / SMOKE_2 scenario —
   reproduces the same conditions under which the original rubric
   orientation bug surfaced.
2. ``SUMMARIZATION_SCENARIO`` — a toy non-classifier scenario. Current
   runner asks Haiku for a terse summary; alternative asks Haiku for a
   summary that preserves named entities. Tests whether the discrimination
   algorithm — and in particular the tightened rubric prompts — still
   behave sensibly on a generative (non-boolean-output) task.

Run from repo root (with ``.env`` populated)::

    python scripts/smoke_test.py

The API key is read from ``.env`` via ``python-dotenv`` — never from the
shell environment. Never logged, printed, or echoed by this script.
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

from hypothesize.adapters.errors import (
    AutoAlternativeUnavailable,
    BudgetExhausted,
)
from hypothesize.core.discrimination import find_discriminating_inputs
from hypothesize.core.json_extract import parse_json_response
from hypothesize.core.judge import RubricJudge
from hypothesize.core.types import Budget, Hypothesis
from hypothesize.llm.anthropic import AnthropicBackend
from hypothesize.llm.config import AnthropicConfig, RunnerCallLog

MODEL = "claude-haiku-4-5-20251001"
BUDGET_CAP = 100
TARGET_N = 5
MIN_REQUIRED = 3
MAX_TOKENS = 2048


# --------------------------------------------------------------------
# Shared utilities
# --------------------------------------------------------------------


def classify_phase(messages: list[dict]) -> str:
    """Fingerprint a core-backend call by its system prompt."""
    system = ""
    for m in messages:
        if m.get("role") == "system":
            system = m.get("content", "") or ""
            break
    if "decompose a failure hypothesis" in system:
        return "decompose"
    if "design inputs that probe" in system:
        return "generate"
    if "write concise evaluation rubrics" in system:
        return "rubric_build"
    if "apply a rubric" in system:
        return "rubric_judge"
    if "evaluate two candidate outputs" in system:
        return "pairwise_judge"
    if "rewrite an LLM system prompt" in system:
        return "rewrite_prompt"
    return "unknown"


class RecordingBackend:
    """Wraps an ``AnthropicBackend`` to record raw response text per call.

    The production backend's ``on_call`` hook surfaces token counts but
    not response text. The smoke report needs the text to summarise
    parse cleanliness, observed input shapes, etc. — so we wrap it.
    """

    def __init__(self, label: str, inner: AnthropicBackend) -> None:
        self.label = label
        self.inner = inner
        self.call_log: list[dict[str, Any]] = []

    async def complete(self, messages: list[dict], **kwargs: Any) -> str:
        text = await self.inner.complete(messages, **kwargs)
        phase = classify_phase(messages)
        self.call_log.append(
            {"phase": phase, "messages": messages, "response": text}
        )
        preview = text.replace("\n", " ")[:120]
        print(
            f"[{self.label}] call #{len(self.call_log)} phase={phase} "
            f"-> {preview!r}",
            file=sys.stderr,
        )
        return text


# --------------------------------------------------------------------
# Scenario shape
# --------------------------------------------------------------------


SystemRunner = Any  # async callable: dict -> dict


@dataclass
class Scenario:
    name: str
    hypothesis: Hypothesis
    context: list[str]
    # Factory is (alt_backend_for_live_systems) -> (current_runner, alt_runner)
    build_runners: Any  # callable
    notes: str = ""
    # On-scenario output accumulators populated during run()
    core_logs: list[RunnerCallLog] = field(default_factory=list)
    core_backend: RecordingBackend | None = None
    alt_backend: RecordingBackend | None = None
    budget: Budget | None = None
    result: Any = None
    elapsed: float = 0.0


# --------------------------------------------------------------------
# Scenario 1: sarcasm classifier (reused from SMOKE_2)
# --------------------------------------------------------------------


async def _sarcasm_current_runner(input_data: dict[str, Any]) -> dict[str, Any]:
    """Deliberately dumb classifier: always 'positive'."""
    return {"sentiment": "positive"}


class _SarcasmAwareRunner:
    """Alternative runner: asks Haiku to classify, explicitly flagging sarcasm.

    Uses a separate backend instance so its calls don't mix with the core
    algorithm's budget accounting. The core algorithm only sees the single
    LLMBackend passed to find_discriminating_inputs.
    """

    def __init__(self, backend: RecordingBackend) -> None:
        self.backend = backend

    async def __call__(self, input_data: dict[str, Any]) -> dict[str, Any]:
        text = ""
        for key in ("text", "input", "content", "sentence", "query", "message"):
            if isinstance(input_data.get(key), str) and input_data[key]:
                text = input_data[key]
                break
        if not text:
            text = json.dumps(input_data)

        prompt = [
            {
                "role": "system",
                "content": (
                    "You classify sentiment. Detect sarcasm: surface-positive "
                    "text with clearly negative intent counts as negative. "
                    "Respond with exactly one word: positive or negative."
                ),
            },
            {"role": "user", "content": f"Text: {text}\n\nSentiment:"},
        ]
        try:
            raw = await self.backend.complete(prompt)
        except Exception as e:
            print(
                f"[alt_runner] giving up on input, treating as 'positive': {e!r}",
                file=sys.stderr,
            )
            return {"sentiment": "positive"}

        label = raw.strip().lower().split()[0] if raw.strip() else "positive"
        label = label.rstrip(".,!?:;")
        if label == "negative":
            return {"sentiment": "negative"}
        return {"sentiment": "positive"}


def _build_sarcasm_runners(
    alt_backend: RecordingBackend,
) -> tuple[Any, Any]:
    return _sarcasm_current_runner, _SarcasmAwareRunner(alt_backend)


SARCASM_SCENARIO = Scenario(
    name="sarcasm classifier",
    hypothesis=Hypothesis(
        text=(
            "the sentiment classifier fails on sarcastic positive text "
            "(surface tokens positive, intent negative)"
        )
    ),
    context=[
        "The current system is a naive sentiment classifier that always "
        "predicts 'positive' for any input.",
        "The alternative system is expected to detect sarcastic statements "
        "whose surface tokens read positive but whose intent is negative.",
    ],
    build_runners=_build_sarcasm_runners,
    notes=(
        "Classifier scenario. Boolean-ish output shape ({'sentiment': str}); "
        "reproduces the SMOKE_2 conditions under which the rubric "
        "orientation bug originally surfaced."
    ),
)


# --------------------------------------------------------------------
# Scenario 2: summarization — non-classifier shape
# --------------------------------------------------------------------


class _TerseSummaryRunner:
    """Current runner: terse one-sentence summary, no special entity care."""

    def __init__(self, backend: RecordingBackend) -> None:
        self.backend = backend

    async def __call__(self, input_data: dict[str, Any]) -> dict[str, Any]:
        document = ""
        for key in ("document", "text", "input", "content"):
            if isinstance(input_data.get(key), str) and input_data[key]:
                document = input_data[key]
                break
        if not document:
            document = json.dumps(input_data)

        prompt = [
            {
                "role": "system",
                "content": (
                    "You summarize short documents. Produce exactly one "
                    "concise sentence. No more. No less."
                ),
            },
            {"role": "user", "content": f"Document:\n{document}\n\nSummary:"},
        ]
        try:
            raw = await self.backend.complete(prompt)
        except Exception as e:
            print(
                f"[summ_current] giving up on input: {e!r}", file=sys.stderr
            )
            return {"summary": ""}
        return {"summary": raw.strip()}


class _EntityPreservingSummaryRunner:
    """Alternative runner: summary explicitly preserving named entities."""

    def __init__(self, backend: RecordingBackend) -> None:
        self.backend = backend

    async def __call__(self, input_data: dict[str, Any]) -> dict[str, Any]:
        document = ""
        for key in ("document", "text", "input", "content"):
            if isinstance(input_data.get(key), str) and input_data[key]:
                document = input_data[key]
                break
        if not document:
            document = json.dumps(input_data)

        prompt = [
            {
                "role": "system",
                "content": (
                    "You summarize short documents in exactly one sentence. "
                    "You MUST preserve all named entities — people, places, "
                    "organizations, and product names — that appear in the "
                    "document. If the document names a person, include that "
                    "name. If it names a city, include the city. If a "
                    "company or product appears, include it verbatim."
                ),
            },
            {"role": "user", "content": f"Document:\n{document}\n\nSummary:"},
        ]
        try:
            raw = await self.backend.complete(prompt)
        except Exception as e:
            print(
                f"[summ_alt] giving up on input: {e!r}", file=sys.stderr
            )
            return {"summary": ""}
        return {"summary": raw.strip()}


def _build_summarization_runners(
    alt_backend: RecordingBackend,
) -> tuple[Any, Any]:
    return (
        _TerseSummaryRunner(alt_backend),
        _EntityPreservingSummaryRunner(alt_backend),
    )


SUMMARIZATION_SCENARIO = Scenario(
    name="summarization: entity preservation",
    hypothesis=Hypothesis(
        text=(
            "the summarizer fails to preserve named entities — people, "
            "places, organizations — mentioned in the source document, "
            "dropping them in favor of generic nouns"
        )
    ),
    context=[
        "The current system is a terse one-sentence summarizer with no "
        "explicit instruction to preserve named entities; it often "
        "paraphrases 'Dr. Sato at Tokyo University' as 'a researcher'.",
        "The alternative system is explicitly instructed to preserve all "
        "named entities — people, places, organizations, and products — "
        "verbatim in its one-sentence summary.",
    ],
    build_runners=_build_summarization_runners,
    notes=(
        "Non-classifier scenario. Free-text output shape "
        "({'summary': str}); exercises the discrimination pipeline on a "
        "generative task where the rubric must reason about what the "
        "summary contains rather than comparing a fixed label."
    ),
)


# --------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------


def _section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _h1(title: str) -> None:
    print()
    print("#" * 72)
    print(f"# {title}")
    print("#" * 72)


def report(scenario: Scenario) -> None:
    assert scenario.core_backend is not None
    assert scenario.alt_backend is not None
    assert scenario.budget is not None
    assert scenario.result is not None

    core = scenario.core_backend
    alt = scenario.alt_backend
    budget = scenario.budget
    result = scenario.result
    core_logs = scenario.core_logs
    elapsed = scenario.elapsed

    _section(f"RESULT SUMMARY — {scenario.name}")
    print(f"Status:        {result.status}")
    print(f"Budget used:   {result.budget_used}/{budget.max_llm_calls}")
    print(f"Wall time:     {elapsed:.1f}s")
    print(f"Core calls:    {len(core.call_log)}")
    print(
        f"Alt-runner:    {len(alt.call_log)} (not counted against core budget)"
    )

    _section("CALLS PER PHASE (core backend)")
    phase_counts: dict[str, int] = {}
    for call in core.call_log:
        phase = call["phase"]
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
    for phase in (
        "decompose",
        "generate",
        "rubric_build",
        "rubric_judge",
        "pairwise_judge",
        "rewrite_prompt",
        "unknown",
    ):
        if phase in phase_counts:
            print(f"  {phase:15} {phase_counts[phase]}")

    _section("TOKEN USAGE PER PHASE")
    if core_logs:
        by_phase: dict[str, list[RunnerCallLog]] = {}
        for entry, log in zip(core.call_log, core_logs, strict=False):
            by_phase.setdefault(entry["phase"], []).append(log)
        for phase, logs in sorted(by_phase.items()):
            in_total = sum(log.input_tokens for log in logs)
            out_total = sum(log.output_tokens for log in logs)
            print(
                f"  {phase:15} calls={len(logs)} "
                f"in={in_total} out={out_total}"
            )
        in_grand = sum(log.input_tokens for log in core_logs)
        out_grand = sum(log.output_tokens for log in core_logs)
        print(f"  {'TOTAL':15} calls={len(core_logs)} in={in_grand} out={out_grand}")
    else:
        print("  (no on_call telemetry recorded)")

    _section("DIMENSIONS RETURNED BY DECOMPOSE")
    dims = None
    for call in core.call_log:
        if call["phase"] != "decompose":
            continue
        parsed = parse_json_response(call.get("response", ""))
        if isinstance(parsed, dict) and isinstance(parsed.get("dimensions"), list):
            dims = parsed["dimensions"]
        else:
            print("  decompose response did NOT parse to expected shape")
            preview = (call.get("response") or "")[:500]
            print(f"  raw (first 500 chars): {preview!r}")
        break
    if dims is None:
        print("  (no dimensions — see parse failure above or missing call)")
    elif not isinstance(dims, list):
        print(f"  'dimensions' key is not a list; got {type(dims).__name__}")
    else:
        print(f"  count: {len(dims)}")
        for d in dims:
            name = d.get("name", "?") if isinstance(d, dict) else "?"
            desc = d.get("description", "?") if isinstance(d, dict) else "?"
            print(f"  - {name}: {desc[:100]}")

    _section("JSON PARSE CLEANLINESS (on calls that expect JSON)")
    parse_failures: list[tuple[int, str, str]] = []
    json_expected = {"decompose", "generate", "rubric_judge", "pairwise_judge"}
    for i, call in enumerate(core.call_log):
        if call["phase"] not in json_expected:
            continue
        if parse_json_response(call.get("response", "")) is None:
            parse_failures.append((i, call["phase"], call.get("response", "")))
    if not parse_failures:
        print("  All JSON-expected responses parsed cleanly via parse_json_response.")
    else:
        print(f"  {len(parse_failures)} parse failure(s):")
        for i, phase, raw in parse_failures:
            print(f"  - call #{i + 1} (phase={phase}):")
            for line in raw[:500].splitlines():
                print(f"      {line}")

    _section("CANDIDATE input_data SHAPES (from generate calls)")
    all_shapes: list[list[str]] = []
    for call in core.call_log:
        if call["phase"] != "generate":
            continue
        parsed = parse_json_response(call.get("response", ""))
        if not isinstance(parsed, dict):
            print("  (one generate response did not parse)")
            continue
        for item in parsed.get("candidates", []):
            if isinstance(item, dict) and isinstance(item.get("input_data"), dict):
                all_shapes.append(sorted(item["input_data"].keys()))
    if not all_shapes:
        print("  (no candidate shapes captured)")
    else:
        print(f"  {len(all_shapes)} candidates across all generate calls")
        distinct: dict[tuple[str, ...], int] = {}
        for keys in all_shapes:
            distinct[tuple(keys)] = distinct.get(tuple(keys), 0) + 1
        for keys, count in sorted(distinct.items(), key=lambda kv: -kv[1]):
            print(f"  keys={list(keys)!r} × {count}")

    _section("RUBRIC BUILD OUTPUT")
    for call in core.call_log:
        if call["phase"] != "rubric_build":
            continue
        resp = call.get("response") or ""
        first_lines = resp.strip().splitlines()[:8]
        print("  First lines of rubric:")
        for line in first_lines:
            print(f"    {line}")
        break

    _section("SAMPLE rubric_judge VERDICT REASONS")
    verdicts_shown = 0
    for call in core.call_log:
        if call["phase"] != "rubric_judge":
            continue
        parsed = parse_json_response(call.get("response", ""))
        if isinstance(parsed, dict):
            print(
                f"  passed={parsed.get('passed')!r:<6} "
                f"reason={str(parsed.get('reason', ''))[:160]}"
            )
            verdicts_shown += 1
        if verdicts_shown >= 6:
            break
    if verdicts_shown == 0:
        print("  (no rubric_judge calls — scenario did not reach that phase)")

    _section("DISCRIMINATION OUTCOME")
    if result.status == "ok":
        print(f"  discriminating cases: {len(result.test_cases)}")
        if result.test_cases:
            print()
            print("  First discriminating case (raw):")
            first = result.test_cases[0].model_dump()
            for line in json.dumps(first, indent=2, ensure_ascii=False).splitlines():
                print(f"    {line}")
    else:
        assert result.insufficient is not None
        print("  status: insufficient_evidence")
        print(f"  reason: {result.insufficient.reason}")
        print(f"  candidates_tried:     {result.insufficient.candidates_tried}")
        print(f"  discriminating_found: {result.insufficient.discriminating_found}")


async def run_scenario(scenario: Scenario) -> None:
    _h1(f"SCENARIO: {scenario.name}")
    print(f"Notes:        {scenario.notes}")
    print(f"Hypothesis:   {scenario.hypothesis.text}")
    print(f"Model:        {MODEL}")
    print(f"Budget cap:   {BUDGET_CAP} core LLM calls")
    print(f"Target N:     {TARGET_N}")
    print(f"Min required: {MIN_REQUIRED}")

    config = AnthropicConfig(default_model=MODEL, max_tokens=MAX_TOKENS)
    core_logs: list[RunnerCallLog] = []
    inner_core = AnthropicBackend(config=config, on_call=core_logs.append)
    inner_alt = AnthropicBackend(config=config)
    core_backend = RecordingBackend("core", inner_core)
    alt_backend = RecordingBackend("alt", inner_alt)

    current_runner, alt_runner = scenario.build_runners(alt_backend)

    budget = Budget(max_llm_calls=BUDGET_CAP)
    judge = RubricJudge(llm=core_backend)

    start = time.monotonic()
    try:
        result = await find_discriminating_inputs(
            hypothesis=scenario.hypothesis,
            current_runner=current_runner,
            alternative_runner=alt_runner,
            context=scenario.context,
            judge=judge,
            llm=core_backend,
            budget=budget,
            target_n=TARGET_N,
            min_required=MIN_REQUIRED,
        )
    except (AutoAlternativeUnavailable, BudgetExhausted):
        raise
    except Exception as e:
        elapsed = time.monotonic() - start
        print(
            f"\nUnhandled exception after {elapsed:.1f}s: "
            f"{type(e).__name__}: {e!r}",
            file=sys.stderr,
        )
        raise
    elapsed = time.monotonic() - start

    scenario.core_backend = core_backend
    scenario.alt_backend = alt_backend
    scenario.core_logs = core_logs
    scenario.budget = budget
    scenario.result = result
    scenario.elapsed = elapsed

    report(scenario)


async def main() -> int:
    load_dotenv()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or len(api_key) < 10:
        print(
            "ERROR: ANTHROPIC_API_KEY is not loaded. Populate ./.env with "
            "ANTHROPIC_API_KEY=sk-ant-... and re-run.",
            file=sys.stderr,
        )
        return 1

    print("=" * 72)
    print("HYPOTHESIZE smoke test — real Anthropic API (two scenarios)")
    print("=" * 72)
    print(f"Model:        {MODEL}")
    print(f"Per-scenario budget cap: {BUDGET_CAP} core LLM calls")
    print(f"Target N:     {TARGET_N}")
    print(f"Min required: {MIN_REQUIRED}")
    print()
    print("Streaming LLM call previews to stderr ...")

    session_start = time.monotonic()
    for scenario in (SARCASM_SCENARIO, SUMMARIZATION_SCENARIO):
        await run_scenario(scenario)

    session_elapsed = time.monotonic() - session_start

    _h1("SESSION TOTALS")
    total_core_calls = 0
    total_alt_calls = 0
    total_in = 0
    total_out = 0
    for scenario in (SARCASM_SCENARIO, SUMMARIZATION_SCENARIO):
        assert scenario.core_backend is not None
        assert scenario.alt_backend is not None
        total_core_calls += len(scenario.core_backend.call_log)
        total_alt_calls += len(scenario.alt_backend.call_log)
        total_in += sum(log.input_tokens for log in scenario.core_logs)
        total_out += sum(log.output_tokens for log in scenario.core_logs)
        print(
            f"  {scenario.name:40} core_calls={len(scenario.core_backend.call_log)} "
            f"alt_calls={len(scenario.alt_backend.call_log)} "
            f"core_in_tokens={sum(log.input_tokens for log in scenario.core_logs)} "
            f"core_out_tokens={sum(log.output_tokens for log in scenario.core_logs)}"
        )
    print()
    print(f"  TOTAL core_calls={total_core_calls} alt_calls={total_alt_calls}")
    print(f"  TOTAL core_in_tokens={total_in} core_out_tokens={total_out}")
    print(f"  Session wall time: {session_elapsed:.1f}s")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
