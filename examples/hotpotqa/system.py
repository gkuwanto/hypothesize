"""HotpotQA multi-hop QA — scaffold (NOT YET RUNNABLE).

Skeleton for a real-dataset example. Demonstrates the shape of a
non-classifier hypothesize integration without committing to a full
implementation in this session. The ``make_runner`` factory is in
place for the prompt-factory convention; the runner body raises
``NotImplementedError`` with the exact TODO list.

Finish this example by:

1. Downloading HotpotQA via ``datasets`` (the dependency is already
   declared in pyproject.toml). Pick the ``distractor`` split.
2. Wiring a retrieval step into ``run`` — at minimum, return the gold
   contexts named in the dataset entry; for a more honest test, pass
   the distractors too.
3. Replacing the ``raise NotImplementedError`` body with an actual
   Claude call that takes the question + contexts and returns
   ``{"answer": str}``.
"""

from __future__ import annotations

from typing import Any, Protocol

# TODO: replace this prompt with one tuned for multi-hop reasoning.
SYSTEM_PROMPT = (
    "You answer multi-hop questions using the provided contexts. "
    "Cite the supporting context sentence(s) inline. "
    "Reply with one short answer; no extra prose."
)


class _Backend(Protocol):
    async def complete(self, messages: list[dict], **kwargs: Any) -> str: ...


def make_runner(
    prompt: str | None = None,
    *,
    backend: _Backend | None = None,
):
    """Return an async runner — currently a stub.

    Mirrors the prompt-factory convention so the auto-alternative path
    works once the body is filled in. The signature is intentionally
    identical to ``examples/sarcasm/system.py`` so swapping examples
    is a one-line config change.
    """
    effective_prompt = prompt if prompt is not None else SYSTEM_PROMPT

    async def run(input_data: dict[str, Any]) -> dict[str, Any]:
        # TODO: read input_data['question'] and input_data['contexts'].
        # TODO: call ``backend.complete`` with the prompt + question + contexts.
        # TODO: return {"answer": <claude's response>}.
        # ``effective_prompt`` and ``backend`` are bound here for the
        # closure; they are unused until the TODO above is filled in.
        _ = (effective_prompt, backend, input_data)
        raise NotImplementedError(
            "TODO: implement HotpotQA runner. See examples/hotpotqa/README.md "
            "for the data download steps and the runner skeleton."
        )

    return run


run = make_runner()
