"""Tests for hypothesize.mcp.tools — MCP tool bodies."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from hypothesize.mcp import tools
from tests._fixtures.mock_backend import MockBackend


def _write_run_config(tmp_path: Path, name: str = "demo") -> Path:
    sysfile = tmp_path / "system.py"
    sysfile.write_text(
        'SYSTEM_PROMPT = "be precise"\n'
        "def make_runner(prompt=None):\n"
        "    async def run(input_data):\n"
        "        return {'sentiment': 'positive'}\n"
        "    return run\n"
        "run = make_runner()\n"
    )
    cfg = {
        "name": name,
        "current": {
            "adapter": "python_module",
            "module_path": str(sysfile),
        },
        "alternative": {"adapter": "auto"},
        "hypothesis": {"text": f"{name} fails on x"},
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def _write_benchmark(path: Path, hypothesis: str = "fails on y") -> Path:
    payload = {
        "hypothesis": hypothesis,
        "metadata": {"status": "ok", "model": "claude-haiku-4-5-20251001"},
        "test_cases": [
            {"input": {"text": "case 1"}, "expected_behavior": "be right"},
            {"input": {"text": "case 2"}, "expected_behavior": "be right"},
        ],
    }
    path.write_text(yaml.safe_dump(payload))
    return path


# discover_systems ----------------------------------------------------


async def test_discover_systems_finds_top_level_config(tmp_path: Path) -> None:
    _write_run_config(tmp_path, name="root_demo")
    found = await tools.discover_systems(str(tmp_path))
    assert len(found) == 1
    assert found[0]["name"] == "root_demo"
    assert found[0]["adapter"] == "python_module"
    assert Path(found[0]["path"]).name == "config.yaml"


async def test_discover_systems_finds_examples_subdir(tmp_path: Path) -> None:
    examples = tmp_path / "examples" / "myexample"
    examples.mkdir(parents=True)
    _write_run_config(examples, name="ex1")
    found = await tools.discover_systems(str(tmp_path))
    assert len(found) == 1
    assert found[0]["name"] == "ex1"


async def test_discover_systems_skips_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text("not: a: valid: config:")
    found = await tools.discover_systems(str(tmp_path))
    assert found == []


async def test_discover_systems_returns_empty_for_empty_dir(tmp_path: Path) -> None:
    found = await tools.discover_systems(str(tmp_path))
    assert found == []


# list_benchmarks -----------------------------------------------------


async def test_list_benchmarks_finds_yamls(tmp_path: Path) -> None:
    bench_dir = tmp_path / "tests" / "discriminating"
    bench_dir.mkdir(parents=True)
    _write_benchmark(bench_dir / "a.yaml", hypothesis="hyp a")
    _write_benchmark(bench_dir / "b.yaml", hypothesis="hyp b")
    found = await tools.list_benchmarks(str(tmp_path))
    assert len(found) == 2
    hyps = {b["hypothesis"] for b in found}
    assert hyps == {"hyp a", "hyp b"}
    for b in found:
        assert b["status"] == "ok"
        assert b["n_test_cases"] == 2
        assert "path" in b


# read_benchmark ------------------------------------------------------


async def test_read_benchmark_returns_dict(tmp_path: Path) -> None:
    bench = _write_benchmark(tmp_path / "x.yaml", hypothesis="hyp x")
    result = await tools.read_benchmark(str(bench))
    assert result["hypothesis"] == "hyp x"
    assert result["metadata"]["status"] == "ok"
    assert len(result["test_cases"]) == 2


async def test_read_benchmark_raises_on_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await tools.read_benchmark(str(tmp_path / "nope.yaml"))


# formulate_hypothesis ------------------------------------------------


async def test_formulate_hypothesis_returns_structured(tmp_path: Path) -> None:
    backend = MockBackend(
        responses=[
            json.dumps(
                {"text": "the system fails on x", "context_refs": []}
            )
        ]
    )
    result = await tools.formulate_hypothesis(
        complaint="my classifier gets sarcasm wrong",
        context={"repo_path": str(tmp_path)},
        backend=backend,
    )
    assert result["text"] == "the system fails on x"
    assert result["context_refs"] == []
    assert len(backend.calls) == 1


async def test_formulate_hypothesis_handles_malformed_response(tmp_path: Path) -> None:
    backend = MockBackend(responses=["not json at all"])
    with pytest.raises(ValueError):
        await tools.formulate_hypothesis(
            complaint="x",
            context={},
            backend=backend,
        )


async def test_formulate_hypothesis_handles_missing_text_key(tmp_path: Path) -> None:
    backend = MockBackend(responses=[json.dumps({"context_refs": []})])
    with pytest.raises(ValueError):
        await tools.formulate_hypothesis(
            complaint="x",
            context={},
            backend=backend,
        )


# run_discrimination --------------------------------------------------


async def test_run_discrimination_returns_dict_payload(tmp_path: Path) -> None:
    cfg_path = _write_run_config(tmp_path, name="demo")

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
    rewrite = json.dumps(
        {
            "rewritten_prompt": "be MORE precise",
            "rationale": "added clarity",
        }
    )
    rubric_build = "Rubric: handle X correctly."
    verdict_pairs: list[str] = []
    for _ in range(15):
        verdict_pairs.append(json.dumps({"passed": False, "reason": "fails"}))
        verdict_pairs.append(json.dumps({"passed": True, "reason": "passes"}))

    # Order of calls: rewrite (auto-alt setup) -> decompose -> 3 generate -> rubric_build -> verdicts
    backend = MockBackend(
        responses=[
            rewrite,
            decompose,
            generate,
            generate,
            generate,
            rubric_build,
            *verdict_pairs,
        ]
    )

    result = await tools.run_discrimination(
        config_path=str(cfg_path),
        hypothesis="the system fails on x",
        target_n=2,
        budget=200,
        backend=backend,
    )
    assert result["metadata"]["status"] == "ok"
    assert result["hypothesis"] == "the system fails on x"
    assert isinstance(result["test_cases"], list)
