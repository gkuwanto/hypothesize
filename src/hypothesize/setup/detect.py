"""Detect Claude Code and Claude Desktop installations on this host.

All detection is purely best-effort and side-effect free: presence of a
binary on ``PATH`` for Claude Code, presence of the platform-specific
config directory for Claude Desktop. Returning ``None`` means "not
detected"; the wizard surfaces a manual-install hint instead of
attempting installation.
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path


def claude_code_present() -> bool:
    """Return True iff a ``claude`` binary is on the user's ``PATH``."""
    return shutil.which("claude") is not None


def claude_desktop_config_path() -> Path | None:
    """Return the platform-specific Claude Desktop config path, or None.

    Returns ``None`` when the OS is unrecognised, when ``APPDATA`` is
    unset on Windows, or when the parent directory does not exist (i.e.
    Claude Desktop has never been launched on this machine).
    """
    system = platform.system()
    if system == "Darwin":
        path = (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return None
        path = Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif system == "Linux":
        path = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    else:
        return None
    if not path.parent.exists():
        return None
    return path


def skill_install_dir() -> Path:
    """Return the canonical install location for the hypothesize skill."""
    return Path.home() / ".claude" / "skills" / "hypothesize"
