"""Smoke tests for the Click group at hypothesize.cli.main."""

from __future__ import annotations

from click.testing import CliRunner

from hypothesize import __version__
from hypothesize.cli.main import cli


def test_version_flag_prints_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for sub in ("run", "list", "validate"):
        assert sub in result.output


def test_run_stub_exits_zero_with_placeholder() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["run"])
    assert result.exit_code == 0
    assert "not implemented" in result.output


def test_list_stub_exits_zero_with_placeholder() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "not implemented" in result.output


def test_validate_stub_exits_zero_with_placeholder() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["validate"])
    assert result.exit_code == 0
    assert "not implemented" in result.output
