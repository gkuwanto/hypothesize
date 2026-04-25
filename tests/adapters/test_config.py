"""Tests for ``SystemConfig`` and ``load_system_config``.

Covers the core validation shape: required fields, literal-constrained
``adapter``, pydantic ``extra="forbid"`` on unknown keys, and YAML round
trip via the loader.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hypothesize.adapters.base import Runner, SystemAdapter
from hypothesize.adapters.config import SystemConfig, load_system_config


def test_protocol_exposes_build_runner_and_extract_prompt() -> None:
    assert hasattr(SystemAdapter, "build_runner")
    assert hasattr(SystemAdapter, "extract_prompt")


def test_runner_type_alias_is_callable_type() -> None:
    # Runner is a typing alias; just confirm it imports and is usable.
    assert Runner is not None


def test_system_config_minimum_python_module_shape() -> None:
    cfg = SystemConfig(
        name="toy",
        adapter="python_module",
        module_path=Path("examples/toy/system.py"),
    )
    assert cfg.name == "toy"
    assert cfg.adapter == "python_module"
    assert cfg.entrypoint == "run"  # default


def test_system_config_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        SystemConfig(
            name="toy",
            adapter="python_module",
            module_path=Path("x.py"),
            bogus_field=True,  # type: ignore[call-arg]
        )


def test_system_config_rejects_invalid_adapter_literal() -> None:
    with pytest.raises(ValidationError):
        SystemConfig(
            name="toy",
            adapter="not_real",  # type: ignore[arg-type]
        )


def test_system_config_requires_name() -> None:
    with pytest.raises(ValidationError):
        SystemConfig(adapter="python_module")  # type: ignore[call-arg]


def test_load_system_config_reads_yaml(tmp_path: Path) -> None:
    yaml_text = """\
name: sentiment
adapter: python_module
module_path: examples/sentiment/system.py
entrypoint: run
"""
    path = tmp_path / "system.yaml"
    path.write_text(yaml_text)
    cfg = load_system_config(path)
    assert cfg.name == "sentiment"
    assert cfg.adapter == "python_module"
    assert cfg.module_path == Path("examples/sentiment/system.py")
    assert cfg.entrypoint == "run"


def test_load_system_config_rejects_unknown_yaml_key(tmp_path: Path) -> None:
    path = tmp_path / "system.yaml"
    path.write_text(
        "name: x\nadapter: python_module\nmodule_path: a.py\nweirdo: 1\n"
    )
    with pytest.raises(ValidationError):
        load_system_config(path)


def test_load_system_config_supports_http_adapter_fields(tmp_path: Path) -> None:
    path = tmp_path / "system.yaml"
    path.write_text("name: h\nadapter: http\nurl: https://example.com/\n")
    cfg = load_system_config(path)
    assert cfg.adapter == "http"
    assert cfg.url == "https://example.com/"


def test_load_system_config_supports_cli_adapter_fields(tmp_path: Path) -> None:
    path = tmp_path / "system.yaml"
    path.write_text("name: c\nadapter: cli\ncommand:\n  - python\n  - run.py\n")
    cfg = load_system_config(path)
    assert cfg.adapter == "cli"
    assert cfg.command == ["python", "run.py"]
