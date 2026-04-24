"""Tests for the ``parse_json_response`` utility.

The extractor defines a five-step ladder (clean parse → fence-strip →
brace-slice → trailing-comma repair → None). This file covers each rung
with realistic messy LLM responses, including the ten state-machine- and
framing-sensitive cases called out in ``tasks.md``.

The corpus is data-driven: each case is ``(name, raw, expected)`` and is
iterated via ``pytest.mark.parametrize`` so new cases cost one tuple.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hypothesize.core.json_extract import parse_json_response

FIXTURES = Path(__file__).parent.parent / "_fixtures" / "smoke_responses"


# ---------------------------------------------------------------------------
# Cases — each entry: (name, raw, expected_value)
# expected=... means the parser must return exactly that Python value.
# expected=None means the parser must return None (unsalvageable input).
# ---------------------------------------------------------------------------

CLEAN_OBJECT = ('{"x": 1, "y": "hello"}', {"x": 1, "y": "hello"})

CASES: list[tuple[str, str, object]] = [
    ("clean_object", CLEAN_OBJECT[0], CLEAN_OBJECT[1]),
    (
        "clean_array",
        '[1, 2, "three"]',
        [1, 2, "three"],
    ),
    (
        "fenced_json_tag",
        '```json\n{"x": 1}\n```',
        {"x": 1},
    ),
    (
        "fenced_bare",
        '```\n{"x": 1}\n```',
        {"x": 1},
    ),
    (
        "fenced_python_tag",
        '```python\n{"x": 1}\n```',
        {"x": 1},
    ),
    (
        "fenced_javascript_tag",
        '```javascript\n{"x": 1}\n```',
        {"x": 1},
    ),
    (
        "leading_prose",
        'Sure, here\'s your JSON: {"x": 1}',
        {"x": 1},
    ),
    (
        "trailing_prose",
        '{"x": 1}. Let me know if you need anything else.',
        {"x": 1},
    ),
    (
        "leading_prose_and_fence",
        'Here\'s the result:\n```json\n{"x": 1}\n```',
        {"x": 1},
    ),
    (
        "array_root_in_fence",
        '```json\n[1, 2, 3]\n```',
        [1, 2, 3],
    ),
    (
        "trailing_comma_object",
        '{"x": 1, "y": 2,}',
        {"x": 1, "y": 2},
    ),
    (
        "trailing_comma_array",
        '[1, 2, 3,]',
        [1, 2, 3],
    ),
    (
        "trailing_comma_in_fence",
        '```json\n{"x": 1, "y": 2,}\n```',
        {"x": 1, "y": 2},
    ),
    (
        "escaped_quote_in_string",
        r'{"msg": "she said \"hi\""}',
        {"msg": 'she said "hi"'},
    ),
    (
        "literal_brace_in_string",
        '{"template": "use {name}"}',
        {"template": "use {name}"},
    ),
    (
        "literal_comma_bracket_in_string",
        '{"note": "see list,]"}',
        {"note": "see list,]"},
    ),
    (
        "nested_json_in_string",
        r'{"payload": "{\"x\": 1}"}',
        {"payload": '{"x": 1}'},
    ),
    (
        "double_fenced",
        '````\n```json\n{"x": 1}\n```\n````',
        {"x": 1},
    ),
    (
        "fence_inside_string",
        '{"code": "```python\\nprint(1)\\n```"}',
        {"code": "```python\nprint(1)\n```"},
    ),
    (
        "whitespace_surrounding",
        '  \n  {"x": 1}  \n  ',
        {"x": 1},
    ),
    (
        "nested_object",
        '{"outer": {"inner": {"deep": 1}}}',
        {"outer": {"inner": {"deep": 1}}},
    ),
    (
        "prose_prefix_with_colon_then_array",
        'Result: [1, 2]',
        [1, 2],
    ),
    (
        "array_with_objects_and_trailing_comma",
        '[{"a": 1}, {"b": 2},]',
        [{"a": 1}, {"b": 2}],
    ),
    (
        "fenced_with_leading_language_whitespace",
        '```json   \n{"x": 1}\n```',
        {"x": 1},
    ),
    (
        "empty_string",
        "",
        None,
    ),
    (
        "whitespace_only",
        "   \n\t  \n",
        None,
    ),
    (
        "malformed_mismatched_brackets",
        '{"x": [1, 2}',
        None,
    ),
    (
        "unquoted_keys",
        '{x: 1}',
        None,
    ),
    (
        "single_quoted_strings",
        "{'x': 1}",
        None,
    ),
]


@pytest.mark.parametrize(("name", "raw", "expected"), CASES, ids=[c[0] for c in CASES])
def test_parse_json_response_corpus(name: str, raw: str, expected: object) -> None:
    assert parse_json_response(raw) == expected


def test_none_input_returns_none() -> None:
    # Typed as str but runtime-safe: None is a common caller mishap.
    assert parse_json_response(None) is None  # type: ignore[arg-type]


def test_import_is_side_effect_free() -> None:
    # Re-importing must not raise or mutate module state.
    import importlib

    import hypothesize.core.json_extract as mod

    importlib.reload(mod)
    assert callable(mod.parse_json_response)


def test_smoke_fixture_decompose_haiku_fenced() -> None:
    """First-smoke-run response parses to a dict with 3-7 dimensions."""
    raw = (FIXTURES / "decompose_haiku_fenced.txt").read_text()
    parsed = parse_json_response(raw)
    assert isinstance(parsed, dict)
    dims = parsed.get("dimensions")
    assert isinstance(dims, list)
    assert 3 <= len(dims) <= 7
    for item in dims:
        assert isinstance(item, dict)
        assert "name" in item
        assert "description" in item


def test_trailing_comma_nested_object() -> None:
    # Trailing-comma repair must apply inside nested structures.
    raw = '{"outer": {"a": 1, "b": 2,}, "list": [1, 2,],}'
    assert parse_json_response(raw) == {"outer": {"a": 1, "b": 2}, "list": [1, 2]}


def test_trailing_comma_not_touched_inside_string() -> None:
    # String contains ",}" as literal text; repair must not remove that comma.
    raw = '{"note": "ends with ,}", "ok": true}'
    assert parse_json_response(raw) == {"note": "ends with ,}", "ok": True}
