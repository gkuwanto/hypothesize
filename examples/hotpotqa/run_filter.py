"""Filter pass over a fixed HotpotQA candidate pool.

This script is the HotpotQA-specific equivalent of `hypothesize run`.
It exists because the standard discrimination pipeline is built around
LLM-generated candidates and a `RubricJudge`; HotpotQA needs the
opposite shape — pre-supplied candidates from a real eval dataset and
an `ExactMatchJudge` against gold answers.

Mechanism:

1. Load 50 candidates from `data/multi_hop_50.jsonl`.
2. For each candidate, run both prompts (DIRECT and DECOMPOSE) against
   Claude Haiku via the closed-book QA runner in `system.py`.
3. Judge each output against the gold answer with a normalized exact
   match (case- and punctuation-insensitive containment).
4. A discriminating case is one where DIRECT fails and DECOMPOSE passes.
5. Write the result to `output/multi_hop_filter_run1.yaml` in a shape
   compatible with the CLI's output format.

Run from repo root:

    python examples/hotpotqa/run_filter.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from hypothesize.cli.config import load_run_config
from hypothesize.core.types import (
    Budget,
    DiscriminationResult,
    Hypothesis,
    TestCase,
    Verdict,
)
from hypothesize.llm.anthropic import AnthropicBackend

EXAMPLES_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLES_ROOT.parent.parent
DATA_PATH = EXAMPLES_ROOT / "data" / "multi_hop_50.jsonl"
OUTPUT_PATH = EXAMPLES_ROOT / "output" / "multi_hop_filter_run1.yaml"
CONFIG_PATH = EXAMPLES_ROOT / "config.yaml"


def _load_system_module():
    spec = importlib.util.spec_from_file_location(
        "_hotpotqa_filter_module", EXAMPLES_ROOT / "system.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_candidates() -> list[dict]:
    items: list[dict] = []
    with DATA_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


_NORMALIZE_RE = re.compile(r"[^a-z0-9 ]+")


def _norm(text: str) -> str:
    """Lowercase, strip non-alphanumerics, collapse whitespace."""
    return " ".join(_NORMALIZE_RE.sub(" ", text.lower()).split())


def _exact_match(predicted: str, gold: str) -> bool:
    """Case- and punctuation-insensitive containment.

    HotpotQA gold answers are short text spans; the model often
    produces a full noun phrase that contains the gold span (or
    vice versa). Strict equality is too brittle. We accept either
    direction of containment on the normalised forms.
    """
    p = _norm(predicted)
    g = _norm(gold)
    if not g:
        return False
    return p == g or g in p or p in g


async def _run_one(runner, question: str) -> dict[str, Any]:
    return await runner({"question": question})


async def _run_filter() -> None:
    load_dotenv()
    config = load_run_config(CONFIG_PATH)
    candidates = _load_candidates()
    print(f"loaded {len(candidates)} candidates from {DATA_PATH}")

    system_module = _load_system_module()
    backend = AnthropicBackend(config=config.llm)

    direct_runner = system_module.make_runner(
        prompt=system_module.DIRECT_PROMPT, backend=backend
    )
    decompose_runner = system_module.make_runner(
        prompt=system_module.DECOMPOSE_PROMPT, backend=backend
    )

    budget = Budget(max_llm_calls=config.budget.max_llm_calls)
    hypothesis = Hypothesis(
        text=(
            "the QA system fails on multi-hop questions requiring chained "
            "reasoning across two entities, where the intermediate entity "
            "is not named in the question"
        )
    )

    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(candidates, start=1):
        if budget.exhausted():
            print(f"  budget exhausted after {idx - 1} candidates")
            break
        question = item["question"]
        gold = item["gold_answer"]
        direct_out = await _run_one(direct_runner, question)
        budget.charge()
        decompose_out = await _run_one(decompose_runner, question)
        budget.charge()
        direct_pass = _exact_match(direct_out["answer"], gold)
        decompose_pass = _exact_match(decompose_out["answer"], gold)
        rows.append(
            {
                "id": item["id"],
                "question": question,
                "gold_answer": gold,
                "direct_answer": direct_out["answer"],
                "decompose_answer": decompose_out["answer"],
                "direct_pass": direct_pass,
                "decompose_pass": decompose_pass,
            }
        )
        marker = "→D" if (not direct_pass and decompose_pass) else "  "
        print(
            f"  [{idx:02d}/{len(candidates)}] {marker} "
            f"direct={'P' if direct_pass else 'F'} "
            f"decompose={'P' if decompose_pass else 'F'} | "
            f"{question[:60]}"
        )

    both_correct = sum(r["direct_pass"] and r["decompose_pass"] for r in rows)
    both_wrong = sum(
        not r["direct_pass"] and not r["decompose_pass"] for r in rows
    )
    only_decompose = sum(
        not r["direct_pass"] and r["decompose_pass"] for r in rows
    )
    only_direct = sum(
        r["direct_pass"] and not r["decompose_pass"] for r in rows
    )

    print()
    print(f"  total candidates run: {len(rows)}")
    print(f"  both correct:         {both_correct}")
    print(f"  both wrong:           {both_wrong}")
    print(f"  only decompose right: {only_decompose}  ← discriminating")
    print(f"  only direct right:    {only_direct}")
    print(f"  budget used:          {budget.calls_used}/{budget.max_llm_calls}")

    test_cases: list[TestCase] = []
    for r in rows:
        if not r["direct_pass"] and r["decompose_pass"]:
            test_cases.append(
                TestCase(
                    input_data={"question": r["question"]},
                    expected_behavior=(
                        f"answer should match gold {r['gold_answer']!r} "
                        f"(decomposed prompt produced {r['decompose_answer']!r})"
                    ),
                    hypothesis_tag=hypothesis.text,
                    discrimination_evidence={
                        "id": r["id"],
                        "gold_answer": r["gold_answer"],
                        "current_output": {"answer": r["direct_answer"]},
                        "alternative_output": {"answer": r["decompose_answer"]},
                        "current_verdict": Verdict(
                            passed=False,
                            reason=(
                                f"answer {r['direct_answer']!r} does not "
                                f"match gold {r['gold_answer']!r}"
                            ),
                            judge_type="exact_match",
                        ).model_dump(),
                        "alternative_verdict": Verdict(
                            passed=True,
                            reason=(
                                f"answer {r['decompose_answer']!r} matches "
                                f"gold {r['gold_answer']!r}"
                            ),
                            judge_type="exact_match",
                        ).model_dump(),
                    },
                )
            )

    result = DiscriminationResult(
        status="ok" if test_cases else "insufficient_evidence",
        test_cases=test_cases,
        budget_used=budget.calls_used,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "hypothesis": hypothesis.text,
        "metadata": {
            "generated_at": datetime.now(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "model": config.llm.default_model,
            "budget_used": result.budget_used,
            "budget_max": config.budget.max_llm_calls,
            "status": result.status,
            "config_name": config.name,
            "candidate_source": str(DATA_PATH.relative_to(REPO_ROOT)),
            "candidates_total": len(rows),
            "stats": {
                "both_correct": both_correct,
                "both_wrong": both_wrong,
                "only_decompose_right": only_decompose,
                "only_direct_right": only_direct,
            },
        },
        "test_cases": [
            {
                "input": tc.input_data,
                "expected_behavior": tc.expected_behavior,
                "discrimination_evidence": tc.discrimination_evidence,
            }
            for tc in result.test_cases
        ],
        "all_rows": rows,
    }
    OUTPUT_PATH.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    )
    print(f"\n  wrote {len(test_cases)} discriminating cases to {OUTPUT_PATH}")


def main() -> None:
    asyncio.run(_run_filter())


if __name__ == "__main__":
    main()
