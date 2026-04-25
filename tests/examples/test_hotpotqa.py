"""Tests for examples/hotpotqa/ — scaffold-only example."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from hypothesize.cli.config import load_run_config

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
    assert hasattr(module, "make_runner")
    assert hasattr(module, "run")


async def test_runner_raises_not_implemented_with_todo_message() -> None:
    module = _load_hotpotqa_module()
    runner = module.make_runner()
    with pytest.raises(NotImplementedError) as exc_info:
        await runner({"question": "x"})
    assert "TODO" in str(exc_info.value)


def test_config_yaml_validates() -> None:
    cfg_path = EXAMPLES_ROOT / "config.yaml"
    assert cfg_path.exists()
    config = load_run_config(cfg_path)
    assert config.name == "hotpotqa-multihop"
    assert config.alternative.adapter == "auto"


def test_readme_describes_manual_setup() -> None:
    readme = EXAMPLES_ROOT / "README.md"
    assert readme.exists()
    text = readme.read_text()
    assert "NOT YET RUNNABLE" in text or "scaffold" in text.lower()
    assert "hotpot" in text.lower()
    assert "TODO" in text
