"""Live tests against the real Anthropic API.

These exercise (a) the basic ``complete`` round-trip, with token
accounting via the ``on_call`` hook, and (b) the JSON-extractor
applied to whatever framing real Haiku ships back when asked for
JSON. Skip cleanly when ``ANTHROPIC_API_KEY`` is not loaded; never
assert on specific model wording.

Run:    pytest tests/_live -m live -v
"""

from __future__ import annotations

import pytest

from hypothesize.core.json_extract import parse_json_response
from hypothesize.llm.config import RunnerCallLog

pytestmark = pytest.mark.live


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_anthropic_backend_basic_call(anthropic_backend_factory) -> None:
    """One tiny round-trip; expect non-empty text + a logged RunnerCallLog."""
    logs: list[RunnerCallLog] = []
    backend = anthropic_backend_factory(on_call=logs.append)

    text = await backend.complete(
        [
            {
                "role": "user",
                "content": "Reply with exactly the single word: pong",
            }
        ]
    )

    assert isinstance(text, str)
    assert text.strip(), "expected non-empty assistant text"
    assert len(logs) == 1, "on_call should fire exactly once per complete"
    log = logs[0]
    assert isinstance(log, RunnerCallLog)
    assert log.input_tokens > 0
    assert log.output_tokens > 0
    assert log.model  # model name surfaced from config


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_anthropic_backend_handles_real_fenced_response(
    anthropic_backend,
) -> None:
    """Ask for JSON; verify parse_json_response copes with Haiku's framing.

    Whether Haiku wraps the response in fences, prefixes prose, or
    returns clean JSON, the extractor should produce a dict with the
    requested keys. The point of this test is to keep
    ``parse_json_response`` honest against real-world framing — not to
    assert any specific structural choice.
    """
    raw = await anthropic_backend.complete(
        [
            {
                "role": "user",
                "content": (
                    "Return JSON with two keys: 'colour' (string) and "
                    "'count' (integer). Pick any plausible values. "
                    "No prose outside the JSON."
                ),
            }
        ]
    )

    parsed = parse_json_response(raw)
    assert isinstance(parsed, dict), (
        f"extractor failed on real Haiku response; raw was: {raw!r}"
    )
    assert "colour" in parsed
    assert "count" in parsed
    assert isinstance(parsed["colour"], str)
    assert isinstance(parsed["count"], int)
