"""What the conversation's message loader hands the chat, pinned before it is typed (A14b).

The messages come back newest first, each with the token summary of its run. Two rules
shape what the page receives: an assistant bubble with no visible text (an ephemeral
progress message) is dropped, and in a run that answered more than once (a HITL flow)
only the NEWEST assistant message carries the run's tokens and cost — the earlier ones
show none, so a run is never counted twice on screen.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.field_names import (
    FIELD_CONTENT,
    FIELD_COST_EUR,
    FIELD_GOOGLE_API_REQUESTS,
    FIELD_RUN_ID,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
)
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.repository import ConversationRepository
from src.domains.conversations.service import ConversationService

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)
TOKEN_FIELDS = (
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
    FIELD_TOKENS_CACHE,
    FIELD_COST_EUR,
    FIELD_GOOGLE_API_REQUESTS,
)


def _message(role: str, content: str, run_id: str | None, minutes_ago: int) -> ConversationMessage:
    return ConversationMessage(
        id=uuid4(),
        conversation_id=uuid4(),
        role=role,
        content=content,
        message_metadata={FIELD_RUN_ID: run_id} if run_id else {},
        created_at=NOW - timedelta(minutes=minutes_ago),
    )


def _summary(tokens: int) -> dict[str, Any]:
    return {
        "prompt_tokens": tokens,
        "completion_tokens": tokens // 2,
        "cached_tokens": tokens // 4,
        "cost_eur": tokens / 1000,
        FIELD_GOOGLE_API_REQUESTS: 1,
    }


async def _loaded(
    monkeypatch: pytest.MonkeyPatch,
    rows: Sequence[tuple[ConversationMessage, dict[str, Any] | None]],
) -> list[dict[str, Any]]:
    async def loaded(
        self: ConversationRepository, **_: object
    ) -> Sequence[tuple[ConversationMessage, dict[str, Any] | None]]:
        return rows

    monkeypatch.setattr(ConversationRepository, "get_messages_with_token_summaries", loaded)
    service = ConversationService()
    monkeypatch.setattr(
        service, "get_active_conversation", AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    )
    return await service.get_messages_with_tokens_v2(uuid4(), 50, AsyncMock())


async def test_an_assistant_bubble_with_no_visible_text_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kept = _message("assistant", "Done.", None, 1)
    empty_user = _message("user", "", None, 2)
    rows = [(kept, None), (_message("assistant", "  \n ", None, 3), None), (empty_user, None)]

    loaded = await _loaded(monkeypatch, rows)

    assert [entry["id"] for entry in loaded] == [kept.id, empty_user.id]


async def test_only_the_newest_answer_of_a_run_carries_its_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    newest = _message("assistant", "Here it is.", "run-1", 1)
    earlier = _message("assistant", "Shall I?", "run-1", 2)
    question = _message("user", "Book it", "run-1", 3)
    rows = [(newest, _summary(1000)), (earlier, _summary(1000)), (question, _summary(1000))]

    loaded = {entry["id"]: entry for entry in await _loaded(monkeypatch, rows)}

    assert loaded[newest.id][FIELD_TOKENS_IN] == 1000
    assert loaded[newest.id][FIELD_COST_EUR] == 1.0
    assert all(loaded[earlier.id][field] is None for field in TOKEN_FIELDS)
    # The rule speaks of answers: the person's message keeps what the join gave it.
    assert loaded[question.id][FIELD_TOKENS_IN] == 1000


async def test_a_message_without_a_run_keeps_its_summary_and_its_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alone = _message("assistant", "Hello", None, 1)

    (entry,) = await _loaded(monkeypatch, [(alone, _summary(400))])

    assert entry[FIELD_CONTENT] == "Hello" and entry[FIELD_TOKENS_OUT] == 200
    assert entry[FIELD_TOKENS_CACHE] == 100 and entry[FIELD_GOOGLE_API_REQUESTS] == 1


async def test_a_message_without_a_summary_shows_no_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    (entry,) = await _loaded(monkeypatch, [(_message("assistant", "Hi", "run-9", 1), None)])

    assert all(entry[field] is None for field in TOKEN_FIELDS)


async def test_no_active_conversation_loads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ConversationService()
    monkeypatch.setattr(service, "get_active_conversation", AsyncMock(return_value=None))

    assert await service.get_messages_with_tokens_v2(uuid4(), 50, AsyncMock()) == []
