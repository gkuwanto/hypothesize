"""Tests for setup detection helpers.

Covers:
- ``claude_code_present`` — checks ``claude`` binary on PATH.
- ``claude_desktop_config_path`` — platform-specific resolution.
- ``find_skill_install_dir`` — ``~/.claude/skills/hypothesize`` location.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from hypothesize.setup import detect


def test_claude_code_present_true_when_binary_on_path() -> None:
    with mock.patch("shutil.which", return_value="/usr/local/bin/claude"):
        assert detect.claude_code_present() is True


def test_claude_code_present_false_when_binary_absent() -> None:
    with mock.patch("shutil.which", return_value=None):
        assert detect.claude_code_present() is False


def test_claude_desktop_config_path_macos(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    parent = fake_home / "Library/Application Support/Claude"
    parent.mkdir(parents=True)
    with (
        mock.patch("platform.system", return_value="Darwin"),
        mock.patch.object(Path, "home", return_value=fake_home),
    ):
        result = detect.claude_desktop_config_path()
    assert result == parent / "claude_desktop_config.json"


def test_claude_desktop_config_path_macos_returns_none_when_parent_missing(
    tmp_path: Path,
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with (
        mock.patch("platform.system", return_value="Darwin"),
        mock.patch.object(Path, "home", return_value=fake_home),
    ):
        result = detect.claude_desktop_config_path()
    assert result is None


def test_claude_desktop_config_path_linux(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    parent = fake_home / ".config/Claude"
    parent.mkdir(parents=True)
    with (
        mock.patch("platform.system", return_value="Linux"),
        mock.patch.object(Path, "home", return_value=fake_home),
    ):
        result = detect.claude_desktop_config_path()
    assert result == parent / "claude_desktop_config.json"


def test_claude_desktop_config_path_windows(tmp_path: Path) -> None:
    appdata = tmp_path / "AppData/Roaming"
    parent = appdata / "Claude"
    parent.mkdir(parents=True)
    with (
        mock.patch("platform.system", return_value="Windows"),
        mock.patch.dict(os.environ, {"APPDATA": str(appdata)}, clear=False),
    ):
        result = detect.claude_desktop_config_path()
    assert result == parent / "claude_desktop_config.json"


def test_claude_desktop_config_path_unknown_os_returns_none() -> None:
    with mock.patch("platform.system", return_value="Plan9"):
        assert detect.claude_desktop_config_path() is None


def test_skill_install_dir_uses_user_home(tmp_path: Path) -> None:
    with mock.patch.object(Path, "home", return_value=tmp_path):
        result = detect.skill_install_dir()
    assert result == tmp_path / ".claude" / "skills" / "hypothesize"
