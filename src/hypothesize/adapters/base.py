"""``SystemAdapter`` protocol and ``Runner`` type alias.

A ``Runner`` is the async callable shape that
``find_discriminating_inputs`` consumes as ``current_runner`` /
``alternative_runner``: it takes a dict of input data and returns a
dict of system output.

Each adapter implements ``build_runner`` (mandatory) and
``extract_prompt`` (optional; returns ``None`` when the adapter cannot
introspect the system's prompt). The optional method exists so that
the auto-alternative generator — a utility in a later task — can
rewrite the prompt for supported adapters without having to know which
adapter type it's dealing with.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from hypothesize.adapters.config import SystemConfig

Runner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


@runtime_checkable
class SystemAdapter(Protocol):
    """Build a ``Runner`` from a ``SystemConfig``.

    Stateless: ``build_runner`` returns a fresh closure per call.
    """

    def build_runner(self, config: SystemConfig) -> Runner: ...

    def extract_prompt(self, config: SystemConfig) -> str | None:
        """Return the system prompt for auto-alt rewriting, or ``None``.

        Adapters that cannot introspect their system's prompt return
        ``None``. Auto-alt then raises a clear error pointing the user
        at the prompt-factory convention documented in the Python-
        module adapter.
        """
