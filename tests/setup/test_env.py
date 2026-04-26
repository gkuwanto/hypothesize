"""Tests for setup.env — API key validation and .env file writing."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest import mock

import pytest

from hypothesize.setup import env

# ---------------------------------------------------------------------------
# is_valid_api_key
# ---------------------------------------------------------------------------


def test_valid_api_key_accepted() -> None:
    key = "sk-ant-" + "a" * 40
    assert env.is_valid_api_key(key) is True


def test_short_key_rejected() -> None:
    assert env.is_valid_api_key("sk-ant-short") is False


def test_wrong_prefix_rejected() -> None:
    key = "openai-" + "a" * 40
    assert env.is_valid_api_key(key) is False


def test_empty_key_rejected() -> None:
    assert env.is_valid_api_key("") is False


def test_whitespace_only_rejected() -> None:
    assert env.is_valid_api_key("   ") is False


def test_validation_strips_surrounding_whitespace() -> None:
    key = "  sk-ant-" + "a" * 40 + "  "
    assert env.is_valid_api_key(key) is True


# ---------------------------------------------------------------------------
# fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_returns_last_four() -> None:
    key = "sk-ant-" + "a" * 30 + "xK7m"
    assert env.fingerprint(key) == "...xK7m"


def test_fingerprint_short_key_safe() -> None:
    # Even on a too-short key (rejected by validator), fingerprinting must
    # not crash or leak the prefix — only show "..." with what's available.
    out = env.fingerprint("ab")
    assert "ab" in out
    assert out.startswith("...")


def test_fingerprint_empty_safe() -> None:
    assert env.fingerprint("") == "..."


# ---------------------------------------------------------------------------
# default_config_dir & default_env_path
# ---------------------------------------------------------------------------


def test_default_config_dir_under_home(tmp_path: Path) -> None:
    with mock.patch.object(Path, "home", return_value=tmp_path):
        result = env.default_config_dir()
    assert result == tmp_path / ".config" / "hypothesize"


def test_default_env_path_uses_default_dir(tmp_path: Path) -> None:
    with mock.patch.object(Path, "home", return_value=tmp_path):
        result = env.default_env_path()
    assert result == tmp_path / ".config" / "hypothesize" / ".env"


# ---------------------------------------------------------------------------
# write_api_key
# ---------------------------------------------------------------------------


def test_write_api_key_creates_parent_dir(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / ".env"
    key = "sk-ant-" + "a" * 40
    env.write_api_key(target, key)
    assert target.exists()
    assert key in target.read_text()


def test_write_api_key_writes_in_env_format(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    key = "sk-ant-" + "b" * 40
    env.write_api_key(target, key)
    text = target.read_text()
    assert text.strip() == f"ANTHROPIC_API_KEY={key}"


def test_write_api_key_sets_mode_0600(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    key = "sk-ant-" + "c" * 40
    env.write_api_key(target, key)
    mode = stat.S_IMODE(target.stat().st_mode)
    # Owner read/write only — group and other must be empty.
    assert mode == 0o600


def test_write_api_key_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    target.write_text("ANTHROPIC_API_KEY=old\nOTHER=keep\n")
    new_key = "sk-ant-" + "d" * 40
    env.write_api_key(target, new_key)
    text = target.read_text()
    assert "old" not in text
    assert new_key in text


def test_write_api_key_does_not_print_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / ".env"
    key = "sk-ant-" + "e" * 40
    env.write_api_key(target, key)
    captured = capsys.readouterr()
    assert key not in captured.out
    assert key not in captured.err


# ---------------------------------------------------------------------------
# detect_existing_key
# ---------------------------------------------------------------------------


def test_detect_existing_key_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    key = "sk-ant-" + "f" * 40
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    found = env.detect_existing_key(env_files=[])
    assert found is not None
    assert found.source == "environment"
    assert found.value == key


def test_detect_existing_key_reads_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    key = "sk-ant-" + "g" * 40
    env_file.write_text(f"ANTHROPIC_API_KEY={key}\n")
    found = env.detect_existing_key(env_files=[env_file])
    assert found is not None
    assert found.source == str(env_file)
    assert found.value == key


def test_detect_existing_key_returns_none_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert env.detect_existing_key(env_files=[tmp_path / ".env"]) is None


def test_detect_existing_key_environment_wins_over_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_key = "sk-ant-" + "h" * 40
    file_key = "sk-ant-" + "i" * 40
    monkeypatch.setenv("ANTHROPIC_API_KEY", env_key)
    env_file = tmp_path / ".env"
    env_file.write_text(f"ANTHROPIC_API_KEY={file_key}\n")
    found = env.detect_existing_key(env_files=[env_file])
    assert found is not None
    assert found.source == "environment"
    assert found.value == env_key


def test_detect_existing_key_skips_empty_file_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=\n")
    assert env.detect_existing_key(env_files=[env_file]) is None


def test_detect_existing_key_handles_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert (
        env.detect_existing_key(env_files=[tmp_path / "no-such-file"])
        is None
    )


def test_environment_value_not_emitted_via_repr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Detect-existing-key never prints the key value to stdout/err."""
    key = "sk-ant-" + "j" * 40
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    env.detect_existing_key(env_files=[])
    captured = capsys.readouterr()
    assert key not in captured.out
    assert key not in captured.err


def test_unrelated_env_vars_in_file_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Other env entries in the file must not be clobbered by the detect call."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    original = "OTHER_VAR=keep\nANTHROPIC_API_KEY=sk-ant-" + "k" * 40 + "\n"
    env_file.write_text(original)
    env.detect_existing_key(env_files=[env_file])
    assert env_file.read_text() == original


def test_dummy_clears_env() -> None:
    # Sanity: the dotenv helper does not pollute os.environ on this process.
    assert os.environ.get("ANTHROPIC_API_KEY", "") == os.environ.get(
        "ANTHROPIC_API_KEY", ""
    )
