#!/usr/bin/env python3
"""Smoke test: run find_discriminating_inputs against the real Anthropic API.

This is a one-off diagnostic, not product code and not part of the pytest
suite. It exists to surface the gap between MockBackend (which always
returns well-formed scripted JSON) and real Claude (which may or may not).
Findings are written to scripts/SMOKE_FINDINGS.md and inform Feature 02's
design.

Scenario: a deliberately broken sentiment classifier that always predicts
"positive", pitted against a sarcasm-aware classifier built on Claude
Haiku. The discrimination algorithm should find sarcastic-positive inputs
where the dumb classifier fails and the alternative succeeds.

Run from repo root:

    ANTHROPIC_API_KEY=sk-ant-... python scripts/smoke_test.py

Requires the core package importable (i.e. run on a branch that has
Feature 01 merged in, or checked out).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

import anthropic

from hypothesize.core.discrimination import find_discriminating_inputs
from hypothesize.core.judge import RubricJudge
from hypothesize.core.types import Budget, Hypothesis

MODEL = "claude-haiku-4-5-20251001"
BUDGET_CAP = 30
TARGET_N = 5
MIN_REQUIRED = 3
MAX_TOKENS = 2048


class RealAnthropicBackend:
    """Inline LLMBackend wrapping anthropic.AsyncAnthropic. Diagnostic only.

    Every call is logged (messages + response or error). The first 200
    characters of each response are mirrored to stderr so a human watching
    the script run can see what Claude is actually returning. This class
    is not the future production backend; Feature 02 will design that
    properly.
    """

    def __init__(self, label: str, model: str = MODEL) -> None:
        self.client = anthropic.AsyncAnthropic()
        self.model = model
        self.label = label
        self.call_log: list[dict[str, Any]] = []

    async def complete(self, messages: list[dict], **kwargs: Any) -> str:
        system: str | None = None
        api_messages: list[dict] = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content")
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        api_kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": api_messages,
        }
        if system is not None:
            api_kwargs["system"] = system

        try:
            resp = await self.client.messages.create(**api_kwargs)
        except Exception as e:
            print(
                f"[{self.label}] API error: {type(e).__name__}: {e!r}",
                file=sys.stderr,
            )
            self.call_log.append(
                {"messages": messages, "error": f"{type(e).__name__}: {e!r}"}
            )
            raise

        text = ""
        try:
            text = resp.content[0].text  # type: ignore[union-attr]
        except (IndexError, AttributeError) as e:
            print(
                f"[{self.label}] Unexpected response shape: {e!r}",
                file=sys.stderr,
            )
            self.call_log.append(
                {
                    "messages": messages,
                    "error": f"response-shape: {e!r}",
                    "raw_response": repr(resp),
                }
            )
            return ""

        self.call_log.append({"messages": messages, "response": text})
        preview = text.replace("\n", " ")[:200]
        print(
            f"[{self.label}] call #{len(self.call_log)} -> {preview!r}",
            file=sys.stderr,
        )
        return text


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
    return "unknown"


async def current_runner(input_data: dict[str, Any]) -> dict[str, Any]:
    """Deliberately dumb classifier: always 'positive'."""
    return {"sentiment": "positive"}


class SarcasmAwareRunner:
    """Alternative runner: asks Haiku to classify, explicitly flagging sarcasm.

    Uses a separate backend instance so its calls don't mix with the core
    algorithm's budget accounting. The core algorithm only sees the single
    LLMBackend passed to find_discriminating_inputs.
    """

    def __init__(self, backend: RealAnthropicBackend) -> None:
        self.backend = backend

    async def __call__(self, input_data: dict[str, Any]) -> dict[str, Any]:
        text = ""
        for key in ("text", "input", "content", "sentence", "query", "message"):
            if isinstance(input_data.get(key), str) and input_data[key]:
                text = input_data[key]
                break
        if not text:
            # Fall back to JSON-dumping the whole input so the classifier
            # at least has something to read.
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
        # Strip trailing punctuation
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
    core: RealAnthropicBackend,
    alt: RealAnthropicBackend,
    result: Any,
    budget: Budget,
    elapsed: float,
) -> None:
    _section("RESULT SUMMARY")
    print(f"Status:        {result.status}")
    print(f"Budget used:   {result.budget_used}/{budget.max_llm_calls}")
    print(f"Wall time:     {elapsed:.1f}s")
    print(f"Core calls:    {len(core.call_log)}")
    print(f"Alt-runner:    {len(alt.call_log)} (not counted against core budget)")

    _section("CALLS PER PHASE (core backend)")
    phase_counts: dict[str, int] = {}
    for call in core.call_log:
        phase = classify_phase(call["messages"])
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
    for phase in (
        "decompose",
        "generate",
        "rubric_build",
        "rubric_judge",
        "pairwise_judge",
        "unknown",
    ):
        if phase in phase_counts:
            print(f"  {phase:15} {phase_counts[phase]}")

    _section("DIMENSIONS RETURNED BY DECOMPOSE")
    dims = None
    for call in core.call_log:
        if classify_phase(call["messages"]) != "decompose":
            continue
        response = call.get("response", "")
        try:
            parsed = json.loads(response)
            dims = parsed.get("dimensions")
        except (json.JSONDecodeError, TypeError):
            print("  decompose response did NOT parse as JSON")
            print(f"  raw (first 500 chars): {response[:500]!r}")
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
        phase = classify_phase(call["messages"])
        if phase not in json_expected:
            continue
        response = call.get("response", "")
        try:
            json.loads(response)
        except (json.JSONDecodeError, TypeError):
            parse_failures.append((i, phase, response))
    if not parse_failures:
        print("  All JSON-expected responses parsed cleanly.")
    else:
        print(f"  {len(parse_failures)} parse failure(s):")
        for i, phase, raw in parse_failures:
            print(f"  - call #{i+1} (phase={phase}):")
            for line in raw[:500].splitlines():
                print(f"      {line}")

    _section("CANDIDATE input_data SHAPES (from generate calls)")
    all_shapes: list[list[str]] = []
    for call in core.call_log:
        if classify_phase(call["messages"]) != "generate":
            continue
        response = call.get("response", "")
        try:
            parsed = json.loads(response)
        except (json.JSONDecodeError, TypeError):
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
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY environment variable is not set.\n"
            "Set it before running: export ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        return 1

    start = time.monotonic()

    core_backend = RealAnthropicBackend(label="core")
    alt_backend = RealAnthropicBackend(label="alt")

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
    except Exception as e:
        elapsed = time.monotonic() - start
        print(
            f"\nUnhandled exception after {elapsed:.1f}s: "
            f"{type(e).__name__}: {e!r}",
            file=sys.stderr,
        )
        raise

    elapsed = time.monotonic() - start
    report(core_backend, alt_backend, result, budget, elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
