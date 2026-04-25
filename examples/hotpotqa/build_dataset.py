"""One-shot script to build examples/hotpotqa/data/multi_hop_50.jsonl.

Run from repo root:

    python examples/hotpotqa/build_dataset.py

Loads the HotpotQA distractor/validation split via the ``datasets``
library and filters to 50 items meeting:

- ``type == "bridge"`` (chained-entity reasoning) — comparison
  questions are also multi-hop but their failure modes look more
  like calibration than chained reasoning, which dilutes the
  hypothesis being tested.
- Question length under 25 words.
- Answer length under 5 words.
- A small "interesting-entity" filter: prefer questions naming a
  recognizable thing (film, city, person, band) over abstract
  ones. Implemented as a keyword-presence heuristic; not exact.

Drops the ``context`` and ``supporting_facts`` columns (closed-book).
Writes JSONL with ``{id, question, gold_answer, type}``.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from datasets import load_dataset

OUT_PATH = Path(__file__).resolve().parent / "data" / "multi_hop_50.jsonl"

# Bias the selection toward bridge questions whose surface form names
# a recognizable cultural artefact (film, album, novel, band, city).
# Keeps the set demo-friendly without hand-curating every item.
_INTEREST_KEYWORDS = (
    "film",
    "movie",
    "album",
    "novel",
    "book",
    "band",
    "song",
    "show",
    "series",
    "city",
    "actor",
    "actress",
    "director",
    "singer",
    "author",
    "writer",
)


def _is_interesting(question: str) -> bool:
    q = question.lower()
    return any(kw in q for kw in _INTEREST_KEYWORDS)


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ds = load_dataset("hotpot_qa", "distractor", split="validation")

    pool: list[dict] = []
    for item in ds:
        if item["type"] != "bridge":
            continue
        if len(item["question"].split()) > 25:
            continue
        if len(item["answer"].split()) > 5:
            continue
        if not _is_interesting(item["question"]):
            continue
        pool.append(
            {
                "id": item["id"],
                "question": item["question"],
                "gold_answer": item["answer"],
                "type": item["type"],
            }
        )

    print(f"pool size after filtering: {len(pool)}")
    rng = random.Random(20260425)
    rng.shuffle(pool)
    selected = pool[:50]
    with OUT_PATH.open("w") as f:
        for entry in selected:
            f.write(json.dumps(entry) + "\n")
    print(f"wrote {len(selected)} items to {OUT_PATH}")


if __name__ == "__main__":
    main()
