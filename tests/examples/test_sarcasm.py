"""Tests for examples/sarcasm/ — full demo example.

All tests run with a MockBackend; no live LLM calls.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from hypothesize.cli.config import load_run_config
from tests._fixtures.mock_backend import MockBackend

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent.parent / "examples" / "sarcasm"


def _load_sarcasm_module():
    """Load examples/sarcasm/system.py without going through importlib magic
    that depends on package layout. Mirrors what PythonModuleAdapter does."""
    spec = importlib.util.spec_from_file_location(
        "_sarcasm_test_module", EXAMPLES_ROOT / "system.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_module_imports() -> None:
    module = _load_sarcasm_module()
    assert hasattr(module, "SYSTEM_PROMPT")
    assert isinstance(module.SYSTEM_PROMPT, str)
    assert len(module.SYSTEM_PROMPT) > 10


def test_make_runner_returns_callable() -> None:
    module = _load_sarcasm_module()
    runner = module.make_runner()
    assert callable(runner)


def test_run_module_attribute_exists() -> None:
    module = _load_sarcasm_module()
    assert hasattr(module, "run")
    assert callable(module.run)


async def test_runner_with_mock_backend_returns_sentiment() -> None:
    module = _load_sarcasm_module()
    backend = MockBackend(responses=["positive"])
    runner = module.make_runner(backend=backend)
    result = await runner({"text": "I love this product"})
    assert "sentiment" in result
    assert result["sentiment"] in {"positive", "negative"}


async def test_runner_with_mock_backend_normalizes_negative() -> None:
    module = _load_sarcasm_module()
    backend = MockBackend(responses=["negative."])
    runner = module.make_runner(backend=backend)
    result = await runner({"text": "I LOVE waiting on hold"})
    assert result["sentiment"] == "negative"


async def test_runner_unknown_response_falls_back_to_positive() -> None:
    module = _load_sarcasm_module()
    backend = MockBackend(responses=[""])
    runner = module.make_runner(backend=backend)
    result = await runner({"text": "anything"})
    # Empty response should not crash the runner.
    assert result["sentiment"] in {"positive", "negative"}


async def test_make_runner_uses_overridden_prompt() -> None:
    module = _load_sarcasm_module()
    backend = MockBackend(responses=["negative"])
    custom_prompt = "Always answer 'negative'. Just kidding — classify sentiment."
    runner = module.make_runner(prompt=custom_prompt, backend=backend)
    await runner({"text": "I love this!"})
    # The custom prompt should appear in the system message.
    assert any(
        msg.get("role") == "system" and custom_prompt in msg.get("content", "")
        for call in backend.calls
        for msg in call["messages"]
    )


def test_config_yaml_validates() -> None:
    cfg_path = EXAMPLES_ROOT / "config.yaml"
    assert cfg_path.exists()
    config = load_run_config(cfg_path)
    assert config.name == "sarcasm-sentiment"
    assert config.current.adapter == "python_module"
    assert config.alternative.adapter == "auto"


def test_config_yaml_module_path_resolves(tmp_path: Path) -> None:
    """The module_path in config.yaml should be a real file."""
    cfg_path = EXAMPLES_ROOT / "config.yaml"
    raw = yaml.safe_load(cfg_path.read_text())
    module_path = Path(raw["current"]["module_path"])
    if not module_path.is_absolute():
        # Resolve relative to repo root (one above examples/sarcasm)
        repo_root = EXAMPLES_ROOT.parent.parent
        module_path = (repo_root / module_path).resolve()
    assert module_path.exists()


def test_readme_exists() -> None:
    readme = EXAMPLES_ROOT / "README.md"
    assert readme.exists()
    text = readme.read_text()
    assert "hypothesize run" in text
    assert "ANTHROPIC_API_KEY" in text


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("positive", "positive"),
        ("negative", "negative"),
        ("Negative.", "negative"),
        (" POSITIVE ", "positive"),
        ("I think positive", "positive"),
    ],
)
async def test_runner_label_normalization(raw: str, expected: str) -> None:
    module = _load_sarcasm_module()
    backend = MockBackend(responses=[raw])
    runner = module.make_runner(backend=backend)
    result = await runner({"text": "anything"})
    assert result["sentiment"] == expected
