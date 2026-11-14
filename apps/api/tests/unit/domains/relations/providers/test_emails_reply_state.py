"""The mail exchanged with a person says where each message stands (ADR-379).

A person's 360° view and the overview a model reads listed each message alone: a mail
of theirs asking for an answer kept its « reply expected » badge after the answer was
sent, and nothing said whether a mail the owner sent had been answered.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.mail_reply_state import ReplyMessage, ReplyState
from src.core.prompt_store import read_prompt_file
from src.domains.connectors.clients.mail_conversation import Conversation
from src.domains.relations.overview import fallback
from src.domains.relations.overview.blocks import provider_blocks
from src.domains.relations.overview_scope import OverviewSection, RelationOverviewScope
from src.domains.relations.providers.client import CategoryClient
from src.domains.relations.providers.emails import fetch_exchanged_emails
from src.domains.relations.providers.schemas import (
    ContextSection,
    ContextStatus,
    ExchangedEmail,
    RelationContext,
)

pytestmark = pytest.mark.unit

USER_ID = uuid4()
NOW = datetime.now(UTC)
THEIRS = "Gerard <gerard@x.com>"
MINE = "Me <me@example.org>"


def _message(message_id: str, *, sent: bool = False, minutes_ago: int) -> dict[str, Any]:
    """A message of the exchange: theirs unless ``sent``, in its own conversation."""
    return {
        "id": message_id,
        "threadId": f"t-{message_id}",
        "labelIds": ["SENT"] if sent else ["INBOX"],
        "from": MINE if sent else THEIRS,
        "to": THEIRS if sent else MINE,
        "subject": f"subject {message_id}",
        "snippet": "a line of it",
        "internalDate": str(int((NOW - timedelta(minutes=minutes_ago)).timestamp() * 1000)),
    }


def _later(message: dict[str, Any], message_id: str, *, mine: bool) -> dict[str, Any]:
    """A message written in ``message``'s conversation after it."""
    return {
        **_message(message_id, sent=mine, minutes_ago=0),
        "threadId": message["threadId"],
    }


def _mailbox(
    by_direction: dict[str, list[dict[str, Any]]], conversations: dict[str, Conversation]
) -> AsyncMock:
    """A mailbox answering each direction's search, and telling ``conversations``."""
    mailbox = AsyncMock()

    async def _search(query: str, **_: object) -> dict[str, Any]:
        direction = "sent" if query.startswith("in:sent to:") else "received"
        found = [] if query.startswith("in:sent cc:") else by_direction.get(direction, [])
        return {"messages": [dict(message) for message in found]}

    mailbox.search_emails = AsyncMock(side_effect=_search)
    mailbox.conversations_of = AsyncMock(return_value=conversations)
    return mailbox


async def _exchange(mailbox: AsyncMock, *, limit: int = 10) -> list[ExchangedEmail]:
    @contextlib.asynccontextmanager
    async def _open(*_: object) -> AsyncIterator[CategoryClient]:
        yield CategoryClient(client=mailbox, connector_type=None)

    with patch("src.domains.relations.providers.emails.open_category_client", _open):
        return await fetch_exchanged_emails(
            USER_ID, addresses=["gerard@x.com"], limit=limit, window_days=30, now=NOW
        )


class TestTheExchangeSaysWhereEachMessageStands:
    async def test_a_mail_answered_and_a_mail_that_got_a_reply_both_say_so(self) -> None:
        theirs = _message("theirs", minutes_ago=60)
        mine = _message("mine", sent=True, minutes_ago=30)
        told = {
            theirs["threadId"]: Conversation(messages=(theirs, _later(theirs, "a1", mine=True))),
            mine["threadId"]: Conversation(messages=(mine, _later(mine, "a2", mine=False))),
        }

        found = await _exchange(_mailbox({"received": [theirs], "sent": [mine]}, told))

        standing = {email.id: email.reply_state and email.reply_state.status for email in found}
        assert standing == {"theirs": "answered", "mine": "reply_received"}

    async def test_the_instants_of_a_state_are_utc_like_the_rest_of_the_contract(self) -> None:
        """A record a model reads never holds two zones: ``occurred_at`` is UTC."""
        theirs = _message("theirs", minutes_ago=60)
        told = {theirs["threadId"]: Conversation(messages=(theirs, _later(theirs, "a", mine=True)))}

        (email,) = await _exchange(_mailbox({"received": [theirs]}, told))

        assert email.reply_state is not None and email.reply_state.message is not None
        assert email.reply_state.message.at.utcoffset() == timedelta(0)
        assert email.reply_state.observed_at.utcoffset() == timedelta(0)

    async def test_only_the_listed_messages_are_looked_up(self) -> None:
        """Three searches per address may find far more than the section lists."""
        received = [_message(f"m{index}", minutes_ago=index + 1) for index in range(5)]
        mailbox = _mailbox({"received": received}, {})

        found = await _exchange(mailbox, limit=2)

        looked_up = [message["id"] for message in mailbox.conversations_of.await_args.args[0]]
        assert looked_up == [email.id for email in found] == ["m0", "m1"]


def _answered() -> ReplyState:
    return ReplyState(
        status="answered",
        message=ReplyMessage(
            message_id="a1", at=NOW - timedelta(minutes=5), correspondents="Gerard", excerpt="ok"
        ),
        observed_at=NOW,
        valid_until=NOW + timedelta(minutes=2),
    )


def _context(*emails: ExchangedEmail) -> RelationContext:
    off = ContextSection(status=ContextStatus.NOT_REQUESTED, generated_at=NOW)
    return RelationContext(
        contact=off,
        emails=ContextSection(status=ContextStatus.OK, generated_at=NOW, emails=list(emails)),
        events=off,
        window_days=30,
        email_window_days=30,
    )


def test_the_overview_a_model_reads_says_an_answered_mail_is_answered() -> None:
    answered = ExchangedEmail(
        id="theirs", direction="received", subject="Quote", reply_state=_answered()
    )
    plain = ExchangedEmail(id="other", direction="received", subject="News")
    scope = RelationOverviewScope(sections=[OverviewSection.EMAILS])

    first, second = provider_blocks(_context(answered, plain), scope)["emails"]

    assert first["reply_state"].startswith("answered on ")
    assert "reply_state" not in second


def test_the_debrief_prompt_explains_the_field_its_evidence_carries() -> None:
    """A field nobody explains is read as the model pleases."""
    assert "`reply_state`" in read_prompt_file("relation_debrief_prompt")


async def test_mail_found_by_name_says_where_it_stands_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    theirs = _message("theirs", minutes_ago=60)
    told = {theirs["threadId"]: Conversation(messages=(theirs, _later(theirs, "a", mine=True)))}
    mailbox = AsyncMock()
    mailbox.search_emails = AsyncMock(return_value={"messages": [dict(theirs)]})
    mailbox.conversations_of = AsyncMock(return_value=told)

    @contextlib.asynccontextmanager
    async def _open(*_: object) -> AsyncIterator[CategoryClient]:
        yield CategoryClient(client=mailbox, connector_type=None)

    monkeypatch.setattr(fallback, "open_category_client", _open)

    (found,) = await fallback.fetch_recent_emails(USER_ID, "Gerard") or []

    assert found["subject"] == "subject theirs"
    assert found["reply_state"].startswith("answered on ")
