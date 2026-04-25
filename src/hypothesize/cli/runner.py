"""Backend / runner / judge composition shared by the CLI and MCP.

``run_discrimination(config, hypothesis, target_n, min_required, budget,
backend)`` is the single entry point both ``hypothesize run`` and the
MCP ``run_discrimination`` tool call. It builds the current and
alternative runners, the rubric judge, and threads the supplied
backend through every LLM call site.

The function is async so callers can wrap it in their own event loop
or compose with other async work.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from hypothesize.adapters.auto_alternative import make_auto_alternative
from hypothesize.adapters.cli import CliAdapter
from hypothesize.adapters.config import SystemConfig
from hypothesize.adapters.http import HttpAdapter
from hypothesize.adapters.python_module import PythonModuleAdapter
from hypothesize.cli.config import RunConfig
from hypothesize.core.discrimination import find_discriminating_inputs
from hypothesize.core.judge import RubricJudge
from hypothesize.core.llm import LLMBackend
from hypothesize.core.types import Budget, DiscriminationResult, Hypothesis

Runner = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _resolve_adapter(kind: str) -> Any:
    match kind:
        case "python_module":
            return PythonModuleAdapter()
        case "http":
            return HttpAdapter()
        case "cli":
            return CliAdapter()
    raise ValueError(f"Unknown adapter kind: {kind!r}")


async def build_runners(
    config: RunConfig,
    hypothesis: Hypothesis,
    backend: LLMBackend,
    budget: Budget,
) -> tuple[Runner, Runner]:
    """Construct ``(current_runner, alternative_runner)`` from a ``RunConfig``.

    Auto-alt is resolved here so callers don't have to duplicate the
    sentinel handling. The supplied ``backend`` is used only for the
    auto-alt prompt-rewrite call; the discrimination algorithm proper
    receives the same backend separately via ``run_discrimination``.
    """
    current_adapter = _resolve_adapter(config.current.adapter)
    current_runner: Runner = current_adapter.build_runner(config.current)

    if config.alternative.adapter == "auto":
        alternative_runner: Runner = await make_auto_alternative(
            config.current, hypothesis, backend, budget
        )
    else:
        alt_sc: SystemConfig = config.alternative.to_system_config(
            fallback_name=f"{config.name}-alternative"
        )
        alt_adapter = _resolve_adapter(alt_sc.adapter)
        alternative_runner = alt_adapter.build_runner(alt_sc)

    return current_runner, alternative_runner


async def run_discrimination(
    config: RunConfig,
    hypothesis: Hypothesis,
    target_n: int,
    min_required: int,
    budget: Budget,
    backend: LLMBackend,
) -> DiscriminationResult:
    """Single entry point shared by the CLI and the MCP server."""
    current_runner, alternative_runner = await build_runners(
        config, hypothesis, backend, budget
    )
    judge = RubricJudge(llm=backend)
    return await find_discriminating_inputs(
        hypothesis=hypothesis,
        current_runner=current_runner,
        alternative_runner=alternative_runner,
        context=hypothesis.context_refs,
        judge=judge,
        llm=backend,
        budget=budget,
        target_n=target_n,
        min_required=min_required,
    )
