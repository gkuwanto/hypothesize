"""Adapter that loads a user-authored Python module as a system.

Expected shapes for the user's module (documented for the hackathon
example sets):

Prompt-opaque (simplest)::

    async def run(input_data: dict) -> dict: ...

Or, exposing the prompt-factory convention that enables automatic
alternative generation::

    SYSTEM_PROMPT = "You are..."

    def make_runner(prompt: str | None = None):
        effective = prompt if prompt is not None else SYSTEM_PROMPT
        async def run(input_data: dict) -> dict: ...
        return run

    run = make_runner()

The adapter prefers ``make_runner`` when both are present. Sync
entrypoints are wrapped in a thin async shim; async entrypoints pass
through. Modules are cached by absolute path so repeated construction
(e.g. current + auto-alternative) does not re-execute module bodies.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any

from hypothesize.adapters.base import Runner
from hypothesize.adapters.config import SystemConfig
from hypothesize.adapters.errors import AutoAlternativeUnavailable


class PythonModuleAdapter:
    """Loads a user Python file and yields a ``Runner`` from it."""

    def __init__(self) -> None:
        self._cache: dict[Path, ModuleType] = {}

    # -- loading --------------------------------------------------------

    def _load(self, module_path: Path) -> ModuleType:
        resolved = Path(module_path).resolve()
        cached = self._cache.get(resolved)
        if cached is not None:
            return cached
        if not resolved.exists():
            raise FileNotFoundError(f"Python module not found: {resolved}")
        spec = importlib.util.spec_from_file_location(
            f"_hypothesize_user_{resolved.stem}_{id(resolved)}",
            resolved,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not import Python module at {resolved}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self._cache[resolved] = module
        return module

    def _require_module(self, config: SystemConfig) -> ModuleType:
        if config.module_path is None:
            raise ValueError(
                "SystemConfig.module_path is required for the python_module adapter."
            )
        return self._load(config.module_path)

    # -- SystemAdapter protocol -----------------------------------------

    def build_runner(self, config: SystemConfig) -> Runner:
        module = self._require_module(config)
        make_runner = getattr(module, "make_runner", None)
        if callable(make_runner):
            candidate = make_runner(prompt=None)
        else:
            candidate = getattr(module, config.entrypoint, None)
            if candidate is None:
                raise AttributeError(
                    f"Module {config.module_path} exposes neither "
                    f"'make_runner' nor the configured entrypoint "
                    f"{config.entrypoint!r}."
                )
        return _ensure_async(candidate)

    def extract_prompt(self, config: SystemConfig) -> str | None:
        module = self._require_module(config)
        if not callable(getattr(module, "make_runner", None)):
            return None
        prompt = getattr(module, "SYSTEM_PROMPT", None)
        if isinstance(prompt, str):
            return prompt
        return None

    # -- auto-alt hook --------------------------------------------------

    def build_runner_with_prompt(
        self, config: SystemConfig, prompt: str
    ) -> Runner:
        """Return a runner bound to ``prompt`` via the module's factory.

        Raises ``AutoAlternativeUnavailable`` when the module does not
        expose ``make_runner``. The message names the convention so the
        user can add it without reading the design doc.
        """
        module = self._require_module(config)
        make_runner = getattr(module, "make_runner", None)
        if not callable(make_runner):
            raise AutoAlternativeUnavailable(
                f"Module {config.module_path} does not expose a "
                f"'make_runner(prompt=None)' factory. Automatic "
                f"alternative generation requires this hook. Add it "
                f"alongside SYSTEM_PROMPT and 'run = make_runner()'."
            )
        return _ensure_async(make_runner(prompt=prompt))


def _ensure_async(candidate: Any) -> Runner:
    if inspect.iscoroutinefunction(candidate):
        return candidate
    if not callable(candidate):
        raise TypeError(
            f"Expected a callable runner, got {type(candidate).__name__}."
        )

    async def _shim(input_data: dict[str, Any]) -> dict[str, Any]:
        return candidate(input_data)

    return _shim
