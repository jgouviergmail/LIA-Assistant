"""The reply a person confirms says when they already answered that message (ADR-379).

The chat's reply tool prepares a card the person approves before anything leaves. When
the mailbox says the original was already answered, the card carries it — the person
may still answer again, knowingly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.tools.emails_tools import ReplyEmailDraftTool
from src.domains.connectors.clients.mail_conversation import Conversation

pytestmark = [pytest.mark.unit]

START = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)


def _millis(minute: int) -> str:
    return str(int((START + timedelta(minutes=minute)).timestamp() * 1000))


ORIGINAL: dict[str, Any] = {
    "id": "m1",
    "threadId": "t1",
    "labelIds": ["INBOX"],
    "internalDate": _millis(0),
    "from": "Paul <paul@example.com>",
    "to": "me@example.com",
    "cc": "",
    "subject": "Budget",
}
REPLY: dict[str, Any] = {
    "id": "m2",
    "threadId": "t1",
    "labelIds": ["SENT"],
    "internalDate": _millis(30),
    "from": "me@example.com",
    "to": "Paul <paul@example.com>",
    "cc": "",
    "snippet": "Agreed.",
}


def _client(conversation: Conversation | None) -> AsyncMock:
    client = AsyncMock()
    client.get_message = AsyncMock(return_value=dict(ORIGINAL))
    client.get_own_address = AsyncMock(return_value="me@example.com")
    client.conversations_of = AsyncMock(
        return_value={} if conversation is None else {"t1": conversation}
    )
    return client


async def _card(client: AsyncMock) -> dict[str, Any]:
    tool = ReplyEmailDraftTool()
    result = await tool.execute_api_call(client, uuid4(), message_id="m1", body="One more thing.")
    (item,) = tool.format_registry_response(result).registry_updates.values()
    content = item.payload["content"]
    assert isinstance(content, dict)
    return content


async def test_a_reply_to_an_answered_message_carries_when_it_was_answered() -> None:
    card = await _card(_client(Conversation(messages=(dict(ORIGINAL), dict(REPLY)))))

    assert card["already_answered"] is True
    assert datetime.fromisoformat(card["answered_at"]) == START + timedelta(minutes=30)


@pytest.mark.parametrize(
    "conversation",
    [Conversation(messages=(dict(ORIGINAL),)), None],
    ids=["unanswered", "the-mailbox-cannot-tell"],
)
async def test_a_first_reply_carries_nothing_of_the_kind(conversation: Conversation | None) -> None:
    card = await _card(_client(conversation))

    assert card["already_answered"] is False and card["answered_at"] is None


async def test_the_subject_of_the_reply_is_unchanged() -> None:
    """The subject rule moved to the clients' own helper: same words, empty stays empty."""
    card = await _card(_client(None))
    assert card["subject"] == "Re: Budget"

    client = _client(None)
    client.get_message.return_value = {**ORIGINAL, "subject": "RE: Budget"}
    assert (await _card(client))["subject"] == "RE: Budget"

    client.get_message.return_value = {**ORIGINAL, "subject": ""}
    assert (await _card(client))["subject"] == ""
