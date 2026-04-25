"""Live-test configuration.

Loads ``ANTHROPIC_API_KEY`` from a project-root ``.env`` so the tests
need no shell-side configuration. Tests skip cleanly with a pointed
message when the key is absent — the live suite must never crash mid-
call when the environment is half-configured.

Live tests default to Haiku for cost. Tests that need Opus reasoning
can override via the per-test ``model=`` kwarg on ``complete``.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from hypothesize.llm.anthropic import AnthropicBackend
from hypothesize.llm.config import AnthropicConfig

load_dotenv()


_LIVE_MODEL = "claude-haiku-4-5-20251001"


def _api_key_loaded() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY")
    return bool(key) and len(key) > 10


@pytest.fixture
def anthropic_backend() -> AnthropicBackend:
    """Configured ``AnthropicBackend`` for live tests; skip if no key."""
    if not _api_key_loaded():
        pytest.skip(
            "ANTHROPIC_API_KEY not loaded; configure .env to run live tests"
        )
    return AnthropicBackend(
        config=AnthropicConfig(
            default_model=_LIVE_MODEL,
            max_tokens=2048,
        )
    )


@pytest.fixture
def anthropic_backend_factory():
    """Factory that builds an ``AnthropicBackend`` with a custom ``on_call``.

    Lets tests register a token-logging callback at construction time
    (the only point where ``AnthropicBackend`` accepts ``on_call``).
    """
    if not _api_key_loaded():
        pytest.skip(
            "ANTHROPIC_API_KEY not loaded; configure .env to run live tests"
        )

    def _build(on_call=None) -> AnthropicBackend:
        return AnthropicBackend(
            config=AnthropicConfig(
                default_model=_LIVE_MODEL,
                max_tokens=2048,
            ),
            on_call=on_call,
        )

    return _build
