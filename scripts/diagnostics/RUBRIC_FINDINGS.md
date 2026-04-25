# Rubric Orientation Diagnostic — 2026-04-24

## Question

Is the rubric orientation instability from SMOKE_2 a prompt clarity problem (fixable by tightening the rubric prompts) or a structural problem with the rubric-judge primitive (requiring migration to pairwise judging)?

## Method

- Hypothesis under test: `the sentiment classifier fails on sarcastic positive text (surface tokens positive, intent negative)`
- 6 hand-crafted (input, output) pairs: items 1-4 are sarcasm-sensitive (2 exhibit-failure, 2 handle-correctly), items 5-6 are non-sarcastic sanity cases.
- N = 10 independent rubric builds per (model × prompt) cell. Each rubric applied to all 6 inputs = 70 calls per cell.
- Orientation classification, per rubric run, based on the 4 sarcasm-sensitive items: 4/4 agreement with the handles-correctly=passed=true convention → `correct`; 4/4 agreement with the reverse → `inverted`; anything else → `inconsistent`; unparseable → `malformed`.
- Cells run: (current prompt, Haiku 4.5); (current prompt, Sonnet 4.6); (tightened prompt, Haiku 4.5). Plus Part 4: pairwise judge on 3 sarcastic pairs × N=10 runs on Haiku 4.5.

## Part 1: Current prompt on Haiku 4.5

Current `build_rubric_prompt` + `rubric_judge_prompt`, unmodified. This reproduces the SMOKE_2 observation at N=10 against the rubric primitive directly (no `find_discriminating_inputs` wiring).

| run | orientation | sarcasm agreements (/4) | notes |
|---|---|---|---|
| 1 | inverted | 0 |  |
| 2 | inverted | 0 |  |
| 3 | inverted | 0 |  |
| 4 | inverted | 0 |  |
| 5 | inverted | 0 |  |
| 6 | inverted | 0 |  |
| 7 | inverted | 0 |  |
| 8 | inconsistent | 1 | item1:False; item2:False; item3:True; item4:False |
| 9 | inverted | 0 |  |
| 10 | inverted | 0 |  |

**Summary:** correct=0/10, inverted=9/10, inconsistent=1/10, malformed=0/10.

Representative judgment reasons (sarcasm-sensitive items):

- (run 1, item 1, expected_pass=False, got_passed=True): Text contains positive surface tokens ('great'), unambiguous sarcastic intent through contradiction with 'just what I needed,' would be misclassified as positive by a sentiment analyzer, and human readers clearly perceive underlying negative sentiment about the unwanted training.
- (run 1, item 2, expected_pass=True, got_passed=False): The classifier correctly identifies the true negative sentiment, but the rubric requires the classifier to mislabel it as positive/neutral for the output to pass.
- (run 1, item 3, expected_pass=False, got_passed=True): The text contains positive tokens ('love', 'best'), uses clear sarcasm through contradiction (loving tedious work), would be mislabeled as positive by a classifier, and the negative intent is unambiguous to readers.
- (run 1, item 4, expected_pass=True, got_passed=False): The classifier output is 'negative', but the rubric requires the classifier to contradict true sentiment by labeling sarcastic negative text as positive or neutral.
- (run 2, item 1, expected_pass=False, got_passed=True): All rubric criteria are satisfied: positive tokens ('great,' 'needed'), clearly negative intent (frustration about mandatory training), detectable sarcasm without context, classifier incorrectly outputs positive sentiment, and the text is realistic workplace sarcasm.

Sample rubric text (run 1):

