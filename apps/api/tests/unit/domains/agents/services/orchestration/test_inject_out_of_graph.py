"""Voice-only exchanges enter the next turn in order, both roles (ADR-299, spec A7);
proactive notifications keep entering as before."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.core.constants import LIVE_TURN_MESSAGE_TYPE
from src.domains.agents.services.orchestration.service import OrchestrationService

pytestmark = pytest.mark.unit


def _row(role: str, content: str, type_: str) -> SimpleNamespace:
    return SimpleNamespace(
        role=role, content=content, message_metadata={"type": type_}, created_at=datetime.now(UTC)
    )


async def _inject(rows: list[SimpleNamespace]) -> list:
    repo = MagicMock()
    repo.get_proactive_messages_after = AsyncMock(return_value=rows)
    state: dict = {"messages": []}
    with (
        patch("src.domains.conversations.repository.ConversationRepository", return_value=repo),
        patch("src.infrastructure.database.get_db_context") as ctx,
    ):
        ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        service = OrchestrationService.__new__(OrchestrationService)
        count = await service._inject_proactive_messages(state, uuid.uuid4(), None, "run")
    assert count == len(rows)
    return state["messages"]


async def test_injects_a_human_then_an_ai_message_in_order() -> None:
    messages = await _inject(
        [
            _row("user", "hello", LIVE_TURN_MESSAGE_TYPE),
            _row("assistant", "hi!", LIVE_TURN_MESSAGE_TYPE),
            _row("assistant", "a reminder", "proactive_reminder"),
        ]
    )
    assert isinstance(messages[0], HumanMessage) and messages[0].content == "hello"
    assert isinstance(messages[1], AIMessage) and messages[1].content == "hi!"
    assert messages[0].additional_kwargs["live_turn"] is True
    assert messages[1].additional_kwargs["live_turn"] is True
    assert messages[2].additional_kwargs["proactive_notification"] is True
    assert messages[2].additional_kwargs["proactive_type"] == "proactive_reminder"


async def test_a_proactive_row_keeps_its_shape() -> None:
    messages = await _inject([_row("assistant", "news", "proactive_interest")])
    assert isinstance(messages[0], AIMessage)
    assert "live_turn" not in messages[0].additional_kwargs
