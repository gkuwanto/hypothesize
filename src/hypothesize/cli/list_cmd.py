"""``hypothesize list`` — find existing benchmark YAMLs in a directory.

A YAML file is considered a hypothesize benchmark when its top-level
dict carries: ``hypothesis: str``, ``metadata: dict`` containing a
``status`` key, and ``test_cases: list``. Anything else (or any file
that fails to parse) is silently skipped.

Output is one line per match, tab-separated:
``<path>\\t<hypothesis>\\t<status>\\t<n_test_cases>``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import yaml


def is_benchmark(payload: Any) -> bool:
    """Return True iff ``payload`` matches the documented benchmark shape."""
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("hypothesis"), str)
        and isinstance(payload.get("metadata"), dict)
        and isinstance(payload["metadata"].get("status"), str)
        and isinstance(payload.get("test_cases"), list)
    )


def find_benchmarks(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Walk ``root`` for YAML files that match the benchmark shape."""
    matches: list[tuple[Path, dict[str, Any]]] = []
    for yaml_path in sorted(root.rglob("*.yaml")):
        try:
            raw = yaml.safe_load(yaml_path.read_text())
        except yaml.YAMLError:
            continue
        if is_benchmark(raw):
            matches.append((yaml_path, raw))
    return matches


@click.command(name="list")
@click.argument(
    "path",
    type=click.Path(path_type=Path, file_okay=False, exists=False),
    default=".",
    required=False,
)
def list_cmd(path: Path) -> None:
    """List benchmark YAMLs under PATH (default: cwd)."""
    root = Path(path)
    if not root.exists():
        # Empty output, exit 0 — same behavior as "no matches".
        return
    for yaml_path, payload in find_benchmarks(root):
        hypothesis = payload["hypothesis"]
        status = payload["metadata"]["status"]
        n_cases = len(payload["test_cases"])
        click.echo(f"{yaml_path}\t{hypothesis}\t{status}\t{n_cases}")
