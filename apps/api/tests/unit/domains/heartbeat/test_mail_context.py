"""The heartbeat's mail source lists the unread mail still awaiting the person.

Measured 2026-11-11: the push wake and the Gmail delta list every NEW inbox message,
and the section the decision reads is titled « UNREAD EMAILS ». A message the person
had already opened — and answered — reached the decision as unread, and could be
announced with an offer to reply. Unread is not unanswered either (ADR-379): a message
answered from a phone's notification may stay marked unread.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, tzinfo
from types import SimpleNamespace
from typing import Any, Self
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.core.constants import PUSH_WAKE_MAIL_MAX_MESSAGES
from src.core.prompt_store import read_prompt_file
from src.domains.connectors.clients.mail_conversation import Conversation
from src.domains.heartbeat import wake_context
from src.domains.heartbeat.context_prompt import _section_unread_emails
from src.domains.heartbeat.mail_context import format_email_date, unread_mail_summaries
from src.domains.heartbeat.schemas import HeartbeatContext
from src.domains.push_channels.wake import WakePayload

pytestmark = pytest.mark.unit

_USER = SimpleNamespace(id=uuid.uuid4(), timezone="Europe/Paris")
_DELTA = "src.domains.heartbeat.gmail_delta.delta_messages_or_none"


def _message(message_id: str, *, unread: bool) -> dict[str, Any]:
    return {
        "id": message_id,
        "threadId": f"t-{message_id}",
        "labelIds": ["INBOX", "UNREAD"] if unread else ["INBOX"],
        "from": "Sender <sender@example.org>",
        "subject": f"subject {message_id}",
        "snippet": "a line of it",
        "internalDate": str(int(time.time() * 1000)),
    }


def _mailbox(
    now: dict[str, dict[str, Any]] | None = None,
    *,
    cached: dict[str, dict[str, Any]] | None = None,
    conversations: dict[str, Conversation] | None = None,
) -> AsyncMock:
    """A mailbox as it stands ``now``, what its cache still holds of it, and the
    conversations it can tell of (none by default: it then says nothing of replies)."""
    mailbox = AsyncMock()
    mailbox.conversations_of = AsyncMock(return_value=conversations or {})

    async def _get(message_id: str, *, use_cache: bool = True, **_: object) -> dict[str, Any]:
        if use_cache and cached and message_id in cached:
            return dict(cached[message_id])
        return dict((now or {})[message_id])

    mailbox.get_message = AsyncMock(side_effect=_get)
    return mailbox


def _wake(*messages: dict[str, Any], new_history_id: str | None = None) -> WakePayload:
    return WakePayload(
        user_id=_USER.id,
        provider="google_gmail",
        enqueued_at=datetime.now(UTC),
        messages=messages,
        new_history_id=new_history_id,
    )


async def _summaries(
    mailbox: AsyncMock, *, wake: WakePayload | None = None
) -> list[dict[str, str]] | None:
    return await unread_mail_summaries(mailbox, _USER.id, _USER, settings, wake)


def _subjects(listed: list[dict[str, str]] | None) -> list[str]:
    return [row["subject"] for row in listed or []]


def _opened_then_one_unread() -> list[dict[str, Any]]:
    """As many opened messages as a decision looks at, less one, then an unread one."""
    opened = [
        _message(f"read{index}", unread=False) for index in range(PUSH_WAKE_MAIL_MAX_MESSAGES - 1)
    ]
    return [*opened, _message("new", unread=True)]


class TestAWake:
    async def test_it_lists_only_the_unread_mail_it_carries(self) -> None:
        wake = _wake(_message("read", unread=False), _message("new", unread=True))

        listed = await _summaries(_mailbox(), wake=wake)

        assert _subjects(listed) == ["subject new"]

    async def test_opened_mail_never_takes_the_place_of_unread_mail_behind_it(self) -> None:
        """The cap bounds what is listed, never what is looked at."""
        listed = await _summaries(_mailbox(), wake=_wake(*_opened_then_one_unread()))

        assert _subjects(listed) == ["subject new"]

    async def test_mail_all_opened_announces_nothing_and_still_consumes_the_delta(self) -> None:
        """Nothing to announce is an answer: the next tick must not read that delta again."""
        wake = _wake(_message("read", unread=False), new_history_id="778")
        with patch.object(wake_context, "advance_gmail_anchor", AsyncMock()) as advance:
            listed = await _summaries(_mailbox(), wake=wake)

        assert listed is None
        advance.assert_awaited_once_with(_USER.id, "778")


class TestATickDelta:
    async def test_it_lists_only_the_new_mail_still_unread(self) -> None:
        now = {"read": _message("read", unread=False), "new": _message("new", unread=True)}
        with patch(_DELTA, AsyncMock(return_value=[{"id": "read"}, {"id": "new"}])):
            listed = await _summaries(_mailbox(now))

        assert _subjects(listed) == ["subject new"]

    async def test_opened_mail_never_takes_the_place_of_unread_mail_behind_it(self) -> None:
        now = {message["id"]: message for message in _opened_then_one_unread()}
        ids = [{"id": message_id} for message_id in now]
        with patch(_DELTA, AsyncMock(side_effect=lambda _c, _u, limit: ids[:limit])):
            listed = await _summaries(_mailbox(now))

        assert _subjects(listed) == ["subject new"]

    async def test_a_message_is_read_fresh_never_from_a_copy_cached_before_it_was_opened(
        self,
    ) -> None:
        """A cached copy still says « unread » of a message the person opened since."""
        now = {"m": _message("m", unread=False)}
        cached = {"m": _message("m", unread=True)}
        with patch(_DELTA, AsyncMock(return_value=[{"id": "m"}])):
            assert await _summaries(_mailbox(now, cached=cached)) is None

    async def test_at_most_the_configured_number_is_listed(self) -> None:
        cap = settings.heartbeat_context_emails_max
        now = {f"m{i}": _message(f"m{i}", unread=True) for i in range(PUSH_WAKE_MAIL_MAX_MESSAGES)}
        ids = [{"id": message_id} for message_id in now]
        with patch(_DELTA, AsyncMock(side_effect=lambda _c, _u, limit: ids[:limit])):
            listed = await _summaries(_mailbox(now))

        assert len(listed or []) == min(cap, PUSH_WAKE_MAIL_MAX_MESSAGES)


class TestTheSearchRoad:
    async def test_it_drops_a_hit_that_is_not_unread(self) -> None:
        """A cached page may still hold a message opened since it was read."""
        mailbox = _mailbox()
        mailbox.search_emails = AsyncMock(
            return_value={
                "messages": [_message("read", unread=False), _message("new", unread=True)]
            }
        )
        with patch(_DELTA, AsyncMock(return_value=None)):
            listed = await _summaries(mailbox)

        assert _subjects(listed) == ["subject new"]

    async def test_a_hit_named_by_its_id_is_read_from_what_the_search_just_cached(self) -> None:
        """A provider listing ids caches each message as it searches: no second round trip."""
        mailbox = _mailbox(cached={"m": _message("m", unread=True)})
        mailbox.search_emails = AsyncMock(return_value={"messages": [{"id": "m"}]})
        with patch(_DELTA, AsyncMock(return_value=None)):
            listed = await _summaries(mailbox)

        assert _subjects(listed) == ["subject m"]


def _own(message_id: str, thread: str, *, labels: list[str]) -> dict[str, Any]:
    """A message of the person's own in ``thread``, written after the one it answers."""
    return {
        "id": message_id,
        "threadId": thread,
        "labelIds": labels,
        "from": "Me <me@example.org>",
        "to": "Sender <sender@example.org>",
        "snippet": "my words",
        "internalDate": str(int(time.time() * 1000) + 60_000),
    }


