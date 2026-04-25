"""``hypothesize`` MCP server.

Exposes five tools wrapping the discrimination pipeline and the
benchmark-discovery primitives. Tool bodies live in
:mod:`hypothesize.mcp.tools` so they are testable as plain async
functions independent of MCP transport. This module wires those
functions into a ``FastMCP`` server.

Run with::

    python -m hypothesize.mcp.server
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from hypothesize.mcp import tools


def build_server() -> FastMCP:
    """Construct and return a FastMCP server with hypothesize tools.

    Factored out of module scope so tests can introspect the
    registered tool list without spinning up transport.
    """
    server = FastMCP("hypothesize")

    @server.tool()
    async def discover_systems(repo_path: str) -> list[dict[str, Any]]:
        """Find candidate config.yaml files under ``repo_path``."""
        return await tools.discover_systems(repo_path)

    @server.tool()
    async def list_benchmarks(repo_path: str) -> list[dict[str, Any]]:
        """List existing hypothesize-generated benchmark YAMLs."""
        return await tools.list_benchmarks(repo_path)

    @server.tool()
    async def read_benchmark(path: str) -> dict[str, Any]:
        """Load a benchmark YAML and return it as a dict."""
        return await tools.read_benchmark(path)

    @server.tool()
    async def formulate_hypothesis(
        complaint: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Convert a vague complaint into a structured hypothesis."""
        return await tools.formulate_hypothesis(complaint, context or {})

    @server.tool()
    async def run_discrimination(
        config_path: str,
        hypothesis: str,
        target_n: int = 5,
        budget: int = 100,
    ) -> dict[str, Any]:
        """Run discrimination against a config; return the YAML payload."""
        return await tools.run_discrimination(
            config_path=config_path,
            hypothesis=hypothesis,
            target_n=target_n,
            budget=budget,
        )

    return server


server = build_server()


def main() -> None:
    """Entry point for ``python -m hypothesize.mcp.server``."""
    server.run()


if __name__ == "__main__":
    main()
