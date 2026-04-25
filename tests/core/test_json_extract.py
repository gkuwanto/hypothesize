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


# ---------------------------------------------------------------------------
# State-machine stress tests
#
# The corpus cases above for "escaped quote", "literal brace in string",
# "literal comma+bracket in string", and "nested JSON in string" are all
# valid JSON, so they win at step 2 (json.loads) without exercising the
# state-machine scanner used by steps 4 and 5. The tests below force the
# scanner to run on each of those features by either wrapping in prose
# (forcing brace-slice) or appending a trailing comma (forcing repair),
# so we genuinely verify the scanner handles the edge cases.
# ---------------------------------------------------------------------------


def test_state_machine_handles_escaped_quote_under_brace_slice() -> None:
    # Leading prose forces step 4. Inside the JSON, ``\"`` must not be
    # treated as an end-of-string by the scanner.
    raw = r'Here is the JSON: {"msg": "she said \"hi\""}'
    assert parse_json_response(raw) == {"msg": 'she said "hi"'}


def test_state_machine_handles_escaped_backslash_under_brace_slice() -> None:
    # ``\\`` followed by ``"`` is end-of-string; the scanner must skip
    # the escape pair (\\) so the trailing ``"`` is recognized.
    raw = r'Result: {"path": "C:\\Users\\x"}'
    assert parse_json_response(raw) == {"path": r"C:\Users\x"}


def test_state_machine_handles_literal_brace_under_trailing_comma_repair() -> None:
    # Trailing comma forces step 5 to scan. The literal ``{`` and ``}``
    # inside the string must not change the scanner's bracket depth.
    raw = '{"template": "use {name}", "ok": true,}'
    assert parse_json_response(raw) == {"template": "use {name}", "ok": True}


def test_state_machine_handles_literal_brace_under_brace_slice() -> None:
    # Trailing prose forces brace-slice. The literal ``{`` inside the
    # string must not extend the slice past the true closer.
    raw = '{"template": "use {name}"} -- end of message'
    assert parse_json_response(raw) == {"template": "use {name}"}


def test_state_machine_handles_literal_comma_bracket_under_repair() -> None:
    # Trailing comma forces step 5. The ``,]`` literal inside the
    # string must not be touched by the comma-removal pass.
    raw = '{"note": "see list,]", "ok": true,}'
    assert parse_json_response(raw) == {"note": "see list,]", "ok": True}


def test_state_machine_handles_nested_json_in_string_under_brace_slice() -> None:
    # Leading prose forces step 4. Inner braces appearing as escaped
    # characters within the string must not affect bracket depth.
    raw = r'Here: {"payload": "{\"x\": 1}"}'
    assert parse_json_response(raw) == {"payload": '{"x": 1}'}


def test_state_machine_handles_nested_json_in_string_under_repair() -> None:
    # Force step 5; combined with the inner-brace string, a wrong
    # bracket-counter would mis-locate the trailing comma.
    raw = r'{"payload": "{\"x\": 1}", "ok": true,}'
    assert parse_json_response(raw) == {"payload": '{"x": 1}', "ok": True}


def test_state_machine_handles_quote_then_brace_in_string() -> None:
    # An escaped quote immediately followed by a literal ``}`` inside
    # the string is the most adversarial combo for a naive scanner.
    raw = r'Note: {"msg": "she said \"go away\"}", "k": 1}'
    assert parse_json_response(raw) == {"msg": 'she said "go away"}', "k": 1}

