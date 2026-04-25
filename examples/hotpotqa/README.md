# Example: HotpotQA closed-book multi-hop QA

A second real-dataset example alongside `examples/sarcasm/`. Where
sarcasm uses `RubricJudge` and generates synthetic candidates from a
hypothesis, this example operates as a **filter** over a fixed eval
dataset using `ExactMatchJudge` against gold answers.

The mechanism in one paragraph:

> Closed-book QA is run twice on each of 50 HotpotQA bridge questions
> — once with a `DIRECT_PROMPT` that asks for a concise answer, once
> with a `DECOMPOSE_PROMPT` that asks the model to identify
> sub-questions before answering. A discriminating case is one where
> DIRECT got the gold answer wrong and DECOMPOSE got it right.

## Why a separate script, not `hypothesize run`?

The standard pipeline (`src/hypothesize/core/discrimination.py`) is
built around LLM-generated candidates and a rubric-based judge. A
filter pass over a fixed eval set with exact-match judging is a
slightly different code path. Adding it as a CLI flag would have
meant a parallel runner and a new judge selector — too much surface
for one example. Instead, `run_filter.py` calls the underlying
primitives directly. The `config.yaml` is preserved so the example
still surfaces in `hypothesize list` / `discover_systems` and the
shared LLM/budget settings live in one place.

## Files

- `system.py` — closed-book QA runner with `DIRECT_PROMPT` and
  `DECOMPOSE_PROMPT`, both terminating with `Final answer: <X>` so
  responses parse cleanly.
- `data/multi_hop_50.jsonl` — 50 HotpotQA bridge questions with
  gold answers. Built reproducibly by `build_dataset.py`.
- `data/README.md` — source and filter criteria for the dataset.
- `build_dataset.py` — one-shot script to regenerate the dataset.
- `run_filter.py` — runs both prompts on each candidate and writes
  `output/multi_hop_filter_run1.yaml`.
- `output/multi_hop_filter_run1.yaml` — last filter run, including
  `all_rows` and the discriminating subset.
- `CURATED.md` / `CURATED.yaml` — selected cases for video.
- `config.yaml` — the system shape, used by `run_filter.py` and
  surfaced in `hypothesize list`.

## Run it

Set `ANTHROPIC_API_KEY` in `.env` at the repo root, then:

```bash
# Build the dataset (one-time):
python examples/hotpotqa/build_dataset.py

# Run the filter pass:
python examples/hotpotqa/run_filter.py
```

Expected: ~100 LLM calls (50 candidates × 2 prompts), $0.05–$0.15
on Claude Haiku 4.5, ~3 minutes wall time.

## Last run statistics

50 candidates / 17 both correct / 27 both wrong / 3 only-decompose
right / 3 only-direct right. The 3-vs-3 split between the
discriminating directions is itself a finding: decomposed reasoning
helps on chained-entity questions but costs DIRECT-solvable items.
See `CURATED.md`.

## What this example demonstrates

- A non-classifier hypothesize integration with a real eval
  dataset.
- The "filter" mode complementing the "generate" mode the sarcasm
  example uses.
- Honest reporting when the discriminating count is below
  expectations: 3 cases is a finding, not a failure.
