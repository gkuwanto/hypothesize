"""Unit tests for ``make_auto_alternative``.

All tests use the in-memory ``MockBackend`` — no live LLM calls. The
module fixtures live in ``tests/_fixtures/example_systems/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypothesize.adapters.auto_alternative import make_auto_alternative
from hypothesize.adapters.config import SystemConfig
from hypothesize.adapters.errors import (
    AutoAlternativeUnavailable,
    BudgetExhausted,
)
from hypothesize.core.types import Budget, Hypothesis
from tests._fixtures.mock_backend import MockBackend

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "_fixtures" / "example_systems"


def _config(filename: str) -> SystemConfig:
    return SystemConfig(
        name="fixture",
        adapter="python_module",
        module_path=EXAMPLE_DIR / filename,
    )


def _hypothesis() -> Hypothesis:
    return Hypothesis(text="model fails on negation")


@pytest.mark.asyncio
async def test_clean_rewrite_response_returns_working_runner() -> None:
    rewritten = "You are a helpful test fixture. Pay attention to negation."
    response = json.dumps(
        {"rewritten_prompt": rewritten, "rationale": "added negation note"}
    )
    backend = MockBackend(responses=[response])
    budget = Budget(max_llm_calls=5)

    runner = await make_auto_alternative(
        current=_config("make_runner_system.py"),
        hypothesis=_hypothesis(),
        llm=backend,
        budget=budget,
    )
    out = await runner({"x": 1})
    assert out["prompt"] == rewritten
    assert out["echoed"] == {"x": 1}
    assert budget.calls_used == 1
    assert len(backend.calls) == 1


@pytest.mark.asyncio
async def test_fenced_rewrite_response_is_tolerated() -> None:
    payload = {"rewritten_prompt": "FENCED_REWRITE", "rationale": "ok"}
    response = "```json\n" + json.dumps(payload) + "\n```"
    backend = MockBackend(responses=[response])
    budget = Budget(max_llm_calls=5)

    runner = await make_auto_alternative(
        current=_config("make_runner_system.py"),
        hypothesis=_hypothesis(),
        llm=backend,
        budget=budget,
    )
    out = await runner({"k": "v"})
    assert out["prompt"] == "FENCED_REWRITE"
    assert budget.calls_used == 1


@pytest.mark.asyncio
async def test_malformed_response_raises_auto_alt_unavailable() -> None:
    backend = MockBackend(responses=["this is not JSON at all"])
    budget = Budget(max_llm_calls=5)

    with pytest.raises(AutoAlternativeUnavailable) as exc_info:
        await make_auto_alternative(
            current=_config("make_runner_system.py"),
            hypothesis=_hypothesis(),
            llm=backend,
            budget=budget,
        )
    msg = str(exc_info.value).lower()
    assert "rewrite" in msg or "json" in msg or "rewritten_prompt" in msg


@pytest.mark.asyncio
async def test_response_missing_required_key_raises_auto_alt_unavailable() -> None:
    response = json.dumps({"rationale": "no rewritten_prompt key here"})
    backend = MockBackend(responses=[response])
    budget = Budget(max_llm_calls=5)

    with pytest.raises(AutoAlternativeUnavailable):
        await make_auto_alternative(
            current=_config("make_runner_system.py"),
            hypothesis=_hypothesis(),
            llm=backend,
            budget=budget,
        )


@pytest.mark.asyncio
async def test_module_without_make_runner_raises_auto_alt_unavailable() -> None:
    """``bare_run.py`` exposes neither SYSTEM_PROMPT nor make_runner."""
    backend = MockBackend(responses=["should not be called"])
    budget = Budget(max_llm_calls=5)

    with pytest.raises(AutoAlternativeUnavailable):
        await make_auto_alternative(
            current=_config("bare_run.py"),
            hypothesis=_hypothesis(),
            llm=backend,
            budget=budget,
        )
    # Did not even attempt the LLM call.
    assert len(backend.calls) == 0
    assert budget.calls_used == 0


@pytest.mark.asyncio
async def test_module_with_only_system_prompt_raises_auto_alt_unavailable() -> None:
    """``system_prompt_only.py`` has SYSTEM_PROMPT but no make_runner."""
    backend = MockBackend(responses=["should not be called"])
    budget = Budget(max_llm_calls=5)

    with pytest.raises(AutoAlternativeUnavailable):
        await make_auto_alternative(
            current=_config("system_prompt_only.py"),
            hypothesis=_hypothesis(),
            llm=backend,
            budget=budget,
        )
    assert len(backend.calls) == 0
    assert budget.calls_used == 0


@pytest.mark.asyncio
async def test_exhausted_budget_raises_budget_exhausted() -> None:
    backend = MockBackend(responses=["should not be called"])
    budget = Budget(max_llm_calls=2, calls_used=2)

    with pytest.raises(BudgetExhausted):
        await make_auto_alternative(
            current=_config("make_runner_system.py"),
            hypothesis=_hypothesis(),
            llm=backend,
            budget=budget,
        )
    assert len(backend.calls) == 0


@pytest.mark.asyncio
async def test_non_python_module_adapter_raises_auto_alt_unavailable() -> None:
    """HTTP/CLI stub adapters return None from extract_prompt."""
    backend = MockBackend(responses=["unused"])
    budget = Budget(max_llm_calls=5)
    config = SystemConfig(name="stub", adapter="http", url="http://example/run")

    with pytest.raises(AutoAlternativeUnavailable):
        await make_auto_alternative(
            current=config,
            hypothesis=_hypothesis(),
            llm=backend,
            budget=budget,
        )
    assert len(backend.calls) == 0


@pytest.mark.asyncio
async def test_rewrite_payload_with_non_string_value_rejected() -> None:
    response = json.dumps({"rewritten_prompt": 42, "rationale": "wrong type"})
    backend = MockBackend(responses=[response])
    budget = Budget(max_llm_calls=5)

    with pytest.raises(AutoAlternativeUnavailable):
        await make_auto_alternative(
            current=_config("make_runner_system.py"),
            hypothesis=_hypothesis(),
            llm=backend,
            budget=budget,
        )
