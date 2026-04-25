"""Tests for ``AnthropicBackend``.

Every test injects a stub ``AsyncAnthropic`` client — no network calls,
no real API key required. The backend surface verified here is:

- message translation (``role == "system"`` separated from user/assistant)
- model selection (config default, per-call override)
- budget short-circuit (no API call when budget exhausted)
- telemetry via ``on_call`` receiving a ``RunnerCallLog``
- empty / malformed response content returns ``""`` (no raise)
- error mapping to typed exceptions in ``hypothesize.llm.errors``
- retry with exponential backoff on rate-limit and transient errors
"""

from __future__ import annotations

import asyncio
from typing import Any

import anthropic
import httpx
import pytest

from hypothesize.core.types import Budget
from hypothesize.llm.anthropic import AnthropicBackend
from hypothesize.llm.config import AnthropicConfig, RunnerCallLog
from hypothesize.llm.errors import (
    AnthropicAuthError,
    AnthropicClientError,
    AnthropicRateLimited,
    AnthropicTransientError,
)

# ---------------------------------------------------------------------------
# Stubs: a minimal async client that mirrors the shape of anthropic.AsyncAnthropic
# ---------------------------------------------------------------------------


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Block:
    def __init__(self, text: str) -> None:
        self.text = text


class _Response:
    def __init__(
        self,
        text: str = "ok",
        input_tokens: int = 3,
        output_tokens: int = 5,
        content: list[_Block] | None = None,
    ) -> None:
        self.content = content if content is not None else [_Block(text)]
        self.usage = _Usage(input_tokens, output_tokens)


class _Messages:
    def __init__(self, script: list[Any] | None = None) -> None:
        # script items are either _Response instances or Exception instances
        self.script = list(script) if script else []
        self.calls: list[dict] = []

    async def create(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        if not self.script:
            return _Response()
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _StubClient:
    def __init__(self, script: list[Any] | None = None) -> None:
        self.messages = _Messages(script)


def _httpx_response(status: int) -> httpx.Response:
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status, request=req)


