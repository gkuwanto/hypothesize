"""LLM-layer prompt templates.

This module hosts prompts whose consumer is the adapter / backend layer
rather than the core algorithm. The first such prompt —
``rewrite_prompt_messages`` for automatic alternative generation — is
populated by Feature 02 task 2.7. Keeping the module present (if empty)
now preserves the import surface promised by the Feature 02 design.
"""

from __future__ import annotations
