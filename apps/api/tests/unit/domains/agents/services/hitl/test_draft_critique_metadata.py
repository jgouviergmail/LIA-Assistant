"""The draft-critique metadata chunk carries what a ticket run needs (lot 7).

A workboard run reads ``hitl_interrupt_metadata`` to carry the draft to the
person: the tool that built it names the replay, and a FOR_EACH batch travels
whole — approving the first of three must never run the other two unseen. The
chat's card ignores fields it does not know, so this is additive.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.services.hitl.interactions.draft_critique import (
    DraftCritiqueInteraction,
)

pytestmark = pytest.mark.unit


def _chunk(context: dict[str, Any]) -> dict[str, Any]:
    interaction = DraftCritiqueInteraction(question_generator=None)  # type: ignore[arg-type]
    return interaction.build_metadata_chunk(
        context=context, message_id="m-1", conversation_id="c-1"
    )


class TestWhatTheChunkCarries:
    def test_the_tool_that_built_the_draft(self) -> None:
        chunk = _chunk(
            {
                "draft_id": "d-1",
                "draft_type": "tool_call",
                "draft_content": {"tool_name": "mcp_x_delete"},
                "tool_name": "mcp_x_delete",
            }
        )
        assert chunk["action_requests"][0]["tool_name"] == "mcp_x_delete"

    def test_a_batch_travels_whole(self) -> None:
        drafts = [
            {"draft_id": "d-1", "draft_type": "email", "draft_content": {"to": "a"}},
            {"draft_id": "d-2", "draft_type": "email", "draft_content": {"to": "b"}},
        ]
        chunk = _chunk(
            {
                "draft_id": "d-1",
                "draft_type": "email",
                "draft_content": {"to": "a"},
                "batch_total": 2,
                "batch_drafts": drafts,
            }
        )
        request = chunk["action_requests"][0]
        assert request["batch_total"] == 2
        assert request["batch_drafts"] == drafts

    def test_a_lone_draft_says_nothing_about_a_batch(self) -> None:
        chunk = _chunk({"draft_id": "d-1", "draft_type": "email", "draft_content": {}})
        request = chunk["action_requests"][0]
        assert "batch_total" not in request
        assert "batch_drafts" not in request
        assert request["tool_name"] is None
