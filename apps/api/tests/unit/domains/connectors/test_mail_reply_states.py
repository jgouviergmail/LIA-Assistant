"""Where each listed message stands in its conversation — the one door (ADR-379).

Every surface that lists mail asks here. The door reads the page's conversations once,
decides each message's reply state, and fails OPEN: a mailbox that cannot be read, a time
budget reached or the switch turned off leave the page without states — « not known »,
never « unanswered » — and the reason is counted.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from prometheus_client import REGISTRY

from src.core.config import settings
from src.core.field_names import FIELD_MAIL_ANSWERED, FIELD_MAIL_ANSWERED_AT
from src.core.mail_reply_state import REPLY_STATE_KEY, read_reply_state
from src.domains.connectors.clients.mail_conversation import Conversation
from src.domains.connectors.mail_reply_states import (
    answered_mark,
    attach_reply_states,
    reply_states_of,
)
from src.domains.connectors.models import ConnectorType

pytestmark = pytest.mark.unit

ME = "Me <me@example.org>"
MARC = "Marc Dupont <marc@example.org>"
PARIS = "Europe/Paris"
#: A November morning: Paris is one hour ahead of UTC.
START = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)


def _millis(minute: int) -> str:
    return str(int((START + timedelta(minutes=minute)).timestamp() * 1000))


def _row(message_id: str, thread: str, minute: int, labels: list[str], **over: Any) -> dict:
    return {
        "id": message_id,
        "threadId": thread,
        "internalDate": _millis(minute),
        "labelIds": labels,
        "snippet": f"words of {message_id}",
        "cc": "",
        **over,
    }


def received(message_id: str, thread: str, minute: int = 0, **over: Any) -> dict:
    return _row(message_id, thread, minute, ["INBOX"], **{"from": MARC, "to": ME, **over})


def sent(message_id: str, thread: str, minute: int = 30, **over: Any) -> dict:
    return _row(message_id, thread, minute, ["SENT"], **{"from": ME, "to": MARC, **over})


class _Mailbox:
    """A mailbox's client, as the door uses it: the conversations it holds, by thread."""

    connector_type = ConnectorType.GOOGLE_GMAIL

    def __init__(
        self,
        conversations: Mapping[str, Conversation],
        *,
        error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.conversations = conversations
        self.error = error
        self.delay = delay
        self.asked: list[list[str]] = []
        self.kept: list[int] = []

    async def conversations_of(
        self, messages: Sequence[Mapping[str, Any]], max_messages: int
    ) -> dict[str, Conversation]:
        self.asked.append([str(message["id"]) for message in messages])
        self.kept.append(max_messages)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        threads = {message["threadId"] for message in messages}
        return {key: value for key, value in self.conversations.items() if key in threads}


def _answered_and_not() -> tuple[list[dict], _Mailbox]:
    asked, reply, waiting = received("m1", "t1"), sent("m2", "t1"), received("n1", "t2")
    mailbox = _Mailbox(
        {
            "t1": Conversation(messages=(asked, reply)),
            "t2": Conversation(messages=(waiting,)),
        }
    )
    return [dict(asked), dict(waiting)], mailbox


def _count(outcome: str) -> float:
    labels = {"provider": ConnectorType.GOOGLE_GMAIL.value, "outcome": outcome}
    return REGISTRY.get_sample_value("mail_reply_state_reads_total", labels) or 0.0


class TestAPageIsSituated:
    async def test_each_listed_message_gets_its_state_by_its_id(self) -> None:
        listed, mailbox = _answered_and_not()

        states = await reply_states_of(mailbox, listed, user_timezone=PARIS)

        assert {key: state.status for key, state in states.items()} == {
            "m1": "answered",
            "n1": "unanswered",
        }
        assert mailbox.asked == [["m1", "n1"]]  # one read for the page

    async def test_the_conversations_are_read_to_the_configured_depth(self) -> None:
        listed, mailbox = _answered_and_not()

        await reply_states_of(mailbox, listed, user_timezone=PARIS)

        assert mailbox.kept == [settings.mail_reply_state_conversation_max_messages]

    async def test_instants_are_told_in_the_accounts_zone(self) -> None:
        listed, mailbox = _answered_and_not()

        states = await reply_states_of(mailbox, listed, user_timezone=PARIS)

        reply = states["m1"].message
        assert reply is not None
        assert reply.at.isoformat() == "2026-11-10T09:30:00+01:00"

    async def test_a_reading_of_the_moment_is_valid_for_the_configured_time(self) -> None:
        listed, mailbox = _answered_and_not()

        state = (await reply_states_of(mailbox, listed, user_timezone=PARIS))["n1"]

        assert state.valid_until - state.observed_at == timedelta(
            seconds=settings.mail_reply_state_validity_seconds
        )

    async def test_the_state_travels_on_the_message_as_plain_data(self) -> None:
        listed, mailbox = _answered_and_not()

        await attach_reply_states(mailbox, listed, user_timezone=PARIS)

        carried = listed[0][REPLY_STATE_KEY]
        assert isinstance(carried, dict)
        assert read_reply_state(carried) is not None
        assert carried["status"] == "answered"

    async def test_a_message_whose_conversation_was_not_read_carries_nothing(self) -> None:
        listed, mailbox = _answered_and_not()
        mailbox.conversations = {"t1": mailbox.conversations["t1"]}

        await attach_reply_states(mailbox, listed, user_timezone=PARIS)

        assert REPLY_STATE_KEY in listed[0]
        assert REPLY_STATE_KEY not in listed[1]


class TestWhatIsNotAsked:
    async def test_an_empty_page_reads_nothing(self) -> None:
        mailbox = _Mailbox({})

        assert await reply_states_of(mailbox, [], user_timezone=PARIS) == {}
        assert mailbox.asked == []

    @pytest.mark.parametrize("label", ["SPAM", "TRASH", "DRAFT"])
    async def test_what_nobody_answers_is_not_read(self, label: str) -> None:
        listed, mailbox = _answered_and_not()
        listed[1]["labelIds"] = [label]

        states = await reply_states_of(mailbox, listed, user_timezone=PARIS)

        assert mailbox.asked == [["m1"]]
        assert "n1" not in states

    async def test_a_page_longer_than_the_bound_is_situated_up_to_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        listed, mailbox = _answered_and_not()
        monkeypatch.setattr(settings, "mail_reply_state_max_messages", 1)

        states = await reply_states_of(mailbox, listed, user_timezone=PARIS)

        assert mailbox.asked == [["m1"]]
        assert list(states) == ["m1"]

    async def test_switched_off_no_mailbox_is_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        listed, mailbox = _answered_and_not()
        monkeypatch.setattr(settings, "mail_reply_state_enabled", False)

        await attach_reply_states(mailbox, listed, user_timezone=PARIS)

        assert mailbox.asked == []
        assert all(REPLY_STATE_KEY not in message for message in listed)


class TestAFailureLeavesThePageWithoutStates:
    async def test_a_mailbox_that_cannot_be_read_is_counted_and_costs_nothing_else(self) -> None:
        listed, mailbox = _answered_and_not()
        mailbox.error = RuntimeError("the mailbox is away")
        before = _count("failed")

        states = await reply_states_of(mailbox, listed, user_timezone=PARIS)

        assert states == {}
        assert _count("failed") == before + 1

    async def test_a_read_past_its_time_budget_is_counted_as_such(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        listed, mailbox = _answered_and_not()
        mailbox.delay = 0.5
        monkeypatch.setattr(settings, "mail_reply_state_timeout_seconds", 0.01)
        before = _count("timeout")

        states = await reply_states_of(mailbox, listed, user_timezone=PARIS)

        assert states == {}
        assert _count("timeout") == before + 1

    async def test_a_page_read_is_counted_as_read(self) -> None:
        listed, mailbox = _answered_and_not()
        before = _count("read")

        await reply_states_of(mailbox, listed, user_timezone=PARIS)

        assert _count("read") == before + 1

    async def test_a_cancelled_caller_is_never_read_as_a_failure(self) -> None:
        """A turn the person stopped is not a mailbox that failed."""
        listed, mailbox = _answered_and_not()
        mailbox.delay = 5
        before = _count("failed") + _count("timeout")

        task = asyncio.create_task(reply_states_of(mailbox, listed, user_timezone=PARIS))
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert _count("failed") + _count("timeout") == before


class TestTheMailboxsOwnMark:
    """What a mailbox itself marks of a message comes WITH the message.

    A reader that cannot afford a conversation read — a proactive discussion's evidence,
    versioned and read again before any use — is told the mark alone. A message the door
    situates leaves with its state, never with the evidence behind it: one fact, told once.
    """

    def test_a_dated_mark_says_when_in_utc(self) -> None:
        marked = received(
            "m1", "t1", **{FIELD_MAIL_ANSWERED: True, FIELD_MAIL_ANSWERED_AT: _millis(40)}
        )

        assert answered_mark(marked) == "answered on 2026-11-10T08:40+00:00"

    def test_a_mark_with_no_date_claims_none(self) -> None:
        """IMAP keeps a flag, not the instant it was set."""
        assert answered_mark(received("m1", "t1", **{FIELD_MAIL_ANSWERED: True})) == "answered"

    def test_no_mark_says_nothing(self) -> None:
        """« Not known », never « unanswered »: a reply may have left no mark."""
        assert answered_mark(received("m1", "t1")) == ""

    @pytest.mark.parametrize("enabled", [True, False])
    async def test_a_situated_message_never_carries_the_mark_itself(
        self, monkeypatch: pytest.MonkeyPatch, enabled: bool
    ) -> None:
        listed, mailbox = _answered_and_not()
        listed[0] |= {FIELD_MAIL_ANSWERED: True, FIELD_MAIL_ANSWERED_AT: _millis(40)}
        monkeypatch.setattr(settings, "mail_reply_state_enabled", enabled)

        await attach_reply_states(mailbox, listed, user_timezone=PARIS)

        assert (REPLY_STATE_KEY in listed[0]) is enabled
        assert FIELD_MAIL_ANSWERED not in listed[0]
        assert FIELD_MAIL_ANSWERED_AT not in listed[0]
