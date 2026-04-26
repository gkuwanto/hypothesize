"""Tests for setup.install_skill — copy bundled SKILL.md to user's skills dir."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from hypothesize.setup import install_skill


def test_bundled_skill_path_locates_skill_md() -> None:
    """The bundled SKILL.md must be locatable in installed and editable layouts."""
    path = install_skill.bundled_skill_path()
    assert path.exists()
    assert path.name == "SKILL.md"
    text = path.read_text()
    assert "name: hypothesize" in text


def test_install_skill_copies_skill_md(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "hypothesize"
    install_skill.install_skill(target)
    assert (target / "SKILL.md").exists()
    assert "name: hypothesize" in (target / "SKILL.md").read_text()


def test_install_skill_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "path" / "hypothesize"
    install_skill.install_skill(target)
    assert (target / "SKILL.md").exists()


def test_install_skill_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "hypothesize"
    target.mkdir()
    (target / "SKILL.md").write_text("stale content")
    install_skill.install_skill(target)
    text = (target / "SKILL.md").read_text()
    assert "stale content" not in text
    assert "name: hypothesize" in text


def test_install_skill_already_installed(tmp_path: Path) -> None:
    target = tmp_path / "hypothesize"
    assert install_skill.is_installed(target) is False
    install_skill.install_skill(target)
    assert install_skill.is_installed(target) is True


def test_install_skill_permission_denied_raises_oserror(tmp_path: Path) -> None:
    """Permission errors propagate as OSError so the wizard can show them."""

    target = tmp_path / "hypothesize"

    def fake_copy(*args: object, **kwargs: object) -> None:
        raise PermissionError("denied")

    with mock.patch("shutil.copyfile", side_effect=fake_copy):
        with pytest.raises(PermissionError):
            install_skill.install_skill(target)
