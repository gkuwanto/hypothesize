# Tasks: Feature 04 — CLI, Skill, MCP, Examples

Conventions match Features 01 and 02: TDD per task, mocks-only, one
commit per task with the task id in the subject. All tests use
`MockBackend` from `tests/_fixtures/mock_backend.py`. No live LLM
calls in this session.

## Task 4.1: CLI scaffolding and Click group

- Status: done
- Depends: none
- Files:
  - `src/hypothesize/cli/__init__.py` (new)
  - `src/hypothesize/cli/main.py` (new)
  - `tests/cli/__init__.py` (new)
  - `tests/cli/test_main.py` (new)
  - `pyproject.toml` (verify entry point only — no edit if already
    correct)
- Acceptance:
  - `hypothesize.cli.main:cli` is a `click.Group`. Importing it has
    no side effects.
  - The group declares `--version` and `--help`. `--version` prints
    `hypothesize, version <hypothesize.__version__>`.
  - Three subcommands are registered as no-op stubs that print
    `"<subcommand> not implemented yet"` and exit 0:
    `run`, `list`, `validate`.
  - `pyproject.toml` already exposes `hypothesize =
    "hypothesize.cli.main:cli"` under `[project.scripts]`. Verify
    this points at the right symbol; the bootstrap declared
    `hypothesize.cli.main:main` which does not exist yet — fix it
    to `:cli` if needed.
  - Tests use `click.testing.CliRunner`. At least 4 tests:
    `--version`, `--help` lists subcommands, each subcommand stub
    prints its placeholder.
  - `ruff check src/ tests/` clean.

## Task 4.2: `hypothesize run` end-to-end (with MockBackend)

- Status: done
- Depends: 4.1
- Files:
  - `src/hypothesize/cli/config.py` (new — `RunConfig` model + loader)
  - `src/hypothesize/cli/runner.py` (new — backend/runner
    construction)
  - `src/hypothesize/cli/output.py` (new — `DiscriminationResult` ->
    YAML)
  - `src/hypothesize/cli/run.py` (new — Click command body)
  - `src/hypothesize/cli/main.py` (replace stub with real run
    registration)
  - `tests/cli/test_config.py` (new)
  - `tests/cli/test_runner.py` (new)
  - `tests/cli/test_output.py` (new)
  - `tests/cli/test_run.py` (new)
  - `tests/_fixtures/cli_fixtures/` (new — example RunConfig YAML,
    scripted MockBackend response files)
- Acceptance:
  - `RunConfig` is a pydantic v2 model with `extra="forbid"`. It
    composes `SystemConfig` (current/alternative), `Hypothesis`,
    `AnthropicConfig`, `Budget`, plus a `defaults` block carrying
    `target_n: int = 5` and `min_required: int = 3`.
  - `RunConfig.alternative.adapter == "auto"` is accepted as a
    sentinel. The runner module resolves it via
    `make_auto_alternative`.
  - `load_run_config(path)` reads YAML and constructs the model.
    Pydantic errors propagate as `pydantic.ValidationError`.
  - `cli/runner.py` exposes `run_discrimination(config, hypothesis,
    target_n, budget, backend) -> DiscriminationResult`. The
    `backend` argument lets tests inject a `MockBackend`.
  - `cli/output.py` exposes `result_to_yaml(result, hypothesis,
    config_name, model_name) -> str` producing the schema in
    `design.md`.
  - `cli/run.py` adds a `--backend [anthropic|mock]` option and a
    `--mock-script PATH` companion. With `--backend=mock`, the
    Click command loads the JSON script, builds a `MockBackend`,
    and threads it through `run_discrimination`. Default backend
    value is `anthropic`.
  - Exit codes match the design table: 0 ok, 1 insufficient
    evidence, 2 config errors, 3 runner errors.
  - Tests cover (at least): config validation success/failure,
    runner builds correct runners for `auto` alternative and for an
    explicit alternative, output YAML matches a snapshot, the full
    CLI run with `--backend=mock` writes a YAML file the tests can
    re-read.
  - At least 12 tests across these files. ≥80% coverage on the new
    modules.
  - `ruff check` clean.

## Task 4.3: `hypothesize list` and `hypothesize validate`

- Status: done
- Depends: 4.2
- Files:
  - `src/hypothesize/cli/list_cmd.py` (new — module name avoids
    shadowing `list`)
  - `src/hypothesize/cli/validate.py` (new)
  - `src/hypothesize/cli/main.py` (register the two commands)
  - `tests/cli/test_list_cmd.py` (new)
  - `tests/cli/test_validate.py` (new)
