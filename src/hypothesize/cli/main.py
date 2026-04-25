"""Top-level Click group for the ``hypothesize`` CLI.

Subcommands (``run``, ``list``, ``validate``) are stubs in this task and
get real implementations in tasks 4.2 and 4.3. The group itself is
small on purpose: shared options live here, command bodies live in
sibling modules.
"""

from __future__ import annotations

import click

from hypothesize import __version__


@click.group(
    help="Turn LLM failure hypotheses into discriminating regression benchmarks.",
)
@click.version_option(__version__, prog_name="hypothesize")
def cli() -> None:
    """Hypothesize CLI entry point."""


@cli.command(name="run")
def run_cmd() -> None:
    """Run discrimination against a system config."""
    click.echo("run not implemented yet")


@cli.command(name="list")
def list_cmd() -> None:
    """List existing benchmark YAMLs in a directory."""
    click.echo("list not implemented yet")


@cli.command(name="validate")
def validate_cmd() -> None:
    """Validate a benchmark YAML against the documented schema."""
    click.echo("validate not implemented yet")
