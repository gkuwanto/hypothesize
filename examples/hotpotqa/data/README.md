# HotpotQA multi-hop subset

`multi_hop_50.jsonl` — 50 bridge questions sampled from HotpotQA's
`distractor` validation split. Closed-book; the dataset's distractor
passages and supporting facts are intentionally dropped so the
example exercises chained reasoning, not retrieval.

## Source

```
datasets.load_dataset("hotpot_qa", "distractor", split="validation")
```

## Filter applied

- `type == "bridge"` — comparison questions are also multi-hop but
  their failure modes look more like calibration than chained
  reasoning, which dilutes the hypothesis being tested.
- Question under 25 words.
- Answer under 5 words.
- Question contains a "recognizable artefact" keyword (film, album,
  city, actor, etc.) — keeps the demo set culturally legible
  without hand-curating every item.

## Reproducing

```
python examples/hotpotqa/build_dataset.py
```

The script seeds `random` with `20260425`, so the selection is
reproducible.

## Schema

```jsonl
{"id": "<hotpotqa-id>", "question": "...", "gold_answer": "...", "type": "bridge"}
```

## Caveats

- HotpotQA gold answers are short text spans extracted from gold
  passages. A handful are slightly noisy (the "name of the
  biography" entry whose gold answer is the biographer's name, for
  instance). The video-curation step in `CURATED.md` filters these
  out by inspection.
- The split is **validation**, not test. Test answers are not
  released by the dataset authors. Validation is fine for a
  filter-pass demo.