```
# Rubric: Sarcastic Positive Text Classification

• **Contains positive surface tokens**: The text must include recognizable positive words or phrases (e.g., "great," "love," "amazing," "wonderful," "perfect") that would normally trigger positive sentiment.

• **Clear sarcastic intent**: The context or phrasing must make it unambiguous that the positive words are used ironically to express actual negative sentiment (e.g., through exaggeration, contradiction, or obvious incongruity).

• **Classifier output contradicts true sentiment**: The classifier must label the text as positive or neutral when the true underlying sentiment is clearly negative.

• **Intent mismatch is unambiguous to human readers**: A reasonable evaluator would have no doubt that the intended sentiment is negative, not positive.

• **Sarcasm is the primary mechanism**: The negative sentiment arises specifically from sarcastic inversion, not from mixed sentiments, multiple topics, or other factors that might complicate classification.
```


## Part 2: Current prompt on Sonnet 4.6

Identical prompt and inputs as Part 1. Model swap to Sonnet 4.6 tests whether prompt-following fidelity scales with capability.

| run | orientation | sarcasm agreements (/4) | notes |
|---|---|---|---|
| 1 | correct | 4 |  |
| 2 | correct | 4 |  |
| 3 | correct | 4 |  |
| 4 | correct | 4 |  |
| 5 | correct | 4 |  |
| 6 | correct | 4 |  |
| 7 | correct | 4 |  |
| 8 | correct | 4 |  |
| 9 | correct | 4 |  |
| 10 | correct | 4 |  |

**Summary:** correct=10/10, inverted=0/10, inconsistent=0/10, malformed=0/10.

Representative judgment reasons (sarcasm-sensitive items):

- (run 1, item 1, expected_pass=False, got_passed=False): The classifier labeled sarcastic negative text as positive, failing to detect the ironic intent behind 'Oh great' and 'Just what I needed today.'
- (run 1, item 2, expected_pass=True, got_passed=True): The classifier correctly identified the negative/sarcastic intent behind the overtly positive surface language, labeling it as negative.
- (run 1, item 3, expected_pass=False, got_passed=False): The classifier labeled sarcastic text with clearly negative intent as positive, violating the requirement to identify ironic/sarcastic negative intent despite positive surface language.
- (run 1, item 4, expected_pass=True, got_passed=True): The classifier correctly identified the negative/sarcastic intent behind the overtly positive surface language, labeling it as negative.
- (run 2, item 1, expected_pass=False, got_passed=False): The classifier labeled an obviously sarcastic statement ('Oh great, another mandatory training session...Just what I needed today') as positive, violating the rule against treating sarcastic positive phrases as genuinely positive sentiment.

Sample rubric text (run 1):

```
**Rubric: Sarcastic Positive Text Sentiment Classification**

- The classifier must not assign a positive sentiment label to a text that uses positive surface language to convey a clearly negative or critical intent (e.g., "Oh great, another Monday" should not be labeled positive).
- The classifier must correctly identify the negative or ironic intent in sarcastic statements that contain overtly positive words, phrases, or exclamations (e.g., "Wow, just what I always wanted!" in a clearly negative context).
- The classifier's output label must match the ground-truth negative sentiment assigned by human annotators who evaluated the underlying communicative intent, not the surface vocabulary.
- When contextual cues (e.g., hyperbole, irony markers, implausible praise) signal sarcasm, the classifier must not default to a positive label solely based on lexical sentiment scores or word-level features.
- The classifier must perform on sarcastic positive examples at a level no worse than a defined threshold (e.g., within 10 percentage points of its accuracy on straightforward negative text), demonstrating no systematic bias toward surface token polarity.
- If the classifier provides a confidence score, it must not assign high confidence (e.g., above 0.80) to a positive label for text that human annotators unanimously rated as negative in intent.
```


## Part 3: Tightened prompt on Haiku 4.5

Tightened rubric builder + judge prompts that pin `passed=true` = 'handles correctly, does NOT exhibit failure' explicitly in both the builder system message and the judge system message. The builder is also asked to embed the convention into the rubric body. See `tightened_build_rubric_prompt` and `tightened_rubric_judge_prompt` in `rubric_orientation.py`.

