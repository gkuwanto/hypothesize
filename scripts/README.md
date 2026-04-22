# scripts/

One-off diagnostic and operations scripts. Not part of the product
package, not run by pytest, not imported from `src/hypothesize/`. These
files exist to be run by a human and to inform later design work.

## smoke_test.py

`smoke_test.py` exercises `find_discriminating_inputs` against the real
Anthropic API. Its purpose is to surface everything `MockBackend` cannot
simulate: whether Claude's JSON outputs actually parse, what
`input_data` shapes the candidate generator invents, whether the rubric
judge degrades gracefully on messy real responses, and how the budget
breakdown distributes across phases in practice. The findings from
running it inform Feature 02's design — especially around JSON-mode
output, input-shape inference, and real-backend error handling. Do not
generalize the inline `RealAnthropicBackend`; Feature 02 will design the
production backend with its own spec.

Run from the repo root with a real API key:

```
export ANTHROPIC_API_KEY=sk-ant-...
python scripts/smoke_test.py
```

It uses `claude-haiku-4-5-20251001`, caps the core algorithm at 30 LLM
calls, and should complete in under 60 seconds of wall time. Each LLM
call's first 200 characters are streamed to stderr as they happen.
After the run, read `scripts/SMOKE_FINDINGS.md` for the structured
findings that informed Feature 02.
