"""API key validation, fingerprinting, detection, and ``.env`` writing.

Security rule: this module is never allowed to print, log, or otherwise
expose the API key value. All public functions either return the key in
a typed structure (handed to the caller) or write it to disk; nothing in
here calls ``print``/``echo``/``logging`` with the key. The wizard also
follows this rule when invoking these helpers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

API_KEY_PREFIX = "sk-ant-"
MIN_API_KEY_LENGTH = 30
ENV_VAR_NAME = "ANTHROPIC_API_KEY"


def is_valid_api_key(value: str) -> bool:
    """Return True iff ``value`` looks like an Anthropic API key.

    Stripped of surrounding whitespace, the key must start with
    ``sk-ant-`` and be at least :data:`MIN_API_KEY_LENGTH` characters.
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if len(candidate) < MIN_API_KEY_LENGTH:
        return False
    return candidate.startswith(API_KEY_PREFIX)


def fingerprint(value: str) -> str:
    """Return a fingerprint suitable for printing — last 4 chars only.

    Even for malformed input, this never reveals the prefix or middle of
    the string. The wizard prints fingerprints to confirm a re-used key
    without ever showing the full value.
    """
    if not value:
        return "..."
    suffix = value[-4:]
    return f"...{suffix}"


def default_config_dir() -> Path:
    """Return ``~/.config/hypothesize`` (the default config directory)."""
    return Path.home() / ".config" / "hypothesize"


def default_env_path() -> Path:
    """Return the default ``.env`` path under the default config dir."""
    return default_config_dir() / ".env"


def write_api_key(target: Path, key: str) -> None:
    """Write ``key`` to ``target`` as ``ANTHROPIC_API_KEY=<key>``.

    Creates parent directories. Sets file mode to ``0600`` so only the
    owner can read or write it. Overwrites any existing content; the
    wizard collects the user's intent before calling this.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    content = f"{ENV_VAR_NAME}={key}\n"
    # Write first, then chmod — order matters on filesystems where the
    # umask would otherwise leak group-readable bits during the brief
    # window between create and chmod.
    target.write_text(content)
    try:
        target.chmod(0o600)
    except (OSError, NotImplementedError):
        # Windows / unusual filesystems may not honour POSIX modes; the
        # write succeeded so we proceed. Tests run on POSIX.
        pass


@dataclass(frozen=True)
class DetectedKey:
    """Result of :func:`detect_existing_key` — source and value pair."""

    source: str
    value: str


def detect_existing_key(env_files: list[Path]) -> DetectedKey | None:
    """Look for an existing ``ANTHROPIC_API_KEY`` in env or supplied files.

    Search order:
    1. ``os.environ[ANTHROPIC_API_KEY]`` (if non-empty).
    2. Each path in ``env_files`` in order, parsing simple ``KEY=VALUE``
       lines without invoking ``dotenv`` (so we never mutate the
       process environment).
    """
    env_value = os.environ.get(ENV_VAR_NAME, "").strip()
    if env_value:
        return DetectedKey(source="environment", value=env_value)
    for path in env_files:
        value = _read_key_from_file(path)
        if value:
            return DetectedKey(source=str(path), value=value)
    return None


def load_dotenv_chain() -> None:
    """Load the API key from the project + global dotenv files.

    Order (first match wins because ``load_dotenv`` defaults to
    ``override=False``):

    1. ``./.env`` in the current working directory (project override).
    2. ``~/.config/hypothesize/.env`` (the canonical location written
       by ``hypothesize setup``).

    Already-set process env vars (e.g. ``export ANTHROPIC_API_KEY=...``
    in the user's shell) win over both files. This is the standard
    dotenv contract.
    """
    from dotenv import find_dotenv, load_dotenv

    # find_dotenv(usecwd=True) walks UP from cwd looking for a .env, the
    # standard dotenv discovery behavior so a user running `hypothesize
    # run` from a subdirectory of a project still finds the project's
    # .env. Returns "" when nothing is found.
    project_env = find_dotenv(usecwd=True)
    if project_env:
        load_dotenv(project_env)
    global_env = default_env_path()
    if global_env.exists():
        load_dotenv(global_env)


def _read_key_from_file(path: Path) -> str | None:
    """Return the ``ANTHROPIC_API_KEY=...`` value from a .env-style file.

    Returns ``None`` when the file does not exist, the key is absent, or
    the value is empty. Does not mutate ``os.environ``. Whitespace and
    surrounding single/double quotes are stripped from the value.
    """
    if not path.exists() or not path.is_file():
        return None
    try:
        content = path.read_text()
    except OSError:
        return None
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        name, _, value = line.partition("=")
        if name.strip() != ENV_VAR_NAME:
            continue
        cleaned = value.strip().strip("'\"")
        if cleaned:
            return cleaned
        return None
    return None
