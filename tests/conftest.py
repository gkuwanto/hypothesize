"""Shared fixtures for the hypothesize test suite.

This file exists before the product types it references. Feature 01 task 1.1
will create ``src/hypothesize/core/types.py`` with ``Budget``, ``Hypothesis``,
etc. Until then, the affected fixtures skip with a clear message; the harness
self-tests under ``tests/_harness/`` do not depend on those types and run.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests._fixtures.mock_backend import MockBackend

try:
    from hypothesize.core.types import Budget, Hypothesis

    _TYPES_AVAILABLE = True
except ImportError:
    _TYPES_AVAILABLE = False


def _requires_types() -> None:
    if not _TYPES_AVAILABLE:
        pytest.skip(
            "hypothesize.core.types not yet implemented (Feature 01 task 1.1)"
        )


@pytest.fixture
def mock_llm() -> MockBackend:
    """Return an empty-scripted MockBackend.

    Tests that need scripted responses should construct their own
    ``MockBackend(responses=[...])`` rather than trying to configure this
    fixture — the fixture is intentionally a no-script default that records
    calls and raises on attempted use.
    """
    return MockBackend()


@pytest.fixture
def fresh_budget(request: pytest.FixtureRequest) -> Budget:
    """Return a fresh Budget. Override the cap via indirect parameterization."""
    _requires_types()
    max_calls = getattr(request, "param", 200)
    return Budget(max_llm_calls=max_calls)


@pytest.fixture
def tight_budget() -> Budget:
    """Return a Budget with ``max_llm_calls=3`` for exhaustion-path tests."""
    _requires_types()
    return Budget(max_llm_calls=3)


@pytest.fixture
def sample_hypothesis() -> Hypothesis:
    """Return a representative Hypothesis for tests that don't care about content."""
    _requires_types()
    return Hypothesis(
        text="The current system mishandles negated queries.",
        context_refs=[],
    )


@pytest.fixture
def sample_context() -> list[str]:
    """Return a list of short context strings for tests that need context."""
    return [
        "User stakeholders report failures on negated questions.",
        "Example: 'which products are NOT organic?' returns organic products.",
    ]


class _CallRecorder:
    """Context-manager helper wrapping a MockBackend with assertion sugar."""

    def __init__(self, backend: MockBackend) -> None:
        self.backend = backend

    def __enter__(self) -> _CallRecorder:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def assert_call_count(self, n: int) -> None:
        actual = len(self.backend.calls)
        assert actual == n, f"Expected {n} LLM call(s), recorded {actual}."

    def assert_called_with_substring(self, s: str) -> None:
        for call in self.backend.calls:
            for msg in call.get("messages", []):
                content = msg.get("content") if isinstance(msg, dict) else None
                if isinstance(content, str) and s in content:
                    return
        raise AssertionError(
            f"No recorded call contained substring {s!r}. "
            f"Calls: {self.backend.calls}"
        )


@pytest.fixture
def record_calls(mock_llm: MockBackend) -> _CallRecorder:
    """Wrap ``mock_llm`` in a recorder exposing ``assert_call_count`` etc."""
    return _CallRecorder(mock_llm)
