"""``RunConfig`` — the top-level YAML model the CLI consumes.

Composed of the existing ``SystemConfig`` (current), an
``AlternativeConfig`` (which adds an ``"auto"`` sentinel for
``make_auto_alternative``), an optional ``Hypothesis``, an
``AnthropicConfig``, a ``Budget``, and a small ``defaults`` block for
``target_n`` / ``min_required``.

Lives in ``cli/`` because its sole consumer is the CLI; the
``adapters/`` and ``llm/`` layers expose pieces, the CLI composes
them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from hypothesize.adapters.config import SystemConfig
from hypothesize.core.types import Budget, Hypothesis
from hypothesize.llm.config import AnthropicConfig

AlternativeKind = Literal["python_module", "http", "cli", "auto"]


class AlternativeConfig(BaseModel):
    """Alternative-system spec.

    ``adapter='auto'`` is the sentinel that triggers
    ``make_auto_alternative``. The other adapter values mirror
    ``SystemConfig.adapter``; with one of those, the CLI builds a
    ``SystemConfig`` from this object's fields and constructs the
    runner directly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    adapter: AlternativeKind
    name: str | None = None
    module_path: Path | None = None
    entrypoint: str = "run"
    url: str | None = None
    command: list[str] | None = None

    def to_system_config(self, fallback_name: str) -> SystemConfig:
        """Materialize a ``SystemConfig`` for non-auto adapters.

        Raises ``ValueError`` when called with ``adapter='auto'`` —
        the auto sentinel does not correspond to a static config.
        """
        if self.adapter == "auto":
            raise ValueError(
                "AlternativeConfig.adapter='auto' has no SystemConfig form; "
                "use make_auto_alternative instead."
            )
        return SystemConfig(
            name=self.name or fallback_name,
            adapter=self.adapter,
            module_path=self.module_path,
            entrypoint=self.entrypoint,
            url=self.url,
            command=self.command,
        )


class DefaultsBlock(BaseModel):
    """``target_n`` / ``min_required`` defaults that the CLI flags can override."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_n: int = 5
    min_required: int = 3


class RunConfig(BaseModel):
    """Top-level CLI YAML model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    current: SystemConfig
    alternative: AlternativeConfig
    hypothesis: Hypothesis | None = None
    llm: AnthropicConfig = Field(default_factory=AnthropicConfig)
    budget: Budget = Field(default_factory=lambda: Budget(max_llm_calls=200))
    defaults: DefaultsBlock = Field(default_factory=DefaultsBlock)


def load_run_config(path: Path) -> RunConfig:
    """Load a ``RunConfig`` from a YAML file.

    Raises ``FileNotFoundError`` when ``path`` does not exist; raises
    ``pydantic.ValidationError`` when the YAML is missing required
    fields or carries unknown keys.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    raw = yaml.safe_load(p.read_text())
    if not isinstance(raw, dict):
        raw = {}
    _propagate_name(raw)
    return RunConfig(**raw)


def _propagate_name(raw: dict) -> None:
    """Default ``current.name`` and ``alternative.name`` from top-level ``name``.

    Lets users write a single ``name:`` at the top level without
    repeating it inside each system block. Mutates ``raw`` in place;
    does nothing if either child block already carries an explicit
    ``name`` or the top-level ``name`` is absent.
    """
    top_name = raw.get("name")
    if not isinstance(top_name, str):
        return
    current = raw.get("current")
    if isinstance(current, dict) and "name" not in current:
        current["name"] = top_name
    alternative = raw.get("alternative")
    if isinstance(alternative, dict) and "name" not in alternative:
        alternative["name"] = f"{top_name}-alternative"
