"""ACME support chatbot — emoji-overuse example.

Two prompt variants for the same customer-support surface:

- ``BASE_SYSTEM_PROMPT`` — the original "warm and engaging" prompt
  shipped to production. It says nothing about emoji, leaving Claude
  Haiku free to lean on emoji to perform warmth.
- ``NO_EMOJI_SYSTEM_PROMPT`` — the same prompt, plus an all-caps
  directive forbidding emoji. The all-caps tone is intentional; it is
  what a PM actually writes when they spot the problem in production.

Both are plausible. Neither is a strawman. The ``hypothesize`` filter
pass surfaces customer questions where the difference is visible: the
base prompt produces emoji-heavy responses, the override produces
clean ones.

The module follows the prompt-factory convention from
``src/hypothesize/adapters/python_module.py``: ``SYSTEM_PROMPT``
(aliased to ``BASE_SYSTEM_PROMPT`` for the adapter), ``make_runner
(prompt=None)``, and ``run = make_runner()``. A ``backend`` kwarg
lets tests inject a ``MockBackend`` without touching the network.
"""

from __future__ import annotations

from typing import Any, Protocol

BASE_SYSTEM_PROMPT = (
    "You are a customer support assistant for ACME Co.\n"
    "Be helpful, warm, and engaging with customers. Make them feel welcome.\n"
    "Keep responses concise (2-4 sentences)."
)

NO_EMOJI_SYSTEM_PROMPT = (
    BASE_SYSTEM_PROMPT
    + "\n\nDO NOT USE EMOJIS. NO EMOJIS PLEASE. PROFESSIONAL ONLY."
)

# Alias the adapter looks for.
SYSTEM_PROMPT = BASE_SYSTEM_PROMPT


def extract_prompt() -> str:
    """Return the baseline system prompt."""
    return BASE_SYSTEM_PROMPT


class _Backend(Protocol):
    async def complete(self, messages: list[dict], **kwargs: Any) -> str: ...


def make_runner(
    prompt: str | None = None,
    *,
    backend: _Backend | None = None,
):
    """Return an async runner that answers a customer question via Claude.

    ``prompt=None`` uses ``BASE_SYSTEM_PROMPT``. The override path passes
    ``NO_EMOJI_SYSTEM_PROMPT`` here.

    ``backend=None`` constructs a fresh ``AnthropicBackend`` lazily on
    first use; tests pass a ``MockBackend`` to avoid live calls.
    """
    effective_prompt = prompt if prompt is not None else BASE_SYSTEM_PROMPT

    async def run(input_data: dict[str, Any]) -> dict[str, Any]:
        question = input_data.get("question") or input_data.get("input") or ""
        if not isinstance(question, str):
            question = str(question)

        nonlocal backend
        if backend is None:
            from hypothesize.llm.anthropic import AnthropicBackend
            from hypothesize.llm.config import AnthropicConfig

            backend = AnthropicBackend(
                config=AnthropicConfig(default_model="claude-haiku-4-5-20251001")
            )

        messages = [
            {"role": "system", "content": effective_prompt},
            {"role": "user", "content": question},
        ]
        raw = await backend.complete(messages)
        return {"response": raw}

    return run


run = make_runner()
