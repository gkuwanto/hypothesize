# Smoke Test Findings — 2026-04-24 (SMOKE_3 — rubric orientation fix verification)

Live re-runs of `scripts/smoke_test.py` against the real Anthropic API
with the tightened `build_rubric_prompt` / `rubric_judge_prompt` (Path A
from `scripts/diagnostics/RUBRIC_FINDINGS.md`). Two scenarios back-to-back
per session, each with a 100-call core budget. Two full sessions were
run to check reproducibility.

Model: `claude-haiku-4-5-20251001` for all scenarios and both
current/alternative runners.

This document is the third-run companion to
[`SMOKE_FINDINGS_2.md`](./SMOKE_FINDINGS_2.md) — read that one first for
the rubric orientation bug it documents, which is what SMOKE_3 is
verifying is fixed.

## Date and context

- Date: 2026-04-24
- What changed since SMOKE_2:
  - `src/hypothesize/core/prompts.py::build_rubric_prompt` and
    `::rubric_judge_prompt` rewritten to pin the orientation convention
    (`passed=true = handles correctly, does NOT exhibit failure`)
    explicitly in both the builder and judge system messages, using the
    Part 3 wording from the diagnostic.
  - `build_rubric_prompt` additionally instructs the model to write
    rubric criteria as success-descriptors ("classifier correctly
    identifies...") rather than failure-descriptors ("classifier
    contradicts true sentiment...").
  - Added `tests/core/test_rubric_orientation_regression.py` — four
    offline, `MockBackend`-driven tests that pin the discrimination
    predicate against a fixed-orientation judge payload contract.
  - Refactored `scripts/smoke_test.py` into a `Scenario` dataclass that
    runs two scenarios back-to-back, each with its own 100-call core
    budget: the original sarcasm classifier plus a new summarization
    scenario that tests non-classifier (free-text) output.

## Run results: sarcasm scenario

Comparison with SMOKE_2 three-run baseline:

| Run | Status | Discriminating | Parse failures | Budget used | Wall time |
|---|---|---|---|---|---|
| SMOKE_2 run 1 | `insufficient_evidence` | 0 / 18 | 0 / 43 | 44 / 100 | ~97s |
| SMOKE_2 run 2 | `ok` | 4 / 18 | 0 / 43 | 44 / 100 | ~97s |
| SMOKE_2 run 3 | `insufficient_evidence` | 0 / 18 | 0 / 43 | 44 / 100 | ~97s |
| **SMOKE_3 run 1** | `ok` | **5 / 5** (capped at target_n) | 0 / 43 | 44 / 100 | 88.5s |
| **SMOKE_3 run 2** | `ok` | **5 / 7** (capped at target_n) | 0 / 49 | 51 / 100 | 97.8s |

Notes on SMOKE_3 sarcasm runs:

- Run 1: 6 decomposed dimensions, 18 candidates generated, 36 rubric_judge
  calls, 5 discriminating cases captured (diversity-pruned to target_n).
- Run 2: 7 decomposed dimensions, 21 candidates generated, 42 rubric_judge
  calls, 5 discriminating cases captured. (Dimensions varied between runs
  — decompose is itself non-deterministic — but both runs produced
  abundant discriminations.)
- No inverted verdicts in either run. Every sarcastic-positive input was
  judged `passed=false` on the current (always-positive) system and
  `passed=true` on the sarcasm-aware alternative.

## Run results: non-classifier scenario (summarization: entity preservation)

This scenario is new in SMOKE_3 — no SMOKE_2 baseline. Hypothesis: "the
summarizer fails to preserve named entities — people, places,
organizations — mentioned in the source document, dropping them in favor
of generic nouns." Current runner: terse one-sentence summary with no
entity instruction. Alternative runner: one-sentence summary with
explicit instruction to preserve every named entity.

| Run | Status | Discriminating | Parse failures | Budget used | Wall time |
|---|---|---|---|---|---|
| SMOKE_3 run 1 | `ok` | **5 / 5** (capped at target_n) | 0 / 49 | 51 / 100 | 138.0s |
| SMOKE_3 run 2 | `ok` | **5 / 5** (capped at target_n) | 0 / 49 | 51 / 100 | 125.6s |

Notes:

- Run 1 produced 7 decomposed dimensions (entity density, entity type
  variety, entity prominence, paraphrasability, token budget pressure,
  salience, reference chains) and 21 candidates — mostly
  `{"text": "..."}` but 3 candidates used a richer
  `{"source_text", "compression_ratio", "source_word_count",
  "target_word_count"}` shape. Both shapes ran cleanly through the alt
  runner and the rubric judge.
- Run 2 produced 7 dimensions (a slightly different set — entity type
  variety, entity prominence, entity density, paraphrase opportunity,
  document length, syntactic role, familiarity) and 21 candidates — all
  `{"text": "..."}` this time.
- The summarization alt runner was more verbose than the sarcasm alt
  runner (42 alt calls per scenario vs. 18-21 for sarcasm), because each
  candidate triggers two alt-runner calls (one for current, one for
  alternative) instead of one (current is deterministic in sarcasm).
  This inflates the alt-backend call count but does not hit the core
  budget.
- Every discriminating case captured had an alternative summary that
  preserved the named entities verbatim where the current summary
  generalized — "Dr. James Mitchell from the Mayo Clinic" vs.
  "Researchers from Mayo Clinic", "Tim Cook, Satya Nadella, Sundar
  Pichai" vs. "executives". The rubric judge correctly flagged the
  failure on the current output and the correct handling on the
  alternative output.

## Orientation analysis

Explicit verification that judgments are correctly oriented. Three
representative `rubric_judge.reason` quotes per scenario:

**Sarcasm scenario (run 1 & run 2 combined):**

1. *"The classifier misclassified sarcastic text with surface-level
   positive words ('wonderful', 'love') as genuinely positive, failing
   to recognize the negative communicative intent despite clear
   sarcastic markers."* — `passed=False`, on a current-runner output.
   Correct orientation: the failure is being identified as failure.
2. *"The classifier correctly identified the sarcastic text as negative
   sentiment, matching the actual critical intent rather than the
   surface-level positive words."* — `passed=True`, on an
   alternative-runner output. Correct orientation: handles-correctly is
   being identified as pass.
3. *"The system correctly identified the underlying negative sentiment
   despite surface-positive words ('wonderful,' 'perfect'), recognizing
   the sarcastic complaint about an intrusive late-night work email."*
   — `passed=True` on alt. Consistent with the convention.

**Summarization scenario:**

1. *"The summary drops specific person names (Tim Cook, Satya Nadella,
   Sundar Pichai) and specific universities (Stanford University, MIT,
   UC Berkeley), replacing them with generic terms like 'executives'
   and 'leading university researchers.'"* — `passed=False` on a
   current-runner output. Correct: the entity-dropping failure is
   flagged as failure.
