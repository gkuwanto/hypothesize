"""HotpotQA closed-book multi-hop QA.

Two prompt variants for the same question-answering surface:

- ``DIRECT_PROMPT`` — answer concisely, no explanation. The default.
- ``DECOMPOSE_PROMPT`` — first identify sub-questions, answer each,
  synthesize the final answer. Final response is still a single
  short answer; only the model's internal reasoning differs.

Both prompts are plausible engineering choices a real team might
ship. Neither contains strawman language. The hypothesize filter
pass surfaces inputs where the difference matters: chained-reasoning
questions where DIRECT shortcuts to the named entity and DECOMPOSE
walks the bridge.

Closed-book on purpose. The runner receives only ``{"question": str}``
— no retrieved contexts, no distractors. The failure mode under test
is chained reasoning, not retrieval.

The module follows the prompt-factory convention from
``src/hypothesize/adapters/python_module.py``: ``SYSTEM_PROMPT``,
``make_runner(prompt=None)``, and ``run = make_runner()``. A
``backend`` kwarg lets tests inject a ``MockBackend`` without
touching the network.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

DIRECT_PROMPT = (
    "Answer the question concisely. End your response with a single "
    "line of the form:\n\n"
    "Final answer: <answer>\n\n"
    "where <answer> is just the answer itself — a name, place, "
    "title, or short noun phrase — with no other words."
)

DECOMPOSE_PROMPT = (
    "Answer the question. If it requires reasoning across multiple "
    "entities or facts, first identify the sub-questions, answer "
    "each sub-question, then synthesize the final answer. End your "
    "response with a single line of the form:\n\n"
    "Final answer: <answer>\n\n"
    "where <answer> is just the answer itself — a name, place, "
    "title, or short noun phrase — with no other words."
)

SYSTEM_PROMPT = DIRECT_PROMPT


class _Backend(Protocol):
    async def complete(self, messages: list[dict], **kwargs: Any) -> str: ...


_PREFIX_PATTERNS = (
    re.compile(r"^\s*answer\s*[:\-]\s*", re.IGNORECASE),
    re.compile(r"^\s*the\s+answer\s+is\s*[:\-]?\s*", re.IGNORECASE),
    re.compile(r"^\s*final\s+answer\s*[:\-]\s*", re.IGNORECASE),
)

_FINAL_ANSWER_RE = re.compile(
    r"final\s+answer\s*[:\-]\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)


def _extract_final_answer(text: str) -> str | None:
    """Find the last 'Final answer: X' line in a multi-line response.

    Both prompts instruct Claude to terminate with this exact form;
    when it complies, this picks up the answer regardless of how
    much reasoning preceded it. Returns ``None`` when no such line
    is present so the caller can fall back to whole-text parsing.
    """
    matches = list(_FINAL_ANSWER_RE.finditer(text))
    if not matches:
        return None
    return matches[-1].group(1).strip()


def _normalize_answer(raw: str) -> str:
    """Strip whitespace, common prefixes, surrounding quotes/markdown."""
    if not raw:
        return ""
    final = _extract_final_answer(raw)
    if final is not None:
        text = final
    else:
        text = raw.strip()
        # Verbose response with no "Final answer:" line — take the
        # last non-empty line and hope it's the punchline.
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            text = lines[-1]
    # Strip enclosing markdown bold/italics, then quotes.
    for _ in range(3):
        stripped = text
        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
            stripped = stripped[2:-2].strip()
        if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
            stripped = stripped[1:-1].strip()
        if (
            len(stripped) > 1
            and stripped[0] in {'"', "'", "“", "‘"}
            and stripped[-1] in {'"', "'", "”", "’"}
        ):
            stripped = stripped[1:-1].strip()
        if stripped == text:
            break
        text = stripped
    # Strip leading "Answer:", "The answer is", etc.
    for pattern in _PREFIX_PATTERNS:
        text = pattern.sub("", text, count=1)
    text = text.strip()
    # Drop a single trailing period — but keep abbreviations like "U.S."
    if text.endswith(".") and not text.endswith(".."):
        head = text[:-1]
        if "." not in head[-3:]:
            text = head
    return text.strip()


def make_runner(
    prompt: str | None = None,
    *,
    backend: _Backend | None = None,
):
    """Return an async runner that answers a question via Claude.

    ``prompt=None`` uses the module-level ``SYSTEM_PROMPT`` (the
    direct prompt). The DECOMPOSE_PROMPT variant is loaded by the
    config's alternative system block via ``prompt=``.

    ``backend=None`` constructs a fresh ``AnthropicBackend`` on first
    use; tests pass a ``MockBackend`` to avoid live calls.
    """
    effective_prompt = prompt if prompt is not None else SYSTEM_PROMPT

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
            {"role": "user", "content": f"Question: {question}\n\nAnswer:"},
        ]
        raw = await backend.complete(messages)
        return {"answer": _normalize_answer(raw)}

    return run


run = make_runner()
