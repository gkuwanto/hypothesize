"""Tests for the HTTP and CLI adapter stubs.

Both adapters live as import-clean placeholders in Feature 02; their
``build_runner`` methods raise ``NotImplementedError`` with a message
naming the future feature that owns the implementation. Coverage:
clean import, structural protocol conformance, construction success,
``extract_prompt`` returning ``None`` without raising, and the
expected raise on ``build_runner``.
"""

from __future__ import annotations

import pytest

from hypothesize.adapters.base import SystemAdapter
from hypothesize.adapters.cli import CliAdapter
from hypothesize.adapters.config import SystemConfig
from hypothesize.adapters.http import HttpAdapter


def test_http_adapter_imports_and_constructs() -> None:
    adapter = HttpAdapter()
    assert isinstance(adapter, SystemAdapter)


def test_cli_adapter_imports_and_constructs() -> None:
    adapter = CliAdapter()
    assert isinstance(adapter, SystemAdapter)


def test_http_adapter_build_runner_raises_not_implemented() -> None:
    cfg = SystemConfig(name="x", adapter="http", url="https://example.com/")
    with pytest.raises(NotImplementedError) as exc_info:
        HttpAdapter().build_runner(cfg)
    assert "Feature" in str(exc_info.value)


def test_cli_adapter_build_runner_raises_not_implemented() -> None:
    cfg = SystemConfig(name="x", adapter="cli", command=["echo", "hi"])
    with pytest.raises(NotImplementedError) as exc_info:
        CliAdapter().build_runner(cfg)
    assert "Feature" in str(exc_info.value)


def test_http_adapter_extract_prompt_returns_none() -> None:
    cfg = SystemConfig(name="x", adapter="http", url="https://example.com/")
    assert HttpAdapter().extract_prompt(cfg) is None


def test_cli_adapter_extract_prompt_returns_none() -> None:
    cfg = SystemConfig(name="x", adapter="cli", command=["echo", "hi"])
    assert CliAdapter().extract_prompt(cfg) is None
