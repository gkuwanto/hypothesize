"""End-to-end CLI tests for ``hypothesize setup``.

These tests exercise the Click command directly via :class:`CliRunner`
and a temp filesystem. They never write to ``~/.config`` or ``~/.claude``
on the host machine: detection helpers are patched, and ``--config-dir``
points at ``tmp_path``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from click.testing import CliRunner

from hypothesize.cli.main import cli

VALID_KEY = "sk-ant-" + "y" * 40


def _invoke(args: list[str], **runner_kwargs):  # type: ignore[no-untyped-def]
    runner = CliRunner()
    return runner.invoke(cli, ["setup", *args], **runner_kwargs)


def test_setup_help_works() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["setup", "--help"])
    assert result.exit_code == 0
    for opt in (
        "--non-interactive",
        "--api-key",
        "--skip-claude-code",
        "--skip-claude-desktop",
        "--config-dir",
    ):
        assert opt in result.output


def test_main_help_lists_setup() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "setup" in result.output


def test_non_interactive_writes_env_file(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "cfg"
    result = _invoke(
        [
            "--non-interactive",
            "--api-key",
            VALID_KEY,
            "--skip-claude-code",
            "--skip-claude-desktop",
            "--config-dir",
            str(cfg_dir),
        ]
    )
    assert result.exit_code == 0, result.output
    assert (cfg_dir / ".env").exists()
    assert VALID_KEY in (cfg_dir / ".env").read_text()


def test_non_interactive_missing_api_key_errors(tmp_path: Path) -> None:
    """No --api-key and no env var → exit 2 with clear error."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "setup",
            "--non-interactive",
            "--skip-claude-code",
            "--skip-claude-desktop",
            "--config-dir",
            str(tmp_path / "cfg"),
        ],
        env={"ANTHROPIC_API_KEY": ""},
    )
    assert result.exit_code == 2
    assert "API key required" in result.output


def test_non_interactive_invalid_api_key_errors(tmp_path: Path) -> None:
    result = _invoke(
        [
            "--non-interactive",
            "--api-key",
            "not-a-real-key",
            "--skip-claude-code",
            "--skip-claude-desktop",
            "--config-dir",
            str(tmp_path / "cfg"),
        ]
    )
    assert result.exit_code == 2
    assert "valid Anthropic key" in result.output


