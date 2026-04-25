"""Tests for examples/hotpotqa/ — closed-book multi-hop QA example.

All tests run with a MockBackend; no live LLM calls.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from hypothesize.cli.config import load_run_config
from tests._fixtures.mock_backend import MockBackend

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent.parent / "examples" / "hotpotqa"


def _load_hotpotqa_module():
    spec = importlib.util.spec_from_file_location(
        "_hotpotqa_test_module", EXAMPLES_ROOT / "system.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_module_imports_cleanly() -> None:
    module = _load_hotpotqa_module()
    assert hasattr(module, "SYSTEM_PROMPT")
    assert hasattr(module, "DIRECT_PROMPT")
    assert hasattr(module, "DECOMPOSE_PROMPT")
    assert hasattr(module, "make_runner")
    assert hasattr(module, "run")


def test_default_system_prompt_is_direct() -> None:
    module = _load_hotpotqa_module()
    assert module.SYSTEM_PROMPT == module.DIRECT_PROMPT


def test_both_prompts_are_plausible() -> None:
    module = _load_hotpotqa_module()
    # No strawman language. Both prompts must read as plausible
    # engineering choices a real team might ship.
    forbidden = ["be bad at", "ignore the question", "ignore X"]
    for prompt in (module.DIRECT_PROMPT, module.DECOMPOSE_PROMPT):
        for token in forbidden:
            assert token not in prompt.lower()
        assert len(prompt) > 20


async def test_runner_returns_answer_field() -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=["Paris"])
    runner = module.make_runner(backend=backend)
    result = await runner({"question": "What is the capital of France?"})
    assert "answer" in result
    assert result["answer"] == "Paris"


async def test_runner_strips_whitespace() -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=["  Paris  \n"])
    runner = module.make_runner(backend=backend)
    result = await runner({"question": "What is the capital of France?"})
    assert result["answer"] == "Paris"


async def test_runner_strips_answer_prefix() -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=["Answer: Paris"])
    runner = module.make_runner(backend=backend)
    result = await runner({"question": "What is the capital of France?"})
    assert result["answer"] == "Paris"


async def test_runner_strips_the_answer_is_prefix() -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=["The answer is Paris."])
    runner = module.make_runner(backend=backend)
    result = await runner({"question": "What is the capital of France?"})
    assert result["answer"] == "Paris"


async def test_runner_strips_trailing_punctuation() -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=["Paris."])
    runner = module.make_runner(backend=backend)
    result = await runner({"question": "?"})
    assert result["answer"] == "Paris"


async def test_runner_handles_empty_response() -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=[""])
    runner = module.make_runner(backend=backend)
    result = await runner({"question": "?"})
    assert result["answer"] == ""


async def test_make_runner_uses_overridden_prompt() -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=["Paris"])
    custom = "Answer with the city name."
    runner = module.make_runner(prompt=custom, backend=backend)
    await runner({"question": "?"})
    assert any(
        msg.get("role") == "system" and custom in msg.get("content", "")
        for call in backend.calls
        for msg in call["messages"]
    )


async def test_default_prompt_is_direct_when_none() -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=["Paris"])
    runner = module.make_runner(prompt=None, backend=backend)
    await runner({"question": "?"})
    direct = module.DIRECT_PROMPT
    assert any(
        msg.get("role") == "system" and direct in msg.get("content", "")
        for call in backend.calls
        for msg in call["messages"]
    )


async def test_runner_passes_question_to_user_message() -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=["Paris"])
    runner = module.make_runner(backend=backend)
    question = "Who directed the film starring the actor born in 1980?"
    await runner({"question": question})
    assert any(
        msg.get("role") == "user" and question in msg.get("content", "")
        for call in backend.calls
        for msg in call["messages"]
    )


def test_config_yaml_validates() -> None:
    cfg_path = EXAMPLES_ROOT / "config.yaml"
    assert cfg_path.exists()
    config = load_run_config(cfg_path)
    assert config.name == "hotpotqa-multihop"


def test_readme_describes_run_instructions() -> None:
    readme = EXAMPLES_ROOT / "README.md"
    assert readme.exists()
    text = readme.read_text()
    assert "hotpot" in text.lower()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Paris", "Paris"),
        ("  Paris  ", "Paris"),
        ("Paris.", "Paris"),
        ("Answer: Paris", "Paris"),
        ("The answer is Paris.", "Paris"),
        ("the answer is paris", "paris"),
        ("**Paris**", "Paris"),
        ("\"Paris\"", "Paris"),
        # Final-answer extraction from multi-line reasoning.
        ("First, consider X. Then Y.\n\nFinal answer: Paris", "Paris"),
        (
            "Sub-question 1: ...\nSub-question 2: ...\n\nFinal answer: Paris",
            "Paris",
        ),
        ("Final answer: **Paris**", "Paris"),
        # Falls back to last non-empty line when no Final answer: line.
        ("First line\n\nLast line", "Last line"),
    ],
)
async def test_answer_normalization(raw: str, expected: str) -> None:
    module = _load_hotpotqa_module()
    backend = MockBackend(responses=[raw])
    runner = module.make_runner(backend=backend)
    result = await runner({"question": "?"})
    assert result["answer"] == expected
