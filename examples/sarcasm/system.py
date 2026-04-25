"""Sarcasm sentiment example — the demo's hero system.

A deliberately weak baseline classifier: a one-line system prompt with
no sarcasm guidance. Hypothesize is expected to discover that sarcastic
positive text (surface tokens positive, intent negative) breaks this
prompt, and the auto-alternative path will rewrite the prompt to
mitigate the failure.

The module follows the prompt-factory convention from
``src/hypothesize/adapters/python_module.py`` so ``alternative.adapter:
auto`` works in ``config.yaml``: it exposes ``SYSTEM_PROMPT``,
``make_runner(prompt=None)``, and ``run = make_runner()``.

A ``backend`` kwarg on ``make_runner`` lets tests inject a
``MockBackend`` without touching the network. The CLI's
``PythonModuleAdapter`` calls ``make_runner(prompt=...)`` (no
``backend``), so the production path constructs a fresh
``AnthropicBackend`` lazily on the first call.
"""

from __future__ import annotations

from typing import Any, Protocol

SYSTEM_PROMPT = (
    "You are a sentiment classifier. Read the input and reply with "
    "exactly one word: 'positive' or 'negative'. Do not explain. "
    "Do not return anything other than that one word."
)


class _Backend(Protocol):
    async def complete(self, messages: list[dict], **kwargs: Any) -> str: ...


def _normalize_label(raw: str) -> str:
    """Map a free-text response to one of {'positive', 'negative'}."""
    if not raw:
        return "positive"
    text = raw.strip().lower()
    # If 'negative' appears anywhere in the response, treat as negative;
    # default to positive otherwise. Punctuation is stripped per token.
    for token in text.replace(",", " ").replace(".", " ").split():
        clean = token.strip(".,!?:;\"'")
        if clean == "negative":
            return "negative"
    if "negative" in text:
        return "negative"
    return "positive"


def make_runner(
    prompt: str | None = None,
    *,
    backend: _Backend | None = None,
):
    """Return an async runner that classifies sentiment via Claude.

    ``prompt=None`` uses the module-level ``SYSTEM_PROMPT`` (the
    deliberately weak baseline). The auto-alternative path passes a
    rewritten prompt here.

    ``backend=None`` constructs a fresh ``AnthropicBackend`` on first
    use; tests pass a ``MockBackend`` to avoid live calls.
    """
    effective_prompt = prompt if prompt is not None else SYSTEM_PROMPT

    async def run(input_data: dict[str, Any]) -> dict[str, Any]:
        text = input_data.get("text") or input_data.get("input") or ""
        if not isinstance(text, str):
            text = str(text)

        nonlocal backend
        if backend is None:
            from hypothesize.llm.anthropic import AnthropicBackend
            from hypothesize.llm.config import AnthropicConfig

            backend = AnthropicBackend(
                config=AnthropicConfig(default_model="claude-haiku-4-5-20251001")
            )

        messages = [
            {"role": "system", "content": effective_prompt},
            {"role": "user", "content": f"Text: {text}\n\nSentiment:"},
        ]
        raw = await backend.complete(messages)
        return {"sentiment": _normalize_label(raw)}

    return run


run = make_runner()