2. *"The summary preserves all critical named entities (Dr. James
   Mitchell, Mayo Clinic, Rochester, Stanford University, Nature
   Medicine, Moderna) without substituting generic nouns or pronouns."*
   — `passed=True` on an alt output. Correct: entity preservation is
   flagged as pass.
3. *"The summary omits the named entity 'Pierre Curie' who was
   explicitly mentioned as a collaborator in the source document,
   failing to preserve all proper names central..."* — `passed=False`
   on a current output. Correct.

The tightened rubric build outputs also consistently include an explicit
convention header. From SMOKE_3 run 1 sarcasm rubric:

> *"Convention: passed=true means the classifier correctly handled
> sarcasm and did NOT exhibit the hypothesized failure (misclassifying
> sarcastic positive text as genuinely positive). Criteria below describe
> correct behavior."*

From SMOKE_3 run 2 summarization rubric:

> *"Convention: passed=true means the summary correctly preserves named
> entities and does NOT exhibit the hypothesized failure. passed=false
> means named entities were dropped or replaced with generic nouns."*

Both rubrics also write criteria as success-descriptors ("Detects
underlying negative intent despite positive surface tokens"; "Proper
names retained"). Both the builder-convention-embedding requirement and
the success-descriptor-framing requirement from the tightened prompt
are being followed by Haiku.

No inverted verdicts observed across 168 total `rubric_judge` calls
(36 + 42 + 42 + 42 across both scenarios × both runs) and 4 rubric
builds. SMOKE_2's stochastic inversion is absent.

## Cost

SMOKE_3 session LLM spend. Core backend = calls charged against the
discrimination budget; alt backend = separate runner calls (not charged
against core budget, but real API spend).

### Core-backend token totals

| | SMOKE_3 run 1 | SMOKE_3 run 2 |
|---|---|---|
| sarcasm: decompose | 1 call, 177 in / 728 out | 1 call, 177 in / 979 out |
| sarcasm: generate | 6 calls, 1,816 in / 2,182 out | 7 calls, 2,224 in / 2,519 out |
| sarcasm: rubric_build | 1 call, 263 in / 275 out | 1 call, 263 in / 322 out |
| sarcasm: rubric_judge | 36 calls, 15,782 in / 1,979 out | 42 calls, 20,440 in / 2,465 out |
| summ: decompose | 1 call, 222 in / 932 out | 1 call, 222 in / 950 out |
| summ: generate | 7 calls, 2,516 in / 4,296 out | 7 calls, 2,549 in / 3,700 out |
| summ: rubric_build | 1 call, 274 in / 325 out | 1 call, 274 in / 332 out |
| summ: rubric_judge | 42 calls, 24,120 in / 2,880 out | 42 calls, 23,642 in / 2,667 out |
| **TOTAL core** | **95 calls, 45,170 in / 13,597 out** | **102 calls, 49,791 in / 13,934 out** |
| alt-runner (both scenarios) | 60 calls | 63 calls |

### Approximate session cost (Haiku 4.5)

At ~$1 per 1M input tokens and ~$5 per 1M output tokens:

- Run 1 core: ~$0.045 in + ~$0.068 out ≈ **$0.11**
- Run 2 core: ~$0.050 in + ~$0.070 out ≈ **$0.12**
- Alt-runner: ~$0.02 per run (short prompts and responses)
- **Total SMOKE_3 spend: ~$0.26 across both runs and both scenarios**

Combined with the prior diagnostic session (~$1.50), the cumulative
cost of investigating and fixing the rubric orientation bug is about
**$1.80**.

## Verdict

**Fixed.** Across 4 scenario-runs (2 scenarios × 2 sessions), every run
completed end-to-end with a correctly-oriented rubric, zero parse
failures, and a `status=ok` discrimination result at target_n=5. Both
scenarios hit the discrimination-found-enough branch and returned the
maximum configured 5 test cases. Compared to SMOKE_2's 0/4/0 pattern on
sarcasm (two out of three runs inverted), SMOKE_3 is **5/5 on both
runs** on the same scenario and model tier. The diagnostic's prediction
(10/10 correct on Haiku with the tightened prompt) matches the smoke
behavior — none of the 4 scenario-runs showed any sign of inversion.

The non-classifier scenario additionally clears the generality concern
the diagnostic flagged as a caveat: the tightened prompt is not
sarcasm-specific — it holds up on a summarization-shaped task with
free-text output and an entirely different failure mechanism (entity
loss), with the same 0-inversion record.

## Open questions

1. **Sonnet on the tightened prompt was not tested this session.** The
   diagnostic confirmed Sonnet is 10/10 on the *unmodified* prompt; the
   tightened prompt should be at least as good (it is strictly more
   constraining in the right direction), but not verified empirically.
   Feature 03 should confirm on a single Sonnet smoke run before the
   first external dataset release.
2. **Haiku on a third failure class still untested.** SMOKE_3 covers
   classification (sarcasm) and free-text generation (summarization).
   RAG QA, tool-use correctness, and multi-turn consistency are all
   different shapes. Feature 03 should run a smoke on at least one RAG
   scenario before declaring the rubric primitive production-ready for
   arbitrary hypotheses.
3. **Summarization alt-runner overhead.** Each candidate triggers two
   alt-runner calls in this scenario (both current and alt are LLM
   calls), which inflates the total session call count. This is a
   smoke-test artifact, not an algorithm issue, but Feature 03 may want
   to make the alt-backend/budget boundary more visible in observability.
4. **Entity-preservation rubric leans on the word "critical".** The run
   2 summarization rubric_judge reasons start with "all critical named
   entities" — rubric correctness under the tightened prompt is not in
   question, but the word "critical" hints that the rubric is allowing
   the judge to ignore some minor entities. That is a rubric-quality
   question, not an orientation question, and is out of scope for this
   fix session.
