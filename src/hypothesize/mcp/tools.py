"""MCP tool implementations.

Implementations land in task 4.7. The current shapes are stubs that
let the server module import cleanly.
"""

from __future__ import annotations

from typing import Any

from hypothesize.core.llm import LLMBackend


async def discover_systems(repo_path: str) -> list[dict[str, Any]]:  # pragma: no cover
    raise NotImplementedError("discover_systems lands in task 4.7")


async def list_benchmarks(repo_path: str) -> list[dict[str, Any]]:  # pragma: no cover
    raise NotImplementedError("list_benchmarks lands in task 4.7")


async def read_benchmark(path: str) -> dict[str, Any]:  # pragma: no cover
    raise NotImplementedError("read_benchmark lands in task 4.7")


async def formulate_hypothesis(  # pragma: no cover
    complaint: str,
    context: dict[str, Any] | None = None,
    backend: LLMBackend | None = None,
) -> dict[str, Any]:
    raise NotImplementedError("formulate_hypothesis lands in task 4.7")


async def run_discrimination(  # pragma: no cover
    config_path: str,
    hypothesis: str,
    target_n: int = 5,
    budget: int = 100,
    backend: LLMBackend | None = None,
) -> dict[str, Any]:
    raise NotImplementedError("run_discrimination lands in task 4.7")
