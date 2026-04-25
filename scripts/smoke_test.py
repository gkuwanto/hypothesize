#!/usr/bin/env python3
"""Smoke test: run find_discriminating_inputs against the real Anthropic API.

This is a one-off diagnostic, not product code and not part of the pytest
suite. It exists to surface the gap between MockBackend (which always
returns well-formed scripted JSON) and real Claude (which may or may not).
Findings are written to scripts/SMOKE_FINDINGS_2.md and inform Feature
03's design.

Scenario: a deliberately broken sentiment classifier that always predicts
"positive", pitted against a sarcasm-aware classifier built on Claude
Haiku. The discrimination algorithm should find sarcastic-positive inputs
where the dumb classifier fails and the alternative succeeds.

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


async def current_runner(input_data: dict[str, Any]) -> dict[str, Any]:
    """Deliberately dumb classifier: always 'positive'."""
    return {"sentiment": "positive"}


class SarcasmAwareRunner:
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


def _section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def report(
    core: RecordingBackend,
    alt: RecordingBackend,
    core_logs: list[RunnerCallLog],
    result: Any,
    budget: Budget,
    elapsed: float,
) -> None:
    _section("RESULT SUMMARY")
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
        # Pair logs with phases by index — RecordingBackend records a
        # call_log entry per ``inner.complete`` call, and the inner
        # backend's ``on_call`` fires once per successful response, so
        # entries align by sequence.
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

    start = time.monotonic()

    config = AnthropicConfig(default_model=MODEL, max_tokens=MAX_TOKENS)
    core_logs: list[RunnerCallLog] = []
    inner_core = AnthropicBackend(config=config, on_call=core_logs.append)
    inner_alt = AnthropicBackend(config=config)
    core_backend = RecordingBackend("core", inner_core)
    alt_backend = RecordingBackend("alt", inner_alt)

    hypothesis = Hypothesis(
        text=(
            "the sentiment classifier fails on sarcastic positive text "
            "(surface tokens positive, intent negative)"
        )
    )
    context = [
        "The current system is a naive sentiment classifier that always "
        "predicts 'positive' for any input.",
        "The alternative system is expected to detect sarcastic statements "
        "whose surface tokens read positive but whose intent is negative.",
    ]
    budget = Budget(max_llm_calls=BUDGET_CAP)
    judge = RubricJudge(llm=core_backend)
    alt_runner = SarcasmAwareRunner(alt_backend)

    print("=" * 72)
    print("HYPOTHESIZE smoke test — real Anthropic API")
    print("=" * 72)
    print(f"Model:        {MODEL}")
    print(f"Budget cap:   {BUDGET_CAP} core LLM calls")
    print(f"Target N:     {TARGET_N}")
    print(f"Min required: {MIN_REQUIRED}")
    print(f"Hypothesis:   {hypothesis.text}")
    print()
    print("Streaming LLM call previews to stderr ...")

    try:
        result = await find_discriminating_inputs(
            hypothesis=hypothesis,
            current_runner=current_runner,
            alternative_runner=alt_runner,
            context=context,
            judge=judge,
            llm=core_backend,
            budget=budget,
            target_n=TARGET_N,
            min_required=MIN_REQUIRED,
        )
    except (AutoAlternativeUnavailable, BudgetExhausted):
        # These are pre-pipeline errors and the smoke scenario does not
        # invoke ``make_auto_alternative``. Catching them here is purely
        # defensive — surfacing cleanly rather than crashing.
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
    report(core_backend, alt_backend, core_logs, result, budget, elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
