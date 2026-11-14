"""What the person already answered to an e-mail they are answering again (ADR-379).

Answering twice is allowed — a follow-up, a correction — never blind: the confirmation
card says the message was already answered, and a reply LIA writes reads what the
person said. Fail-open like the door it asks: a mailbox that cannot tell says nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.field_names import FIELD_MAIL_ANSWERED, FIELD_MAIL_ANSWERED_AT
from src.domains.agents.emails.previous_reply import previous_reply_of
from src.domains.connectors.clients.mail_conversation import Conversation

pytestmark = [pytest.mark.unit]

ME = "Me <me@example.org>"
MARC = "Marc Dupont <marc@example.org>"
PARIS = "Europe/Paris"
START = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)


def _millis(minute: int) -> str:
    return str(int((START + timedelta(minutes=minute)).timestamp() * 1000))


def _message(message_id: str, minute: int, labels: list[str], **over: Any) -> dict[str, Any]:
    return {
        "id": message_id,
        "threadId": "t1",
        "internalDate": _millis(minute),
        "labelIds": labels,
        "snippet": f"words of {message_id}",
        "cc": "",
        **over,
    }


ASKED = _message("m1", 0, ["INBOX"], **{"from": MARC, "to": ME})
#: A provider preview: the reply, then the history it quotes.
_PREVIEW = (
    "Yes, Friday works. On Tue, Nov 10, 2026 at 9:00 AM Marc Dupont <marc@example.org> "
    "wrote: Can you make it?"
)
REPLY = _message("m2", 30, ["SENT"], **{"from": ME, "to": MARC, "snippet": _PREVIEW})


def _mailbox(conversation: Conversation | None) -> AsyncMock:
    client = AsyncMock()
    client.conversations_of = AsyncMock(
        return_value={} if conversation is None else {"t1": conversation}
    )
    client.get_message = AsyncMock(
        return_value={**REPLY, "body": "Yes, Friday works for me.\n\nSee you then."}
    )
    return client


async def test_an_answered_message_tells_when_it_was_answered() -> None:
    client = _mailbox(Conversation(messages=(dict(ASKED), dict(REPLY))))

    previous = await previous_reply_of(client, ASKED, user_timezone=PARIS)

    assert previous is not None
    assert previous.at is not None and previous.at.isoformat() == "2026-11-10T09:30:00+01:00"
    client.get_message.assert_not_awaited()  # the card needs no more than the instant


async def test_the_answers_own_words_are_read_when_a_reply_is_to_be_written() -> None:
    client = _mailbox(Conversation(messages=(dict(ASKED), dict(REPLY))))

    previous = await previous_reply_of(client, ASKED, user_timezone=PARIS, with_words=True)

    assert previous is not None
    assert previous.words == "Yes, Friday works for me.\n\nSee you then."
    assert client.get_message.await_args.args[0] == "m2"


async def test_an_answer_that_cannot_be_read_again_keeps_its_excerpt() -> None:
    client = _mailbox(Conversation(messages=(dict(ASKED), dict(REPLY))))
    client.get_message.side_effect = RuntimeError("the mailbox is away")

    previous = await previous_reply_of(client, ASKED, user_timezone=PARIS, with_words=True)

    assert previous is not None and previous.words == "Yes, Friday works."


async def test_the_mailboxs_own_mark_alone_is_still_an_answer() -> None:
    marked = {
        **ASKED,
        FIELD_MAIL_ANSWERED: True,
        FIELD_MAIL_ANSWERED_AT: _millis(45),
    }
    client = _mailbox(Conversation(messages=(marked,)))

    previous = await previous_reply_of(client, ASKED, user_timezone=PARIS, with_words=True)

    assert previous is not None
    assert previous.at is not None and previous.at.isoformat() == "2026-11-10T09:45:00+01:00"
    assert previous.words == ""
    client.get_message.assert_not_awaited()


@pytest.mark.parametrize(
    "conversation",
    [Conversation(messages=(dict(ASKED),)), None],
    ids=["unanswered", "the-mailbox-cannot-tell"],
)
async def test_nothing_is_said_of_a_message_not_known_answered(
    conversation: Conversation | None,
) -> None:
    assert await previous_reply_of(_mailbox(conversation), ASKED, user_timezone=PARIS) is None
