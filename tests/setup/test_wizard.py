"""Tests for setup.wizard — orchestration of the interactive flow."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import click
import pytest
from click.testing import CliRunner

from hypothesize.setup import wizard
from hypothesize.setup.wizard import SetupOptions, run_setup

# ---------------------------------------------------------------------------
# Non-interactive mode
# ---------------------------------------------------------------------------


def _runner_invoke(args_callable):  # type: ignore[no-untyped-def]
    """Run a callable inside an isolated Click CliRunner.

    Click's CliRunner gives us captured stdin/stdout, an isolated working
    directory, and turns on ``CLICK_TEST_MODE`` semantics — important so
    the wizard's ``click.echo`` and ``click.prompt`` calls behave
    predictably.
    """

    @click.command()
    def harness() -> None:
        args_callable()

    runner = CliRunner()
    return runner.invoke(harness, [], catch_exceptions=False)


def _ni_options(tmp_path: Path, **overrides) -> SetupOptions:  # type: ignore[no-untyped-def]
    base = SetupOptions(
        interactive=False,
        api_key="sk-ant-" + "z" * 40,
        skip_claude_code=True,
        skip_claude_desktop=True,
        skip_verification=True,
        config_dir=tmp_path / "cfg",
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_non_interactive_writes_api_key(tmp_path: Path) -> None:
    options = _ni_options(tmp_path)
    result = _runner_invoke(lambda: run_setup(options))
    assert result.exit_code == 0
    env_file = tmp_path / "cfg" / ".env"
    assert env_file.exists()
    text = env_file.read_text()
    assert "sk-ant-" + "z" * 40 in text


def test_non_interactive_requires_api_key(tmp_path: Path) -> None:
    options = SetupOptions(
        interactive=False,
        api_key=None,
        skip_claude_code=True,
        skip_claude_desktop=True,
        config_dir=tmp_path / "cfg",
    )

    with pytest.raises(click.UsageError) as exc:
        run_setup(options)
    assert "API key required" in str(exc.value)


def test_non_interactive_rejects_invalid_api_key(tmp_path: Path) -> None:
    options = _ni_options(tmp_path, api_key="not-a-key")

    with pytest.raises(click.UsageError) as exc:
        run_setup(options)
    assert "valid Anthropic key" in str(exc.value)


def test_non_interactive_skips_claude_code_when_flag_set(tmp_path: Path) -> None:
    options = _ni_options(tmp_path, skip_claude_code=True)
    result = _runner_invoke(lambda: run_setup(options))
    assert result.exit_code == 0
    # The skill must NOT have been installed at the user's actual home —
    # we never wrote there because of skip_claude_code.
    assert "Claude Code skill" in result.output


def test_non_interactive_installs_skill_when_claude_present(
    tmp_path: Path,
) -> None:
    options = _ni_options(tmp_path, skip_claude_code=False)
    fake_skill_dir = tmp_path / "skills" / "hypothesize"
    with (
        mock.patch(
            "hypothesize.setup.wizard.detect.claude_code_present",
            return_value=True,
        ),
        mock.patch(
            "hypothesize.setup.wizard.detect.skill_install_dir",
            return_value=fake_skill_dir,
        ),
    ):
        result = _runner_invoke(lambda: run_setup(options))
    assert result.exit_code == 0
    assert (fake_skill_dir / "SKILL.md").exists()


def test_non_interactive_registers_mcp_when_desktop_present(
    tmp_path: Path,
) -> None:
    options = _ni_options(tmp_path, skip_claude_desktop=False)
    fake_mcp_path = tmp_path / "Claude" / "claude_desktop_config.json"
    with mock.patch(
        "hypothesize.setup.wizard.detect.claude_desktop_config_path",
        return_value=fake_mcp_path,
    ):
        result = _runner_invoke(lambda: run_setup(options))
    assert result.exit_code == 0
    assert fake_mcp_path.exists()
    import json

    payload = json.loads(fake_mcp_path.read_text())
    assert "hypothesize" in payload["mcpServers"]


def test_non_interactive_skips_mcp_when_desktop_absent(
    tmp_path: Path,
) -> None:
    options = _ni_options(tmp_path, skip_claude_desktop=False)
    with mock.patch(
        "hypothesize.setup.wizard.detect.claude_desktop_config_path",
        return_value=None,
    ):
        result = _runner_invoke(lambda: run_setup(options))
    assert result.exit_code == 0
    assert "Claude Desktop MCP" in result.output


# ---------------------------------------------------------------------------
# API key never leaks
# ---------------------------------------------------------------------------


def test_setup_never_prints_api_key(tmp_path: Path) -> None:
    secret = "sk-ant-" + "Q" * 40
    options = _ni_options(tmp_path, api_key=secret)
    result = _runner_invoke(lambda: run_setup(options))
    assert result.exit_code == 0
    assert secret not in result.output
    # The fingerprint shows the last 4, which on this synthetic key is
    # "QQQQ" — that's allowed; the prefix and full key body must NOT
    # appear.
    assert "sk-ant-Q" not in result.output


def test_setup_redacts_api_key_in_verification_errors(tmp_path: Path) -> None:
    secret = "sk-ant-" + "X" * 40
    options = _ni_options(tmp_path, api_key=secret, skip_verification=False)

    def boom(_key: str) -> bool:
        raise RuntimeError(f"upstream returned 401 for {secret}")

    with mock.patch(
        "hypothesize.setup.wizard._verify_api_key", side_effect=boom
    ):
        result = _runner_invoke(lambda: run_setup(options))
    assert result.exit_code == 0
    assert secret not in result.output


# ---------------------------------------------------------------------------
# Interactive mode (light-touch — full coverage in tests/cli/test_setup.py)
# ---------------------------------------------------------------------------


def test_interactive_aborts_on_decline_continue(tmp_path: Path) -> None:
    runner = CliRunner()

    @click.command()
    def harness() -> None:
        run_setup(
            SetupOptions(
                interactive=True,
                api_key=None,
                skip_claude_code=True,
                skip_claude_desktop=True,
                config_dir=tmp_path / "cfg",
            )
        )

    # Decline the welcome prompt.
    result = runner.invoke(harness, [], input="n\n", catch_exceptions=False)
    # User abort exits non-zero from Click's perspective.
    assert "Setup aborted" in result.output


# ---------------------------------------------------------------------------
# Setup defaults
# ---------------------------------------------------------------------------


def test_setup_options_defaults_safe() -> None:
    options = SetupOptions()
    assert options.interactive is True
    assert options.api_key is None
    assert options.skip_claude_code is False
    assert options.skip_claude_desktop is False
    # Verification defaults to skipped — the wizard explicitly opts in.
    assert options.skip_verification is True


def test_ensure_config_dir_creates_path(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "config"
    wizard.ensure_config_dir(target)
    assert target.is_dir()
