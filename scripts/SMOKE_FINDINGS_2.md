# Smoke Test Findings — 2026-04-24 (run 2)

Live re-run of `scripts/smoke_test.py` against the real Anthropic API, now
through Feature 02's `AnthropicBackend` and `parse_json_response`. Model:
`claude-haiku-4-5-20251001`. Wall time: 97.1s. Exit code: 0. Budget cap
raised from 30 to 100 per the task spec.

This document is the second-run companion to
[`SMOKE_FINDINGS.md`](./SMOKE_FINDINGS.md). Read that one first for the
parse-class baseline and Feature 02's motivation.

## Ran successfully?

**Yes — end to end.** No Python exceptions, no API errors, no parse
failures, exit 0. The discrimination algorithm reached the generate
phase, the rubric-build phase, and the rubric-judge phase. Decompose,
generate, and judge all returned cleanly-typed payloads.

But the algorithm produced `insufficient_evidence`: **0 of 18 candidates
were discriminating**. The pipeline is wired correctly — the *result*
exposes a different and more consequential class of issue, surfaced
only because parse-class noise no longer hides it. See "New failure
class" below.

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

## Discrimination outcome

- Status: `insufficient_evidence`
- Reason: *"Found only 0 discriminating inputs after trying 18
  candidates. Hypothesis may be wrong or alternative may not improve."*
- Candidates tried: 18
- Discriminating found: 0

Every alt-runner output was `negative` (the alt is doing its job —
detecting sarcasm and labelling correctly). Every current-runner output
was `positive` (also as designed — the deliberately broken classifier).
The hypothesis is true, the alternative is better, and yet zero
discriminations were flagged. That is the new finding.

## New failure class — rubric semantic inversion

The rubric Claude generates from `build_rubric_prompt` semantically
inverts what the discrimination loop expects.

`discrimination.py` uses:

```python
if not current_verdict.passed and alt_verdict.passed:
    discriminating.append(...)
```

This is consistent with `pairwise_judge_prompt`'s explicit doc-string —
*"decide whether it passes (does NOT exhibit the failure)"* — i.e.
**`passed=true` means "system handles the case correctly"**.

But `build_rubric_prompt` and `rubric_judge_prompt` do not pin the
semantic. They say "An output passes only if it satisfies all criteria"
without specifying what the criteria should encode. Real Haiku
interpreted "satisfies the criteria of the failure hypothesis" as
**"exhibits the failure pattern"**. Sample rubric-judge reasons from
this run, verbatim:

- *"The classifier output is 'negative', but the rubric requires the
  classifier to misclassify sarcastic text as positive."* (alt → false)
- *"The classifier correctly identified the sentiment as negative, but
  the rubric requires the classifier to misclassify..."* (alt → false)
- *"The input contains unambiguous sarcasm... [the system]
  misclassified..."* — passed=true (current → true)

So in this run:

- current (always positive on sarcastic input) → passed=`true`
- alt (negative on sarcastic input)            → passed=`false`

Discrimination predicate `not current.passed AND alt.passed`
= `not true AND false`
= `false` — for every candidate.

Net effect: a *correctly working* alternative against a *demonstrably
broken* current produces **zero** discriminating cases. This is a
silent algorithmic failure — the parse-class fix removed the previous
loud failure and let this quieter one surface.

## Implications for Feature 03 (prioritised)

1. **Fix rubric semantic inversion (highest priority).** Either:
   (a) tighten `build_rubric_prompt` to explicitly encode "passes iff
   handles correctly", with the failure pattern stated in the
   negative; or (b) flip the discrimination predicate to match the
   "passed iff exhibits failure" semantics; or (c) move to pairwise
   judging (already correctly oriented per `pairwise_judge_prompt`)
   and retire the current rubric path. (a) is the smallest change.
   (c) is the cleanest. Either way, this is a Feature 01 / Feature 03
   prompt-design issue, not a Feature 02 issue, and is intentionally
   not patched in this session.

2. **Add a rubric-orientation regression test.** Write a unit test
   that, given a fixture rubric and a clearly-correct vs.
   clearly-broken pair, asserts the discrimination predicate flags
   the broken side. The test should fail on this run's behaviour and
   pass after the fix. Use `MockBackend` so it lives in the offline
   suite.

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
| Discriminations | 0 (parse-class halt) | 0 (semantic inversion) |
| Approx cost | ~$0.001 | ~$0.04 |

The headline change: **the parse class of bug is gone, and the
algorithmic class of bug is now visible**. This is the right kind of
progress — fixing one layer exposes the next.

## Surprises

1. **Zero parse failures, including across 36 distinct rubric_judge
   calls.** I expected at least a few transient framing oddities;
   none materialised. The fence-stripping and brace-slicing handled
   everything Haiku produced this session.

2. **Decompose gave 6 dimensions on a hypothesis the SMOKE_1 run
   never got past.** The visible prefix in SMOKE_1 hinted the content
   would be good; it is.

3. **Generate produced 18 candidates with a single canonical input
   shape.** I had braced for shape drift across dimensions; Haiku
   was uniform.

4. **The rubric inversion is a quiet bug.** Both `current` and `alt`
   judge cleanly with `passed: bool` and a coherent reason — there is
   no parse failure, no exception, no log noise. The only signal is
   that `discriminating_found = 0`. A more ambiguous scenario could
   easily mask this entirely.

5. **The alt-runner worked perfectly.** Every sarcastic-positive input
   was correctly labelled `negative`. The alt is not the bottleneck;
   the rubric is.

## Confidence

n=1 still — one full pipeline run on one scenario. The rubric inversion
finding is the kind of bug that should reproduce reliably across runs
(it is structural in the prompt, not stochastic). But before declaring
the fix-shape settled, Feature 03 should reproduce SMOKE_2 behaviour on
at least one non-classifier scenario (RAG QA or summarisation) to
verify the inversion isn't peculiar to the sentiment domain.
