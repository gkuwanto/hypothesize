# Smoke Test Findings — 2026-04-22

Live run of `scripts/smoke_test.py` against the real Anthropic API. Model:
`claude-haiku-4-5-20251001`. Wall time: 6.7s. Exit code: 0.

## Ran successfully?

**Partially.** The script itself ran cleanly — no Python exceptions, no API
errors, exit code 0. But the discrimination algorithm produced
`insufficient_evidence` on the very first LLM call because Haiku's response
failed to parse as JSON. Budget used: **1 of 30**. The algorithm never
proceeded past `decompose_hypothesis`; generate, rubric-build, and judge were
never invoked. Alt-runner was never called.

This is exactly the class of failure the smoke test was built to find: the
gap between `MockBackend` (which always returns clean scripted JSON) and real
Claude (which does not).

## Root cause: markdown code fences around JSON

The decompose prompt explicitly instructs "Return STRICT JSON... No prose
outside the JSON object." Haiku nevertheless returned:

```
```json
{
  "dimensions": [
    {
      "name": "Sarcasm Signal Strength",
      ...
    },
    ...
  ]
}
```
```

The core code does `json.loads(raw)` without stripping the ` ```json ` /
` ``` ` fences. `json.loads` rejects the entire string, `decompose_hypothesis`
returns `[]`, and `find_discriminating_inputs` cascades to
`InsufficientEvidence` with the reason *"decomposition failed: expected 3-7
probing dimensions from the LLM"*. The content inside the fences actually
looks well-formed and semantically on-topic (see below) — the problem is
purely structural framing.

## Dimensions returned

None made it into `ProbingDimension` objects because of the parse failure,
but the raw response shows Haiku did produce reasonable-looking dimensions.
Visible from the first 500-char dump:

- **Sarcasm Signal Strength** — degree of incongruity between surface
  positive and underlying negative intent
- **Contextual Clues Avai[lable]** — (cut off at 500 chars; likely
  "Contextual Clues Available")

Full dimension count unknown (response truncated in the stderr preview at
200 chars and in the findings dump at 500 chars), but at least 2 were well
under way and the structure looked consistent.

Quality impression from the two visible dimensions: **good**. They are
distinct, on-topic for the hypothesis, and include concrete examples. If
the parse had succeeded, the decomposition step would probably have
produced workable dimensions for the downstream pipeline.

## JSON parse cleanliness

**1 of 1 JSON-expected responses failed to parse** (100% failure rate in
this run, though n=1 so the rate itself isn't robust). The failure mode
was markdown code fencing, not malformed JSON. The content within the
fences is believed to be valid — spot-check of the visible prefix shows
proper `{` / `"key"` / `[` structure.

## Candidate input_data shapes

Not observed — no generate calls were made. We have zero data on what
shape Claude invents for `input_data` in the generate step. This is the
next diagnostic worth running once the fence issue is resolved.

## Discrimination result

- Status: `insufficient_evidence`
- Reason: `decomposition failed: expected 3-7 probing dimensions from the LLM`
- Candidates tried: 0
- Discriminating found: 0

## Budget usage

| Phase | Calls |
|---|---|
| decompose | 1 |
| generate | 0 |
| rubric_build | 0 |
| rubric_judge | 0 |
| **core total** | **1 / 30** |
| alt_runner | 0 (not counted) |

Budget accounting itself worked correctly — `decompose_hypothesis` charged
1 call and stopped.

## Surprises

1. **Haiku adds markdown fences even when the prompt says "no prose outside
   the JSON".** Prompt engineering alone did not prevent this. I expected
   prompt instructions to carry more weight than they did.
2. **The failure surfaced on the very first call.** I had assumed we'd get
   through decomposition and hit issues later (in generate or judge). The
   strictness of `json.loads` at the earliest parsing boundary means a
   single wrapping convention kills the entire pipeline.
3. **Content quality is fine.** The model isn't confused about the task —
   it produces plausible dimensions with useful examples. The bug is purely
   in how the output is framed, not what's in it.
4. **Haiku appended no trailing prose after the closing fence** (based on
   what we can see). Some models add "Here is the JSON:" prefaces or
   explanatory suffixes; Haiku kept itself confined to the fenced block.
   That's good news — a simple fence-stripping helper should be enough.

## Implications for Feature 02

Prioritized, most important first:

1. **Add JSON extraction robustness.** The core's three JSON parsing sites
   (`decompose.py`, `generate.py`, `judge.py`) all do naive `json.loads`.
   Before Feature 02 touches a real LLM it needs either:
   - A `_extract_json(raw: str) -> str | None` helper that strips
     ` ```json ` / ` ``` ` fences and any leading/trailing prose, then
     falls through to `json.loads`; **or**
   - Use of Anthropic's structured-output / JSON-mode feature if it is
     available for Haiku (verify before committing — newer API revisions
     may expose it via a request parameter).

   The helper approach is portable across models; the JSON-mode approach
   eliminates the class of bug entirely if supported. Prefer JSON mode
   where available, with fence-stripping as a defence-in-depth fallback.

2. **Consider a single retry on parse failure.** If `json.loads` fails
   after extraction, a follow-up call with `"your previous response was
   not pure JSON; return only the JSON object this time"` in the user
   turn often recovers, at the cost of one extra LLM call per failure.
   Worth tracking how often this fires; if it's rare it's a cheap
   resilience measure, if it's common the extraction helper isn't working
   and you've masked a deeper bug.

3. **Re-run the smoke test after any fix.** The current run saw only
   decompose; we have no data on generate's `input_data` shape choices,
   rubric-judge's JSON habits, or how RubricJudge behaves end-to-end on
   real inputs. A second smoke pass (same scenario, Feature 02's real
   backend) is needed before assuming the pipeline works. The
   `scripts/smoke_test.py` file here is reusable — just swap the inline
   `RealAnthropicBackend` for Feature 02's production backend.

4. **Audit every prompt for "strict JSON" language.** The prompt
   instructions are not enforceable. Feature 02 should treat the prompt
   as a best-effort hint and the parser as the contract. Do not ship
   believing the prompt will make Claude comply.

5. **Test across models.** This run was Haiku only. Sonnet/Opus may not
   wrap in fences, or may wrap differently. If Feature 02 supports a
   model override, the smoke test should be re-run on each model that
   appears in documented supported lists.

6. **Low confidence, one data point.** n=1 for the JSON-fencing
   observation. A second run could in principle return clean JSON and
   this whole finding would look like noise. I rate that unlikely
   (markdown fencing is a well-known Claude default behavior), but
   Feature 02's test plan should not treat this report as proof of a
   reproducible 100% failure rate.
