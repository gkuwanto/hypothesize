"""LLMBackend protocol.

The core layer talks to LLMs only through this protocol. Production
implementations live in ``src/hypothesize/llm/`` (Feature 02). Tests inject
``tests/_fixtures/mock_backend.MockBackend``, which satisfies this protocol
by scripting responses and recording calls.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMBackend(Protocol):
    """Minimal async completion interface.

    Implementations accept a list of chat-style messages
    (``{"role": ..., "content": ...}``) and return the assistant's text
    response. Extra keyword arguments (e.g. ``model``, ``temperature``) are
    passed through to the underlying provider and recorded by mocks.
    """

    async def complete(self, messages: list[dict], **kwargs: Any) -> str: ...
