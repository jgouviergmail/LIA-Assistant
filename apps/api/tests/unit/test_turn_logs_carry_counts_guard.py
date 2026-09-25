"""The turn's logs above DEBUG carry counts, never the words (CLAUDE.md, Observability).

Measured in production on 2026-09-24 (Loki, field names and lengths only):
``orphan_tool_message_removed`` wrote the first 100 characters of a tool result
at WARNING 330 times in seven days — mail, calendar and contact text — and
``detected_interrupt_resumption`` wrote the person's whole typed answer at INFO.
The events below were fixed together; this guard keeps each of them from
growing its text back. A value may name the text only inside ``len(...)``.

A codebase-wide ratchet over every log above DEBUG is a separate piece of work:
a first scan counts about 150 sites whose field names suggest content.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

FIXED_EVENTS: dict[str, set[str]] = {
    "domains/agents/services/orchestration/service.py": {
        "stale_hitl_detected_treating_as_new_request",
        "detected_interrupt_resumption",
        "hitl_resume_command_adding_user_message",
    },
    "domains/agents/nodes/router_node_v3.py": {"router_v3_start"},
    "domains/agents/utils/message_filters.py": {"orphan_tool_message_removed"},
    # Moved with the content generation out of emails_tools.py (ADR-314).
    "domains/agents/emails/content_generation.py": {
        "email_content_instruction_fallback_to_user_message"
    },
    # The person's image request and its rewrite are never logged (ADR-315).
    "domains/agents/image_generation/prompt_enhancement.py": {
        "image_prompt_enhanced",
        "image_prompt_enhancement_rejected",
    },
}

_LEVELS = {"info", "warning", "error", "exception", "critical"}
_TEXT = re.compile(r"\b(user_message|query|content|message)\b")


def _event_calls(tree: ast.AST, events: set[str]) -> dict[str, list[ast.Call]]:
    found: dict[str, list[ast.Call]] = {event: [] for event in events}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LEVELS
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in found
        ):
            found[node.args[0].value].append(node)
    return found


@pytest.mark.parametrize(("module", "events"), sorted(FIXED_EVENTS.items()))
def test_the_event_carries_counts_never_the_words(module: str, events: set[str]) -> None:
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    calls = _event_calls(tree, events)

    missing = sorted(event for event, found in calls.items() if not found)
    assert not missing, f"{module}: events not found above DEBUG (renamed?): {missing}"
    offenders = [
        f"{event}: {keyword.arg}={ast.unparse(keyword.value)}"
        for event, found in calls.items()
        for call in found
        for keyword in call.keywords
        if _TEXT.search(ast.unparse(keyword.value))
        and not ast.unparse(keyword.value).startswith("len(")
    ]
    assert not offenders, f"{module}: a turn log carries text above DEBUG: {offenders}"
