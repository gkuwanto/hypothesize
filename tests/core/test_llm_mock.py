"""Tests for the LLMBackend protocol and MockBackend integration (Task 1.2)."""

from __future__ import annotations

import inspect

import pytest

from hypothesize.core.llm import LLMBackend
from tests._fixtures.mock_backend import MockBackend


def test_llm_backend_is_a_protocol() -> None:
    assert hasattr(LLMBackend, "complete")


def test_mock_backend_satisfies_protocol_at_runtime() -> None:
    backend: LLMBackend = MockBackend(responses=["x"])
    assert callable(backend.complete)


def test_mock_backend_complete_is_async() -> None:
    backend = MockBackend(responses=["x"])
    assert inspect.iscoroutinefunction(backend.complete)


async def test_mock_backend_replays_script_in_order() -> None:
    backend = MockBackend(responses=["alpha", "beta", "gamma"])
    got = [
        await backend.complete([{"role": "user", "content": "ask 1"}]),
        await backend.complete([{"role": "user", "content": "ask 2"}]),
        await backend.complete([{"role": "user", "content": "ask 3"}]),
    ]
    assert got == ["alpha", "beta", "gamma"]


async def test_mock_backend_records_calls_with_messages_and_kwargs() -> None:
    backend = MockBackend(responses=["ok"])
    await backend.complete(
        [{"role": "user", "content": "hi"}],
        temperature=0.1,
        model="test-model",
    )
    assert len(backend.calls) == 1
    call = backend.calls[0]
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert call["kwargs"] == {"temperature": 0.1, "model": "test-model"}


async def test_mock_backend_raises_index_error_on_exhausted_script() -> None:
    backend = MockBackend(responses=["only"])
    await backend.complete([{"role": "user", "content": "a"}])
    with pytest.raises(IndexError, match="script exhausted"):
        await backend.complete([{"role": "user", "content": "b"}])


async def test_empty_script_raises_immediately() -> None:
    backend = MockBackend()
    with pytest.raises(IndexError, match="script exhausted"):
        await backend.complete([{"role": "user", "content": "x"}])
