# Technical Stack

## Runtime

- Python 3.11 or newer. No support for earlier versions.
- Async where natural (LLM calls are async-first).

## Dependencies

These are the allowed top-level dependencies. Do not add others without
updating this file and `pyproject.toml` in the same commit.

- `anthropic` — Anthropic API client
- `pydantic` (v2) — typed models
- `click` — CLI framework
- `pyyaml` — config file parsing
- `httpx` — HTTP adapter
- `datasets` — HuggingFace dataset loading for examples
- `mcp` — MCP server framework

Dev dependencies:

- `pytest`, `pytest-cov`, `pytest-timeout`, `pytest-asyncio`
- `ruff`
- `mypy` (optional, not blocking)

## LLM choices

- Default model for hypothesis decomposition and candidate generation:
  `claude-opus-4-7` (the most capable model available; this is the
  reasoning-heavy step).
- Default model for rubric-based judging: `claude-haiku-4-5-20251001`
  (cheap, parallel, good enough for structured rubric checks).
- Users can override via config.

## Versioning

- Semantic versioning. Start at `0.1.0`.
- The hackathon demo ships as `0.1.0`.
