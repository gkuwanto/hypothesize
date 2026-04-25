---
name: hypothesize
description: |
  Turn a developer's vague complaint about an LLM-backed system into a
  set of failing regression tests. Invoke when the user describes a
  system that "seems to fail at" something, mentions a stakeholder
  complaint about an LLM behavior, or asks for help building tests
  for a known failure mode.
---

# hypothesize

Hypothesize generates **discriminating** test cases — inputs where
the user's current system fails and a plausibly-better alternative
succeeds. The output is a YAML file that lives in the user's repo
as a regression suite. Past tests can be re-validated with
`hypothesize validate`.

The tool is designed for the most common day-to-day case: a
stakeholder complains, an engineer wants to verify the complaint
and produce a targeted regression test in under a few minutes and
under a dollar of tokens.

## When to invoke

Trigger phrases:

- "my classifier gets X wrong"
- "the model fails when..."
- "the agent ignores Y"
- "stakeholder is complaining that..."
- "I want regression tests for..."
- "help me catch when the system breaks on..."

If the user describes a complaint about an LLM-backed system in
their repo, this skill is probably the right answer. If the user
explicitly asks for comprehensive evals (broad coverage), defer to
other tools — hypothesize optimizes for *minimum discriminating*
sets, not coverage.

## Workflow

### 1. Clarify the complaint into a hypothesis

A hypothesis is a single sentence naming a specific class of input
the system handles incorrectly. Examples:

- "the classifier mislabels sarcastic positive text as positive"
- "the summarizer drops named entities in favor of generic nouns"
- "the QA agent answers from the first retrieved doc and ignores
  the second"

If the user's complaint is already this specific, use it. If not,
ask one or two clarifying questions:

- "What should the system do correctly that it's failing at?"
- "Do you have a small example that triggers the failure?"

Do not invent specifics the user has not given you. A vague
hypothesis produces vague test cases.

### 2. Identify the system

Look for a `config.yaml` in the repo:

- Top level (`./config.yaml`)
- `examples/<name>/config.yaml`
- `hypothesize/<name>/config.yaml`

If you find one, confirm with the user before proceeding ("Run
against `examples/sarcasm/config.yaml`?"). If you find several,
ask which.

If no config exists, tell the user that hypothesize needs a config
pointing at their system, and offer to draft one based on the
existing code. The config shape is documented in
`examples/sarcasm/config.yaml`.

### 3. Run the discrimination

Invoke the CLI:

```
hypothesize run \
  --config <path> \
  --hypothesis "<hypothesis text>"
```

Default budget is 100 calls and target-n is 5 — fine for most
cases. Pass `--budget 200` if the user wants more thorough
exploration. Wall time is typically 60-90 seconds. Cost is usually
under $0.20 with Haiku, under $1 with Opus.

### 4. Surface the results

When the run completes, tell the user:

- How many discriminating cases were found
- Where the YAML was written
- One representative case (input + why it discriminates)

Read the output YAML. Show the user a representative `test_cases`
entry — its `input`, the `expected_behavior`, and a one-line summary
of `discrimination_evidence` (what the current system did vs. what
the alternative did).

If the run returned `insufficient_evidence`, do not silently treat
it as a failure of the tool. Tell the user:

> Hypothesize tried N candidates but found only M discriminating
> ones. The hypothesis may be wrong, or the alternative may not
> actually be better. Want to revise the hypothesis?

### 5. Optional follow-up: draft a fix

The user may ask you to draft a fixed system prompt based on the
discriminating cases. This is an extension, not part of
hypothesize itself. Read the test cases, propose a prompt edit,
and offer to test it by re-running hypothesize against the new
prompt.

## Example invocations

```
hypothesize run \
  --config examples/sarcasm/config.yaml \
  --hypothesis "the sentiment classifier mislabels sarcastic positive text"
```

```
hypothesize list .
```

```
hypothesize validate tests/discriminating/sarcasm_2026_04_26.yaml
```

```
# Larger budget for thorough exploration
hypothesize run --config <path> --hypothesis "<text>" --budget 200
```

```
# Custom output location
hypothesize run --config <path> --hypothesis "<text>" \
  --output tests/regressions/my_failure.yaml
```

## Failure modes

- **Config not found**: Show the user the search paths
  (`./config.yaml`, `examples/*/config.yaml`,
  `hypothesize/*/config.yaml`) and ask where their config lives.
- **`system.py` raises during load**: Surface the exception
  message. The user has a bug in their `system.py`; they fix it,
  you re-run.
- **`insufficient_evidence`**: See workflow step 4. This is a
  signal, not a tool failure.
- **Budget exhausted**: Re-invoke with `--budget 200`.
- **`AutoAlternativeUnavailable`**: The user's `system.py` doesn't
  expose `make_runner(prompt=None)`. Either ask them to add it, or
  point `alternative` at another system in the config (an explicit
  `python_module` adapter pointing at a different file).
- **Exit code 3 (runtime error)**: Something in the user's runner
  or their backend setup raised. Surface the exception type and
  message; ask the user to triage.

## What NOT to do

- Do not re-run with a different hypothesis without confirming
  with the user first. The user owns the hypothesis; the tool's
  job is to discriminate against it, not to invent alternatives.
- Do not modify the user's `system.py` automatically. Even if the
  discriminating cases obviously suggest a fix, propose the fix
  and let the user apply it.
- Do not run hypothesize when the user just wants a single ad-hoc
  test case. Hypothesize generates *sets* via an LLM-driven loop
  — it costs real tokens.