def _answered_then_one_waiting() -> tuple[list[dict[str, Any]], dict[str, Conversation]]:
    """As many answered messages as a decision looks at, less one, then one still waiting:
    the mailbox as it lists it, and the conversations it tells of."""
    answered = [
        _message(f"a{index}", unread=True) for index in range(PUSH_WAKE_MAIL_MAX_MESSAGES - 1)
    ]
    told = {
        message["threadId"]: Conversation(
            messages=(message, _own(f"r{index}", message["threadId"], labels=["SENT"]))
        )
        for index, message in enumerate(answered)
    }
    return [*answered, _message("waiting", unread=True)], told


class TestWhereEachUnreadMailStands:
    """Unread is not unanswered (ADR-379): a message answered from a phone's notification
    may still be marked unread, and announcing it offers a reply already given."""

    async def test_mail_the_person_already_answered_is_not_announced(self) -> None:
        asked, new = _message("asked", unread=True), _message("new", unread=True)
        told = {"t-asked": Conversation(messages=(asked, _own("r1", "t-asked", labels=["SENT"])))}

        listed = await _summaries(_mailbox(conversations=told), wake=_wake(asked, new))

        assert _subjects(listed) == ["subject new"]

    async def test_answered_mail_never_takes_the_place_of_mail_still_waiting(self) -> None:
        """The cap bounds what is announced, never what is looked at."""
        found, told = _answered_then_one_waiting()

        listed = await _summaries(_mailbox(conversations=told), wake=_wake(*found))

        assert _subjects(listed) == ["subject waiting"]

    async def test_a_search_looks_past_answered_mail_too(self) -> None:
        """A search asked for no more than it lists would never see the mail behind."""
        found, told = _answered_then_one_waiting()
        mailbox = _mailbox(conversations=told)

        async def _search(*, max_results: int, **_: object) -> dict[str, Any]:
            return {"messages": found[:max_results]}

        mailbox.search_emails = AsyncMock(side_effect=_search)
        with patch(_DELTA, AsyncMock(return_value=None)):
            listed = await _summaries(mailbox)

        assert _subjects(listed) == ["subject waiting"]

    async def test_an_unsent_answer_is_said(self) -> None:
        asked = _message("asked", unread=True)
        told = {
            "t-asked": Conversation(
                messages=(asked,), drafts=(_own("d1", "t-asked", labels=["DRAFT"]),)
            )
        }

        listed = await _summaries(_mailbox(conversations=told), wake=_wake(asked))

        assert listed is not None and listed[0]["reply_state"] == "answer_drafted"

    async def test_mail_nobody_answered_carries_no_note(self) -> None:
        asked = _message("asked", unread=True)
        told = {"t-asked": Conversation(messages=(asked,))}

        listed = await _summaries(_mailbox(conversations=told), wake=_wake(asked))

        assert listed is not None and "reply_state" not in listed[0]

    async def test_a_mailbox_that_cannot_tell_announces_as_before(self) -> None:
        mailbox = _mailbox()
        mailbox.conversations_of.side_effect = RuntimeError("the mailbox is away")
        wake = _wake(_message("one", unread=True), _message("two", unread=True))

        listed = await _summaries(mailbox, wake=wake)

        assert _subjects(listed) == ["subject one", "subject two"]


