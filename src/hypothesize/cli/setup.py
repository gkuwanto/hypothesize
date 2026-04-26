"""Body of the ``hypothesize setup`` Click command.

A thin wrapper around :func:`hypothesize.setup.wizard.run_setup`. The
flag-driven side of the CLI is for CI/scripted use; default invocation
is fully interactive.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from hypothesize.setup.wizard import SetupOptions, ensure_config_dir, run_setup


@click.command(name="setup")
@click.option(
    "--non-interactive",
    is_flag=True,
    default=False,
    help="Run without prompts. Requires --api-key (or ANTHROPIC_API_KEY in env).",
)
@click.option(
    "--api-key",
    "api_key",
    type=str,
    default=None,
    help="Anthropic API key. Used in --non-interactive mode.",
)
@click.option(
    "--skip-claude-code",
    is_flag=True,
    default=False,
    help="Skip the Claude Code skill install step.",
)
@click.option(
    "--skip-claude-desktop",
    is_flag=True,
    default=False,
    help="Skip the Claude Desktop MCP registration step.",
)
@click.option(
    "--verify/--no-verify",
    "verify",
    default=False,
    help="Run a single Haiku call to verify the API key (default: no).",
)
@click.option(
    "--config-dir",
    "config_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Override the config directory (default: ~/.config/hypothesize).",
)
def setup_cmd(
    non_interactive: bool,
    api_key: str | None,
    skip_claude_code: bool,
    skip_claude_desktop: bool,
    verify: bool,
    config_dir: Path | None,
) -> None:
    """Configure your API key and (optionally) Claude Code / Claude Desktop."""
    if config_dir is not None:
        ensure_config_dir(config_dir)

    options = SetupOptions(
        interactive=not non_interactive,
        api_key=api_key,
        skip_claude_code=skip_claude_code,
        skip_claude_desktop=skip_claude_desktop,
        skip_verification=not verify,
        config_dir=config_dir,
    )

    try:
        run_setup(options)
    except click.UsageError as exc:
        click.echo(f"error: {exc.message}", err=True)
        sys.exit(2)
    except click.Abort:
        # The wizard already printed "Setup aborted." in its handler.
        sys.exit(1)
