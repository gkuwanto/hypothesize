"""Prompts used by MCP tools.

Currently one entry: ``formulate_hypothesis_messages`` — the prompt
that turns a vague developer complaint into a structured
``Hypothesis`` dict. Lives next to the MCP tools because the only
caller is the MCP layer; ``core/prompts.py`` and ``llm/prompts.py``
are reserved for the algorithm and adapter layers respectively.
"""

from __future__ import annotations

import json
from typing import Any


def formulate_hypothesis_messages(
    complaint: str, context: dict[str, Any]
) -> list[dict]:
    """Build the message list for the formulate_hypothesis tool."""
    system = (
        "You convert vague developer complaints about LLM systems into "
        "testable failure hypotheses. A failure hypothesis names a "
        "specific class of input the system handles incorrectly, "
        "phrased so a developer can verify it by generating discriminating "
        "test cases."
    )
    user = (
        f"Complaint: {complaint}\n\n"
        f"Context: {json.dumps(context)}\n\n"
        "Return STRICT JSON: "
        '{"text": "<hypothesis sentence>", "context_refs": []}. '
        "The hypothesis text should be one sentence. context_refs is "
        "an array of file paths or short identifiers if any are "
        "relevant; otherwise an empty list. No prose outside the JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
