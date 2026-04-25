"""Body of the ``hypothesize run`` Click command.

Wires the user-facing flags (``--config``, ``--hypothesis``,
``--target-n``, ``--budget``, ``--output``, ``--backend``) into the
shared :func:`hypothesize.cli.runner.run_discrimination` entry point,
serialises the result via :mod:`hypothesize.cli.output`, and maps the
five distinct outcomes onto the documented exit-code table.

Exit codes:

- 0: ``status="ok"`` — discrimination succeeded.
- 1: ``status="insufficient_evidence"`` — algorithm returned cleanly
  but with too few discriminating cases. YAML still written.
- 2: config/invocation error. No YAML written.
- 3: runtime error from a runner / backend. No YAML written.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import click
from pydantic import ValidationError

from hypothesize.adapters.errors import (
    AutoAlternativeUnavailable,
    BudgetExhausted,
)
from hypothesize.cli.config import RunConfig, load_run_config
from hypothesize.cli.output import result_to_yaml
from hypothesize.cli.runner import run_discrimination
from hypothesize.core.llm import LLMBackend
from hypothesize.core.types import Budget, Hypothesis


class _ScriptedBackend:
    """LLM backend that replays a list of pre-recorded response strings.

    Powers the ``--backend=mock --mock-script PATH`` flag. The class is
    private to the CLI module: production code uses ``AnthropicBackend``.
    Mirrors the ``LLMBackend`` protocol — one async ``complete``.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._cursor = 0

    async def complete(self, messages: list[dict], **kwargs: object) -> str:
        if self._cursor >= len(self._responses):
            raise IndexError(
                f"--mock-script exhausted: "
                f"{len(self._responses)} response(s) scripted, "
                f"call #{self._cursor + 1} requested."
            )
        out = self._responses[self._cursor]
        self._cursor += 1
        return out


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug[:max_len] or "hypothesis"


def _default_output_path(hypothesis_text: str) -> Path:
    today = datetime.now(UTC).strftime("%Y_%m_%d")
    return (
        Path("tests/discriminating")
        / f"{_slugify(hypothesis_text)}_{today}.yaml"
    )


def _build_backend(
    backend_kind: str,
    mock_script: Path | None,
    config: RunConfig,
) -> LLMBackend:
    if backend_kind == "mock":
        if mock_script is None:
            raise click.UsageError(
                "--backend=mock requires --mock-script PATH"
            )
        responses = json.loads(Path(mock_script).read_text())
        if not isinstance(responses, list):
            raise click.UsageError(
                "--mock-script must contain a JSON list of strings"
            )
        return _ScriptedBackend(responses=[str(r) for r in responses])
    # Default: real Anthropic backend. Load .env so users who follow
    # the documented "set ANTHROPIC_API_KEY in .env" instruction get
    # picked up automatically. Imports are lazy so --backend=mock
    # paths never touch dotenv or AsyncAnthropic.
    from dotenv import load_dotenv

    from hypothesize.llm.anthropic import AnthropicBackend

    load_dotenv()
    key_env = config.llm.api_key_env or "ANTHROPIC_API_KEY"
    if not os.environ.get(key_env):
        raise click.UsageError(
            f"{key_env} is not set. Add it to .env at the repo root "
            f"(ANTHROPIC_API_KEY=sk-ant-...) or export it in your "
            f"shell, then re-run."
        )
    return AnthropicBackend(config=config.llm)


def _resolve_hypothesis(
    config: RunConfig, hypothesis_flag: str | None
) -> Hypothesis:
    if hypothesis_flag is not None:
        return Hypothesis(text=hypothesis_flag)
    if config.hypothesis is not None:
        return config.hypothesis
    raise click.UsageError(
        "no hypothesis: pass --hypothesis or add a 'hypothesis' block "
        "to the config YAML."
    )


@click.command(name="run")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to RunConfig YAML.",
)
@click.option(
    "--hypothesis",
    "-H",
    "hypothesis_text",
    type=str,
    default=None,
    help="Override the hypothesis text from the config.",
)
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Output YAML path. Default: tests/discriminating/<slug>_<date>.yaml.",
)
@click.option(
    "--target-n",
    "-n",
    type=int,
    default=None,
    help="Target number of discriminating cases (default: 5 or YAML's defaults.target_n).",
)
@click.option(
    "--budget",
    "-b",
    type=int,
    default=None,
    help="Max LLM calls (default: 100 or YAML's budget.max_llm_calls).",
)
@click.option(
    "--backend",
    "backend_kind",
    type=click.Choice(["anthropic", "mock"]),
    default="anthropic",
    help="LLM backend (mock is for tests; requires --mock-script).",
)
@click.option(
    "--mock-script",
    "mock_script",
    type=click.Path(path_type=Path),
    default=None,
    help="JSON file containing scripted responses for --backend=mock.",
)
def run_cmd(
    config_path: Path,
    hypothesis_text: str | None,
    output_path: Path | None,
    target_n: int | None,
    budget: int | None,
    backend_kind: str,
    mock_script: Path | None,
) -> None:
    """Run discrimination against a system config."""
    # Step 1: load config
    try:
        config = load_run_config(config_path)
    except FileNotFoundError as exc:
        click.echo(f"error: config not found: {exc}", err=True)
        sys.exit(2)
    except ValidationError as exc:
        click.echo(f"error: config validation failed:\n{exc}", err=True)
        sys.exit(2)

    # Step 2: resolve hypothesis (CLI flag wins over YAML)
    try:
        hypothesis = _resolve_hypothesis(config, hypothesis_text)
    except click.UsageError as exc:
        click.echo(f"error: {exc.message}", err=True)
        sys.exit(2)

    effective_target_n = (
        target_n if target_n is not None else config.defaults.target_n
    )
    effective_min_required = config.defaults.min_required
    effective_budget_max = (
        budget if budget is not None else config.budget.max_llm_calls
    )
    budget_obj = Budget(max_llm_calls=effective_budget_max)

    # Step 3: build backend
    try:
        backend = _build_backend(backend_kind, mock_script, config)
    except click.UsageError as exc:
        click.echo(f"error: {exc.message}", err=True)
        sys.exit(2)

    # Step 4: run discrimination
    try:
        result = asyncio.run(
            run_discrimination(
                config=config,
                hypothesis=hypothesis,
                target_n=effective_target_n,
                min_required=effective_min_required,
                budget=budget_obj,
                backend=backend,
            )
        )
    except (AutoAlternativeUnavailable, BudgetExhausted) as exc:
        click.echo(f"error: {type(exc).__name__}: {exc}", err=True)
        sys.exit(2)
    except FileNotFoundError as exc:
        click.echo(f"error: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001 — top-level runtime error
        click.echo(f"runtime error: {type(exc).__name__}: {exc}", err=True)
        sys.exit(3)

    # Step 5: serialise and write
    out_path = output_path or _default_output_path(hypothesis.text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_text = result_to_yaml(
        result=result,
        hypothesis=hypothesis,
        config_name=config.name,
        model_name=config.llm.default_model,
        target_n=effective_target_n,
        budget_max=effective_budget_max,
    )
    out_path.write_text(yaml_text)

    if result.status == "ok":
        click.echo(
            f"wrote {len(result.test_cases)} test case(s) to {out_path}"
        )
        sys.exit(0)
    else:
        assert result.insufficient is not None
        click.echo(
            f"insufficient_evidence: {result.insufficient.discriminating_found} "
            f"discriminating case(s) found ({result.insufficient.reason}). "
            f"YAML still written to {out_path}",
            err=True,
        )
        sys.exit(1)
