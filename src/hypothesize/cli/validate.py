"""``hypothesize validate`` — check a benchmark YAML against the schema.

Loads ``PATH``, checks that the top-level dict contains
``hypothesis: str``, ``metadata: dict`` with a ``status`` key, and
``test_cases: list``. Exits 0 + a one-line summary on success;
exits 2 + a one-line reason on malformed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml

from hypothesize.cli.list_cmd import is_benchmark


def _validate_payload(payload: object) -> str | None:
    """Return None when valid; otherwise a short reason string."""
    if not isinstance(payload, dict):
        return "top-level YAML must be a mapping"
    if not isinstance(payload.get("hypothesis"), str):
        return "missing or non-string 'hypothesis'"
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return "missing or non-dict 'metadata'"
    if not isinstance(metadata.get("status"), str):
        return "metadata must include a string 'status'"
    if not isinstance(payload.get("test_cases"), list):
        return "missing or non-list 'test_cases'"
    return None


@click.command(name="validate")
@click.argument(
    "path",
    type=click.Path(path_type=Path, dir_okay=False, exists=False),
)
def validate_cmd(path: Path) -> None:
    """Validate the benchmark YAML at PATH."""
    p = Path(path)
    if not p.exists():
        click.echo(f"error: file not found: {p}", err=True)
        sys.exit(2)
    try:
        payload = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        click.echo(f"error: invalid YAML: {exc}", err=True)
        sys.exit(2)
    reason = _validate_payload(payload)
    if reason is not None:
        click.echo(f"error: malformed benchmark: {reason}", err=True)
        sys.exit(2)
    assert isinstance(payload, dict)
    n_cases = len(payload["test_cases"])
    click.echo(f"ok: {payload['hypothesis']} ({n_cases} test cases)")
    # We rely on is_benchmark for the predicate; surface failure if the
    # narrower check disagrees with the manual checks above.
    if not is_benchmark(payload):
        # Defensive — should be unreachable since the manual checks
        # cover the same ground.
        sys.exit(2)
