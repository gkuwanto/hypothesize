"""Parallel-execution smoke test.

50 parametrized variations exercise the ``-n auto`` path while the project
has almost no tests. Any shared-state bug in the fixtures or the backend
surfaces here as a flake when run in parallel.
"""

from __future__ import annotations

import pytest

from tests._fixtures.mock_backend import MockBackend


@pytest.mark.parametrize("response", [f"response-{i}" for i in range(50)])
async def test_tests_can_run_in_parallel(response: str) -> None:
    backend = MockBackend(responses=[response])
    result = await backend.complete([{"role": "user", "content": "ping"}])
    assert result == response
    assert len(backend.calls) == 1
