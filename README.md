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

## Install

The PyPI distribution name is **`hypothesize-cli`**; the import name and
console script are `hypothesize`.

**With pip:**

```bash
pip install hypothesize-cli
hypothesize setup
```

**With uvx (no permanent install):**

```bash
uvx --from hypothesize-cli hypothesize setup
```

If you don't have `uv` yet: `pip install uv`.

The setup wizard will:

- Configure your Anthropic API key (written to `~/.config/hypothesize/.env`
  with mode `0600`)
- Install the Claude Code skill if `claude` is on your PATH
- Register the MCP server with Claude Desktop if its config directory is
  present

You can skip any step. Re-run `hypothesize setup` anytime to reconfigure.
For CI use:

```bash
hypothesize setup \
  --non-interactive \
  --api-key sk-ant-... \
  --skip-claude-code \
  --skip-claude-desktop
```

## Quickstart

After setup, try the bundled sarcasm example:

```bash
hypothesize run \
  --config examples/sarcasm/config.yaml \
  --hypothesis "the sentiment classifier mislabels sarcastic positive text"
```

About 60-90 seconds and ~$0.10-$0.20 in Haiku tokens later, a YAML
file appears in `tests/discriminating/`. Each entry is an input the
baseline classifier got wrong and the rewritten alternative got right.

```bash
hypothesize list .
hypothesize validate tests/discriminating/<your_file>.yaml
```

For more detail, read `examples/sarcasm/README.md`. The same flow
works on your own system once you write a `config.yaml` pointing at
it.

In Claude Code, just paste a complaint:

> My classifier is mislabeling sarcastic reviews as positive.

The hypothesize skill will discover your system, run the
discrimination, and write the regression suite to your repo.

## Surfaces

- **CLI**: `hypothesize run` is the primary command. `hypothesize setup`
  configures your environment. `hypothesize list` and `hypothesize
  validate` browse and check existing benchmarks.
- **Claude Code skill**: bundled with the package and installable via
  `hypothesize setup`. Teaches Claude Code to orchestrate the workflow
  when a developer pastes a complaint.
- **MCP server**: `python -m hypothesize.mcp.server` exposes
  hypothesize's primitives as MCP tools (discover_systems,
  list_benchmarks, read_benchmark, formulate_hypothesis,
  run_discrimination). `hypothesize setup` registers it with Claude
  Desktop.

## Examples

- `examples/sarcasm/` — full demo. Sentiment classifier with a
  deliberately weak baseline prompt, sarcasm hypothesis,
  auto-rewritten alternative.
- `examples/hotpotqa/` — multi-hop QA over a curated 50-item slice.
- `examples/acme_support/` — emoji-policy filter on a support chatbot
  (programmatic judge).

## Development

Editable install (for contributors):

```bash
git clone https://github.com/gkuwanto/hypothesize
cd hypothesize
pip install -e ".[dev]"
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

Test commands:

- `pytest tests/ -n auto -m "not live"` — full non-live suite (~3s).
- `pytest --cov=src/hypothesize` — coverage.
- `ruff check src/ tests/` — lint.
- `pytest -m live` — opt-in live integration tests; require
  `ANTHROPIC_API_KEY`.

## License

MIT
