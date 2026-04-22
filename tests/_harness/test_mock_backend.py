"""Self-tests for MockBackend."""

from __future__ import annotations

import pytest

from tests._fixtures.mock_backend import MockBackend


async def test_mock_backend_returns_scripted_responses_in_order() -> None:
    backend = MockBackend(responses=["first", "second", "third"])
    assert await backend.complete([{"role": "user", "content": "a"}]) == "first"
    assert await backend.complete([{"role": "user", "content": "b"}]) == "second"
    assert await backend.complete([{"role": "user", "content": "c"}]) == "third"


async def test_mock_backend_records_calls_with_messages_and_kwargs() -> None:
    backend = MockBackend(responses=["ok"])
    await backend.complete([{"role": "user", "content": "hi"}], temperature=0.2)
    assert len(backend.calls) == 1
    call = backend.calls[0]
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert call["kwargs"] == {"temperature": 0.2}
    assert call["response"] == "ok"


async def test_mock_backend_raises_on_exhausted_script() -> None:
    backend = MockBackend(responses=["only"])
    await backend.complete([{"role": "user", "content": "x"}])
    with pytest.raises(IndexError, match="script exhausted"):
        await backend.complete([{"role": "user", "content": "y"}])


async def test_mock_backend_reset_clears_calls_and_rewinds() -> None:
    backend = MockBackend(responses=["a", "b"])
    await backend.complete([{"role": "user", "content": "1"}])
    backend.reset()
    assert backend.calls == []
    assert await backend.complete([{"role": "user", "content": "2"}]) == "a"


async def test_mock_backend_with_empty_script_records_but_raises_on_call() -> None:
    backend = MockBackend()
    assert backend.calls == []
    with pytest.raises(IndexError, match="script exhausted"):
        await backend.complete([{"role": "user", "content": "z"}])
