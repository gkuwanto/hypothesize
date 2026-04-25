# Smoke Test Findings — 2026-04-24 (run 2)

Live re-runs of `scripts/smoke_test.py` against the real Anthropic API,
now through Feature 02's `AnthropicBackend` and `parse_json_response`.
Model: `claude-haiku-4-5-20251001`. Wall time per run: ~97s. Exit code
each: 0. Budget cap raised from 30 to 100 per the task spec.

This document is the second-run companion to
[`SMOKE_FINDINGS.md`](./SMOKE_FINDINGS.md). Read that one first for the
parse-class baseline and Feature 02's motivation.

The numbers below are taken from the first run; subsequent reruns
produced very similar shapes — same call counts and parse cleanliness —
but a *different* discrimination outcome. That difference is the most
important finding of this session.

## Ran successfully?

**Yes — end to end, consistently.** No Python exceptions, no API
errors, no parse failures, exit 0 across all runs. The discrimination
algorithm reached the generate, rubric-build, and rubric-judge phases.
Decompose, generate, and judge all returned cleanly-typed payloads.

The discrimination *result* varies from run to run on the same
scenario:

- Run 1 — 0 discriminating cases (`insufficient_evidence`)
- Run 2 — 4 discriminating cases (`status: ok`)
- Run 3 — 0 discriminating cases (`insufficient_evidence`)

Same hypothesis, same context, same model, same prompts. The
non-determinism comes from how Haiku interprets the rubric build/judge
prompts each time. See "New failure class" below — this is the
headline finding.

## Calls per phase (core backend)

| Phase | Calls |
|---|---|
| decompose | 1 |
| generate | 6 |
| rubric_build | 1 |
| rubric_judge | 36 |
| **core total** | **44 / 100** |
| alt_runner | 18 (not counted against core budget) |

Budget headroom: 56 calls unused. Generate produced 18 candidates × 2
judge calls = 36 rubric_judge. The algorithm short-circuits on found
discriminations, so this is the maximal-judge case for the failure
mode we hit.

## Token usage per phase (core backend)

| Phase | Calls | Input tokens | Output tokens |
|---|---|---|---|
| decompose | 1 | 177 | 579 |
| generate | 6 | 1,657 | 2,018 |
| rubric_build | 1 | 95 | 197 |
| rubric_judge | 36 | 10,728 | 2,260 |
| **TOTAL** | **44** | **12,657** | **5,054** |

Approximate cost (Haiku 4.5 pricing): about **$0.04** for the core run,
plus a few cents for the 18 alt-runner calls. Total session cost (this
run plus the live test suite, which made ~12 calls) is well under
$0.10.

## Decompose dimensions

`decompose_hypothesis` returned 6 dimensions, well-typed and on-topic:

- **Sarcasm intensity** — degree to which sarcasm is marked or obvious.
- **Positive token density** — proportion of surface-positive tokens.
- **Context dependency** — whether sarcasm is detectable from the
  statement alone.
- **Irony type** — situational vs. verbal vs. structural.
- **Negation presence** — explicit negation markers alongside positive
  tokens.
- **Emotional tone markers** — punctuation / capitalisation cues.

All six parsed cleanly via `parse_json_response`, all six fit the
`{name, description, examples}` schema. Quality impression: **good**;
these are the kind of dimensions a human prompt engineer would write.

## JSON parse cleanliness

**0 of 43 JSON-expecting responses failed to parse.** Every fenced
response (the previous failure mode) was unwrapped by
`parse_json_response`. Every brace-prefixed-with-prose response (none
observed in this run, but the extractor would handle them) is covered.

The Feature 02 extractor is doing its job — the `SMOKE_1` parse class
of bug is gone.

## Candidate `input_data` shapes

All 18 candidates used `{"text": ...}`. Distribution:

| keys | count |
|---|---|
| `["text"]` | 18 |

