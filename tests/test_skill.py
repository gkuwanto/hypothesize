"""Tests for the Claude Code skill at .claude/skills/hypothesize/SKILL.md.

The skill is markdown text — Claude reads it, not Python. We can only
verify shape and presence: the file exists, has the expected
sections, and references the CLI commands the workflow depends on.
Behavior validation is the user's job after merge.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = REPO_ROOT / ".claude" / "skills" / "hypothesize" / "SKILL.md"


def test_skill_file_exists() -> None:
    assert SKILL_PATH.exists(), f"missing {SKILL_PATH}"


def test_skill_has_top_level_heading() -> None:
    text = SKILL_PATH.read_text()
    # First non-frontmatter heading should be "# hypothesize"
    assert re.search(r"^# hypothesize\s*$", text, re.MULTILINE)


def test_skill_declares_required_sections() -> None:
    text = SKILL_PATH.read_text()
    for section in ("## When to invoke", "## Workflow", "## Example invocations"):
        assert section in text, f"skill missing section: {section}"


def test_skill_workflow_steps_present() -> None:
    text = SKILL_PATH.read_text()
    # The five workflow steps are numbered ### subsections.
    for n in range(1, 5):
        assert re.search(rf"^### {n}\.", text, re.MULTILINE), (
            f"missing workflow step {n}"
        )


def test_skill_references_cli_commands() -> None:
    text = SKILL_PATH.read_text()
    assert "hypothesize run" in text
    assert "hypothesize list" in text
    assert "hypothesize validate" in text
    assert "--config" in text
    assert "--hypothesis" in text


def test_skill_has_no_unfilled_todos() -> None:
    text = SKILL_PATH.read_text()
    assert "TODO" not in text
    assert "FIXME" not in text
    assert "<placeholder>" not in text


def test_skill_has_yaml_frontmatter_block() -> None:
    text = SKILL_PATH.read_text()
    # Frontmatter is between leading --- delimiters.
    assert text.startswith("---\n")
    end = text.find("\n---\n", 4)
    assert end > 0
    frontmatter = text[4:end]
    assert "name: hypothesize" in frontmatter
    assert "description:" in frontmatter