| run | orientation | sarcasm agreements (/4) | notes |
|---|---|---|---|
| 1 | correct | 4 |  |
| 2 | correct | 4 |  |
| 3 | correct | 4 |  |
| 4 | correct | 4 |  |
| 5 | correct | 4 |  |
| 6 | correct | 4 |  |
| 7 | correct | 4 |  |
| 8 | correct | 4 |  |
| 9 | correct | 4 |  |
| 10 | correct | 4 |  |

**Summary:** correct=10/10, inverted=0/10, inconsistent=0/10, malformed=0/10.

Representative judgment reasons (sarcasm-sensitive items):

- (run 1, item 1, expected_pass=False, got_passed=False): The classifier assigned a positive sentiment to clearly sarcastic text with negative intent, failing to recognize the speaker's displeasure about the mandatory training session.
- (run 1, item 2, expected_pass=True, got_passed=True): The classifier correctly identified the sarcastic text as negative, recognizing the speaker's true negative intent despite surface-level positive words like 'great' and 'needed'.
- (run 1, item 3, expected_pass=False, got_passed=False): The classifier assigned positive sentiment to clearly sarcastic text with negative intent, failing to detect or account for the speaker's actual criticism of the codebase.
- (run 1, item 4, expected_pass=True, got_passed=True): The classifier correctly identified the sarcastic text as negative despite surface-level positive tokens ('love', 'best'), demonstrating alignment with the speaker's true negative intent.
- (run 2, item 1, expected_pass=False, got_passed=False): The classifier misclassified sarcastic negative sentiment as positive, failing to recognize that 'Oh great' and 'Just what I needed' are sarcastic expressions masking criticism and frustration about the mandatory training.

Sample rubric text (run 1):

```
# Sentiment Classifier Sarcasm Rubric
**PASSING CONVENTION: passed=true means the classifier correctly handled sarcastic text (did NOT fail on it). passed=false means the classifier exhibited the hypothesized failure.**

• **Sarcasm Detection**: The classifier identifies or accounts for sarcasm in the input, either by explicitly flagging sarcasm or by assigning a sentiment label that reflects the actual (negative) intent rather than surface-level positive tokens alone.

• **Intent vs. Surface Alignment**: The output sentiment label aligns with the speaker's true negative intent, not the positive polarity of individual words (e.g., labels "Great job breaking that vase" as negative despite "great" and "job").

• **No False Positive Sentiment**: The classifier does not assign a positive or neutral sentiment score/label to sarcastic text that carries negative intent.

• **Explanation or Reasoning**: If the output includes any confidence score, explanation, or justification, it demonstrates awareness of the sarcastic framing rather than naive token-level sentiment averaging.

• **Consistency Across Variants**: The classifier performs similarly on common sarcasm patterns (e.g., "Oh sure, that's just perfect," "Yeah, real smart move") and does not treat one variant correctly while failing on another.
```


## Part 4: Pairwise judge baseline on Haiku 4.5

For each pair: output A is the `positive` classification (exhibits failure) and output B is the `negative` classification (handles correctly). Correct orientation = a_passed=False, b_passed=True.

| pair | rep | a_passed (expect F) | b_passed (expect T) | correctly oriented? |
|---|---|---|---|---|
| 1 | 1 | False | True | ✓ |
| 1 | 2 | False | True | ✓ |
| 1 | 3 | False | True | ✓ |
| 1 | 4 | False | True | ✓ |
| 1 | 5 | False | True | ✓ |
| 1 | 6 | False | True | ✓ |
| 1 | 7 | False | True | ✓ |
| 1 | 8 | False | True | ✓ |
| 1 | 9 | False | True | ✓ |
| 1 | 10 | False | True | ✓ |
| 2 | 1 | False | True | ✓ |
| 2 | 2 | False | True | ✓ |
| 2 | 3 | False | True | ✓ |
| 2 | 4 | False | True | ✓ |
| 2 | 5 | False | True | ✓ |
| 2 | 6 | False | True | ✓ |
| 2 | 7 | False | True | ✓ |
| 2 | 8 | False | True | ✓ |
| 2 | 9 | False | True | ✓ |
| 2 | 10 | False | True | ✓ |
| 3 | 1 | False | True | ✓ |
| 3 | 2 | False | True | ✓ |
| 3 | 3 | False | True | ✓ |
| 3 | 4 | False | True | ✓ |
| 3 | 5 | False | True | ✓ |
| 3 | 6 | False | True | ✓ |
| 3 | 7 | False | True | ✓ |
| 3 | 8 | False | True | ✓ |
| 3 | 9 | False | True | ✓ |
| 3 | 10 | False | True | ✓ |

