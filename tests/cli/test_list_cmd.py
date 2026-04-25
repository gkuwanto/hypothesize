"""Tests for `hypothesize list`."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from hypothesize.cli.main import cli


def _write_benchmark(
    path: Path,
    *,
    hypothesis: str = "the system fails on x",
    status: str = "ok",
    n_cases: int = 3,
) -> Path:
    payload = {
        "hypothesis": hypothesis,
        "metadata": {
            "status": status,
            "model": "claude-haiku-4-5-20251001",
            "config_name": "demo",
        },
        "test_cases": [
            {"input": {"text": f"case {i}"}, "expected_behavior": "be right"}
            for i in range(n_cases)
        ],
    }
    path.write_text(yaml.safe_dump(payload))
    return path


def test_list_returns_empty_when_no_benchmarks(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list", str(tmp_path)])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_list_finds_one_benchmark(tmp_path: Path) -> None:
    bench = tmp_path / "tests" / "discriminating"
    bench.mkdir(parents=True)
    _write_benchmark(
        bench / "sarcasm.yaml",
        hypothesis="sarcasm fails",
        status="ok",
        n_cases=5,
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["list", str(tmp_path)])
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line]
    assert len(lines) == 1
    assert "sarcasm.yaml" in lines[0]
    assert "sarcasm fails" in lines[0]
    assert "ok" in lines[0]
    assert "5" in lines[0]


def test_list_finds_many_benchmarks(tmp_path: Path) -> None:
    bench = tmp_path / "tests" / "discriminating"
    bench.mkdir(parents=True)
    _write_benchmark(bench / "a.yaml", hypothesis="hyp a", n_cases=2)
    _write_benchmark(bench / "b.yaml", hypothesis="hyp b", n_cases=4)
    runner = CliRunner()
    result = runner.invoke(cli, ["list", str(tmp_path)])
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line]
    assert len(lines) == 2


def test_list_skips_non_benchmark_yamls(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"name": "demo", "current": {"adapter": "python_module"}})
    )
    bench = tmp_path / "tests" / "discriminating"
    bench.mkdir(parents=True)
    _write_benchmark(bench / "real.yaml")
    runner = CliRunner()
    result = runner.invoke(cli, ["list", str(tmp_path)])
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line]
    assert len(lines) == 1
    assert "real.yaml" in lines[0]


def test_list_default_path_is_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    bench = tmp_path / "tests" / "discriminating"
    bench.mkdir(parents=True)
    _write_benchmark(bench / "x.yaml")
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line]
    assert len(lines) == 1


def test_list_skips_malformed_yaml(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("::: not valid yaml :::")
    runner = CliRunner()
    result = runner.invoke(cli, ["list", str(tmp_path)])
    assert result.exit_code == 0
    assert result.output.strip() == ""
