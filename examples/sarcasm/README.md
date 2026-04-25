# Example: sarcasm sentiment classifier

A deliberately weak sentiment classifier paired with a sarcasm
hypothesis. Walks through hypothesize end-to-end in about 60-90
seconds.

## What this demonstrates

The baseline prompt in `system.py` is one line: "Reply with positive
or negative". It has no guidance on sarcasm. The hypothesis says
sarcastic positive text — surface tokens positive, intent negative —
breaks this classifier. Hypothesize uses the auto-alternative path
to rewrite the prompt mitigating the hypothesis, generates candidate
inputs across several probing dimensions, and discriminates between
the baseline and the rewritten alternative.

When everything is working, the run produces 5 test cases — sarcastic
inputs the baseline classifier misses but the rewritten alternative
catches.

## Prerequisites

```bash
# Install hypothesize in editable mode with dev extras
pip install -e ".[dev]"

# Provide your Anthropic key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

## Run it

```bash
hypothesize run \
  --config examples/sarcasm/config.yaml \
  --hypothesis "the sentiment classifier mislabels sarcastic positive text"
```

If you do not pass `--hypothesis`, the value from `config.yaml` is
used. The output YAML lands in `tests/discriminating/<slug>_<date>.yaml`
unless you override with `--output`.

Expected wall time: 60-90 seconds.
Expected token spend: ~$0.10-$0.20 with `claude-haiku-4-5-20251001`.

## Inspect the result

```bash
hypothesize list .
hypothesize validate tests/discriminating/<your_file>.yaml
```

Open the generated YAML in your editor. Each `test_cases` entry has:

- `input`: the input data the system was tested with
- `expected_behavior`: the alternative's verdict-reason explaining
  what correct handling looks like
- `discrimination_evidence.current_output` /
  `.alternative_output`: the two systems' raw outputs

## Inputs and outputs

The runner accepts `{"text": str}` and returns
`{"sentiment": "positive" | "negative"}`. The runner normalizes a
range of free-text responses (`positive.`, `Negative`, etc.) onto
those two labels.

## What's intentionally bad

`SYSTEM_PROMPT` in `system.py` is one weak line. The point of the
example is to demonstrate the discriminate → rewrite → re-test loop
on a system that *has* a known failure mode. Do not use this prompt
in production.