**Summary:** 30/30 correctly oriented.

Representative reason pairs:

- pair 1 rep 1: A reason = "Output A classifies the sarcastic text as 'positive', which demonstrates the failure hypothesis. The text has positive surface tokens ('great', 'needed') but negative intent (sarcasm expressing frustration about mandatory training)."; B reason = "Output B correctly classifies the text as 'negative', properly detecting the sarcastic intent despite positive surface-level language. This does not exhibit the failure."
- pair 1 rep 2: A reason = "Output A classifies the sarcastic text as 'positive', which exhibits the failure. The text has positive surface tokens ('great', 'needed') but sarcastic intent expressing frustration and negativity."; B reason = "Output B correctly classifies the text as 'negative', capturing the sarcastic intent despite positive surface tokens. This does not exhibit the failure."
- pair 1 rep 3: A reason = "Output A predicts positive sentiment, but the text is clearly sarcastic with negative intent. The speaker is being sarcastic about a mandatory training session they don't want to attend. This output exhibits the hypothesized failure."; B reason = "Output B correctly identifies the sentiment as negative, properly recognizing the sarcastic intent despite surface-level positive words like 'great' and 'needed'. This output does not exhibit the failure."
- pair 1 rep 4: A reason = "Output A predicts positive sentiment, which matches the failure hypothesis. The text contains sarcasm with surface-level positive tokens ('great', 'needed') but negative intent, and the classifier incorrectly classified it as positive."; B reason = 'Output B predicts negative sentiment, which correctly identifies the sarcastic intent despite the superficially positive tokens. This does not exhibit the failure described in the hypothesis.'

## Synthesis

Headline numbers across the four cells:

| cell | model | prompt | correct/N |
|---|---|---|---|
| Part 1 | Haiku 4.5 | current rubric | 0 / 10 |
| Part 2 | Sonnet 4.6 | current rubric | 10 / 10 |
| Part 3 | Haiku 4.5 | tightened rubric | 10 / 10 |
| Part 4 | Haiku 4.5 | pairwise (already pinned) | 30 / 30 |

Three claims supported by the data:

1. **The current `build_rubric_prompt` is not just stochastic on Haiku — it is reliably *inverted*.** SMOKE_2's n=3 sample gave 1/3 correct ("stochastic"). N=10 here gives 0/10 correct (9 fully inverted, 1 inconsistent at 1/4 sarcasm-agreement). The direction matches SMOKE_2; the rate is stronger. The most likely explanation for the SMOKE_2 vs. diagnostic discrepancy is sample variance — at a true rate of ~5% correct, P(≥1 of 3 correct) is ~14%, well within the chance of seeing 1/3 on a single afternoon. There is no evidence here for "rubric-judge in isolation behaves differently than rubric-judge wired through `find_discriminating_inputs`"; both cases are dominated by inversion. Read the run-1 sample rubric in Part 1 to see why: Haiku writes the criteria as descriptions of *what the failure looks like* ("Contains positive surface tokens", "Classifier output contradicts true sentiment"), so a downstream judge naturally reads "satisfies all criteria" → "exhibits the failure" → `passed=true`.

