"""The authorship bench classifies a first call by production's own dictation rule."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.react.measure_email_authorship import REQUESTS, WRITING_TOOL, verdict_of
from src.domains.agents.emails.authorship import WRITING_TOOLS

pytestmark = pytest.mark.unit

INTENT = "Écris à paul@example.com pour lui dire que je serai en retard demain."
DICTATED = "Envoie à paul@example.com : « Salut Paul, je serai en retard ce soir. Jean »"


def _send(**args: Any) -> list[dict[str, Any]]:
    return [{"name": WRITING_TOOL, "args": args}]


@pytest.mark.parametrize(
    ("request_text", "calls", "verdict"),
    [
        (INTENT, [], "no_call"),
        (INTENT, [{"name": "create_mailbox_draft_tool", "args": {}}], "other_tool"),
        (INTENT, _send(content_instruction="say I'll be late"), "instruction"),
        (DICTATED, _send(body="Salut Paul, je serai en retard ce soir. Jean"), "dictated"),
        (INTENT, _send(body="Bonjour Paul,\n\nJe serai en retard demain.\n\nJean"), "agent_text"),
        (INTENT, _send(body="  ", content_instruction="late"), "instruction"),
    ],
)
def test_a_first_call_is_classified_by_the_production_rule(
    request_text: str, calls: list[dict[str, Any]], verdict: str
) -> None:
    assert verdict_of(request_text, calls) == verdict


def test_the_bench_watches_a_writing_tool_and_covers_both_kinds() -> None:
    assert WRITING_TOOL in WRITING_TOOLS
    assert {kind for kind, _request in REQUESTS} >= {"intent", "dictated"}
