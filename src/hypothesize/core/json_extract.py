"""Permissive JSON extraction from messy LLM responses.

A single utility, ``parse_json_response``, implements a five-step ladder:

1. Empty / whitespace → ``None``.
2. Strict ``json.loads`` on the trimmed input.
3. Fence-strip: slice between the first pair of triple-backtick fences
   and retry. The opening fence's optional language tag is ignored.
4. Brace-slice: find the first ``{`` or ``[`` and walk to its matching
   closer using a state-machine scanner that correctly handles JSON
   string literals and escape sequences. Retry on the substring.
5. Trailing-comma repair: strip commas that precede ``}`` or ``]`` when
   outside a string literal, operating on the best candidate produced
   by earlier steps (brace-slice > fence-body > original input). Retry.

If every rung fails, return ``None``. The function never raises — callers
treat ``None`` the same way they handled ``json.JSONDecodeError`` before.
"""

from __future__ import annotations

import json
from typing import Any


def parse_json_response(raw: str) -> Any | None:
    """Parse a JSON value from a possibly-messy LLM response.

    Returns the parsed value (dict, list, str, number, bool, or None)
    on success, or ``None`` if no rung of the extraction ladder produces
    a valid JSON value. Never raises.

    Tolerates markdown code fences (``` ``` ```, ``` ```json ```, other
    language tags), leading / trailing prose around a JSON value, and
    trailing commas before ``}`` or ``]``. Does not tolerate genuinely
    malformed JSON (unquoted keys, single-quoted strings, mismatched
    brackets) — masking those would lose real signal.
    """
    if not isinstance(raw, str):
        return None

    stripped = raw.strip()
    if not stripped:
        return None

    # Step 2: strict parse.
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Step 3: fence-strip. An empty body (as happens when an outer
    # fence wraps an inner fence) is discarded so that step 4 scans the
    # full input and can still locate the inner JSON.
    fence_body = _strip_fence(stripped)
    if fence_body is not None and fence_body.strip():
        try:
            return json.loads(fence_body.strip())
        except json.JSONDecodeError:
            pass
    else:
        fence_body = None

    # Step 4: brace-slice. Prefer operating on the fence body if we
    # have one, since that is typically a cleaner surface; fall back to
    # the original stripped input otherwise.
    slice_input = fence_body if fence_body is not None else stripped
    brace_slice = _brace_slice(slice_input)
    if brace_slice is not None:
        try:
            return json.loads(brace_slice)
        except json.JSONDecodeError:
            pass

    # Step 5: trailing-comma repair. Best-candidate precedence:
    # brace-slice (tightest) > fence-body > stripped (widest).
    if brace_slice is not None:
        candidate = brace_slice
    elif fence_body is not None:
        candidate = fence_body.strip()
    else:
        candidate = stripped

    repaired = _strip_trailing_commas(candidate)
    if repaired != candidate:
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

    return None


def _strip_fence(text: str) -> str | None:
    """Return the body between the first pair of triple-backtick fences.

    Handles an optional language tag on the opening fence line. Returns
    ``None`` when a matched fence pair cannot be located.
    """
    start = text.find("```")
    if start == -1:
        return None

    # Consume the optional language tag through the first newline.
    # We are tolerant: if the opening fence has no newline (e.g. the
    # entire fence is single-line), we treat the body as starting right
    # after the opening backticks.
    after_open = start + 3
    newline = text.find("\n", after_open)
    if newline == -1:
        body_start = after_open
    else:
        body_start = newline + 1

    end = text.find("```", body_start)
    if end == -1:
        return None

    return text[body_start:end]


def _brace_slice(text: str) -> str | None:
    """Return the substring from the first ``{`` or ``[`` through its match.

    Uses a state-machine scanner that correctly skips over string
    literals (including ``\\"``, ``\\\\``, and ``\\uXXXX`` escape
    sequences). Returns ``None`` if no balanced value is found.
    """
    for i, ch in enumerate(text):
        if ch in "{[":
            return _scan_balanced(text, i)
    return None


def _scan_balanced(text: str, start: int) -> str | None:
    """Walk ``text`` from ``start`` (a ``{`` or ``[``) to its matching closer.

    Returns the inclusive substring on success, ``None`` if the value
    is not properly balanced before end-of-input.
    """
    stack: list[str] = []
    in_string = False
    i = start
    n = len(text)

    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\":
                # Skip the escape and whatever character follows it so
                # that ``\"`` does not falsely close the string. For
                # ``\\uXXXX`` we only need to skip the first two chars;
                # the remaining hex digits are not syntactically active.
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack:
                return None
            opener = stack.pop()
            if (opener == "{" and ch != "}") or (opener == "[" and ch != "]"):
                return None
            if not stack:
                return text[start : i + 1]
        i += 1

    return None


def _strip_trailing_commas(text: str) -> str:
    """Remove commas that precede ``}`` or ``]`` outside of string literals.

    Uses the same string-literal-aware scanning logic as ``_scan_balanced``
    so that commas embedded inside string values are never touched.
    """
    result: list[str] = []
    in_string = False
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if in_string:
            result.append(ch)
            if ch == "\\" and i + 1 < n:
                result.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue

        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\n\r":
                j += 1
            if j < n and text[j] in "}]":
                # Skip this comma — it is a trailing comma before a
                # closer, which ``json.loads`` rejects.
                i += 1
                continue

        result.append(ch)
        i += 1

    return "".join(result)