- Acceptance:
  - `hypothesize list [PATH]` walks `PATH` (default cwd) for `.yaml`
    files. A file is considered a hypothesize benchmark when its
    top-level dict carries the keys `hypothesis` (str), `metadata`
    (dict containing `status`), and `test_cases` (list).
  - Output is one line per benchmark: tab-separated columns
    `<path>\t<hypothesis>\t<status>\t<n_test_cases>`. Empty output
    when no matches.
  - `hypothesize validate PATH` loads PATH and checks the same
    shape. Exit 0 + one-line summary on success ("ok: <hypothesis>
    (N test cases)"); exit 2 + reason on malformed.
  - At least 6 tests: list with zero / one / many matches, list
    skips non-benchmark YAMLs, validate ok, validate malformed
    (multiple shapes).

## Task 4.4: `examples/sarcasm/` — full

- Status: done
- Depends: 4.2 (so the config can be validated by the loader)
- Files:
  - `examples/sarcasm/system.py` (new)
  - `examples/sarcasm/config.yaml` (new)
  - `examples/sarcasm/README.md` (new)
  - `tests/examples/__init__.py` (new)
  - `tests/examples/test_sarcasm.py` (new)
- Acceptance:
  - `system.py` exposes `SYSTEM_PROMPT: str`,
    `make_runner(prompt: str | None = None)`, and `run =
    make_runner()`.
  - The baseline `SYSTEM_PROMPT` is a deliberately weak one-line
    classifier instruction (no sarcasm guidance).
  - The runner returned by `make_runner` accepts `{"text": str}` and
    returns `{"sentiment": "positive" | "negative"}`. Internally it
    calls Anthropic via the `AnthropicBackend` — but the module
    accepts an injectable backend as a kwarg or env-driven hook so
    tests can replace it with a `MockBackend`.
  - `config.yaml` validates against `RunConfig` and points at
    `examples/sarcasm/system.py` with `alternative.adapter: auto`.
  - `README.md` walks a first-time user through running the
    example: dependencies installed, `.env` populated,
    `hypothesize run --config examples/sarcasm/config.yaml`.
  - Tests cover (without making LLM calls): the module imports
    cleanly, `make_runner` returns a callable, the runner's input
    schema is documented and exercised against a mock, and
    `RunConfig` validates the YAML.

## Task 4.5: `examples/hotpotqa/` — scaffold

- Status: done
- Depends: 4.2
- Files:
  - `examples/hotpotqa/system.py` (new — skeleton)
  - `examples/hotpotqa/config.yaml` (new — template)
  - `examples/hotpotqa/README.md` (new — manual setup
    instructions)
  - `tests/examples/test_hotpotqa.py` (new)
- Acceptance:
  - `system.py` imports cleanly. `make_runner` is defined; calling
    its returned runner raises `NotImplementedError("TODO: ...")`.
  - `config.yaml` is syntactically valid YAML and validates against
    `RunConfig` (using the placeholder `system.py` module path).
  - `README.md` lists exact steps to make the example runnable: HF
    dataset download, fields to populate in `system.py`.
  - Tests: import succeeds, runner raises `NotImplementedError`
    with a TODO message, README mentions the required setup.

## Task 4.6: MCP server scaffolding

- Status: pending
- Depends: 4.2 (depends on `cli/runner.py`'s `run_discrimination`
  function, which the `run_discrimination` MCP tool reuses)
- Files:
  - `src/hypothesize/mcp/__init__.py` (new)
  - `src/hypothesize/mcp/server.py` (new)
  - `src/hypothesize/mcp/prompts.py` (new — formulate_hypothesis
    prompt)
  - `tests/mcp/__init__.py` (new)
  - `tests/mcp/test_server.py` (new)
- Acceptance:
  - `mcp/server.py` constructs a `FastMCP("hypothesize")`. Tool
    registration is split out so tests can introspect the tool list.
  - `main()` calls `server.run()` and is wired up under
    `if __name__ == "__main__": main()`.
  - Tool registrations exist for: `discover_systems`,
    `list_benchmarks`, `read_benchmark`, `formulate_hypothesis`,
    `run_discrimination`. Tool bodies delegate to functions in
    `mcp/tools.py` (built in 4.7).
  - `tests/mcp/test_server.py` asserts: server constructs without
    errors, the five tool names are registered, `main` is callable
    (no exception when imported).
  - No live LLM calls; tests do not call the tool bodies in this
    task.

## Task 4.7: MCP tool implementations

- Status: pending
- Depends: 4.6
- Files:
  - `src/hypothesize/mcp/tools.py` (new)
  - `tests/mcp/test_tools.py` (new)
- Acceptance:
  - `tools.discover_systems(repo_path)` walks `repo_path` for
    `config.yaml` files at top level, in `examples/<name>/`, and in
    `hypothesize/<name>/`. Returns a list of `{"path", "name",
    "adapter"}` dicts. Skips files that fail `RunConfig`
    validation.
  - `tools.list_benchmarks(repo_path)` reuses the `cli/list_cmd.py`
    walker. Returns `{"path", "hypothesis", "status",
    "n_test_cases"}` per match.
  - `tools.read_benchmark(path)` loads a YAML, returns the dict.
    Raises `FileNotFoundError` on missing file.
  - `tools.formulate_hypothesis(complaint, context, backend)` calls
    `backend.complete` with the prompt from `mcp/prompts.py`,
    parses with `parse_json_response`, validates the shape
    `{"text": str, "context_refs": list[str]}`, returns it. With a
    `MockBackend` injected, tests assert exact behavior.
  - `tools.run_discrimination(config_path, hypothesis, target_n,
    budget, backend)` re-uses `cli.runner.run_discrimination` and
    serialises the result via `cli.output.result_to_yaml` so MCP
    callers get the same payload shape as CLI users (parsed back
    from YAML to a dict).
  - At least 10 tests across the file. ≥80% coverage on
    `mcp/tools.py`.
  - All tests use mocked backends; no live calls.

## Task 4.8: Claude Code skill

- Status: pending
- Depends: 4.2 (the SKILL.md references CLI invocations that must
  work)
- Files:
  - `.claude/skills/hypothesize/SKILL.md` (new)
  - `tests/test_skill.py` (new)
- Acceptance:
  - `SKILL.md` exists at the spec'd path, with the content
    described in `design.md`'s Appendix A. Iterate on the wording
    while keeping every workflow step present.
  - Tests assert: file exists, parses as markdown (treating any
    text as valid markdown is enough — assert that `# hypothesize`
    appears as a top-level heading and that `## Workflow`, `##
    When to invoke`, and `## Example invocations` sections exist),
    SKILL.md mentions the `hypothesize run` invocation pattern, no
    placeholder TODOs.
  - At least 4 assertions in the test file.

## Task 4.9: README Quickstart section

- Status: pending
- Depends: 4.4
- Files:
  - `README.md` (edit — add Quickstart section)
- Acceptance:
  - README gains a `## Quickstart` section under the existing top-
    level header. The section walks through:
    - `pip install -e .[dev]`
    - copying `.env.example` to `.env` and setting
      `ANTHROPIC_API_KEY`
    - running `hypothesize run --config
      examples/sarcasm/config.yaml`
    - inspecting the resulting YAML
  - The Quickstart points at `examples/sarcasm/README.md` for more
    detail.
  - No new tests required (text-only change).

## Task 4.10: Feature 04 review pass

- Status: pending
- Depends: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9
- Files:
  - `DECISIONS.md` (append entry)
  - `.spec/features/04-developer-surface/tasks.md` (mark all done)
- Acceptance:
  - Re-read `requirements.md`. Tick every acceptance criterion in
    a review table.
  - Run `pytest tests/ -n auto -m "not live"`. All green.
  - Run `pytest --cov=src/hypothesize`. Confirm overall coverage
    ≥80% and Feature-04 modules ≥80%.
  - Run `ruff check src/ tests/`. Clean.
  - Verify `hypothesize --help` works in the activated venv.
  - Append a `DECISIONS.md` entry summarising what shipped, what
    deviated from `design.md` (if anything), and the manual
    validation steps the user should perform after merge:
    - `pip install -e .[dev]` and confirm `hypothesize --help`
      runs.
    - Set `ANTHROPIC_API_KEY` in `.env`.
    - `hypothesize run --config examples/sarcasm/config.yaml
      --hypothesis "the sentiment classifier mislabels sarcastic
      positive text"` produces a populated YAML in
      `tests/discriminating/`.
    - In Claude Code: paste a sarcasm complaint and verify the
      skill triggers.
    - Start the MCP server (`python -m hypothesize.mcp.server`)
      and exercise one tool via an MCP client.
