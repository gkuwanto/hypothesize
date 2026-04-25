"""Fixture system: only a bare ``run`` attribute, fully prompt-opaque.

No ``make_runner``, no ``SYSTEM_PROMPT``. ``extract_prompt`` must
return ``None`` and ``build_runner_with_prompt`` must raise
``AutoAlternativeUnavailable``.
"""

from __future__ import annotations

from typing import Any


async def run(input_data: dict[str, Any]) -> dict[str, Any]:
    return {"echoed": input_data}
