"""Fixture system exposing ``SYSTEM_PROMPT`` but no ``make_runner``.

Per design, auto-alt is unavailable for such systems: the adapter's
``extract_prompt`` returns ``None`` because rewriting has no hook to
call. ``run`` still works for the baseline.
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = "Baseline-only prompt; no factory."


async def run(input_data: dict[str, Any]) -> dict[str, Any]:
    return {"echoed": input_data, "prompt": SYSTEM_PROMPT}
