"""Tests for the FastMCP server scaffolding."""

from __future__ import annotations

import asyncio


def test_server_module_imports_cleanly() -> None:
    from hypothesize.mcp import server

    assert hasattr(server, "build_server")
    assert hasattr(server, "main")
    assert callable(server.main)


def test_build_server_constructs_without_errors() -> None:
    from hypothesize.mcp.server import build_server

    s = build_server()
    assert s.name == "hypothesize"


def test_server_registers_five_tools() -> None:
    from hypothesize.mcp.server import build_server

    s = build_server()
    tool_names = {t.name for t in asyncio.run(s.list_tools())}
    assert tool_names == {
        "discover_systems",
        "list_benchmarks",
        "read_benchmark",
        "formulate_hypothesis",
        "run_discrimination",
    }


def test_module_level_server_constructs() -> None:
    from hypothesize.mcp import server

    assert server.server is not None
    assert server.server.name == "hypothesize"


def test_main_is_callable() -> None:
    """``main`` must be importable and callable; we don't actually run it."""
    from hypothesize.mcp.server import main

    assert callable(main)
