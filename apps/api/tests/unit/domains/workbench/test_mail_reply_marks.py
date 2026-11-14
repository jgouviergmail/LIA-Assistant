"""The mail screen's reply marks, read apart from its listing (ADR-369, ADR-379).

A listing is ONE search and never waits for anything else: where each row stands in
its conversation is asked afterwards, for the rows shown, and comes back as the marks
to draw — an answer given, an answer drafted, a reply received. « Nothing yet » is no
mark, and a mailbox that cannot tell marks nothing: the page is never broken by them.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.mail_conversation import Conversation
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import mail_reading
from src.domains.workbench.schemas.mail import MessageRef, ReplyMarksRequest

pytestmark = pytest.mark.unit

USER = uuid4()
PARIS = ZoneInfo("Europe/Paris")
NOW = datetime.now(UTC)
THEIRS = "Ana Lima <ana@example.org>"
MINE = "Me <me@example.org>"


def _door(client: Any) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(
            client=client, connector_type=ConnectorType.GOOGLE_GMAIL, preferred_name=None
        )

    return patch.object(mail_reading, "open_tool_client", opened)


def _row(message_id: str, thread: str, *, labels: list[str], minutes_ago: int) -> dict[str, Any]:
    """A message as its conversation holds it: the person's own when labelled so."""
    mine = bool({"SENT", "DRAFT"} & set(labels))
    return {
        "id": message_id,
        "threadId": thread,
        "labelIds": labels,
        "from": MINE if mine else THEIRS,
        "to": THEIRS if mine else MINE,
        "snippet": "a line of it",
        "internalDate": str(int((NOW - timedelta(minutes=minutes_ago)).timestamp() * 1000)),
    }


def _conversations() -> dict[str, Conversation]:
    """Five conversations, one per way a row can stand."""
    return {
        "t-answered": Conversation(
            messages=(
                _row("answered", "t-answered", labels=["INBOX"], minutes_ago=60),
                _row("a1", "t-answered", labels=["SENT"], minutes_ago=30),
            )
        ),
        "t-drafted": Conversation(
            messages=(_row("drafted", "t-drafted", labels=["INBOX"], minutes_ago=60),),
            drafts=(_row("d1", "t-drafted", labels=["DRAFT"], minutes_ago=30),),
        ),
        "t-waiting": Conversation(
            messages=(_row("waiting", "t-waiting", labels=["INBOX"], minutes_ago=60),)
        ),
        "t-replied": Conversation(
            messages=(
                _row("replied", "t-replied", labels=["SENT"], minutes_ago=60),
                _row("r1", "t-replied", labels=["INBOX"], minutes_ago=30),
            )
        ),
        "t-silent": Conversation(
            messages=(_row("silent", "t-silent", labels=["SENT"], minutes_ago=60),)
        ),
    }


_ROWS = ("answered", "drafted", "waiting", "replied", "silent")


def _asked(*ids: str) -> ReplyMarksRequest:
    return ReplyMarksRequest(messages=[MessageRef(id=row, thread_id=f"t-{row}") for row in ids])


class TestTheMarksOfAPage:
    async def test_only_what_happened_is_marked(self) -> None:
        client = MagicMock(conversations_of=AsyncMock(return_value=_conversations()))
        with _door(client):
            marks = await mail_reading.read_reply_marks(USER, PARIS, _asked(*_ROWS))

        assert {mark.id: mark.status for mark in marks.items} == {
            "answered": "answered",
            "drafted": "answer_drafted",
            "replied": "reply_received",
        }

    async def test_the_mailbox_is_asked_once_for_the_rows_named(self) -> None:
        client = MagicMock(conversations_of=AsyncMock(return_value={}))
        with _door(client):
            await mail_reading.read_reply_marks(USER, PARIS, _asked("answered", "waiting"))

        client.conversations_of.assert_awaited_once()
        assert client.conversations_of.await_args.args[0] == [
            {"id": "answered", "threadId": "t-answered"},
            {"id": "waiting", "threadId": "t-waiting"},
        ]

    async def test_a_mailbox_that_cannot_tell_marks_nothing(self) -> None:
        """The marks are read apart so that the page never depends on them."""
        client = MagicMock(conversations_of=AsyncMock(side_effect=RuntimeError("away")))
        with _door(client):
            marks = await mail_reading.read_reply_marks(USER, PARIS, _asked(*_ROWS))

        assert marks.items == []
