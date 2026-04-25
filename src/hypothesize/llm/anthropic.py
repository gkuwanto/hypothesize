"""``AnthropicBackend``: real ``LLMBackend`` over the Anthropic SDK.

Satisfies the ``LLMBackend`` protocol from ``hypothesize.core.llm``. The
backend:

- translates core-style chat messages (role + content) into the
  ``messages.create`` shape the SDK expects, lifting ``role == "system"``
  entries out into the ``system=`` kwarg;
- honours an optional ``budget=`` kwarg as a safety net (short-circuits
  to an empty string when the budget is exhausted) but never mutates
  the budget — charging stays the core caller's responsibility;
- emits a ``RunnerCallLog`` on each successful call when a caller-
  supplied ``on_call`` callback is registered at construction;
- maps SDK exceptions into the four categories declared in
  ``hypothesize.llm.errors``; retries rate-limit and transient errors
  with 1s / 2s / 4s exponential backoff for up to three attempts.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

import anthropic

from hypothesize.core.types import Budget
from hypothesize.llm.config import AnthropicConfig, RunnerCallLog
from hypothesize.llm.errors import (
    AnthropicAuthError,
    AnthropicClientError,
    AnthropicRateLimited,
    AnthropicTransientError,
)

_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)
_MAX_ATTEMPTS = 3


class AnthropicBackend:
    """Anthropic-backed ``LLMBackend`` implementation."""

    def __init__(
        self,
        config: AnthropicConfig | None = None,
        client: Any = None,
        on_call: Callable[[RunnerCallLog], None] | None = None,
    ) -> None:
        self.config = config or AnthropicConfig()
        self.on_call = on_call
        self.client = client if client is not None else self._build_client()

    def _build_client(self) -> anthropic.AsyncAnthropic:
        if self.config.api_key_env is not None:
            api_key = os.environ.get(self.config.api_key_env)
            return anthropic.AsyncAnthropic(api_key=api_key)
        return anthropic.AsyncAnthropic()

    async def complete(self, messages: list[dict], **kwargs: Any) -> str:
        """Send ``messages`` to Anthropic and return the assistant text.

        Accepts these caller-controlled kwargs:

        - ``budget: Budget`` — if supplied and already exhausted, the
          backend returns ``""`` without calling the API. The budget is
          never mutated here.
        - ``model: str`` — overrides ``config.default_model`` for this
          call only.
        - ``max_tokens: int`` / ``timeout: float`` — override the
          config defaults for this call.

        Any other kwargs are forwarded to ``messages.create`` unchanged.
        """
        budget = kwargs.pop("budget", None)
        if isinstance(budget, Budget) and budget.exhausted():
            return ""

        model = kwargs.pop("model", self.config.default_model)
        max_tokens = kwargs.pop("max_tokens", self.config.max_tokens)
        timeout = kwargs.pop("timeout", self.config.timeout_seconds)

        system, user_messages = _split_system_messages(messages)

        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": user_messages,
            "timeout": timeout,
        }
        if system is not None:
            request["system"] = system
        request.update(kwargs)

        response = await self._call_with_retries(request)

        text = _extract_text(response)

        if self.on_call is not None:
            usage = getattr(response, "usage", None)
            self.on_call(
                RunnerCallLog(
                    model=model,
                    input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                    output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                )
            )

        return text

    async def _call_with_retries(self, request: dict[str, Any]) -> Any:
        last_transient: BaseException | None = None
        last_rate_limit: BaseException | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return await self.client.messages.create(**request)
            except anthropic.AuthenticationError:
                # ``from None`` keeps the upstream response body (which
                # may echo headers hinting at the key) out of the raised
                # exception's context chain.
                raise AnthropicAuthError(
                    "Anthropic authentication failed; "
                    "check the ANTHROPIC_API_KEY environment variable."
                ) from None
            except anthropic.RateLimitError as exc:
                last_rate_limit = exc
                if attempt < _MAX_ATTEMPTS - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    continue
                raise AnthropicRateLimited(
                    "Anthropic rate limit persisted after 3 attempts."
                ) from exc
            except (
                anthropic.APIConnectionError,
                anthropic.InternalServerError,
            ) as exc:
                last_transient = exc
                if attempt < _MAX_ATTEMPTS - 1:
                    await asyncio.sleep(_BACKOFF_SECONDS[attempt])
                    continue
                raise AnthropicTransientError(
                    "Anthropic transient error persisted after 3 attempts."
                ) from exc
            except anthropic.APIStatusError as exc:
                status = getattr(exc, "status_code", "?")
                body = getattr(exc, "body", None)
                raise AnthropicClientError(
                    f"Anthropic client error (status={status}, body={body!r})."
                ) from exc
        # The loop always either returns or raises above; this is
        # unreachable but keeps type checkers content.
        raise AnthropicTransientError(
            "Exhausted retries without a definitive error."
        ) from (last_transient or last_rate_limit)


def _split_system_messages(
    messages: list[dict],
) -> tuple[str | None, list[dict]]:
    system_chunks: list[str] = []
    user_messages: list[dict] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "system":
            if isinstance(content, str):
                system_chunks.append(content)
        else:
            user_messages.append(message)
    system = "\n\n".join(system_chunks) if system_chunks else None
    return system, user_messages


def _extract_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if not content:
        return ""
    first = content[0]
    text = getattr(first, "text", None)
    if not isinstance(text, str):
        return ""
    return text
