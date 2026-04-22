# File Structure Rules

## Directory layout

- `src/hypothesize/core/` — pure domain logic, no I/O, no LLM calls at module
  scope. All LLM access goes through an injected backend. Testable offline.
- `src/hypothesize/adapters/` — external integrations. Python module adapter,
  HTTP adapter, CLI adapter. Each implements the SystemAdapter protocol.
- `src/hypothesize/llm/` — real LLM backends (Anthropic). Mock backend lives
  in `tests/` not `src/`.
- `src/hypothesize/cli/` — Click-based CLI entry point.
- `src/hypothesize/mcp/` — MCP server exposing hypothesize tools.
- `src/hypothesize/skill/` — assets for the Claude Code skill (SKILL.md and
  any helper scripts).
- `tests/` — mirrors `src/hypothesize/` layout. `tests/core/test_*.py`
  matches `src/hypothesize/core/*.py`.
- `examples/<dataset>/` — self-contained example: a `system.py`, a
  `config.yaml`, and a short `README.md` per dataset.
- `.spec/` — planning artifacts. Never imported by code.

## Naming

- Modules: `snake_case`. Types: `PascalCase`. Functions: `snake_case`.
- Test files: `test_<module>.py`. Test functions: `test_<behavior>`.
- No abbreviations in public names. Internal helpers may abbreviate.

## Import rules

- `core/` may not import from `adapters/`, `llm/`, `cli/`, or `mcp/`.
- `adapters/` may import from `core/` only.
- `cli/` and `mcp/` may import from anything in `src/hypothesize/`.
- No circular imports. Enforced by a linter check.
