"""Top-level Click group for the ``hypothesize`` CLI.

Subcommands (``run``, ``list``, ``validate``) are stubs in this task and
get real implementations in tasks 4.2 and 4.3. The group itself is
small on purpose: shared options live here, command bodies live in
sibling modules.
"""

from __future__ import annotations

import click

from hypothesize import __version__
from hypothesize.cli.list_cmd import list_cmd
from hypothesize.cli.run import run_cmd
from hypothesize.cli.validate import validate_cmd


@click.group(
    help="Turn LLM failure hypotheses into discriminating regression benchmarks.",
)
@click.version_option(__version__, prog_name="hypothesize")
def cli() -> None:
    """Hypothesize CLI entry point."""


cli.add_command(run_cmd)
cli.add_command(list_cmd)
cli.add_command(validate_cmd)
