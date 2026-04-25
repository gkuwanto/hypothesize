"""Tests for examples/acme_support/ — chatbot tone example.

All tests run with a MockBackend; no live LLM calls.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from tests._fixtures.mock_backend import MockBackend

EXAMPLES_ROOT = (
    Path(__file__).resolve().parent.parent.parent / "examples" / "acme_support"
)


def _load_system_module():
    spec = importlib.util.spec_from_file_location(
        "_acme_support_test_module", EXAMPLES_ROOT / "system.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_judge_module():
    spec = importlib.util.spec_from_file_location(
        "_acme_support_judge_module", EXAMPLES_ROOT / "judge.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_module_exposes_two_prompts() -> None:
    module = _load_system_module()
    assert hasattr(module, "BASE_SYSTEM_PROMPT")
    assert hasattr(module, "NO_EMOJI_SYSTEM_PROMPT")
    assert isinstance(module.BASE_SYSTEM_PROMPT, str)
    assert isinstance(module.NO_EMOJI_SYSTEM_PROMPT, str)
    # The no-emoji variant adds the all-caps directive on top of the
    # base prompt.
    assert module.BASE_SYSTEM_PROMPT in module.NO_EMOJI_SYSTEM_PROMPT
    assert "EMOJI" in module.NO_EMOJI_SYSTEM_PROMPT


def test_extract_prompt_returns_base() -> None:
    module = _load_system_module()
    assert module.extract_prompt() == module.BASE_SYSTEM_PROMPT


def test_module_exposes_run_and_make_runner() -> None:
    module = _load_system_module()
    assert callable(module.make_runner)
    assert callable(module.run)


async def test_make_runner_default_uses_base_prompt() -> None:
    module = _load_system_module()
    backend = MockBackend(responses=["sure!"])
    runner = module.make_runner(backend=backend)
    await runner({"question": "Hi"})
    system_msgs = [
        msg
        for call in backend.calls
        for msg in call["messages"]
        if msg.get("role") == "system"
    ]
    assert len(system_msgs) == 1
    assert system_msgs[0]["content"] == module.BASE_SYSTEM_PROMPT


async def test_make_runner_uses_no_emoji_override() -> None:
    module = _load_system_module()
    backend = MockBackend(responses=["sure."])
    runner = module.make_runner(prompt=module.NO_EMOJI_SYSTEM_PROMPT, backend=backend)
    await runner({"question": "Hi"})
    system_msgs = [
        msg
        for call in backend.calls
        for msg in call["messages"]
        if msg.get("role") == "system"
    ]
    assert len(system_msgs) == 1
    assert system_msgs[0]["content"] == module.NO_EMOJI_SYSTEM_PROMPT


async def test_runner_returns_response_field() -> None:
    module = _load_system_module()
    backend = MockBackend(responses=["Reset your password at acme.com/reset."])
    runner = module.make_runner(backend=backend)
    out = await runner({"question": "How do I reset my password?"})
    assert "response" in out
    assert out["response"] == "Reset your password at acme.com/reset."


async def test_runner_forwards_question_to_user_message() -> None:
    module = _load_system_module()
    backend = MockBackend(responses=["sure."])
    runner = module.make_runner(backend=backend)
    await runner({"question": "Why was my card charged twice?"})
    user_msgs = [
        msg
        for call in backend.calls
        for msg in call["messages"]
        if msg.get("role") == "user"
    ]
    assert any("Why was my card charged twice?" in m["content"] for m in user_msgs)


# --- judge tests --------------------------------------------------------


def test_count_emojis_zero_for_plain_text() -> None:
    judge = _load_judge_module()
    assert judge.count_emojis("Reset your password at acme.com/reset.") == 0
    assert judge.count_emojis("") == 0
    assert judge.count_emojis("This costs $5. Email me at foo@bar.com.") == 0


def test_count_emojis_picks_up_common_emoji() -> None:
    judge = _load_judge_module()
    assert judge.count_emojis("Hi there! 😊") == 1
    assert judge.count_emojis("Hi there! 😊 Welcome! 🎉") == 2
    # ✨ and 🎉 are in different unicode ranges; both should count.
    assert judge.count_emojis("✨🎉🎊 wow!") == 3


def test_count_emojis_ignores_skin_tone_and_variation_selector() -> None:
    judge = _load_judge_module()
    # 👍🏼 is base + skin-tone modifier — count as one emoji.
    assert judge.count_emojis("Thanks! 👍🏼") == 1
    # ⚠️ is warning + variation selector — count as one emoji.
    assert judge.count_emojis("Use ⚠️ warnings") == 1


async def test_judge_passes_when_no_emojis() -> None:
    judge_mod = _load_judge_module()
    from hypothesize.core.types import Budget, Hypothesis

    judge = judge_mod.EmojiCountJudge()
    hypothesis = Hypothesis(text="bot uses excessive emojis")
    budget = Budget(max_llm_calls=10)
    verdict = await judge.judge(
        input_data={"question": "anything"},
        output={"response": "Reset your password at acme.com/reset."},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert verdict.passed is True
    assert budget.calls_used == 0


async def test_judge_fails_when_emojis_present() -> None:
    judge_mod = _load_judge_module()
    from hypothesize.core.types import Budget, Hypothesis

    judge = judge_mod.EmojiCountJudge()
    hypothesis = Hypothesis(text="bot uses excessive emojis")
    budget = Budget(max_llm_calls=10)
    verdict = await judge.judge(
        input_data={"question": "anything"},
        output={"response": "Hi! 😊 No worries, here to help 🙌"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert verdict.passed is False
    assert "2" in verdict.reason  # mentions the count
    assert budget.calls_used == 0


async def test_judge_fails_gracefully_on_missing_field() -> None:
    judge_mod = _load_judge_module()
    from hypothesize.core.types import Budget, Hypothesis

    judge = judge_mod.EmojiCountJudge(output_key="response")
    hypothesis = Hypothesis(text="bot uses excessive emojis")
    budget = Budget(max_llm_calls=10)
    verdict = await judge.judge(
        input_data={"question": "anything"},
        output={"some_other_key": "x"},
        hypothesis=hypothesis,
        budget=budget,
    )
    assert verdict.passed is False
    assert "response" in verdict.reason
