# Hypothesize

Turn informal LLM failure hypotheses into minimum discriminating regression
benchmarks.

A stakeholder complains. An engineer wants to verify the complaint and
produce a targeted regression test in under a few minutes and a few
dollars of tokens. Hypothesize is built for that loop: it generates the
*minimum set* of inputs that discriminate between a current system and
a plausibly-better alternative, given a stated hypothesis. Tests have
a stated reason for existing — the hypothesis they prove.

Status: 0.1.0 (early development). See `.spec/` for the current plan.

## Quickstart

The fastest way to see hypothesize work is to run the bundled sarcasm
example.

```bash
# Install in editable mode
pip install -e ".[dev]"

# Provide your Anthropic key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# Run the example
hypothesize run --config examples/sarcasm/config.yaml
```

About 60-90 seconds and ~$0.10-$0.20 in Haiku tokens later, a YAML
file appears in `tests/discriminating/`. Each entry is an input the
baseline classifier got wrong and the rewritten alternative got right.

```bash
# Find the new benchmark file
hypothesize list .

# Sanity-check its shape
hypothesize validate tests/discriminating/<your_file>.yaml
```

For more detail, read `examples/sarcasm/README.md`. The same flow
works on your own system once you write a `config.yaml` pointing at
it.

## Surfaces

- **CLI**: `hypothesize run` is the primary command. `hypothesize
  list` and `hypothesize validate` browse and check existing
  benchmarks.
- **Claude Code skill**: `.claude/skills/hypothesize/SKILL.md`
  teaches Claude Code to orchestrate the workflow when a developer
  pastes a complaint. Magic moment: complaint → tests in 60-90s,
  without leaving the editor.
- **MCP server**: `python -m hypothesize.mcp.server` exposes
  hypothesize's primitives as MCP tools (discover_systems,
  list_benchmarks, read_benchmark, formulate_hypothesis,
  run_discrimination) so any MCP-aware host can call them.

## Examples

- `examples/sarcasm/` — full demo. Sentiment classifier with a
  deliberately weak baseline prompt, sarcasm hypothesis,
  auto-rewritten alternative.
- `examples/hotpotqa/` — scaffold for multi-hop QA. Demonstrates
  the shape; user finishes the runner body.

## Development

- `pytest tests/ -n auto -m "not live"` — full non-live suite (~3s).
- `pytest --cov=src/hypothesize` — coverage.
- `ruff check src/ tests/` — lint.
- `pytest -m live` — opt-in live integration tests; require
  `ANTHROPIC_API_KEY`.

## License

MIT
