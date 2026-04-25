"""Tests for `hypothesize validate`."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from hypothesize.cli.main import cli


def _good_payload() -> dict:
    return {
        "hypothesis": "the system fails on x",
        "metadata": {
            "status": "ok",
            "model": "claude-haiku-4-5-20251001",
            "config_name": "demo",
        },
        "test_cases": [
            {"input": {"text": "case 0"}, "expected_behavior": "be right"},
        ],
    }


def test_validate_ok_on_well_formed_benchmark(tmp_path: Path) -> None:
    p = tmp_path / "bench.yaml"
    p.write_text(yaml.safe_dump(_good_payload()))
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(p)])
    assert result.exit_code == 0
    assert "ok" in result.output.lower()


def test_validate_missing_hypothesis_fails(tmp_path: Path) -> None:
    payload = _good_payload()
    del payload["hypothesis"]
    p = tmp_path / "bench.yaml"
    p.write_text(yaml.safe_dump(payload))
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(p)])
    assert result.exit_code == 2


def test_validate_missing_metadata_fails(tmp_path: Path) -> None:
    payload = _good_payload()
    del payload["metadata"]
    p = tmp_path / "bench.yaml"
    p.write_text(yaml.safe_dump(payload))
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(p)])
    assert result.exit_code == 2


def test_validate_missing_test_cases_fails(tmp_path: Path) -> None:
    payload = _good_payload()
    del payload["test_cases"]
    p = tmp_path / "bench.yaml"
    p.write_text(yaml.safe_dump(payload))
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(p)])
    assert result.exit_code == 2


def test_validate_metadata_must_have_status(tmp_path: Path) -> None:
    payload = _good_payload()
    del payload["metadata"]["status"]
    p = tmp_path / "bench.yaml"
    p.write_text(yaml.safe_dump(payload))
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(p)])
    assert result.exit_code == 2


def test_validate_missing_file(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 2
