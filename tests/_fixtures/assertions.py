"""Custom assertion helpers used across the test suite."""

from __future__ import annotations

from typing import Any


def assert_budget_respected(budget: Any, max_expected: int) -> None:
    """Assert ``budget.calls_used <= max_expected`` with a readable message."""
    used = budget.calls_used
    assert used <= max_expected, (
        f"Budget exceeded: used {used} LLM calls, expected at most "
        f"{max_expected} (cap={budget.max_llm_calls})."
    )


def assert_call_pattern(mock_backend: Any, expected_substrings: list[str]) -> None:
    """Assert each expected substring appears in order across recorded calls.

    ``mock_backend`` is a MockBackend instance. Each recorded call is flattened
    to a string by joining message contents, and substrings must match in the
    given order (though a single call may contain multiple consecutive matches).
    """
    flat = []
    for call in mock_backend.calls:
        for msg in call.get("messages", []):
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, str):
                flat.append(content)
    haystack = "\n".join(flat)

    cursor = 0
    for needle in expected_substrings:
        idx = haystack.find(needle, cursor)
        assert idx != -1, (
            f"Expected substring not found in order: {needle!r}. "
            f"Recorded calls:\n{haystack}"
        )
        cursor = idx + len(needle)
