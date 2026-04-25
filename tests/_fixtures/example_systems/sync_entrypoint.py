"""Fixture system: sync ``run`` entrypoint, no prompt factory."""

from __future__ import annotations

from typing import Any


def run(input_data: dict[str, Any]) -> dict[str, Any]:
    return {"echoed": input_data, "kind": "sync"}
