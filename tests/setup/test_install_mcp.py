"""Tests for setup.install_mcp — Claude Desktop MCP server registration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

from hypothesize.setup import install_mcp


def _write_config(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_build_entry_uses_sys_executable() -> None:
    entry = install_mcp.build_mcp_entry(env_file=Path("/cfg/.env"))
    assert entry["command"] == sys.executable
    # The launcher module loads dotenv chain before starting the server.
    assert entry["args"] == ["-m", "hypothesize.mcp.launch"]
    assert entry["env"]["HYPOTHESIZE_API_KEY_FILE"] == "/cfg/.env"


def test_register_creates_config_when_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    install_mcp.register_mcp_server(
        config_path=config_path, env_file=tmp_path / ".env"
    )
    payload = json.loads(config_path.read_text())
    assert "mcpServers" in payload
    assert "hypothesize" in payload["mcpServers"]
    assert payload["mcpServers"]["hypothesize"]["args"] == [
        "-m",
        "hypothesize.mcp.launch",
    ]


def test_register_preserves_other_mcp_servers(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    other_entry = {"command": "node", "args": ["server.js"]}
    _write_config(
        config_path,
        {
            "mcpServers": {"other": other_entry},
            "globalShortcut": "Cmd+Shift+H",
        },
    )
    install_mcp.register_mcp_server(
        config_path=config_path, env_file=tmp_path / ".env"
    )
    payload = json.loads(config_path.read_text())
    assert payload["mcpServers"]["other"] == other_entry
    assert "hypothesize" in payload["mcpServers"]
    assert payload["globalShortcut"] == "Cmd+Shift+H"


def test_register_overwrites_existing_hypothesize_entry(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    _write_config(
        config_path,
        {"mcpServers": {"hypothesize": {"command": "outdated"}}},
    )
    install_mcp.register_mcp_server(
        config_path=config_path, env_file=tmp_path / ".env"
    )
    payload = json.loads(config_path.read_text())
    assert payload["mcpServers"]["hypothesize"]["command"] == sys.executable


def test_register_writes_atomically_via_temp(tmp_path: Path) -> None:
    """The implementation should write to a temp file and rename.

    We patch :func:`os.replace` (the atomic-rename primitive used after
    the temp write) and verify it's called with a temp path argument
    that lives next to the target. This is a structural assertion: we
    don't want a partial-write to corrupt the user's config.
    """
    config_path = tmp_path / "claude_desktop_config.json"
    _write_config(config_path, {"mcpServers": {}})
    with mock.patch("os.replace", wraps=__import__("os").replace) as replace:
        install_mcp.register_mcp_server(
            config_path=config_path, env_file=tmp_path / ".env"
        )
    assert replace.called
    args, _ = replace.call_args
    src, dst = args
    assert Path(dst) == config_path
    assert Path(src).parent == config_path.parent


def test_register_does_not_corrupt_on_failed_rename(tmp_path: Path) -> None:
    """If os.replace fails, the original config must remain intact."""
    config_path = tmp_path / "claude_desktop_config.json"
    original_payload = {
        "mcpServers": {"keep": {"command": "keep-me"}},
        "marker": "untouched",
    }
    _write_config(config_path, original_payload)

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("simulated rename failure")

    with mock.patch("os.replace", side_effect=boom):
        with pytest.raises(OSError):
            install_mcp.register_mcp_server(
                config_path=config_path, env_file=tmp_path / ".env"
            )
    # Original file is unchanged.
    assert json.loads(config_path.read_text()) == original_payload
    # And no leftover temp files lying next to it.
    siblings = [
        p
        for p in config_path.parent.iterdir()
        if p != config_path and p.suffix != ".json"
    ]
    assert siblings == []


def test_register_rejects_malformed_existing_json(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{not valid json")
    with pytest.raises(install_mcp.MalformedConfigError):
        install_mcp.register_mcp_server(
            config_path=config_path, env_file=tmp_path / ".env"
        )
    # Malformed file must NOT be overwritten.
    assert config_path.read_text() == "{not valid json"


def test_already_registered_returns_true_when_present(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    install_mcp.register_mcp_server(
        config_path=config_path, env_file=tmp_path / ".env"
    )
    assert install_mcp.is_registered(config_path) is True


def test_already_registered_returns_false_when_absent(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    _write_config(config_path, {"mcpServers": {}})
    assert install_mcp.is_registered(config_path) is False


def test_already_registered_returns_false_when_file_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    assert install_mcp.is_registered(config_path) is False


def test_register_writes_indented_json(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    install_mcp.register_mcp_server(
        config_path=config_path, env_file=tmp_path / ".env"
    )
    text = config_path.read_text()
    # Should be human-readable, not single-line.
    assert "\n" in text
