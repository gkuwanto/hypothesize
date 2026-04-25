"""Programmatic emoji judge for the ACME support example.

The hypothesis under test is "the chatbot uses excessive emojis in
customer support responses." That is a structural property of the
response text, not a semantic judgement, so a deterministic counter
is a better fit than a rubric judge: free, instant, and immune to
rubric-orientation drift.

``count_emojis`` counts emoji *graphemes*: skin-tone modifiers
(U+1F3FB-U+1F3FF), the variation selectors (U+FE0E, U+FE0F), and
zero-width joiners (U+200D) decorate adjacent base emoji rather than
adding new ones, so they are excluded from the count.

``EmojiCountJudge`` satisfies the ``Judge`` protocol from
``hypothesize.core.judge``. It does no I/O and never charges the
budget; ``judge_type`` is reported as ``"exact_match"`` because that
is the closest LLM-free slot in the existing ``JudgeType`` Literal —
this keeps the judge compatible with the YAML output schema without
changing core types.
"""

from __future__ import annotations

import re
from typing import Any

from hypothesize.core.types import Budget, Hypothesis, Verdict

# Base-emoji ranges. These are the codepoints that draw a glyph; the
# decorator codepoints (skin tones, variation selectors, ZWJ) are
# stripped before counting so a thumbs-up + skin tone reads as 1.
_EMOJI_BASE_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001f1e0-\U0001f1ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa70-\U0001faff"
    "☀-➿"
    "]"
)

_DECORATOR_RE = re.compile(
    "[\U0001f3fb-\U0001f3ff︎️‍]"
)


def count_emojis(text: str) -> int:
    """Count emoji graphemes in ``text``.

    Returns 0 for plain ASCII; counts each base-emoji codepoint once,
    discarding decorator codepoints. Punctuation and currency symbols
    are not counted.
    """
    if not text:
        return 0
    stripped = _DECORATOR_RE.sub("", text)
    return len(_EMOJI_BASE_RE.findall(stripped))


class EmojiCountJudge:
    """Pass iff ``output[output_key]`` contains zero emoji."""

    def __init__(self, output_key: str = "response") -> None:
        self.output_key = output_key

    async def judge(
        self,
        input_data: dict[str, Any],
        output: dict[str, Any],
        hypothesis: Hypothesis,
        budget: Budget,
    ) -> Verdict:
        if self.output_key not in output:
            return Verdict(
                passed=False,
                reason=f"missing output field {self.output_key!r}",
                judge_type="exact_match",
            )
        text = output[self.output_key]
        if not isinstance(text, str):
            text = str(text)
        n = count_emojis(text)
        if n == 0:
            return Verdict(
                passed=True,
                reason="0 emojis in response",
                judge_type="exact_match",
            )
        return Verdict(
            passed=False,
            reason=f"{n} emoji(s) in response",
            judge_type="exact_match",
        )
