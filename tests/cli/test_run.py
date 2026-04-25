"""Tests for the `hypothesize run` Click command (with mock backend)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from hypothesize.cli.main import cli


def _write_explicit_alt_config(tmp_path: Path) -> tuple[Path, Path, Path]:
    sysfile = tmp_path / "system.py"
    sysfile.write_text(
        "def make_runner(prompt=None):\n"
        "    async def run(input_data):\n"
        "        return {'sentiment': 'positive'}\n"
        "    return run\n"
        "run = make_runner()\n"
    )
    altfile = tmp_path / "alt_system.py"
    altfile.write_text(
        "def make_runner(prompt=None):\n"
        "    async def run(input_data):\n"
        "        return {'sentiment': 'negative'}\n"
        "    return run\n"
        "run = make_runner()\n"
    )
    config = {
        "name": "demo",
        "current": {
            "adapter": "python_module",
            "module_path": str(sysfile),
        },
        "alternative": {
            "adapter": "python_module",
            "module_path": str(altfile),
        },
        "hypothesis": {"text": "the system fails on x"},
        "defaults": {"target_n": 2, "min_required": 1},
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(config))
    return cfg_path, sysfile, altfile


def _scripted_responses_for_ok() -> list[str]:
    decompose = json.dumps(
        {
            "dimensions": [
                {"name": f"d{i}", "description": f"d{i}", "examples": []}
                for i in range(3)
            ]
        }
    )
    generate = json.dumps(
        {
            "candidates": [
                {"input_data": {"text": f"in {i}"}, "rationale": f"r {i}"}
                for i in range(3)
            ]
        }
    )
    rubric_build = "Rubric: handle X correctly."
    verdict_pairs = []
    for _ in range(15):
        verdict_pairs.append(json.dumps({"passed": False, "reason": "fails"}))
        verdict_pairs.append(json.dumps({"passed": True, "reason": "passes"}))
    return [
        decompose,
        generate,
        generate,
        generate,
        rubric_build,
        *verdict_pairs,
    ]


def test_run_writes_yaml_with_mock_backend(tmp_path: Path) -> None:
    cfg_path, _, _ = _write_explicit_alt_config(tmp_path)
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(_scripted_responses_for_ok()))
    output_path = tmp_path / "out.yaml"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "run",
            "--config",
            str(cfg_path),
            "--backend",
            "mock",
            "--mock-script",
            str(script_path),
            "--output",
            str(output_path),
            "--target-n",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    assert output_path.exists()
    parsed = yaml.safe_load(output_path.read_text())
    assert parsed["metadata"]["status"] == "ok"
    assert parsed["hypothesis"] == "the system fails on x"
    assert len(parsed["test_cases"]) == 2


def test_run_returns_exit_code_1_on_insufficient(tmp_path: Path) -> None:
    cfg_path, _, _ = _write_explicit_alt_config(tmp_path)
    decompose = json.dumps(
        {
            "dimensions": [
                {"name": f"d{i}", "description": f"d{i}", "examples": []}
                for i in range(3)
            ]
        }
    )
    generate = json.dumps(
        {
            "candidates": [
                {"input_data": {"text": f"in {i}"}, "rationale": f"r {i}"}
                for i in range(3)
            ]
        }
    )
    rubric_build = "Rubric: handle X correctly."
    # Both pass — no discrimination at all
    verdicts = [json.dumps({"passed": True, "reason": "passes"}) for _ in range(40)]
    script = [decompose, generate, generate, generate, rubric_build, *verdicts]

    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(script))
    output_path = tmp_path / "out.yaml"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "run",
            "--config",
            str(cfg_path),
            "--backend",
            "mock",
            "--mock-script",
            str(script_path),
            "--output",
            str(output_path),
            "--target-n",
            "2",
        ],
    )
    assert result.exit_code == 1, result.output
    assert output_path.exists()
    parsed = yaml.safe_load(output_path.read_text())
    assert parsed["metadata"]["status"] == "insufficient_evidence"


def test_run_exit_2_on_missing_config(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "run",
            "--config",
            str(tmp_path / "nope.yaml"),
            "--hypothesis",
            "x",
        ],
    )
    assert result.exit_code == 2
    assert "config" in result.output.lower() or "config" in (result.stderr or "").lower()


def test_run_exit_2_on_invalid_config(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("not_a_valid: config")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["run", "--config", str(cfg), "--hypothesis", "x"],
    )
    assert result.exit_code == 2


def test_run_uses_hypothesis_flag_over_yaml(tmp_path: Path) -> None:
    cfg_path, _, _ = _write_explicit_alt_config(tmp_path)
    script_path = tmp_path / "script.json"
    script_path.write_text(json.dumps(_scripted_responses_for_ok()))
    output_path = tmp_path / "out.yaml"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "run",
            "--config",
            str(cfg_path),
            "--hypothesis",
            "OVERRIDDEN HYPOTHESIS",
            "--backend",
            "mock",
            "--mock-script",
            str(script_path),
            "--output",
            str(output_path),
            "--target-n",
            "2",
        ],
    )
    assert result.exit_code == 0
    parsed = yaml.safe_load(output_path.read_text())
    assert parsed["hypothesis"] == "OVERRIDDEN HYPOTHESIS"


def test_run_exit_2_when_no_hypothesis_anywhere(tmp_path: Path) -> None:
    """Config with no hypothesis block AND no --hypothesis flag => error."""
    cfg_path, _, _ = _write_explicit_alt_config(tmp_path)
    raw = yaml.safe_load(cfg_path.read_text())
    del raw["hypothesis"]
    cfg_path.write_text(yaml.safe_dump(raw))
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--config", str(cfg_path)])
    assert result.exit_code == 2