def _httpx_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch asyncio.sleep so backoff delays do not slow the suite."""

    async def _noop(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _noop)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_backend_constructs_with_injected_client_and_default_config() -> None:
    client = _StubClient()
    backend = AnthropicBackend(client=client)
    assert backend.config.default_model  # populated from AnthropicConfig default
    assert backend.client is client


def test_backend_accepts_custom_config() -> None:
    cfg = AnthropicConfig(default_model="claude-custom", max_tokens=512)
    client = _StubClient()
    backend = AnthropicBackend(config=cfg, client=client)
    assert backend.config.default_model == "claude-custom"
    assert backend.config.max_tokens == 512


# ---------------------------------------------------------------------------
# Translation + basic call
# ---------------------------------------------------------------------------


async def test_complete_translates_system_messages_to_system_kwarg() -> None:
    client = _StubClient(script=[_Response(text="ok")])
    backend = AnthropicBackend(client=client)
    await backend.complete(
        [
            {"role": "system", "content": "you are a helper"},
            {"role": "user", "content": "hi"},
        ]
    )
    call = client.messages.calls[0]
    assert call.get("system") == "you are a helper"
    assert call.get("messages") == [{"role": "user", "content": "hi"}]


async def test_complete_joins_multiple_system_messages() -> None:
    client = _StubClient(script=[_Response()])
    backend = AnthropicBackend(client=client)
    await backend.complete(
        [
            {"role": "system", "content": "part 1"},
            {"role": "system", "content": "part 2"},
            {"role": "user", "content": "hi"},
        ]
    )
    call = client.messages.calls[0]
    assert "part 1" in call["system"]
    assert "part 2" in call["system"]


async def test_complete_returns_text_from_first_content_block() -> None:
    client = _StubClient(script=[_Response(text="hello world")])
    backend = AnthropicBackend(client=client)
    result = await backend.complete([{"role": "user", "content": "hi"}])
    assert result == "hello world"


async def test_complete_uses_default_model_when_no_override() -> None:
    cfg = AnthropicConfig(default_model="claude-default-x")
    client = _StubClient(script=[_Response()])
    backend = AnthropicBackend(config=cfg, client=client)
    await backend.complete([{"role": "user", "content": "hi"}])
    assert client.messages.calls[0]["model"] == "claude-default-x"


async def test_complete_per_call_model_overrides_default() -> None:
    cfg = AnthropicConfig(default_model="claude-default-x")
    client = _StubClient(script=[_Response()])
    backend = AnthropicBackend(config=cfg, client=client)
    await backend.complete(
        [{"role": "user", "content": "hi"}], model="claude-haiku-override"
    )
    assert client.messages.calls[0]["model"] == "claude-haiku-override"


async def test_complete_passes_max_tokens_from_config() -> None:
    cfg = AnthropicConfig(max_tokens=128)
    client = _StubClient(script=[_Response()])
    backend = AnthropicBackend(config=cfg, client=client)
    await backend.complete([{"role": "user", "content": "hi"}])
    assert client.messages.calls[0]["max_tokens"] == 128


# ---------------------------------------------------------------------------
# Empty / malformed response content
# ---------------------------------------------------------------------------


async def test_empty_content_block_returns_empty_string() -> None:
    client = _StubClient(script=[_Response(content=[])])
    backend = AnthropicBackend(client=client)
    result = await backend.complete([{"role": "user", "content": "hi"}])
    assert result == ""


async def test_content_block_without_text_returns_empty_string() -> None:
    class _NoText:
        pass

    client = _StubClient(script=[_Response(content=[_NoText()])])  # type: ignore[list-item]
    backend = AnthropicBackend(client=client)
    result = await backend.complete([{"role": "user", "content": "hi"}])
    assert result == ""


# ---------------------------------------------------------------------------
# Budget short-circuit
# ---------------------------------------------------------------------------


async def test_budget_exhausted_returns_empty_without_calling_api() -> None:
    client = _StubClient()  # no response scripted — calling it would fail
    backend = AnthropicBackend(client=client)
    b = Budget(max_llm_calls=0)
    assert b.exhausted()
    result = await backend.complete([{"role": "user", "content": "hi"}], budget=b)
    assert result == ""
    assert client.messages.calls == []


async def test_backend_does_not_mutate_budget() -> None:
    client = _StubClient(script=[_Response()])
    backend = AnthropicBackend(client=client)
    b = Budget(max_llm_calls=10)
    await backend.complete([{"role": "user", "content": "hi"}], budget=b)
    assert b.calls_used == 0  # charging is the core caller's responsibility


# ---------------------------------------------------------------------------
# on_call telemetry
# ---------------------------------------------------------------------------


async def test_on_call_receives_runner_call_log() -> None:
    received: list[RunnerCallLog] = []
    client = _StubClient(script=[_Response(input_tokens=11, output_tokens=22)])
    cfg = AnthropicConfig(default_model="claude-y")
    backend = AnthropicBackend(config=cfg, client=client, on_call=received.append)
    await backend.complete([{"role": "user", "content": "hi"}])
    assert len(received) == 1
    log = received[0]
    assert isinstance(log, RunnerCallLog)
    assert log.model == "claude-y"
    assert log.input_tokens == 11
    assert log.output_tokens == 22


async def test_on_call_not_invoked_on_budget_shortcircuit() -> None:
    received: list[RunnerCallLog] = []
    client = _StubClient()
    backend = AnthropicBackend(client=client, on_call=received.append)
    b = Budget(max_llm_calls=0)
    await backend.complete([{"role": "user", "content": "hi"}], budget=b)
    assert received == []


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


async def test_authentication_error_maps_to_typed_exception() -> None:
    err = anthropic.AuthenticationError(
        "invalid key",
        response=_httpx_response(401),
        body=None,
    )
    client = _StubClient(script=[err])
    backend = AnthropicBackend(client=client)
    with pytest.raises(AnthropicAuthError) as exc_info:
        await backend.complete([{"role": "user", "content": "hi"}])
    # Auth error must not retry.
    assert len(client.messages.calls) == 1
    # Message must not include the raw upstream exception text verbatim
    # (which can include response bodies that hint at the key).
    assert "ANTHROPIC_API_KEY" in str(exc_info.value)


async def test_rate_limit_retries_three_times_then_raises() -> None:
    err = lambda: anthropic.RateLimitError(  # noqa: E731
        "429", response=_httpx_response(429), body=None
    )
    client = _StubClient(script=[err(), err(), err()])
    backend = AnthropicBackend(client=client)
    with pytest.raises(AnthropicRateLimited):
        await backend.complete([{"role": "user", "content": "hi"}])
    assert len(client.messages.calls) == 3


async def test_rate_limit_then_success_on_retry() -> None:
    err = anthropic.RateLimitError(
        "429", response=_httpx_response(429), body=None
    )
    client = _StubClient(script=[err, _Response(text="recovered")])
    backend = AnthropicBackend(client=client)
    result = await backend.complete([{"role": "user", "content": "hi"}])
    assert result == "recovered"
    assert len(client.messages.calls) == 2


async def test_api_connection_error_retries_then_maps_to_transient() -> None:
    err = lambda: anthropic.APIConnectionError(request=_httpx_request())  # noqa: E731
    client = _StubClient(script=[err(), err(), err()])
    backend = AnthropicBackend(client=client)
    with pytest.raises(AnthropicTransientError):
        await backend.complete([{"role": "user", "content": "hi"}])
    assert len(client.messages.calls) == 3


async def test_internal_server_error_retries_then_maps_to_transient() -> None:
    err = lambda: anthropic.InternalServerError(  # noqa: E731
        "500", response=_httpx_response(500), body=None
    )
    client = _StubClient(script=[err(), err(), err()])
    backend = AnthropicBackend(client=client)
    with pytest.raises(AnthropicTransientError):
        await backend.complete([{"role": "user", "content": "hi"}])
    assert len(client.messages.calls) == 3


async def test_bad_request_error_maps_to_client_error_no_retry() -> None:
    err = anthropic.BadRequestError(
        "bad request",
        response=_httpx_response(400),
        body={"error": "bad"},
    )
    client = _StubClient(script=[err])
    backend = AnthropicBackend(client=client)
    with pytest.raises(AnthropicClientError) as exc_info:
        await backend.complete([{"role": "user", "content": "hi"}])
    assert len(client.messages.calls) == 1
    # Status and body should be present for debugging.
    s = str(exc_info.value)
    assert "400" in s
