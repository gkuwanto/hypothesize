"""Register the hypothesize MCP server with Claude Desktop atomically.

Claude Desktop's config file is a single JSON document at a
platform-specific path. Other MCP servers and unrelated keys may already
be present, so we deep-merge our entry under ``mcpServers.hypothesize``
and leave everything else untouched. Writes go through a sibling temp
file followed by ``os.replace`` so a crash mid-write cannot corrupt the
user's existing config.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ENTRY_NAME = "hypothesize"


class MalformedConfigError(ValueError):
    """Raised when the existing Claude Desktop config is not valid JSON.

    The wizard surfaces this without overwriting the file — the user
    needs to repair their config manually before we can safely merge.
    """


def build_mcp_entry(env_file: Path) -> dict[str, Any]:
    """Return the mcpServers entry payload for hypothesize.

    Uses :data:`sys.executable` as the ``command`` so the entry points
    at the same Python interpreter the user installed hypothesize
    into, regardless of whether that's a system Python, a venv, or a
    uvx-managed temporary environment.

    The launch module loads ``~/.config/hypothesize/.env`` itself, so
    Claude Desktop does not need to forward the API key. The
    ``HYPOTHESIZE_API_KEY_FILE`` env entry is passed for documentation
    only — it records which file the launcher should pick up first if
    a future revision honors it as an explicit override.
    """
    return {
        "command": sys.executable,
        "args": ["-m", "hypothesize.mcp.launch"],
        "env": {"HYPOTHESIZE_API_KEY_FILE": str(env_file)},
    }


def is_registered(config_path: Path) -> bool:
    """Return True iff ``config_path`` already has a hypothesize entry."""
    if not config_path.exists():
        return False
    try:
        payload = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(payload, dict):
        return False
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict):
        return False
    return ENTRY_NAME in servers


def register_mcp_server(*, config_path: Path, env_file: Path) -> None:
    """Atomically merge a hypothesize entry into Claude Desktop's config.

    - If ``config_path`` does not exist, creates it with a minimal
      ``{"mcpServers": {"hypothesize": ...}}`` payload.
    - If it exists and is valid JSON, merges the hypothesize entry
      under ``mcpServers``, preserving all other keys and other MCP
      server entries.
    - If it exists but is malformed JSON, raises
      :class:`MalformedConfigError` without modifying the file.

    Writes go through a sibling temp file + ``os.replace``, so the
    original config remains intact if any step fails. The directory
    must be writable; ``OSError`` propagates so the wizard can show a
    clear path/permission error.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        try:
            text = config_path.read_text()
        except OSError as exc:  # pragma: no cover — surfaced to wizard
            raise MalformedConfigError(f"cannot read {config_path}: {exc}") from exc
        if text.strip():
            try:
                existing = json.loads(text)
            except json.JSONDecodeError as exc:
                raise MalformedConfigError(
                    f"{config_path} is not valid JSON: {exc.msg}"
                ) from exc
            if not isinstance(existing, dict):
                raise MalformedConfigError(
                    f"{config_path} root is not a JSON object"
                )
        else:
            existing = {}
    else:
        existing = {}

    servers = existing.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers[ENTRY_NAME] = build_mcp_entry(env_file=env_file)
    existing["mcpServers"] = servers

    _atomic_write_json(config_path, existing)


def _atomic_write_json(target: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``target`` via a sibling temp file + replace.

    We open the temp file in the same directory as the target so that
    ``os.replace`` is a single-filesystem rename, which is atomic on
    POSIX and on modern Windows. If anything between writing the temp
    and replacing fails, we delete the temp and re-raise.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, target)
    except Exception:
        # Best-effort cleanup of the temp file; suppress secondary errors so
        # the original failure is what the caller sees.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
