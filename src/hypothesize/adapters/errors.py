"""Typed exceptions raised by the adapter layer.

Feature 02 task 2.5 introduces ``AutoAlternativeUnavailable``, raised by
``PythonModuleAdapter.build_runner_with_prompt`` when the user's
module does not expose the prompt-factory convention required for
automatic alternative generation. Task 2.7 (session B) will extend
this module with ``BudgetExhausted`` for the auto-alt utility's
pre-pipeline budget check.
"""

from __future__ import annotations


class AutoAlternativeUnavailable(Exception):  # noqa: N818 — spec-named
    """The configured system cannot support automatic alternative generation.

    Raised when the user's Python module omits ``make_runner`` — in
    which case the adapter has no hook for plugging in a rewritten
    prompt. The exception message should name the convention and
    point the user at a worked example.
    """
