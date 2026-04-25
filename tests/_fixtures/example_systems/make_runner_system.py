"""Fixture system exposing the prompt-factory convention.

``make_runner(prompt=None)`` returns a runner bound to the given prompt
(or ``SYSTEM_PROMPT`` when none is passed). ``SYSTEM_PROMPT`` is a
plain module-level string so ``extract_prompt`` can surface it.
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = "You are a helpful test fixture."


def make_runner(prompt: str | None = None):
    effective = prompt if prompt is not None else SYSTEM_PROMPT

    async def run(input_data: dict[str, Any]) -> dict[str, Any]:
        return {"prompt": effective, "echoed": input_data}

    return run


run = make_runner()