This matches what a human would write for a sentiment classifier and
matches the shape `SarcasmAwareRunner` expects. The Feature 01 design
note about delegating shape inference to the LLM held up: with no
input-template scaffolding, Haiku consistently produced the right
shape from the hypothesis text alone.

## Discrimination outcome (run-by-run)

| Run | Status | Discriminating | Reason |
|---|---|---|---|
| 1 | `insufficient_evidence` | 0 / 18 | rubric inverted |
| 2 | `ok` | 4 / 18 | rubric correctly oriented |
| 3 | `insufficient_evidence` | 0 / 18 | rubric inverted |

In all runs every alt-runner output was `negative` (alt classifier
doing its job) and every current-runner output was `positive` (broken
classifier as designed). The hypothesis is true, the alternative is
better, and the algorithm sometimes finds the cases and sometimes
doesn't.

Run 2 produced cases like:

> input: *"Oh great, another mandatory training session on workplace
> safety. Just what I needed today."*
>
> current_output: `{"sentiment": "positive"}` →
> verdict.passed = false ("incorrectly labeled sarcastic text...")
>
> alternative_output: `{"sentiment": "negative"}` →
> verdict.passed = true ("correctly predicted negative sentiment...")

That is exactly the discrimination shape the algorithm is meant to
produce. So the wiring is correct end-to-end. The instability lives in
the rubric semantics.

## New failure class — rubric semantic inversion (stochastic)

The rubric Claude generates from `build_rubric_prompt` is sometimes
oriented one way, sometimes the other. `discrimination.py` uses:

```python
if not current_verdict.passed and alt_verdict.passed:
    discriminating.append(...)
```

This is consistent with `pairwise_judge_prompt`'s explicit doc-string —
*"decide whether it passes (does NOT exhibit the failure)"* — i.e.
**`passed=true` means "system handles the case correctly"**.

But `build_rubric_prompt` and `rubric_judge_prompt` do not pin that
semantic. They say "An output passes only if it satisfies all
criteria" without specifying what the criteria should encode. Real
Haiku resolves the ambiguity differently across runs:

- *Inverted run* — sample reasons:
  - *"The classifier output is 'negative', but the rubric requires
    the classifier to misclassify sarcastic text as positive."*
    (alt → false)
  - *"The classifier correctly identified the sentiment as negative,
    but the rubric requires the classifier to misclassify..."*
    (alt → false)

  In this orientation, `passed=true` means "exhibits the failure".
  Current always-positive on sarcastic input → passed=true; alt
  always-negative on sarcastic input → passed=false. The discrimination
  predicate `not current.passed AND alt.passed` is `not true AND false`
  = `false` for every candidate.

- *Correct run* — sample reasons:
  - *"The classifier incorrectly labeled sarcastic text with clearly
    negative intent... as positive, failing to detect the sarcasm."*
    (current → false)
  - *"The classifier correctly predicted negative sentiment despite
    the sarcastic positive surface language..."* (alt → true)

  In this orientation, `passed=true` means "handles correctly". The
  predicate fires as designed and the algorithm produces 4 cases.

The rubric prompt does not constrain orientation, so Haiku coin-flips.
This is silent — the rubric_judge response is well-formed JSON, the
reason text is coherent, no parse failure, no exception. The only
observable signal is the discrimination outcome flipping between runs.

## Implications for Feature 03 (prioritised)

1. **Pin rubric semantic orientation (highest priority).** The rubric
   prompts do not constrain whether `passed=true` means "handles
   correctly" or "exhibits failure". Either:
   (a) tighten `build_rubric_prompt` to explicitly state the
   convention — *"a system passes when its output does NOT exhibit
   the hypothesised failure"* — and embed that convention into the
   rubric body; or
   (b) move to pairwise judging (already correctly oriented per
   `pairwise_judge_prompt`) and retire the rubric path for
   discrimination, keeping rubric judging only for absolute scoring.
   (a) is the smaller change. (b) is the cleaner.
   This is a Feature 01 / Feature 03 prompt-design issue, not a
   Feature 02 issue, and is intentionally not patched in this session.

