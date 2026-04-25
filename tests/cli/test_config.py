"""Tests for the CLI's RunConfig YAML loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from hypothesize.cli.config import AlternativeConfig, load_run_config


def _write_yaml(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(payload))
    return p


def _minimal_payload(tmp_path: Path) -> dict:
    sysfile = tmp_path / "system.py"
    sysfile.write_text("async def run(input_data):\n    return {}\n")
    return {
        "name": "demo",
        "current": {
            "adapter": "python_module",
            "module_path": str(sysfile),
        },
        "alternative": {"adapter": "auto"},
        "hypothesis": {"text": "the system fails on negation"},
    }


def test_load_minimal_yaml(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    config = load_run_config(_write_yaml(tmp_path, payload))
    assert config.name == "demo"
    assert config.current.adapter == "python_module"
    assert config.alternative.adapter == "auto"
    assert config.hypothesis is not None
    assert config.hypothesis.text == "the system fails on negation"
    # defaults block has sensible defaults
    assert config.defaults.target_n == 5
    assert config.defaults.min_required == 3


def test_alternative_auto_sentinel_accepted(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    config = load_run_config(_write_yaml(tmp_path, payload))
    assert config.alternative.adapter == "auto"
    assert config.alternative.module_path is None


def test_alternative_explicit_python_module(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    alt_sysfile = tmp_path / "alt_system.py"
    alt_sysfile.write_text("async def run(input_data):\n    return {}\n")
    payload["alternative"] = {
        "adapter": "python_module",
        "module_path": str(alt_sysfile),
    }
    config = load_run_config(_write_yaml(tmp_path, payload))
    assert config.alternative.adapter == "python_module"
    assert config.alternative.module_path == alt_sysfile


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    payload["unknown_key"] = "boom"
    with pytest.raises(ValidationError):
        load_run_config(_write_yaml(tmp_path, payload))


def test_unknown_alternative_key_rejected(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    payload["alternative"]["typo_field"] = "boom"
    with pytest.raises(ValidationError):
        load_run_config(_write_yaml(tmp_path, payload))


def test_missing_name_rejected(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    del payload["name"]
    with pytest.raises(ValidationError):
        load_run_config(_write_yaml(tmp_path, payload))


def test_hypothesis_block_optional(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    del payload["hypothesis"]
    config = load_run_config(_write_yaml(tmp_path, payload))
    assert config.hypothesis is None


def test_llm_block_default(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    config = load_run_config(_write_yaml(tmp_path, payload))
    assert config.llm.default_model.startswith("claude-")


def test_llm_block_override(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    payload["llm"] = {"default_model": "claude-haiku-4-5-20251001"}
    config = load_run_config(_write_yaml(tmp_path, payload))
    assert config.llm.default_model == "claude-haiku-4-5-20251001"


def test_budget_block_default(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    config = load_run_config(_write_yaml(tmp_path, payload))
    assert config.budget.max_llm_calls == 200


def test_defaults_block_override(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    payload["defaults"] = {"target_n": 7, "min_required": 2}
    config = load_run_config(_write_yaml(tmp_path, payload))
    assert config.defaults.target_n == 7
    assert config.defaults.min_required == 2


def test_alternative_config_is_frozen(tmp_path: Path) -> None:
    alt = AlternativeConfig(adapter="auto")
    with pytest.raises(ValidationError):
        alt.adapter = "python_module"  # type: ignore[misc]


def test_run_config_rejects_invalid_adapter(tmp_path: Path) -> None:
    payload = _minimal_payload(tmp_path)
    payload["alternative"] = {"adapter": "telnet"}
    with pytest.raises(ValidationError):
        load_run_config(_write_yaml(tmp_path, payload))


def test_load_run_config_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_run_config(tmp_path / "nope.yaml")
