"""Unit tests for ``src/hypothesize/llm/prompts.py``.

Asserts the message shape and the presence of the inputs the rewrite
prompt is supposed to convey to Claude. The exact wording is not
asserted — wording-level checks would couple the tests to prose that
will likely evolve.
"""

from __future__ import annotations

from hypothesize.core.types import Hypothesis
from hypothesize.llm.prompts import rewrite_prompt_messages


def test_rewrite_prompt_messages_has_system_and_user_roles() -> None:
    messages = rewrite_prompt_messages(
        "You are a helpful assistant.",
        Hypothesis(text="model fails on negation"),
    )
    assert isinstance(messages, list)
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user"]
    for m in messages:
        assert isinstance(m["content"], str)
        assert m["content"]


def test_rewrite_prompt_messages_includes_current_prompt_and_hypothesis() -> None:
    current = "ORIGINAL_PROMPT_BODY_TOKEN"
    hyp = Hypothesis(text="HYPOTHESIS_TEXT_TOKEN")
    messages = rewrite_prompt_messages(current, hyp)
    user = messages[1]["content"]
    assert "ORIGINAL_PROMPT_BODY_TOKEN" in user
    assert "HYPOTHESIS_TEXT_TOKEN" in user


def test_rewrite_prompt_messages_requests_strict_json_with_two_keys() -> None:
    messages = rewrite_prompt_messages(
        "current", Hypothesis(text="hyp")
    )
    user = messages[1]["content"]
    # Asks for both keys somewhere in the user instructions.
    assert "rewritten_prompt" in user
    assert "rationale" in user
