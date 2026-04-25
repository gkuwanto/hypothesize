"""Automatic alternative-system generator.

Given a ``current`` ``SystemConfig`` whose adapter exposes
``extract_prompt`` and ``build_runner_with_prompt``, asks an
``LLMBackend`` to rewrite the prompt to specifically mitigate a stated
failure ``Hypothesis``, then returns a ``Runner`` bound to the rewritten
prompt.

The function is a utility, not an adapter subclass: composition over
inheritance, so any future adapter that grows ``extract_prompt`` /
``build_runner_with_prompt`` plugs in without a parallel class.
"""

from __future__ import annotations

from typing import Any

from hypothesize.adapters.base import Runner
from hypothesize.adapters.cli import CliAdapter
from hypothesize.adapters.config import SystemConfig
from hypothesize.adapters.errors import (
    AutoAlternativeUnavailable,
    BudgetExhausted,
)
from hypothesize.adapters.http import HttpAdapter
from hypothesize.adapters.python_module import PythonModuleAdapter
from hypothesize.core.json_extract import parse_json_response
from hypothesize.core.llm import LLMBackend
from hypothesize.core.types import Budget, Hypothesis
from hypothesize.llm.prompts import rewrite_prompt_messages


def _resolve_adapter(config: SystemConfig) -> Any:
    """Return a fresh adapter instance for ``config.adapter``."""
    match config.adapter:
        case "python_module":
            return PythonModuleAdapter()
        case "http":
            return HttpAdapter()
        case "cli":
            return CliAdapter()
    # Pydantic ``Literal`` already prevents this, but Python's match
    # is non-exhaustive.
    raise AutoAlternativeUnavailable(
        f"Unknown adapter kind: {config.adapter!r}"
    )


def _validate_payload(payload: Any) -> str:
    """Return the rewritten prompt from ``payload`` or raise.

    The contract: ``payload`` must be a dict with non-empty string
    values for ``rewritten_prompt`` and ``rationale``. Anything else is
    a pre-pipeline failure.
    """
    if not isinstance(payload, dict):
        raise AutoAlternativeUnavailable(
            "rewrite response did not parse to a JSON object; "
            "the LLM returned something we cannot use as a rewrite. "
            'Expected {"rewritten_prompt": str, "rationale": str}.'
        )
    rewritten = payload.get("rewritten_prompt")
    rationale = payload.get("rationale")
    if not isinstance(rewritten, str) or not rewritten:
        raise AutoAlternativeUnavailable(
            "rewrite response missing or non-string 'rewritten_prompt'. "
            'Expected {"rewritten_prompt": str, "rationale": str}.'
        )
    if not isinstance(rationale, str):
        raise AutoAlternativeUnavailable(
            "rewrite response missing or non-string 'rationale'. "
            'Expected {"rewritten_prompt": str, "rationale": str}.'
        )
    return rewritten


async def make_auto_alternative(
    current: SystemConfig,
    hypothesis: Hypothesis,
    llm: LLMBackend,
    budget: Budget,
) -> Runner:
    """Build a ``Runner`` whose system prompt has been rewritten by Claude.

    Steps (six-step algorithm from design.md):

    1. Resolve the adapter implied by ``current.adapter``.
    2. Read the current prompt via ``adapter.extract_prompt(current)``.
       ``None`` means the system is prompt-opaque — raise
       ``AutoAlternativeUnavailable``.
    3. If ``budget`` is exhausted, raise ``BudgetExhausted``.
    4. Call ``llm.complete`` with the rewrite prompt, charge the budget
       on return, parse the response with ``parse_json_response``.
    5. Validate the payload shape; raise ``AutoAlternativeUnavailable``
       if it does not match.
    6. Return ``adapter.build_runner_with_prompt(current, rewritten)``.
    """
    adapter = _resolve_adapter(current)
    current_prompt = adapter.extract_prompt(current)
    if current_prompt is None:
        raise AutoAlternativeUnavailable(
            f"Adapter {type(adapter).__name__} cannot expose a system "
            f"prompt for {current.name!r}. Automatic alternative "
            f"generation requires a Python-module system that defines "
            f"both 'SYSTEM_PROMPT' and 'make_runner(prompt=None)'. "
            f"Add the prompt-factory convention or supply an explicit "
            f"alternative system."
        )
    if budget.exhausted():
        raise BudgetExhausted(
            "Budget exhausted before automatic alternative could be "
            "generated. Increase max_llm_calls or supply an explicit "
            "alternative system."
        )

    raw = await llm.complete(rewrite_prompt_messages(current_prompt, hypothesis))
    budget.charge()

    payload = parse_json_response(raw)
    rewritten = _validate_payload(payload)

    return adapter.build_runner_with_prompt(current, rewritten)
