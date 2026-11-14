"""The response model reads the person's messages with when they were written (lot 17)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.nodes.response_node import _prepare_conversational_messages
from src.infrastructure.llm.message_view import stamped_now

pytestmark = pytest.mark.unit

TUESDAY = datetime(2026, 11, 10, 0, 12, tzinfo=UTC)  # 09:12 in Tokyo
FRIDAY = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)  # 18:30 in Tokyo


def _state() -> dict[str, Any]:
    return {
        "messages": [
            stamped_now(HumanMessage("I have the dentist tomorrow at 10.", id="h1"), TUESDAY),
            AIMessage("Noted.", id="a1"),
            stamped_now(HumanMessage("Is it still ahead of me?", id="h2"), FRIDAY),
        ],
        "user_timezone": "Asia/Tokyo",
        "execution_mode": "pipeline",
    }


async def _prepared(state: dict[str, Any], **overrides: Any) -> list[Any]:
    options: dict[str, Any] = {
        "neutralize_history_formatting": False,
        "plan_rejection_reason": None,
        "current_turn_attachments": None,
        "last_user_message": "Is it still ahead of me?",
        "has_vision_content": False,
        **overrides,
    }
    return await _prepare_conversational_messages(state, "run", **options)  # type: ignore[arg-type]


async def test_each_message_the_person_wrote_reads_with_its_instant_in_their_zone() -> None:
    messages = await _prepared(_state())

    assert [message.content for message in messages] == [
        "[Tue 10 Nov 2026, 09:12] I have the dentist tomorrow at 10.",
        "Noted.",
        "[Fri 13 Nov 2026, 18:30] Is it still ahead of me?",
    ]


def test_a_script_skill_reads_the_same_instants_in_its_text_history() -> None:
    from src.domains.agents.nodes.response_node import _build_conversation_history

    history, last, _query = _build_conversation_history(_state(), "run", False)  # type: ignore[arg-type]

    assert "[USER]: [Tue 10 Nov 2026, 09:12] I have the dentist tomorrow at 10." in history
    assert last == "Is it still ahead of me?"  # the query itself is read as written


async def test_a_question_read_with_its_images_keeps_its_instant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def vision(**kwargs: Any) -> HumanMessage:
        return HumanMessage([{"type": "text", "text": kwargs["text"]}, {"type": "image_url"}])

    monkeypatch.setattr("src.domains.attachments.llm_content.build_vision_message_async", vision)

    messages = await _prepared(_state(), current_turn_attachments=[{"id": "f1"}])

    assert messages[-1].content[0] == {"type": "text", "text": "[Fri 13 Nov 2026, 18:30]"}
    assert messages[-1].content[1] == {"type": "text", "text": "Is it still ahead of me?"}