2. **Prompt-following fidelity scales with model capability on the unmodified prompt.** Sonnet 4.6 with the *current* prompt is 10/10 correct. The semantic ambiguity that breaks Haiku is one Sonnet resolves silently. Sonnet's run-1 rubric (Part 2 sample) is also written from the "criteria the system must satisfy to handle the case correctly" framing rather than the "criteria the failure exhibits" framing — i.e. Sonnet is making a different, correct interpretive choice from the same underlying prompt.

3. **The structural primitive is fine; the prompt wording is the problem.** Path B (pairwise) was 30/30 on Haiku, but Path A (rubric prompt explicitly pinned) was *also* 10/10 on Haiku at the same model tier. The structural change (migrate to pairwise) is not required by the data. The cheaper change (rewrite ~6 lines of `build_rubric_prompt` and `rubric_judge_prompt`) is sufficient.

A note on what this experiment did *not* test: only one hypothesis (sarcasm classifier) and one model below Sonnet (Haiku 4.5). A weaker sarcasm signal or a more abstract failure mode could re-introduce ambiguity even with the tightened prompt. The recommendation below is conditional on this caveat.

## Recommendation

**Path A (tighten the rubric prompt).** The tightened prompt pins orientation on Haiku at the ceiling (10/10), which means the smallest-possible change to `src/hypothesize/core/prompts.py` resolves the SMOKE_2 finding without disturbing the pipeline shape. Pairwise is also a clean win on Haiku (30/30) and remains available as a fallback if a future scenario surfaces a Path-A regression.

- **Evidence basis (most decisive):** Part 3 = 10/10 correct on Haiku 4.5, vs. Part 1 = 0/10 on the same model with the unmodified prompt. The delta is the prompt; nothing else changed.
- **Concrete change implied:**
  1. Rewrite `build_rubric_prompt` to (a) state the convention `passed=true = handles correctly, does NOT exhibit failure` in the system message, (b) instruct the builder to embed that convention into the rubric body, and (c) frame criteria as "system must satisfy ___" rather than "failure looks like ___". The Part 3 wording in `scripts/diagnostics/rubric_orientation.py` is a working draft; the production version should match its semantics, not its exact prose.
  2. Rewrite `rubric_judge_prompt` to repeat the convention in the judge's system message (`CRITICAL: passed=true means ...`). This is belt-and-suspenders against rubrics that omit the convention header.
  3. Add a regression test (offline, mocked LLM) that pins the discrimination predicate's orientation. SMOKE_2 already documented the desired test shape; this experiment confirms it is the right test.
- **Risks:**
  - One hypothesis tested (sarcasm). A weaker-signal failure mode (e.g. RAG hallucination scoring) could re-introduce ambiguity even with the tightened prompt. Mitigation: re-run a smoke against a non-classifier scenario after the fix lands.
  - Tightening the prompt costs ~4 input tokens per call but does not increase Haiku's output length materially (Part 3 output tokens were 6,073 vs. Part 1's 5,607 — a 446-token bump across 70 calls, ≈ $0.004 in incremental Haiku cost per pipeline run). Negligible.
- **Conditions that would flip the recommendation to Path B:**
  - A second hypothesis where the tightened prompt drops below ~8/10 on Haiku, *and* pairwise stays ≥28/30 on the same scenario.
  - Or: a future need for confidence-graded scoring rather than binary pass/fail, which is awkward in pairwise (only relative confidence is observable) and natural in rubric.

## Cost accounting

- Part 1 (Haiku current): calls=70 input_tokens=19920 output_tokens=5607
- Part 2 (Sonnet current): calls=70 input_tokens=23002 output_tokens=5404
- Part 3 (Haiku tightened): calls=70 input_tokens=27860 output_tokens=6073
- Part 4 (Haiku pairwise): calls=30 input_tokens=4350 output_tokens=4333
- Wall time: 427.8s