2. **Add a rubric-orientation regression test.** A live test that
   runs the pipeline at fixed seed (or, given LLM non-determinism, a
   small set of repetitions) and asserts ≥ 1 discrimination on the
   sarcasm scenario would flag a regression in either direction.
   Offline: a unit test where the rubric_judge LLM is mocked with a
   "handles correctly" payload, asserting the discrimination
   predicate fires on a current-fails / alt-passes pair.

3. **`parse_json_response` is solid; consider closing the JSON-mode
   ticket.** Zero parse failures across 43 JSON-expecting calls in a
   real run. The defence-in-depth case for Anthropic's tool-use
   structured outputs is now weaker: the extractor alone is enough.
   Park the JSON-mode work unless SMOKE_3 produces a contrary signal.

4. **Token spend is dominated by `rubric_judge` and grows linearly
   with candidate count.** This run: 36 judge calls × ~290 in-tokens
   each = ~10.7k tokens. If candidate counts grow with bigger
   hypotheses, judge cost will dominate. A pairwise judge halves the
   call count for the same evidence; cost-aware planners should
   prefer it.

5. **Generate-phase shape inference held up.** No need for Feature 03
   to add an `input_template` config field unless a non-classifier
   example surfaces shape drift in a different domain.

## Changes from SMOKE_1 to SMOKE_2

| | SMOKE_1 (2026-04-22) | SMOKE_2 (2026-04-24) |
|---|---|---|
| Backend | inline `RealAnthropicBackend` | Feature 02 `AnthropicBackend` |
| JSON parse | naive `json.loads` | `parse_json_response` 5-step ladder |
| Budget cap | 30 | 100 |
| Calls made | 1 | 44 |
| Parse failures | 1/1 (100%) | 0/43 (0%) |
| Phases reached | decompose only | decompose + generate + rubric_build + rubric_judge |
| Discriminations | 0 (parse-class halt) | 0 / 4 / 0 across 3 runs (rubric stochastic) |
| Approx cost | ~$0.001 | ~$0.04 per run, ~$0.12 across 3 runs |

The headline change: **the parse class of bug is gone, and the
algorithmic class of bug is now visible**. This is the right kind of
progress — fixing one layer exposes the next.

## Surprises

1. **Zero parse failures, including across 36+ distinct rubric_judge
   calls per run.** The fence-stripping and brace-slicing handled
   everything Haiku produced this session.

2. **Decompose gave 6 dimensions consistently across runs**, on a
   hypothesis the SMOKE_1 run never got past.

3. **Generate produced 18 candidates with a single canonical input
   shape (`{"text": ...}`) on every run.** I had braced for shape
   drift across dimensions; Haiku was uniform.

4. **The rubric inversion is a *stochastic* quiet bug.** I expected
   the inversion to be either deterministic ("the prompt is
   structurally backwards") or absent ("a one-off"). Three runs at
   2-of-3 inverted is a third possibility I did not anticipate, and
   the worst kind: the algorithm sometimes works, which is enough to
   suppress alarms but not enough to ship.

5. **The alt-runner worked perfectly across every run.** Every
   sarcastic-positive input was correctly labelled `negative`. The
   alt is not the bottleneck; the rubric is.

6. **Run 2 (the working run) found 4 discriminating cases in 44
   calls.** When the rubric is correctly oriented, the algorithm is
   surprisingly efficient — well under the budget cap and well under
   the target_n=5 even at min_required=3. This is encouraging for
   the cost-per-hypothesis claim once the rubric is pinned.

## Confidence

n=3 on this scenario, all on Haiku 4.5. The stochastic-rubric finding
should reproduce on different scenarios but the *rate* of inversion
will vary. Feature 03 should run the smoke against at least one
non-classifier scenario (RAG QA or summarisation) before declaring
the fix-shape settled, and ideally against Sonnet/Opus too — the
prompt-following gradient there may already pin the orientation.
