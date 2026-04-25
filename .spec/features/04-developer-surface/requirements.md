# Feature 04: CLI, Claude Code Skill, and MCP Server

## Goal

Wrap the working `hypothesize` library in a developer-facing surface a
person actually uses. Three surfaces share one runtime: a `hypothesize`
CLI for direct invocation, a Claude Code skill that orchestrates the
"complaint → discriminating benchmark" magic moment, and an MCP server
that exposes hypothesize's primitives to any MCP-aware host. Plus one
hand-crafted example (`sarcasm`) the demo runs against, and one
scaffolded example (`hotpotqa`) that demonstrates the tool's
generality without committing to a full real-dataset implementation
this session.

After this feature, a developer can: open Claude Code in their repo,
describe a complaint, and 60-90 seconds later have a YAML file of
failing test cases on disk — without ever leaving the editor. They can
also run `hypothesize run` from the terminal directly, or wire the MCP
server into Claude Desktop.

## Acceptance criteria

- A `hypothesize` console-script entry point exists in `pyproject.toml`
  pointing at `hypothesize.cli.main:cli`. After `pip install -e .`,
  `hypothesize --help` prints usage and lists the subcommands.
- `hypothesize run --config CONFIG --hypothesis TEXT [--output OUT]
  [--target-n N] [--budget N]` runs the discrimination algorithm end
  to end and writes a YAML result file. With a backend injected by
  the test harness (no live calls), the command produces a YAML that
  matches the documented schema.
- The CLI respects sensible defaults: output path
  `tests/discriminating/<slug>_<YYYY_MM_DD>.yaml`, target-n=5,
  budget=100. Defaults are documented in `--help`.
- `hypothesize list [PATH]` prints any hypothesize-generated YAML
  benchmarks found under `PATH` (default: cwd), one per line.
- `hypothesize validate PATH` reads a benchmark YAML and prints a
  one-line summary plus exit code 0 (well-formed) or 2 (malformed).
- The output YAML schema is documented in `design.md` and includes:
  the original hypothesis, run metadata (timestamp, model,
  budget_used, status), and a `test_cases` array carrying input data,
  expected behavior, and discrimination evidence.
- A Claude Code skill exists at `.claude/skills/hypothesize/SKILL.md`.
  The skill describes a workflow that orchestrates: clarify a vague
  complaint into a hypothesis, identify the user's system from a
  config in the repo, invoke the CLI, summarise the resulting test
  cases. The skill text is itself testable — automated tests assert
  that the file exists, parses as markdown, and contains every
  workflow step.
- An MCP server exists at `src/hypothesize/mcp/server.py`. It exposes
  five tools wrapping hypothesize primitives: `discover_systems`,
  `run_discrimination`, `list_benchmarks`, `read_benchmark`, and
  `formulate_hypothesis`. Tool input/output shapes are JSON-friendly
  dicts. Tests instantiate the server in-process and exercise tool
  callables directly without spinning up MCP transport.
- `examples/sarcasm/` contains a complete, runnable example: a
  `system.py` exposing `SYSTEM_PROMPT` and `make_runner(prompt=None)`
  per the prompt-factory convention, a `config.yaml`, and a
  `README.md` with copy-paste invocations. The system mirrors the
  baseline used in SMOKE_3 so the demo flow tracks validated
  behavior.
- `examples/hotpotqa/` is scaffolded: a `system.py` skeleton with
  TODO markers for the data path, a `config.yaml` template, and a
  `README.md` describing the manual download steps. Importing the
  module does not crash, and the README explicitly states that this
  example is not runnable until the user fills in the TODOs.
- `README.md` gains a Quickstart section that walks a first-time
  user through running the sarcasm example.
- Test coverage on Feature 04 code (CLI, MCP server, examples
  scaffolding) is at least 80%, measured with `pytest --cov`. Every
  test uses `MockBackend` from `tests/_fixtures/mock_backend.py`. No
  live LLM calls in this session.

## Non-goals

- Live integration tests (deferred to manual user validation after
  merge, captured as a list in `DECISIONS.md`).
- Multi-provider support. Anthropic only.
- Web dashboard, HTTP server beyond the MCP server.
- SQLite or other persistent storage. Benchmark YAMLs in git are the
  store.
- Auto-fix feature (Claude proposes the fixed prompt). Out of scope;
  may be referenced in `design.md` as future work but not built.
- Cost estimation, dry-run, or preview modes. Budget cap is the
  control; users opt in by passing `--budget`.
- Streaming progress output. CLI prints final results, not streams.
- Internationalization. English only.
- Rich terminal output beyond Click's native facilities. No
  `rich`-style spinners, live tables, or animated progress.
- HTTP and CLI adapter implementations. Still stubs from Feature 02.
- A second full real-dataset example. Only `sarcasm` is full;
  `hotpotqa` is a scaffold with TODO markers.

## Dependencies

- Feature 01 complete and merged (core discrimination algorithm,
  protocols, types).
- Feature 02 complete and merged (`AnthropicBackend`,
  `PythonModuleAdapter`, `SystemConfig`, `make_auto_alternative`).
- Rubric orientation fix complete and merged (SMOKE_3 confirms the
  end-to-end pipeline produces correctly-oriented discrimination
  results).
- All dependencies in `tech.md` already declared in
  `pyproject.toml`. No new runtime dependencies are added in this
  feature.
