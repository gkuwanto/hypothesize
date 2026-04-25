# Example: HotpotQA multi-hop QA (scaffold)

> **NOT YET RUNNABLE.** This directory is a scaffold. Finish the TODOs
> in `system.py` before invoking the CLI against this config.

## Why this example exists

Demonstrates the shape of a hypothesize integration with a
real-dataset, non-classifier system — multi-hop QA with retrieval —
without committing to a full implementation in-session. The sarcasm
example is the demo's hero; this one shows the path for users who
want to apply hypothesize to a richer system.

## Manual setup

1. **Download HotpotQA.** The `datasets` dependency is already in
   `pyproject.toml`. From the repo root:

   ```python
   from datasets import load_dataset
   ds = load_dataset("hotpot_qa", "distractor", split="validation[:200]")
   ds.save_to_disk("examples/hotpotqa/data")
   ```

   200 entries is enough to discriminate; the full set is too slow.

2. **Decide what shape to feed the runner.** A reasonable choice:

   ```python
   {"question": str, "contexts": list[str], "gold_answer": str}
   ```

   Hypothesize's generate phase will infer the shape from the
   hypothesis; you can also write candidates by hand if you want
   more control.

3. **Fill in `system.py`.** The runner currently raises
   `NotImplementedError` with a TODO message. Replace the body with
   a Claude call that takes the question + contexts and returns
   `{"answer": str}`. Use `backend.complete` if you want the
   prompt-factory convention to work for auto-alternative; otherwise,
   construct an `AnthropicBackend` directly.

4. **Tune the hypothesis.** The default in `config.yaml` is one of
   many reasonable failure modes for multi-hop QA. Other angles:

   - "the QA system trusts the first context regardless of relevance"
   - "the QA system fails when the second hop requires a date or
     number it cannot read directly"
   - "the QA system hallucinates entities that match the question's
     surface form but are not in the contexts"

## Run it (after the TODOs are done)

```bash
hypothesize run --config examples/hotpotqa/config.yaml
```

## Why we kept the scaffold

The sarcasm example is enough to validate the magic moment. A second
real-dataset example proves the tool's generality without doubling
the demo surface in a single session. The scaffold gives a future
contributor a clear starting point.
