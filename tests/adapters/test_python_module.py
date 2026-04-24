"""Tests for ``PythonModuleAdapter``.

Exercises each contract variant (async entrypoint, sync entrypoint,
``make_runner``-based, ``SYSTEM_PROMPT``-only, bare ``run``-only, and
error paths for missing entrypoint / missing path). Uses the fixture
modules under ``tests/_fixtures/example_systems/``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hypothesize.adapters.config import SystemConfig
from hypothesize.adapters.errors import AutoAlternativeUnavailable
from hypothesize.adapters.python_module import PythonModuleAdapter

FIXTURES = (
    Path(__file__).parent.parent / "_fixtures" / "example_systems"
).resolve()


def _cfg(name: str, entrypoint: str = "run") -> SystemConfig:
    return SystemConfig(
        name="fixture",
        adapter="python_module",
        module_path=FIXTURES / f"{name}.py",
        entrypoint=entrypoint,
    )


# ---------------------------------------------------------------------------
# build_runner
# ---------------------------------------------------------------------------


async def test_async_entrypoint_passes_through() -> None:
    adapter = PythonModuleAdapter()
    runner = adapter.build_runner(_cfg("async_entrypoint"))
    result = await runner({"x": 1})
    assert result == {"echoed": {"x": 1}, "kind": "async"}


async def test_sync_entrypoint_wrapped_in_async_shim() -> None:
    adapter = PythonModuleAdapter()
    runner = adapter.build_runner(_cfg("sync_entrypoint"))
    result = await runner({"x": 2})
    assert result == {"echoed": {"x": 2}, "kind": "sync"}


async def test_make_runner_is_preferred_over_entrypoint() -> None:
    """When a module exposes ``make_runner``, it is used with prompt=None."""
    adapter = PythonModuleAdapter()
    runner = adapter.build_runner(_cfg("make_runner_system"))
    result = await runner({"q": "hi"})
    assert result["prompt"] == "You are a helpful test fixture."
    assert result["echoed"] == {"q": "hi"}


async def test_bare_run_only_uses_entrypoint() -> None:
    adapter = PythonModuleAdapter()
    runner = adapter.build_runner(_cfg("bare_run"))
    result = await runner({"k": "v"})
    assert result == {"echoed": {"k": "v"}}


def test_missing_entrypoint_raises_attribute_error() -> None:
    adapter = PythonModuleAdapter()
    with pytest.raises(AttributeError):
        adapter.build_runner(_cfg("no_entrypoint"))


def test_missing_module_path_raises_value_error() -> None:
    adapter = PythonModuleAdapter()
    cfg = SystemConfig(name="x", adapter="python_module", module_path=None)
    with pytest.raises(ValueError):
        adapter.build_runner(cfg)


def test_nonexistent_module_path_raises_file_not_found() -> None:
    adapter = PythonModuleAdapter()
    cfg = SystemConfig(
        name="x",
        adapter="python_module",
        module_path=FIXTURES / "does_not_exist.py",
    )
    with pytest.raises(FileNotFoundError):
        adapter.build_runner(cfg)


# ---------------------------------------------------------------------------
# extract_prompt
# ---------------------------------------------------------------------------


def test_extract_prompt_returns_value_when_both_present() -> None:
    adapter = PythonModuleAdapter()
    prompt = adapter.extract_prompt(_cfg("make_runner_system"))
    assert prompt == "You are a helpful test fixture."


def test_extract_prompt_none_when_only_system_prompt_present() -> None:
    """SYSTEM_PROMPT alone is not enough — auto-alt needs make_runner."""
    adapter = PythonModuleAdapter()
    assert adapter.extract_prompt(_cfg("system_prompt_only")) is None


def test_extract_prompt_none_for_bare_run_only() -> None:
    adapter = PythonModuleAdapter()
    assert adapter.extract_prompt(_cfg("bare_run")) is None


# ---------------------------------------------------------------------------
# build_runner_with_prompt (auto-alt hook)
# ---------------------------------------------------------------------------


async def test_build_runner_with_prompt_uses_make_runner() -> None:
    adapter = PythonModuleAdapter()
    runner = adapter.build_runner_with_prompt(
        _cfg("make_runner_system"), prompt="REWRITTEN"
    )
    result = await runner({"q": "hello"})
    assert result["prompt"] == "REWRITTEN"


def test_build_runner_with_prompt_raises_without_make_runner() -> None:
    adapter = PythonModuleAdapter()
    with pytest.raises(AutoAlternativeUnavailable):
        adapter.build_runner_with_prompt(_cfg("bare_run"), prompt="IGNORED")


def test_build_runner_with_prompt_raises_when_only_system_prompt() -> None:
    """SYSTEM_PROMPT without make_runner → auto-alt unavailable."""
    adapter = PythonModuleAdapter()
    with pytest.raises(AutoAlternativeUnavailable):
        adapter.build_runner_with_prompt(
            _cfg("system_prompt_only"), prompt="IGNORED"
        )


# ---------------------------------------------------------------------------
# caching
# ---------------------------------------------------------------------------


def test_module_loaded_once_and_cached_by_absolute_path() -> None:
    adapter = PythonModuleAdapter()
    cfg = _cfg("async_entrypoint")
    first = adapter._load(cfg.module_path)  # type: ignore[arg-type]
    second = adapter._load(cfg.module_path)  # type: ignore[arg-type]
    assert first is second


# ---------------------------------------------------------------------------
# protocol conformance
# ---------------------------------------------------------------------------


def test_adapter_is_structural_system_adapter() -> None:
    from hypothesize.adapters.base import SystemAdapter

    adapter = PythonModuleAdapter()
    assert isinstance(adapter, SystemAdapter)
