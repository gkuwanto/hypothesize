"""Tests for hypothesize.mcp.launch — the dotenv-loading MCP entry point."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock


def test_launch_loads_global_dotenv_before_starting_server(
    tmp_path: Path, monkeypatch
) -> None:
    """The launcher must call load_dotenv_chain before starting the server.

    We assert two things: the chain helper is invoked, and the server's
    main runs after it (so any tools the server exposes will see the
    key in os.environ).
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    fake_home = tmp_path / "home"
    (fake_home / ".config" / "hypothesize").mkdir(parents=True)
    key = "sk-ant-" + "Z" * 40
    (fake_home / ".config" / "hypothesize" / ".env").write_text(
        f"ANTHROPIC_API_KEY={key}\n"
    )

    captured: dict[str, str | None] = {"key_at_server_start": None}

    def fake_server_main() -> None:
        captured["key_at_server_start"] = os.environ.get("ANTHROPIC_API_KEY")

    with (
        mock.patch.object(Path, "home", return_value=fake_home),
        mock.patch(
            "hypothesize.mcp.server.main", side_effect=fake_server_main
        ),
    ):
        from hypothesize.mcp.launch import main

        main()

    assert captured["key_at_server_start"] == key


def test_launch_module_can_be_imported_without_running_server() -> None:
    """Importing the module must not start the server (no top-level I/O)."""
    import hypothesize.mcp.launch as launch

    assert callable(launch.main)
