"""CLI adapter — stub.

Feature 02 ships only the import-clean class shape so dispatch code in
the auto-alternative utility (task 2.7) and the Feature 04 CLI compiles
without special-casing. Real implementation lands post-hackathon.
"""

from __future__ import annotations

from hypothesize.adapters.base import Runner
from hypothesize.adapters.config import SystemConfig


class CliAdapter:
    """Placeholder; raises on ``build_runner``."""

    def build_runner(self, config: SystemConfig) -> Runner:
        raise NotImplementedError(
            "CLI adapter is not implemented in Feature 02. "
            "Planned post-hackathon (Feature 04 or later)."
        )

    def extract_prompt(self, config: SystemConfig) -> str | None:
        return None
