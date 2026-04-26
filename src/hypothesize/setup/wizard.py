"""Interactive and non-interactive orchestration for ``hypothesize setup``.

The :func:`run_setup` entry point handles both modes from a single
options object: in interactive mode it prompts via ``click``; in
non-interactive mode it consumes the options directly. Either way it
delegates each step to a single helper in :mod:`detect`, :mod:`env`,
:mod:`install_skill`, or :mod:`install_mcp` so the orchestration logic
stays small and testable.

Security: nothing in this module ever prints, logs, or otherwise emits
the API key value. Only the fingerprint is shown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import click

from hypothesize.setup import detect, env, install_mcp, install_skill


@dataclass
class SetupOptions:
    """All decisions the wizard needs to run.

    In interactive mode this is built incrementally as the user answers
    prompts. In non-interactive mode the CLI populates it from flags.
    """

    interactive: bool = True
    api_key: str | None = None
    skip_claude_code: bool = False
    skip_claude_desktop: bool = False
    skip_verification: bool = True
    config_dir: Path | None = None
    overwrite_existing_skill: bool = False
    overwrite_existing_mcp: bool = False


@dataclass
class StepOutcome:
    """Per-step result the wizard prints in its summary."""

    label: str
    status: str  # "done" | "skipped" | "failed"
    detail: str = ""


@dataclass
class SetupResult:
    """Aggregated result of the wizard run, used by tests and the summary."""

    outcomes: list[StepOutcome] = field(default_factory=list)
    env_path: Path | None = None
    skill_path: Path | None = None
    mcp_config_path: Path | None = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_setup(
    options: SetupOptions,
    *,
    output: click.utils.LazyFile | None = None,
) -> SetupResult:
    """Execute the setup flow described by ``options``.

    Returns a :class:`SetupResult` describing each step. The wizard
    prints progress and a final summary. The caller (the CLI command)
    decides the process exit code based on the result.
    """
    result = SetupResult()
    try:
        if options.interactive:
            _print_welcome()
        _step_api_key(options, result)
        _step_claude_code(options, result)
        _step_claude_desktop(options, result)
        _step_verification(options, result)
    except click.Abort:
        # User aborted with Ctrl-C. Print a clean message and re-raise so
        # the CLI exits non-zero.
        click.echo("\nSetup aborted. Re-run `hypothesize setup` to retry.")
        raise

    _print_summary(result)
    return result


# ---------------------------------------------------------------------------
# Step 1 — welcome banner
# ---------------------------------------------------------------------------


def _print_welcome() -> None:
    click.echo("Hypothesize setup")
    click.echo("")
    click.echo("This wizard will:")
    click.echo("  1. Configure your Anthropic API key")
    click.echo(
        "  2. Optionally install the Claude Code skill (if Claude Code is detected)"
    )
    click.echo(
        "  3. Optionally register the MCP server with Claude Desktop (if detected)"
    )
    click.echo("")
    click.echo(
        "You can skip any step. Re-run `hypothesize setup` anytime to reconfigure."
    )
    click.echo("")
    if click.confirm("Continue?", default=True):
        return
    raise click.Abort()


# ---------------------------------------------------------------------------
# Step 2 — API key
# ---------------------------------------------------------------------------


def _resolve_env_path(options: SetupOptions) -> Path:
    if options.config_dir is not None:
        return options.config_dir / ".env"
    return env.default_env_path()


def _candidate_env_files(target_env_path: Path) -> list[Path]:
    """Return the search list for an existing key, in the documented order.

    1. ``.env`` in the current working directory.
    2. ``~/.config/hypothesize/.env`` (or the user's ``--config-dir``).
    """
    candidates: list[Path] = []
    cwd_env = Path.cwd() / ".env"
    candidates.append(cwd_env)
    if target_env_path != cwd_env:
        candidates.append(target_env_path)
    return candidates


def _step_api_key(options: SetupOptions, result: SetupResult) -> None:
    target = _resolve_env_path(options)
    result.env_path = target

    if not options.interactive:
        if not options.api_key:
            raise click.UsageError(
                "API key required for non-interactive setup. Provide via "
                "--api-key or set ANTHROPIC_API_KEY env var."
            )
        if not env.is_valid_api_key(options.api_key):
            raise click.UsageError(
                "Provided --api-key does not look like a valid Anthropic key "
                "(must start with 'sk-ant-' and be at least 30 chars)."
            )
        env.write_api_key(target, options.api_key.strip())
        result.outcomes.append(
            StepOutcome("API key configured", "done", str(target))
        )
        return

    click.echo("")
    click.echo("Step 1: API key")
    existing = env.detect_existing_key(env_files=_candidate_env_files(target))
    if existing is not None:
        click.echo(
            f"  Found existing key from {existing.source} "
            f"(key ending in {env.fingerprint(existing.value)})."
        )
        choice = click.prompt(
            "  [u]se this key, [r]eplace it, or [s]kip API key setup?",
            type=click.Choice(["u", "r", "s"], case_sensitive=False),
            default="u",
        ).lower()
        if choice == "u":
            # Persist to the canonical location so future runs find it
            # without depending on cwd.
            if existing.source != str(target):
                env.write_api_key(target, existing.value)
                result.outcomes.append(
                    StepOutcome("API key configured", "done", str(target))
                )
            else:
                result.outcomes.append(
                    StepOutcome("API key configured", "done", str(target))
                )
            return
        if choice == "s":
            result.outcomes.append(
                StepOutcome("API key configured", "skipped", "")
            )
            return
        # Fall through to prompt for a replacement.

    new_key = _prompt_for_api_key()
    if new_key is None:
        result.outcomes.append(StepOutcome("API key configured", "skipped", ""))
        return
    env.write_api_key(target, new_key)
    click.echo(f"  API key saved to {target} (read-only to you).")
    result.outcomes.append(StepOutcome("API key configured", "done", str(target)))


def _prompt_for_api_key(max_attempts: int = 3) -> str | None:
    """Prompt for an API key up to ``max_attempts`` times. None on abort."""
    for attempt in range(1, max_attempts + 1):
        raw = click.prompt(
            "  Enter your Anthropic API key (input hidden, paste with cmd-v)",
            hide_input=True,
            default="",
            show_default=False,
        )
        if env.is_valid_api_key(raw):
            return raw.strip()
        remaining = max_attempts - attempt
        if remaining > 0:
            click.echo(
                f"  Key did not look valid (must start with 'sk-ant-' "
                f"and be at least {env.MIN_API_KEY_LENGTH} chars). "
                f"{remaining} attempt(s) remaining."
            )
    click.echo("  Too many invalid attempts; skipping API key setup.")
    return None


# ---------------------------------------------------------------------------
# Step 3 — Claude Code skill
# ---------------------------------------------------------------------------


def _step_claude_code(options: SetupOptions, result: SetupResult) -> None:
    target = detect.skill_install_dir()
    result.skill_path = target

    if options.skip_claude_code:
        result.outcomes.append(
            StepOutcome("Claude Code skill installed", "skipped", "")
        )
        return

    present = detect.claude_code_present()

    if not options.interactive:
        if not present:
            result.outcomes.append(
                StepOutcome(
                    "Claude Code skill installed",
                    "skipped",
                    "claude binary not on PATH",
                )
            )
            return
        try:
            install_skill.install_skill(target)
        except OSError as exc:
            result.outcomes.append(
                StepOutcome("Claude Code skill installed", "failed", str(exc))
            )
            return
        result.outcomes.append(
            StepOutcome("Claude Code skill installed", "done", str(target))
        )
        return

    click.echo("")
    click.echo("Step 2: Claude Code skill")
    if not present:
        click.echo("  Claude Code not detected (no `claude` binary on PATH).")
        click.echo(
            "  If you install Claude Code later, re-run `hypothesize setup`."
        )
        result.outcomes.append(
            StepOutcome("Claude Code skill installed", "skipped", "not detected")
        )
        return

    if install_skill.is_installed(target):
        if not click.confirm(
            f"  Hypothesize skill is already installed at {target}. Reinstall?",
            default=False,
        ):
            result.outcomes.append(
                StepOutcome(
                    "Claude Code skill installed", "skipped", "already installed"
                )
            )
            return
    else:
        if not click.confirm(
            "  Install the hypothesize skill for Claude Code?",
            default=True,
        ):
            result.outcomes.append(
                StepOutcome("Claude Code skill installed", "skipped", "")
            )
            return

    try:
        install_skill.install_skill(target)
    except OSError as exc:
        click.echo(f"  Could not write to {target}: {exc}")
        result.outcomes.append(
            StepOutcome("Claude Code skill installed", "failed", str(exc))
        )
        return
    click.echo(f"  Skill installed to {target}. Reload Claude Code to use it.")
    result.outcomes.append(
        StepOutcome("Claude Code skill installed", "done", str(target))
    )


# ---------------------------------------------------------------------------
# Step 4 — Claude Desktop MCP
# ---------------------------------------------------------------------------


def _step_claude_desktop(options: SetupOptions, result: SetupResult) -> None:
    if options.skip_claude_desktop:
        result.outcomes.append(
            StepOutcome("Claude Desktop MCP registered", "skipped", "")
        )
        return

    config_path = detect.claude_desktop_config_path()
    result.mcp_config_path = config_path
    env_file = _resolve_env_path(options)

    if not options.interactive:
        if config_path is None:
            result.outcomes.append(
                StepOutcome(
                    "Claude Desktop MCP registered",
                    "skipped",
                    "Claude Desktop not detected",
                )
            )
            return
        try:
            install_mcp.register_mcp_server(
                config_path=config_path, env_file=env_file
            )
        except (install_mcp.MalformedConfigError, OSError) as exc:
            result.outcomes.append(
                StepOutcome("Claude Desktop MCP registered", "failed", str(exc))
            )
            return
        result.outcomes.append(
            StepOutcome("Claude Desktop MCP registered", "done", str(config_path))
        )
        return

    click.echo("")
    click.echo("Step 3: Claude Desktop MCP server")
    if config_path is None:
        click.echo(
            "  Claude Desktop not detected (no config directory at the "
            "platform-specific location)."
        )
        click.echo(
            "  If you install Claude Desktop later, re-run `hypothesize setup`."
        )
        result.outcomes.append(
            StepOutcome(
                "Claude Desktop MCP registered", "skipped", "not detected"
            )
        )
        return

    click.echo(f"  Config path: {config_path}")
    if install_mcp.is_registered(config_path):
        if not click.confirm(
            "  hypothesize is already registered. Overwrite?", default=False
        ):
            result.outcomes.append(
                StepOutcome(
                    "Claude Desktop MCP registered",
                    "skipped",
                    "already registered",
                )
            )
            return
    else:
        if not click.confirm(
            "  Register the hypothesize MCP server with Claude Desktop?",
            default=True,
        ):
            result.outcomes.append(
                StepOutcome("Claude Desktop MCP registered", "skipped", "")
            )
            return

    try:
        install_mcp.register_mcp_server(
            config_path=config_path, env_file=env_file
        )
    except install_mcp.MalformedConfigError as exc:
        click.echo(
            f"  ERROR: existing config is malformed JSON: {exc}\n"
            f"  Repair {config_path} manually, then re-run setup."
        )
        result.outcomes.append(
            StepOutcome("Claude Desktop MCP registered", "failed", str(exc))
        )
        return
    except OSError as exc:
        click.echo(f"  ERROR writing config: {exc}")
        result.outcomes.append(
            StepOutcome("Claude Desktop MCP registered", "failed", str(exc))
        )
        return
    click.echo("  Registered. Restart Claude Desktop to load the server.")
    result.outcomes.append(
        StepOutcome("Claude Desktop MCP registered", "done", str(config_path))
    )


# ---------------------------------------------------------------------------
# Step 5 — optional verification call
# ---------------------------------------------------------------------------


def _step_verification(options: SetupOptions, result: SetupResult) -> None:
    if options.skip_verification:
        result.outcomes.append(
            StepOutcome("Verification call", "skipped", "")
        )
        return

    if options.interactive:
        click.echo("")
        click.echo("Step 4: Verification")
        if not click.confirm(
            "  Run a quick verification call to test the API key? "
            "(uses ~$0.001 of API credit)",
            default=False,
        ):
            result.outcomes.append(
                StepOutcome("Verification call", "skipped", "")
            )
            return

    target_env = _resolve_env_path(options)
    api_key = _load_key_for_verification(target_env, options.api_key)
    if not api_key:
        result.outcomes.append(
            StepOutcome(
                "Verification call",
                "failed",
                "no API key available to verify",
            )
        )
        return

    try:
        ok = _verify_api_key(api_key)
    except Exception as exc:  # noqa: BLE001 — surface any error category
        result.outcomes.append(
            StepOutcome("Verification call", "failed", _redact(str(exc), api_key))
        )
        return

    if ok:
        result.outcomes.append(StepOutcome("Verification call", "done", ""))
    else:
        result.outcomes.append(
            StepOutcome(
                "Verification call",
                "failed",
                "API responded but did not return the expected text",
            )
        )


def _load_key_for_verification(
    target_env: Path, options_key: str | None
) -> str | None:
    if options_key and env.is_valid_api_key(options_key):
        return options_key.strip()
    detected = env.detect_existing_key(env_files=[target_env])
    if detected:
        return detected.value
    return None


def _verify_api_key(api_key: str) -> bool:
    """Make a single Haiku call. Imports lazily so tests don't load anthropic."""
    from anthropic import Anthropic  # local import keeps cli imports light

    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8,
        messages=[{"role": "user", "content": "Say 'ok'"}],
    )
    for block in response.content:
        text = getattr(block, "text", "")
        if isinstance(text, str) and "ok" in text.lower():
            return True
    return False


