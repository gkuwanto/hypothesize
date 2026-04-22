"""Diversity heuristic: greedy k-center over Jaccard distance on input tokens.

Given a list of ``TestCase`` objects and a target size, pick a subset of
cases that are maximally dissimilar, as measured by Jaccard distance on
whitespace-lowercased tokens of every value in ``input_data``. The first
case is used as the seed; each subsequent pick maximizes the minimum
Jaccard distance to the already-selected set. Ties break by original order
(strict greater-than comparison), which makes the output deterministic.
"""

from __future__ import annotations

from typing import Any

from hypothesize.core.types import TestCase


def _tokens(value: Any) -> set[str]:
    parts: list[str] = []

    def _visit(v: Any) -> None:
        if isinstance(v, dict):
            for child in v.values():
                _visit(child)
        elif isinstance(v, (list, tuple)):
            for child in v:
                _visit(child)
        else:
            parts.append(str(v))

    _visit(value)
    combined = " ".join(parts).lower()
    return set(combined.split())


def _jaccard_distance(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    intersection = a & b
    return 1.0 - (len(intersection) / len(union))


def diversify_subset(cases: list[TestCase], target_n: int) -> list[TestCase]:
    """Return up to ``target_n`` cases, maximizing pairwise diversity."""
    if target_n <= 0 or not cases:
        return []
    if len(cases) <= target_n:
        return list(cases)

    token_sets = [_tokens(c.input_data) for c in cases]
    selected: list[int] = [0]
    remaining: list[int] = list(range(1, len(cases)))

    while len(selected) < target_n and remaining:
        best_idx: int | None = None
        best_min_dist = -1.0
        for candidate in remaining:
            min_dist = min(
                _jaccard_distance(token_sets[candidate], token_sets[s])
                for s in selected
            )
            if min_dist > best_min_dist:
                best_min_dist = min_dist
                best_idx = candidate
        assert best_idx is not None
        selected.append(best_idx)
        remaining.remove(best_idx)

    return [cases[i] for i in selected]
