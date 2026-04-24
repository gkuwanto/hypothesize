"""Backend-configuration and telemetry models.

``AnthropicConfig`` is the per-backend setting bundle used to construct
``AnthropicBackend``; ``RunnerCallLog`` is an informational record
surfaced via the backend's optional ``on_call`` callback.

Both are frozen pydantic v2 models. They are declared here rather than in
``src/hypothesize/core/`` because they are strictly a concern of the LLM
backend layer — the core's ``LLMBackend`` protocol does not know or care
about them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AnthropicConfig(BaseModel):
    """Per-backend configuration.

    The ``default_model`` is used when a specific ``complete()`` call does
    not override via a per-call ``model=`` kwarg. ``api_key_env`` names
    the environment variable the backend should read the key from when
    it constructs its own ``AsyncAnthropic`` client; when ``None``, the
    SDK's built-in default (``ANTHROPIC_API_KEY``) is honored.
    """

    model_config = ConfigDict(frozen=True)

    default_model: str = "claude-opus-4-7"
    max_tokens: int = 2048
    timeout_seconds: float = 60.0
    api_key_env: str | None = None


class RunnerCallLog(BaseModel):
    """Informational token-accounting record.

    Emitted per successful ``complete()`` call when an ``on_call``
    callback is registered on the backend. ``Budget`` still counts
    calls, not tokens — this record is strictly telemetry for callers
    that want per-phase token accounting.
    """

    model_config = ConfigDict(frozen=True)

    model: str
    input_tokens: int
    output_tokens: int
    phase: str | None = None
