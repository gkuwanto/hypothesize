"""MockBackend: an in-memory LLMBackend used by the test harness.

Implements the ``LLMBackend`` protocol defined in Feature 01's design.md:
an async ``complete(messages, **kwargs) -> str`` method. The backend replays
scripted responses in order and records every call for later assertion.
"""

from __future__ import annotations

from typing import Any


class MockBackend:
    """Scripted, call-recording backend for tests.

    Construct with an ordered list of response strings. Each call to
    ``complete`` pops the next response and appends a record to ``calls``.
    Exhausting the script raises ``IndexError`` with a clear message so
    tests that under-script fail loudly instead of hanging.
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses: list[str] = list(responses) if responses else []
        self._cursor: int = 0
        self.calls: list[dict[str, Any]] = []

    async def complete(self, messages: list[dict], **kwargs: Any) -> str:
        """Return the next scripted response and record the call."""
        if self._cursor >= len(self._responses):
            raise IndexError(
                f"MockBackend script exhausted: "
                f"{len(self._responses)} response(s) scripted, "
                f"call #{self._cursor + 1} requested. "
                f"Add more responses or check the test."
            )
        response = self._responses[self._cursor]
        self._cursor += 1
        self.calls.append(
            {"messages": messages, "kwargs": kwargs, "response": response}
        )
        return response

    def reset(self) -> None:
        """Clear recorded calls and rewind the script to the first response."""
        self.calls = []
        self._cursor = 0