def test_non_interactive_creates_config_dir_if_missing(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "deep" / "nested" / "cfg"
    assert not cfg_dir.exists()
    result = _invoke(
        [
            "--non-interactive",
            "--api-key",
            VALID_KEY,
            "--skip-claude-code",
            "--skip-claude-desktop",
            "--config-dir",
            str(cfg_dir),
        ]
    )
    assert result.exit_code == 0, result.output
    assert (cfg_dir / ".env").exists()


def test_non_interactive_full_install(tmp_path: Path) -> None:
    """All three install steps succeed when both apps are detected."""
    cfg_dir = tmp_path / "cfg"
    skill_dir = tmp_path / "skills" / "hypothesize"
    mcp_path = tmp_path / "Claude" / "claude_desktop_config.json"
    with (
        mock.patch(
            "hypothesize.setup.wizard.detect.claude_code_present",
            return_value=True,
        ),
        mock.patch(
            "hypothesize.setup.wizard.detect.skill_install_dir",
            return_value=skill_dir,
        ),
        mock.patch(
            "hypothesize.setup.wizard.detect.claude_desktop_config_path",
            return_value=mcp_path,
        ),
    ):
        result = _invoke(
            [
                "--non-interactive",
                "--api-key",
                VALID_KEY,
                "--config-dir",
                str(cfg_dir),
            ]
        )
    assert result.exit_code == 0, result.output
    assert (cfg_dir / ".env").exists()
    assert (skill_dir / "SKILL.md").exists()
    assert mcp_path.exists()
    payload = json.loads(mcp_path.read_text())
    assert "hypothesize" in payload["mcpServers"]
    # The mcp entry's env file must point at the same .env we just wrote.
    assert payload["mcpServers"]["hypothesize"]["env"][
        "HYPOTHESIZE_API_KEY_FILE"
    ] == str(cfg_dir / ".env")
    # And the entry invokes the launcher (which loads the key file)
    # rather than the bare server module.
    assert payload["mcpServers"]["hypothesize"]["args"] == [
        "-m",
        "hypothesize.mcp.launch",
    ]


def test_non_interactive_summary_emits_status_glyphs(tmp_path: Path) -> None:
    result = _invoke(
        [
            "--non-interactive",
            "--api-key",
            VALID_KEY,
            "--skip-claude-code",
            "--skip-claude-desktop",
            "--config-dir",
            str(tmp_path / "cfg"),
        ]
    )
    assert result.exit_code == 0
    assert "Setup complete" in result.output
    # ✓ for done, ✗ for skipped — both must appear in this run.
    assert "✓" in result.output
    assert "✗" in result.output


def test_setup_does_not_print_api_key(tmp_path: Path) -> None:
    sentinel_key = "sk-ant-" + "K" * 40
    result = _invoke(
        [
            "--non-interactive",
            "--api-key",
            sentinel_key,
            "--skip-claude-code",
            "--skip-claude-desktop",
            "--config-dir",
            str(tmp_path / "cfg"),
        ]
    )
    assert result.exit_code == 0
    # Full key body must not appear in user-facing output.
    assert sentinel_key not in result.output
    # The "K" * 40 body must not appear either.
    assert "K" * 40 not in result.output


def test_setup_with_malformed_existing_config_does_not_clobber(
    tmp_path: Path,
) -> None:
    """Malformed Claude Desktop config: surface the error, leave file alone."""
    cfg_dir = tmp_path / "cfg"
    mcp_path = tmp_path / "Claude" / "claude_desktop_config.json"
    mcp_path.parent.mkdir(parents=True)
    original = "{not valid json"
    mcp_path.write_text(original)
    with mock.patch(
        "hypothesize.setup.wizard.detect.claude_desktop_config_path",
        return_value=mcp_path,
    ):
        result = _invoke(
            [
                "--non-interactive",
                "--api-key",
                VALID_KEY,
                "--skip-claude-code",
                "--config-dir",
                str(cfg_dir),
            ]
        )
    # Setup completes (other steps succeed) but reports the failure.
    assert result.exit_code == 0
    assert mcp_path.read_text() == original
    assert "⚠" in result.output


def test_interactive_full_flow_with_input(tmp_path: Path) -> None:
    """Drive the interactive wizard end-to-end via stdin."""
    skill_dir = tmp_path / "skills" / "hypothesize"
    mcp_path = tmp_path / "Claude" / "claude_desktop_config.json"
    runner = CliRunner()
    with (
        mock.patch(
            "hypothesize.setup.wizard.detect.claude_code_present",
            return_value=True,
        ),
        mock.patch(
            "hypothesize.setup.wizard.detect.skill_install_dir",
            return_value=skill_dir,
        ),
        mock.patch(
            "hypothesize.setup.wizard.detect.claude_desktop_config_path",
            return_value=mcp_path,
        ),
        runner.isolated_filesystem() as cwd,
    ):
        cfg_dir = Path(cwd) / "cfg"
        # Inputs: continue?=y, key=VALID_KEY, install skill?=y,
        # register MCP?=y. Verification not asked because default skips.
        result = runner.invoke(
            cli,
            ["setup", "--config-dir", str(cfg_dir)],
            input=f"y\n{VALID_KEY}\ny\ny\n",
            env={"ANTHROPIC_API_KEY": ""},
        )
        assert result.exit_code == 0, result.output
        assert (cfg_dir / ".env").exists()
        assert (skill_dir / "SKILL.md").exists()
        assert mcp_path.exists()


def test_interactive_aborts_at_welcome(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as cwd:
        cfg_dir = Path(cwd) / "cfg"
        result = runner.invoke(
            cli,
            [
                "setup",
                "--skip-claude-code",
                "--skip-claude-desktop",
                "--config-dir",
                str(cfg_dir),
            ],
            input="n\n",
            env={"ANTHROPIC_API_KEY": ""},
        )
    assert result.exit_code == 1
    assert "Setup aborted" in result.output


def test_interactive_recognises_existing_env_var(tmp_path: Path) -> None:
    """Using an existing key from env should not require typing it again."""
    runner = CliRunner()
    with runner.isolated_filesystem() as cwd:
        cfg_dir = Path(cwd) / "cfg"
        result = runner.invoke(
            cli,
            [
                "setup",
                "--skip-claude-code",
                "--skip-claude-desktop",
                "--config-dir",
                str(cfg_dir),
            ],
            # Inputs: continue?=y, choose [u]se this key
            input="y\nu\n",
            env={"ANTHROPIC_API_KEY": VALID_KEY},
        )
        assert result.exit_code == 0, result.output
        assert (cfg_dir / ".env").exists()
        assert VALID_KEY in (cfg_dir / ".env").read_text()
    # Fingerprint shown but not the full key.
    assert VALID_KEY not in result.output
    assert "..." in result.output


def test_interactive_invalid_then_valid_key(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as cwd:
        cfg_dir = Path(cwd) / "cfg"
        result = runner.invoke(
            cli,
            [
                "setup",
                "--skip-claude-code",
                "--skip-claude-desktop",
                "--config-dir",
                str(cfg_dir),
            ],
            input=f"y\nbogus-key-too-short\n{VALID_KEY}\n",
            env={"ANTHROPIC_API_KEY": ""},
        )
        assert result.exit_code == 0, result.output
        assert (cfg_dir / ".env").exists()
        assert VALID_KEY in (cfg_dir / ".env").read_text()
    assert "did not look valid" in result.output


def test_interactive_three_invalid_keys_skips(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as cwd:
        cfg_dir = Path(cwd) / "cfg"
        result = runner.invoke(
            cli,
            [
                "setup",
                "--skip-claude-code",
                "--skip-claude-desktop",
                "--config-dir",
                str(cfg_dir),
            ],
            input="y\nbad1\nbad2\nbad3\n",
            env={"ANTHROPIC_API_KEY": ""},
        )
        assert result.exit_code == 0
        assert not (cfg_dir / ".env").exists()
    assert "Too many invalid attempts" in result.output


def test_setup_with_verify_calls_anthropic(tmp_path: Path) -> None:
    """``--verify`` invokes the verification helper exactly once."""
    cfg_dir = tmp_path / "cfg"
    with mock.patch(
        "hypothesize.setup.wizard._verify_api_key", return_value=True
    ) as verify_mock:
        result = _invoke(
            [
                "--non-interactive",
                "--api-key",
                VALID_KEY,
                "--skip-claude-code",
                "--skip-claude-desktop",
                "--config-dir",
                str(cfg_dir),
                "--verify",
            ]
        )
    assert result.exit_code == 0, result.output
    verify_mock.assert_called_once()
    # The key passed in is what gets verified.
    (passed_key,), _kwargs = verify_mock.call_args
    assert passed_key == VALID_KEY
