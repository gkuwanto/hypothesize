"""Serialise a ``DiscriminationResult`` to the documented YAML schema.

The schema lives in ``.spec/features/04-developer-surface/design.md``
under "Output YAML schema". A tiny dict-builder keeps the code easy to
audit; YAML serialisation goes through ``yaml.safe_dump`` with block
style and ``sort_keys=False`` so the output reads top-to-bottom in
the order a human would read it (hypothesis → metadata → cases).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml

from hypothesize.core.types import DiscriminationResult, Hypothesis


def result_to_dict(
    result: DiscriminationResult,
    hypothesis: Hypothesis,
    config_name: str,
    model_name: str,
    target_n: int,
    budget_max: int,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the YAML-shape dict from a ``DiscriminationResult``."""
    if generated_at is None:
        generated_at = datetime.now(UTC)

    payload: dict[str, Any] = {
        "hypothesis": hypothesis.text,
        "metadata": {
            "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
            "model": model_name,
            "budget_used": result.budget_used,
            "budget_max": budget_max,
            "status": result.status,
            "target_n": target_n,
            "config_name": config_name,
        },
        "test_cases": [
            {
                "input": tc.input_data,
                "expected_behavior": tc.expected_behavior,
                "discrimination_evidence": tc.discrimination_evidence,
            }
            for tc in result.test_cases
        ],
    }
    if result.insufficient is not None:
        payload["insufficient"] = {
            "reason": result.insufficient.reason,
            "candidates_tried": result.insufficient.candidates_tried,
            "discriminating_found": result.insufficient.discriminating_found,
        }
    return payload


def result_to_yaml(
    result: DiscriminationResult,
    hypothesis: Hypothesis,
    config_name: str,
    model_name: str,
    target_n: int,
    budget_max: int,
    generated_at: datetime | None = None,
) -> str:
    """Serialise the dict from :func:`result_to_dict` to YAML."""
    payload = result_to_dict(
        result=result,
        hypothesis=hypothesis,
        config_name=config_name,
        model_name=model_name,
        target_n=target_n,
        budget_max=budget_max,
        generated_at=generated_at,
    )
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
