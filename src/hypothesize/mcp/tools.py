"""MCP tool bodies.

Plain async functions. Each tool returns a JSON-serialisable dict (or
list of dicts), takes plain inputs, and is testable in isolation.

The MCP server in :mod:`hypothesize.mcp.server` wraps each function in
a ``FastMCP`` tool registration; the server registrations do not pass
the optional ``backend`` argument that several of these accept.
``backend`` is a private testing hook: production code paths use the
default ``AnthropicBackend``, and tests inject a ``MockBackend``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from hypothesize.cli.config import load_run_config
from hypothesize.cli.list_cmd import find_benchmarks
from hypothesize.cli.output import result_to_dict
from hypothesize.cli.runner import run_discrimination as _cli_run_discrimination
from hypothesize.core.json_extract import parse_json_response
from hypothesize.core.llm import LLMBackend
from hypothesize.core.types import Budget, Hypothesis
from hypothesize.mcp.prompts import formulate_hypothesis_messages


def _default_anthropic_backend(config_: Any = None) -> Any:
    """Build the default ``AnthropicBackend`` for tool callers.

    Loads ``.env`` so users who follow the documented "set
    ANTHROPIC_API_KEY in .env" instruction get picked up
    automatically, and raises a clear error before instantiating the
    SDK if the key is still missing. The chain helper checks the
    project's .env (walking up from cwd) and then the canonical
    ``hypothesize setup`` location at ~/.config/hypothesize/.env.
    Imports are lazy so the test paths that supply their own
    ``backend`` never touch dotenv.
    """
    from hypothesize.llm.anthropic import AnthropicBackend
    from hypothesize.setup.env import load_dotenv_chain

    load_dotenv_chain()
    key_env = (
        (config_.llm.api_key_env if config_ is not None else None)
        or "ANTHROPIC_API_KEY"
    )
    if not os.environ.get(key_env):
        raise RuntimeError(
            f"{key_env} is not set. Run `hypothesize setup` to write it "
            f"to ~/.config/hypothesize/.env, or export it in the MCP "
            f"server's environment."
        )
    if config_ is not None:
        return AnthropicBackend(config=config_.llm)
    return AnthropicBackend()


# ----------------------------------------------------------------------
# discover_systems
# ----------------------------------------------------------------------


async def discover_systems(repo_path: str) -> list[dict[str, Any]]:
    """Find candidate ``config.yaml`` files under ``repo_path``.

    Search paths: top level, ``examples/<name>/``, and
    ``hypothesize/<name>/``. Files that fail ``RunConfig`` validation
    are silently skipped — the tool reports candidates, not errors.
    """
    root = Path(repo_path)
    if not root.exists():
        return []
    candidates: list[Path] = []
    top_level = root / "config.yaml"
    if top_level.is_file():
        candidates.append(top_level)
    for parent_name in ("examples", "hypothesize"):
        parent = root / parent_name
        if not parent.is_dir():
            continue
        for child in sorted(parent.iterdir()):
            if not child.is_dir():
                continue
            cfg = child / "config.yaml"
            if cfg.is_file():
                candidates.append(cfg)

    found: list[dict[str, Any]] = []
    for cfg_path in candidates:
        try:
            config = load_run_config(cfg_path)
        except (ValidationError, FileNotFoundError, yaml.YAMLError):
            continue
        found.append(
            {
                "path": str(cfg_path),
                "name": config.name,
                "adapter": config.current.adapter,
            }
        )
    return found


# ----------------------------------------------------------------------
# list_benchmarks
# ----------------------------------------------------------------------


async def list_benchmarks(repo_path: str) -> list[dict[str, Any]]:
    """Return summary entries for every hypothesize benchmark under ``repo_path``."""
    root = Path(repo_path)
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for path, payload in find_benchmarks(root):
        out.append(
            {
                "path": str(path),
                "hypothesis": payload["hypothesis"],
                "status": payload["metadata"]["status"],
                "n_test_cases": len(payload["test_cases"]),
            }
        )
    return out


# ----------------------------------------------------------------------
# read_benchmark
# ----------------------------------------------------------------------


async def read_benchmark(path: str) -> dict[str, Any]:
    """Load a benchmark YAML and return it as a dict."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Benchmark not found: {p}")
    raw = yaml.safe_load(p.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Benchmark YAML must be a mapping: {p}")
    return raw


# ----------------------------------------------------------------------
# formulate_hypothesis
# ----------------------------------------------------------------------


async def formulate_hypothesis(
    complaint: str,
    context: dict[str, Any] | None = None,
    backend: LLMBackend | None = None,
) -> dict[str, Any]:
    """Convert a vague complaint into a structured hypothesis dict.

    With ``backend=None``, constructs a fresh ``AnthropicBackend``;
    tests pass a ``MockBackend`` directly.
    """
    if backend is None:
        backend = _default_anthropic_backend()

    messages = formulate_hypothesis_messages(complaint, context or {})
    raw = await backend.complete(messages)
    payload = parse_json_response(raw)
    if not isinstance(payload, dict):
        raise ValueError(
            "formulate_hypothesis: LLM response did not parse to a JSON object"
        )
    text = payload.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError(
            "formulate_hypothesis: response missing or non-string 'text' field"
        )
    refs = payload.get("context_refs", [])
    if not isinstance(refs, list):
        refs = []
    return {"text": text, "context_refs": [str(r) for r in refs]}


# ----------------------------------------------------------------------
# run_discrimination
# ----------------------------------------------------------------------


async def run_discrimination(
    config_path: str,
    hypothesis: str,
    target_n: int = 5,
    budget: int = 100,
    backend: LLMBackend | None = None,
) -> dict[str, Any]:
    """Run the same code path the CLI does; return the YAML-shaped dict."""
    config = load_run_config(Path(config_path))

    if backend is None:
        backend = _default_anthropic_backend(config_=config)

    hyp = Hypothesis(text=hypothesis)
    budget_obj = Budget(max_llm_calls=budget)
    result = await _cli_run_discrimination(
        config=config,
        hypothesis=hyp,
        target_n=target_n,
        min_required=config.defaults.min_required,
        budget=budget_obj,
        backend=backend,
    )
    return result_to_dict(
        result=result,
        hypothesis=hyp,
        config_name=config.name,
        model_name=config.llm.default_model,
        target_n=target_n,
        budget_max=budget,
        generated_at=datetime.now(UTC),
    )
