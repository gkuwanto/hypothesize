"""Filter pass over a fixed ACME-support candidate pool.

This is the ACME-specific equivalent of `hypothesize run`. It exists
because the standard discrimination pipeline is built around
LLM-generated candidates and a `RubricJudge`; the emoji-overuse
hypothesis is best judged by a deterministic counter over a fixed
hand-written pool of customer questions.

Mechanism:

1. Load 30 candidates from `data/customer_questions.jsonl`.
2. For each candidate, run both prompts (BASE and NO_EMOJI) against
   Claude Haiku via the chatbot runner in `system.py`.
3. Judge each output with `EmojiCountJudge` (passes iff zero emoji).
4. A discriminating case is one where BASE fails (emoji present) and
   NO_EMOJI passes (no emoji).
5. Write the result to `output/run1.yaml` in a shape compatible with
   the CLI's output format.

Run from repo root:

    python examples/acme_support/run_filter.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
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
)
from hypothesize.llm.anthropic import AnthropicBackend

EXAMPLES_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLES_ROOT.parent.parent
DATA_PATH = EXAMPLES_ROOT / "data" / "customer_questions.jsonl"
OUTPUT_PATH = EXAMPLES_ROOT / "output" / "run1.yaml"
CONFIG_PATH = EXAMPLES_ROOT / "config.yaml"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
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


async def _run_one(runner, question: str) -> dict[str, Any]:
    return await runner({"question": question})


async def _run_filter() -> None:
    load_dotenv()
    config = load_run_config(CONFIG_PATH)
    candidates = _load_candidates()
    print(f"loaded {len(candidates)} candidates from {DATA_PATH}")

    system_module = _load_module(
        "_acme_filter_system", EXAMPLES_ROOT / "system.py"
    )
    judge_module = _load_module(
        "_acme_filter_judge", EXAMPLES_ROOT / "judge.py"
    )

    backend = AnthropicBackend(config=config.llm)

    base_runner = system_module.make_runner(
        prompt=system_module.BASE_SYSTEM_PROMPT, backend=backend
    )
    no_emoji_runner = system_module.make_runner(
        prompt=system_module.NO_EMOJI_SYSTEM_PROMPT, backend=backend
    )

    judge = judge_module.EmojiCountJudge(output_key="response")
    budget = Budget(max_llm_calls=config.budget.max_llm_calls)
    hypothesis = Hypothesis(
        text="the chatbot uses excessive emojis in customer support responses"
    )

    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(candidates, start=1):
        if budget.exhausted():
            print(f"  budget exhausted after {idx - 1} candidates")
            break
        question = item["question"]
        base_out = await _run_one(base_runner, question)
        budget.charge()
        no_emoji_out = await _run_one(no_emoji_runner, question)
        budget.charge()

        base_verdict = await judge.judge(
            input_data={"question": question},
            output=base_out,
            hypothesis=hypothesis,
            budget=budget,
        )
        no_emoji_verdict = await judge.judge(
            input_data={"question": question},
            output=no_emoji_out,
            hypothesis=hypothesis,
            budget=budget,
        )

        base_count = judge_module.count_emojis(base_out["response"])
        no_emoji_count = judge_module.count_emojis(no_emoji_out["response"])

        rows.append(
            {
                "id": item["id"],
                "category": item["category"],
                "question": question,
                "base_response": base_out["response"],
                "no_emoji_response": no_emoji_out["response"],
                "base_emoji_count": base_count,
                "no_emoji_count": no_emoji_count,
                "base_pass": base_verdict.passed,
                "no_emoji_pass": no_emoji_verdict.passed,
            }
        )
        marker = "→D" if (not base_verdict.passed and no_emoji_verdict.passed) else "  "
        print(
            f"  [{idx:02d}/{len(candidates)}] {marker} "
            f"base={'P' if base_verdict.passed else 'F'}({base_count}) "
            f"no_emoji={'P' if no_emoji_verdict.passed else 'F'}({no_emoji_count}) | "
            f"{question[:60]}"
        )

    both_clean = sum(r["base_pass"] and r["no_emoji_pass"] for r in rows)
    both_emoji = sum(
        not r["base_pass"] and not r["no_emoji_pass"] for r in rows
    )
    only_base_emoji = sum(
        not r["base_pass"] and r["no_emoji_pass"] for r in rows
    )
    only_no_emoji_emoji = sum(
        r["base_pass"] and not r["no_emoji_pass"] for r in rows
    )

    print()
    print(f"  total candidates run:        {len(rows)}")
    print(f"  both clean (both pass):      {both_clean}")
    print(f"  both emoji (both fail):      {both_emoji}")
    print(f"  base emoji only (discrim.):  {only_base_emoji}  ← discriminating")
    print(f"  no_emoji emoji only:         {only_no_emoji_emoji}")
    print(f"  budget used:                 {budget.calls_used}/{budget.max_llm_calls}")

    test_cases: list[TestCase] = []
    for r in rows:
        if not r["base_pass"] and r["no_emoji_pass"]:
            test_cases.append(
                TestCase(
                    input_data={"question": r["question"]},
                    expected_behavior=(
                        "response should contain zero emojis "
                        f"(no_emoji prompt produced {r['no_emoji_count']})"
                    ),
                    hypothesis_tag=hypothesis.text,
                    discrimination_evidence={
                        "id": r["id"],
                        "category": r["category"],
                        "current_output": {"response": r["base_response"]},
                        "alternative_output": {"response": r["no_emoji_response"]},
                        "base_emoji_count": r["base_emoji_count"],
                        "no_emoji_count": r["no_emoji_count"],
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
                "both_clean": both_clean,
                "both_emoji": both_emoji,
                "base_emoji_only": only_base_emoji,
                "no_emoji_only": only_no_emoji_emoji,
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
        yaml.safe_dump(
            payload, sort_keys=False, default_flow_style=False, allow_unicode=True
        )
    )
    print(f"\n  wrote {len(test_cases)} discriminating cases to {OUTPUT_PATH}")


def main() -> None:
    asyncio.run(_run_filter())


if __name__ == "__main__":
    main()
