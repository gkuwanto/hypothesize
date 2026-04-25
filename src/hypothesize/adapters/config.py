"""Declarative ``SystemConfig`` and its YAML loader.

``SystemConfig`` is a pydantic v2 model with ``extra="forbid"`` so that
typos in user YAML (``module-path`` vs ``module_path``, etc.) surface
loudly. Only the Python-module adapter is wired in Feature 02; HTTP
and CLI adapters have fields declared but unimplemented construction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

AdapterKind = Literal["python_module", "http", "cli"]


class SystemConfig(BaseModel):
    """Declarative description of a system under test."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    adapter: AdapterKind
    module_path: Path | None = None
    entrypoint: str = "run"
    url: str | None = None
    command: list[str] | None = None


def load_system_config(path: Path) -> SystemConfig:
    """Load a ``SystemConfig`` from a YAML file.

    Raises ``pydantic.ValidationError`` when the YAML is missing
    required fields, contains unknown keys, or carries the wrong type
    for a declared field.
    """
    raw = yaml.safe_load(Path(path).read_text())
    if not isinstance(raw, dict):
        raw = {}
    return SystemConfig(**raw)