_DRAFTED_NOTE = "[REPLY DRAFTED, NOT SENT]"


def test_the_decision_reads_the_note_between_the_time_and_the_mails_own_words() -> None:
    """The note is the system's: it never sits inside the brackets of what a sender wrote."""
    context = HeartbeatContext(
        unread_emails=[
            {
                "from": "Sender",
                "subject": "Quote",
                "date": "09:12",
                "snippet": "a line of it",
                "reply_state": "answer_drafted",
            }
        ]
    )
    sections: list[str] = []

    _section_unread_emails(context, sections)

    assert sections[0].endswith(f'"Quote" (09:12) {_DRAFTED_NOTE} [a line of it...]')


def test_the_decision_prompt_explains_the_note_it_is_shown() -> None:
    """A tag nobody explains is read as the model pleases."""
    assert _DRAFTED_NOTE in read_prompt_file("heartbeat_decision_prompt")


# 12:00 in Paris (CET), deliberately distinct from every date asserted below.
_NOW = datetime(2026, 2, 2, 11, 0, tzinfo=UTC)


class _PinnedDatetime(datetime):
    """``datetime`` whose ``now()`` is pinned; everything else is inherited."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls.fromtimestamp(_NOW.timestamp(), tz)


class TestAMailsTimeOnItsLine:
    """Today's mail says its hour, older mail its day too (pinned clock, audit F056)."""

    @pytest.fixture(autouse=True)
    def _pin_clock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.domains.heartbeat.mail_context.datetime", _PinnedDatetime)

    def test_mail_of_today_shows_its_hour_only(self) -> None:
        paris = ZoneInfo("Europe/Paris")
        received = datetime(2026, 2, 2, 10, 30, tzinfo=paris)

        assert format_email_date(str(int(received.timestamp() * 1000)), paris) == "10:30"

    def test_older_mail_shows_its_day_too(self) -> None:
        received = datetime(2026, 1, 15, 14, 0, tzinfo=UTC)  # 15:00 in Paris

        shown = format_email_date(str(int(received.timestamp() * 1000)), ZoneInfo("Europe/Paris"))

        assert shown == "2026-01-15 15:00"

    def test_an_instant_given_as_a_number_reads_the_same(self) -> None:
        received = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)

        assert (
            format_email_date(int(received.timestamp() * 1000), ZoneInfo("UTC"))
            == "2026-03-10 12:00"
        )

    @pytest.mark.parametrize("unreadable", [None, "not-a-number"])
    def test_an_instant_nobody_can_read_is_said_unknown(self, unreadable: str | None) -> None:
        assert format_email_date(unreadable, ZoneInfo("Europe/Paris")) == "?"
