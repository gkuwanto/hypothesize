"""LLM-layer prompt templates.

This module hosts prompts whose consumer is the adapter / backend layer
rather than the core algorithm. Keeping core-only prompts in
``core/prompts.py`` preserves the Feature 01 "every core LLM call is
grep-able from one file" property; adapter-layer prompts live here.

The single entry today is ``rewrite_prompt_messages``: the prompt
``make_auto_alternative`` uses to ask Claude to rewrite a system prompt
so it specifically mitigates a stated failure hypothesis.
"""

from __future__ import annotations

from hypothesize.core.types import Hypothesis


def rewrite_prompt_messages(
    current_prompt: str, hypothesis: Hypothesis
) -> list[dict]:
    """Build the chat messages that ask Claude to rewrite a system prompt.

    The output is a strict-JSON object with ``rewritten_prompt`` and
    ``rationale`` keys. ``make_auto_alternative`` validates that shape
    after parsing.
    """
    system = (
        "You rewrite an LLM system prompt to specifically mitigate a "
        "stated failure hypothesis while preserving the prompt's "
        "original task and tone. You do not rewrite the prompt from "
        "scratch; you add targeted guidance addressing the failure mode."
    )
    user = (
        f"Current system prompt:\n---\n{current_prompt}\n---\n\n"
        f"Failure hypothesis the rewrite should address:\n"
        f"{hypothesis.text}\n\n"
        'Return STRICT JSON with exactly this shape: '
        '{"rewritten_prompt": str, "rationale": str}. '
        "The rewritten_prompt must be a drop-in replacement for the "
        "current prompt — same task, same tone, with added guidance "
        "targeting the failure mode. The rationale is one sentence "
        "explaining the change you made. No prose outside the JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
