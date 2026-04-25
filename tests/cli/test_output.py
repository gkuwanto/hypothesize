"""Tests for cli.output — DiscriminationResult -> YAML."""

from __future__ import annotations

from datetime import UTC, datetime

import yaml

from hypothesize.cli.output import result_to_yaml
from hypothesize.core.types import (
    DiscriminationResult,
    Hypothesis,
    InsufficientEvidence,
    TestCase,
    Verdict,
)


def _ok_result() -> DiscriminationResult:
    return DiscriminationResult(
        status="ok",
        budget_used=42,
        test_cases=[
            TestCase(
                input_data={"text": "I LOVE waiting on hold"},
                expected_behavior="should detect sarcasm",
                hypothesis_tag="hyp",
                discrimination_evidence={
                    "current_output": {"sentiment": "positive"},
                    "alternative_output": {"sentiment": "negative"},
                    "current_verdict": Verdict(
                        passed=False, reason="missed sarcasm", judge_type="rubric"
                    ).model_dump(),
                    "alternative_verdict": Verdict(
                        passed=True, reason="caught sarcasm", judge_type="rubric"
                    ).model_dump(),
                },
            ),
        ],
    )


def _insufficient_result() -> DiscriminationResult:
    return DiscriminationResult(
        status="insufficient_evidence",
        budget_used=18,
        insufficient=InsufficientEvidence(
            reason="found only 1 case",
            candidates_tried=18,
            discriminating_found=1,
        ),
    )


def test_ok_result_yaml_round_trips() -> None:
    result = _ok_result()
    hypothesis = Hypothesis(text="the system fails on sarcasm")
    out = result_to_yaml(
        result=result,
        hypothesis=hypothesis,
        config_name="sarcasm-sentiment",
        model_name="claude-haiku-4-5-20251001",
        target_n=5,
        budget_max=100,
        generated_at=datetime(2026, 4, 25, 14, 32, 11, tzinfo=UTC),
    )
    parsed = yaml.safe_load(out)
    assert parsed["hypothesis"] == "the system fails on sarcasm"
    assert parsed["metadata"]["status"] == "ok"
    assert parsed["metadata"]["budget_used"] == 42
    assert parsed["metadata"]["budget_max"] == 100
    assert parsed["metadata"]["model"] == "claude-haiku-4-5-20251001"
    assert parsed["metadata"]["config_name"] == "sarcasm-sentiment"
    assert parsed["metadata"]["target_n"] == 5
    assert parsed["metadata"]["generated_at"].startswith("2026-04-25T14:32:11")
    assert isinstance(parsed["test_cases"], list)
    assert parsed["test_cases"][0]["input"] == {"text": "I LOVE waiting on hold"}
    assert parsed["test_cases"][0]["expected_behavior"] == "should detect sarcasm"
    assert (
        parsed["test_cases"][0]["discrimination_evidence"]["current_output"]
        == {"sentiment": "positive"}
    )
    assert "insufficient" not in parsed


def test_insufficient_result_yaml_includes_block() -> None:
    result = _insufficient_result()
    hypothesis = Hypothesis(text="the system fails on sarcasm")
    out = result_to_yaml(
        result=result,
        hypothesis=hypothesis,
        config_name="sarcasm-sentiment",
        model_name="claude-haiku-4-5-20251001",
        target_n=5,
        budget_max=100,
    )
    parsed = yaml.safe_load(out)
    assert parsed["metadata"]["status"] == "insufficient_evidence"
    assert parsed["test_cases"] == []
    assert parsed["insufficient"]["reason"] == "found only 1 case"
    assert parsed["insufficient"]["candidates_tried"] == 18
    assert parsed["insufficient"]["discriminating_found"] == 1


def test_yaml_is_human_readable() -> None:
    """Block style; quoted strings; not a flow-style one-liner."""
    result = _ok_result()
    out = result_to_yaml(
        result=result,
        hypothesis=Hypothesis(text="x"),
        config_name="demo",
        model_name="claude-haiku-4-5-20251001",
        target_n=5,
        budget_max=100,
    )
    # block style => newlines per item
    assert out.count("\n") > 5
    # not a flow style mapping at root
    assert not out.strip().startswith("{")