def _redact(message: str, secret: str) -> str:
    if secret and secret in message:
        return message.replace(secret, env.fingerprint(secret))
    return message


# ---------------------------------------------------------------------------
# Step 6 — summary
# ---------------------------------------------------------------------------


_STATUS_GLYPH = {"done": "✓", "skipped": "✗", "failed": "⚠"}


def _print_summary(result: SetupResult) -> None:
    click.echo("")
    click.echo("Setup complete.")
    click.echo("")
    for outcome in result.outcomes:
        glyph = _STATUS_GLYPH.get(outcome.status, "?")
        suffix = f" — {outcome.detail}" if outcome.detail else ""
        click.echo(f"  {glyph} {outcome.label}{suffix}")
    click.echo("")
    click.echo("Next steps:")
    click.echo("  - Run `hypothesize run --help` to see usage")
    click.echo(
        "  - Or just paste a complaint into Claude Code; the skill will trigger"
    )


# ---------------------------------------------------------------------------
# Helper: ensure config dir exists when overridden
# ---------------------------------------------------------------------------


def ensure_config_dir(path: Path) -> None:
    """Create ``--config-dir`` if it doesn't already exist."""
    path.mkdir(parents=True, exist_ok=True)


__all__ = [
    "SetupOptions",
    "SetupResult",
    "StepOutcome",
    "ensure_config_dir",
    "run_setup",
]
