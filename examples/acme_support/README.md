# Example: ACME support chatbot — emoji overuse

A third example alongside `examples/sarcasm/` and `examples/hotpotqa/`.
This one demonstrates the "stakeholder complaint about tone" workflow:
a PM noticed the bot was using too many emojis, added "DO NOT USE
EMOJIS" to the system prompt, and now wants regression tests that
prove the fix sticks.

The mechanism in one paragraph:

> A customer-support runner is run twice on each of 30 hand-written
> customer questions — once with a "warm and engaging" base prompt,
> once with the same prompt plus an all-caps NO-EMOJI directive. A
> programmatic `EmojiCountJudge` counts emoji graphemes in each
> response. A discriminating case is one where the base response
> contained at least one emoji and the no-emoji response contained
> zero.

## Why a programmatic judge (Path J1)?

Emoji presence is a **structural** property of a string, not a
semantic judgement. Counting emoji codepoints is deterministic, free,
and immune to the rubric-orientation drift that an LLM-based judge
would expose us to ("does the response not contain emojis?" is the
kind of negation a rubric judge can flip). A 50-line judge that lives
inside the example beats a free-form rubric for this hypothesis.

The judge satisfies the `Judge` protocol from
`hypothesize.core.judge` and reports `judge_type="exact_match"` —
that is the closest LLM-free slot in the existing `JudgeType` Literal
and keeps us compatible with the YAML output schema without modifying
core types. See `judge.py`.

## Why a separate script, not `hypothesize run`?

Same reason as `examples/hotpotqa/`. The standard discrimination
pipeline is built around LLM-generated candidates and a `RubricJudge`;
this example needs neither. `run_filter.py` calls the underlying
primitives directly with the example's own judge. `config.yaml` is
preserved so the example surfaces in `hypothesize list` and the
shared LLM/budget settings live in one place.

## Files

- `system.py` — chatbot runner with `BASE_SYSTEM_PROMPT` and
  `NO_EMOJI_SYSTEM_PROMPT`. Both prompts are plausible engineering
  choices; neither is a strawman.
- `judge.py` — `EmojiCountJudge` and `count_emojis` helper.
- `data/customer_questions.jsonl` — 30 questions, 5 per category
  across account_access, billing, product_issues, order_status,
  returns_refunds, general_support.
- `run_filter.py` — runs both prompts on each candidate and writes
  `output/run1.yaml`.
- `output/run1.yaml` — last filter run, including `all_rows` and the
  discriminating subset.
- `CURATED.md` / `CURATED.yaml` — 4 cases selected for video.
- `config.yaml` — the system shape, used by `run_filter.py` and
  surfaced in `hypothesize list`.

## Run it

Set `ANTHROPIC_API_KEY` in `.env` at the repo root, then:

```bash
python examples/acme_support/run_filter.py
```

Expected: 60 LLM calls (30 candidates × 2 prompts), under $0.10 on
Claude Haiku 4.5, ~90 seconds wall time. The judge does no LLM calls.

## Last run statistics

30 candidates / 21 both clean / 0 both with emoji / 9 only-base with
emoji (discriminating) / 0 only-no_emoji with emoji.

The 9 discriminating cases all came in at exactly **one** emoji per
base response — Haiku's "warm and engaging" default is more
restrained than a hypothesis like "excessive emojis" predicts. The
hypothesis is supported (the bot does add emoji and the override
removes them) but the contrast on screen is "1 emoji vs 0", not the
emoji blizzard the word "excessive" might suggest. See `CURATED.md`
for the four selected cases and a per-category breakdown of when
Haiku reaches for emoji and when it does not.

## What this example demonstrates

- A custom programmatic judge plugged into the `Judge` protocol from
  outside `src/`.
- A tone-and-style hypothesis (not an accuracy hypothesis) discriminated
  by a deterministic judge with no LLM cost on the judge side.
- Honest reporting when the discriminating intensity is lower than
  the hypothesis suggested: 9 cases at 1 emoji each is a real
  finding, not a failure, and is documented as such.
