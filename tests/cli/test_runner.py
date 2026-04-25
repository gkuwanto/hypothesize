"""Tests for cli.runner — backend / runner / judge composition."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hypothesize.adapters.config import SystemConfig
from hypothesize.cli.config import (
    AlternativeConfig,
    DefaultsBlock,
    RunConfig,
)
from hypothesize.cli.runner import build_runners, run_discrimination
from hypothesize.core.types import Budget, Hypothesis
from tests._fixtures.mock_backend import MockBackend


def _write_system(tmp_path: Path) -> Path:
    p = tmp_path / "system.py"
    p.write_text(
        'SYSTEM_PROMPT = "be precise"\n'
        "def make_runner(prompt=None):\n"
        "    async def run(input_data):\n"
        "        return {'sentiment': 'positive'}\n"
        "    return run\n"
        "run = make_runner()\n"
    )
    return p


def _make_run_config(
    tmp_path: Path,
    *,
    alternative_kind: str = "auto",
    alt_module: Path | None = None,
) -> RunConfig:
    sysfile = _write_system(tmp_path)
    if alternative_kind == "auto":
        alt = AlternativeConfig(adapter="auto")
    else:
        alt = AlternativeConfig(
            adapter="python_module",
            module_path=alt_module or sysfile,
        )
    return RunConfig(
        name="demo",
        current=SystemConfig(
            name="demo",
            adapter="python_module",
            module_path=sysfile,
        ),
        alternative=alt,
        hypothesis=Hypothesis(text="the system fails on negation"),
        defaults=DefaultsBlock(target_n=2, min_required=1),
    )


def _scripted_decompose_response(n: int = 3) -> str:
    dims = [
        {
            "name": f"dim_{i}",
            "description": f"dimension number {i}",
            "examples": [],
        }
        for i in range(n)
    ]
    return json.dumps({"dimensions": dims})


def _scripted_generate_response(per_dim: int = 3) -> str:
    cands = [
        {
            "input_data": {"text": f"input {i}"},
            "rationale": f"rationale {i}",
        }
        for i in range(per_dim)
    ]
    return json.dumps({"candidates": cands})


def _scripted_rubric_build() -> str:
    return "Rubric:\n- The system handles X correctly.\n"


def _scripted_rubric_judge(passed: bool, reason: str = "ok") -> str:
    return json.dumps({"passed": passed, "reason": reason})


async def test_build_runners_with_explicit_alternative(tmp_path: Path) -> None:
    _write_system(tmp_path)
    alt_file = tmp_path / "alt_system.py"
    alt_file.write_text(
        "def make_runner(prompt=None):\n"
        "    async def run(input_data):\n"
        "        return {'sentiment': 'negative'}\n"
        "    return run\n"
        "run = make_runner()\n"
    )
    config = _make_run_config(
        tmp_path, alternative_kind="python_module", alt_module=alt_file
    )
    backend = MockBackend()
    budget = Budget(max_llm_calls=10)
    current_runner, alt_runner = await build_runners(
        config,
        hypothesis=Hypothesis(text="x"),
        backend=backend,
        budget=budget,
    )
    cur_out = await current_runner({"text": "hi"})
    alt_out = await alt_runner({"text": "hi"})
    assert cur_out == {"sentiment": "positive"}
    assert alt_out == {"sentiment": "negative"}
    # No LLM calls when both runners are explicit modules
    assert len(backend.calls) == 0


async def test_build_runners_with_auto_alternative(tmp_path: Path) -> None:
    config = _make_run_config(tmp_path, alternative_kind="auto")
    backend = MockBackend(
        responses=[
            json.dumps(
                {
                    "rewritten_prompt": "be MORE precise about negation",
                    "rationale": "added negation guidance",
                }
            )
        ]
    )
    budget = Budget(max_llm_calls=10)
    current_runner, alt_runner = await build_runners(
        config,
        hypothesis=Hypothesis(text="x"),
        backend=backend,
        budget=budget,
    )
    # auto-alt charges one call
    assert budget.calls_used == 1
    cur_out = await current_runner({"text": "hi"})
    alt_out = await alt_runner({"text": "hi"})
    assert cur_out == {"sentiment": "positive"}
    # alt runner uses the rewritten prompt — same module, same return shape
    assert alt_out == {"sentiment": "positive"}


async def test_run_discrimination_returns_ok_with_mock_backend(tmp_path: Path) -> None:
    config = _make_run_config(tmp_path, alternative_kind="python_module")
    # 3 dims × 3 candidates = 9 candidates; each candidate -> 2 verdicts = 18 judge calls.
    # Plus 1 decompose + 3 generate + 1 rubric_build = 5. Total ≤ 30, scripted with margin.
    verdict_pairs: list[str] = []
    for _ in range(15):
        verdict_pairs.append(_scripted_rubric_judge(False, "current fails"))
        verdict_pairs.append(_scripted_rubric_judge(True, "alt passes"))
    backend = MockBackend(
        responses=[
            _scripted_decompose_response(3),
            _scripted_generate_response(3),
            _scripted_generate_response(3),
            _scripted_generate_response(3),
            _scripted_rubric_build(),
            *verdict_pairs,
        ]
    )
    budget = Budget(max_llm_calls=200)
    result = await run_discrimination(
        config=config,
        hypothesis=Hypothesis(text="the system fails on negation"),
        target_n=2,
        min_required=1,
        budget=budget,
        backend=backend,
    )
    assert result.status == "ok"
    assert len(result.test_cases) == 2  # diversified to target_n


async def test_run_discrimination_insufficient_evidence(tmp_path: Path) -> None:
    config = _make_run_config(tmp_path, alternative_kind="python_module")
    backend = MockBackend(
        responses=[
            _scripted_decompose_response(3),
            _scripted_generate_response(3),
            _scripted_generate_response(3),
            _scripted_generate_response(3),
            _scripted_rubric_build(),
        ]
        + [_scripted_rubric_judge(True, "all pass") for _ in range(40)]
    )
    budget = Budget(max_llm_calls=200)
    result = await run_discrimination(
        config=config,
        hypothesis=Hypothesis(text="the system fails on negation"),
        target_n=2,
        min_required=1,
        budget=budget,
        backend=backend,
    )
    assert result.status == "insufficient_evidence"
    assert result.insufficient is not None
    assert result.insufficient.discriminating_found == 0


async def test_build_runners_raises_when_auto_unavailable(tmp_path: Path) -> None:
    sysfile = tmp_path / "system.py"
    # No make_runner — auto-alt unavailable
    sysfile.write_text(
        "async def run(input_data):\n    return {'sentiment': 'positive'}\n"
    )
    config = RunConfig(
        name="demo",
        current=SystemConfig(
            name="demo", adapter="python_module", module_path=sysfile
        ),
        alternative=AlternativeConfig(adapter="auto"),
        hypothesis=Hypothesis(text="x"),
    )
    from hypothesize.adapters.errors import AutoAlternativeUnavailable

    backend = MockBackend()
    budget = Budget(max_llm_calls=10)
    with pytest.raises(AutoAlternativeUnavailable):
        await build_runners(
            config,
            hypothesis=Hypothesis(text="x"),
            backend=backend,
            budget=budget,
        )
