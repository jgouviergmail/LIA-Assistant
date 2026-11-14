"""What a contact and the person exchanged (ADR-369, lot 14).

The five latest mails each way and the five latest meetings each organised, by ADDRESS. A calendar
answers a window oldest first, so the window walks back from now: reading two years at once would
hand back the oldest meetings and cut the latest. A source says why it has nothing: « I could not
look » is never « nothing », and nothing here reaches a model.
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
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import (
    WORKBENCH_CONTACT_HISTORY_ITEMS,
    WORKBENCH_CONTACT_HISTORY_MAX_ADDRESSES,
    WORKBENCH_CONTACT_HISTORY_MAX_PHONES,
    WORKBENCH_CONTACT_HISTORY_SPAN_DAYS,
    WORKBENCH_CONTACT_HISTORY_SPANS,
    WORKBENCH_CONTACT_VALUE_MAX_CHARS,
)
from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.mail_conversation import Conversation
from src.domains.connectors.models import ConnectorType
from src.domains.relations.providers import classification
from src.domains.telephony.models import PhoneCallOutcome, PhoneCallStatus
from src.domains.workbench import contacts_history
from src.domains.workbench.contacts_lines import PhoneHistory
from src.domains.workbench.errors import NOT_CONNECTED, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.schemas.contacts import (
    ContactHistoryQuery,
    HistoryCall,
    HistoryText,
)

pytestmark = pytest.mark.unit

USER = uuid4()
ZONE = ZoneInfo("Europe/Paris")
NOW = datetime(2026, 11, 5, 21, 0, tzinfo=UTC)
ANA = "ana@example.org"
QUERY = ContactHistoryQuery(address=[ANA])
FIVE = WORKBENCH_CONTACT_HISTORY_ITEMS


def _hours_ago(hours: int) -> int:
    return int((NOW - timedelta(hours=hours)).timestamp() * 1000)


def _message(message_id: str, hours: int = 1) -> dict[str, Any]:
    return {
        "id": message_id,
        "subject": f"Subject {message_id}",
        "snippet": "A line of it",
        "internalDate": _hours_ago(hours),
    }


def _mail(answers: dict[str, list[dict[str, Any]]] | None = None) -> MagicMock:
    known = answers or {}

    async def search(query: str, **_: Any) -> dict[str, Any]:
        return {"messages": known.get(query, [])}

    return MagicMock(search_emails=AsyncMock(side_effect=search))


def _event(event_id: str, days: int = 1, **fields: Any) -> dict[str, Any]:
    start = NOW - timedelta(days=days)
    return {
        "id": event_id,
        "summary": f"Meeting {event_id}",
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
        **fields,
    }


def _by_ana(event_id: str, days: int = 1) -> dict[str, Any]:
    return _event(event_id, days, organizer={"email": ANA}, attendees=[{"email": "me@x.org"}])


def _by_me(event_id: str, days: int = 1) -> dict[str, Any]:
    return _event(
        event_id,
        days,
        organizer={"email": "me@x.org", "self": True},
        attendees=[{"email": ANA}],
    )


def _calendar(*spans: list[dict[str, Any]], truncated: bool = False) -> MagicMock:
    """Each window answers its own events, oldest first: the most recent window first."""
    answers = iter(spans)

    async def window(*_: Any, **__: Any) -> dict[str, Any]:
        return {"events": next(answers, []), "truncated": truncated}

    return MagicMock(list_events_window=AsyncMock(side_effect=window))


def _door(mail: Any, calendar: Any) -> Any:
    clients = {WorkbenchTool.MAIL: mail, WorkbenchTool.CALENDAR: calendar}

    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any, *, container: Any = None) -> AsyncIterator[Any]:
        assert user_id == USER
        client = clients[tool]
        if isinstance(client, Exception):
            raise client
        yield ActiveClient(
            client=client, connector_type=ConnectorType.GOOGLE_GMAIL, preferred_name=None
        )

    return patch.object(contacts_history, "open_tool_client", opened)


@pytest.fixture(autouse=True)
def _default_calendar() -> Any:
    with patch.object(
        contacts_history, "resolve_owner_container_id", AsyncMock(return_value="cal-1")
    ):
        yield


async def _history(mail: Any, calendar: Any, query: ContactHistoryQuery = QUERY) -> Any:
    with _door(mail, calendar):
        return await contacts_history.contact_history(USER, ZONE, query, NOW)


def _exchanged(message_id: str, hours: int, *, mine: bool) -> dict[str, Any]:
    """A message of the exchange as its conversation holds it."""
    return {
        **_message(message_id, hours),
        "threadId": f"t-{message_id}",
        "labelIds": ["SENT"] if mine else ["INBOX"],
        "from": "Me <me@x.org>" if mine else f"Ana <{ANA}>",
        "to": f"Ana <{ANA}>" if mine else "Me <me@x.org>",
    }


class TestWhereAMailStands:
    """Unread or not, a mail read alone cannot say whether it was answered (ADR-379)."""

    async def test_the_latest_mail_each_way_says_what_happened_next(self) -> None:
        theirs = _exchanged("r1", 5, mine=False)
        ours = _exchanged("s1", 4, mine=True)
        waiting = _exchanged("r2", 3, mine=False)
        mail = _mail({f"from:{ANA}": [theirs, waiting], f"in:sent to:{ANA}": [ours]})
        mail.conversations_of = AsyncMock(
            return_value={
                "t-r1": Conversation(
                    messages=(theirs, {**_exchanged("a1", 2, mine=True), "threadId": "t-r1"})
                ),
                "t-s1": Conversation(
                    messages=(ours, {**_exchanged("a2", 1, mine=False), "threadId": "t-s1"})
                ),
                "t-r2": Conversation(messages=(waiting,)),
            }
        )

        history = await _history(mail, _calendar())

        assert {row.id: row.reply for row in history.received} == {"r1": "answered", "r2": None}
        assert {row.id: row.reply for row in history.sent} == {"s1": "reply_received"}

    async def test_a_mailbox_that_cannot_tell_still_lists_the_exchange(self) -> None:
        mail = _mail({f"from:{ANA}": [_exchanged("r1", 5, mine=False)]})
        mail.conversations_of = AsyncMock(side_effect=RuntimeError("away"))

        history = await _history(mail, _calendar())

        assert [(row.id, row.reply) for row in history.received] == [("r1", None)]
        assert history.mail == "used"


class TestTheMail:
    async def test_each_direction_is_asked_on_its_own_terms(self) -> None:
        mail = _mail()

        await _history(mail, _calendar())

        asked = [call.args[0] for call in mail.search_emails.await_args_list]
        assert asked == [f"from:{ANA}", f"in:sent to:{ANA}", f"in:sent cc:{ANA}"]

    async def test_what_was_received_and_what_was_sent_stand_apart(self) -> None:
        mail = _mail(
            {
                f"from:{ANA}": [_message("r1")],
                f"in:sent to:{ANA}": [_message("s1")],
                f"in:sent cc:{ANA}": [_message("s2", 2)],
            }
        )

        history = await _history(mail, _calendar())

        assert [item.id for item in history.received] == ["r1"]
        assert [item.id for item in history.sent] == ["s1", "s2"]
        assert history.mail == "used"

    async def test_a_row_says_what_it_is_and_when(self) -> None:
        history = await _history(_mail({f"from:{ANA}": [_message("r1", 2)]}), _calendar())

        row = history.received[0]
        assert row.subject == "Subject r1"
        assert row.at == NOW - timedelta(hours=2)

    async def test_the_latest_come_first_and_only_as_many_as_asked(self) -> None:
        rows = [_message(f"r{index}", hours=index + 1) for index in range(FIVE)]
        other = "bo@example.org"
        mail = _mail(
            {
                f"from:{ANA}": list(reversed(rows)),
                f"from:{other}": [_message("newest", hours=0)],
            }
        )

        history = await _history(mail, _calendar(), ContactHistoryQuery(address=[ANA, other]))

        assert [item.id for item in history.received] == ["newest", *[f"r{i}" for i in range(4)]]

    async def test_a_message_with_no_subject_leaves_its_word_to_the_page(self) -> None:
        message = {**_message("r1"), "subject": ""}

        history = await _history(_mail({f"from:{ANA}": [message]}), _calendar())

        assert history.received[0].subject == ""

    async def test_a_message_found_twice_is_listed_once(self) -> None:
        mail = _mail({f"in:sent to:{ANA}": [_message("s1")], f"in:sent cc:{ANA}": [_message("s1")]})

        assert len((await _history(mail, _calendar())).sent) == 1

    async def test_a_page_of_a_search_is_as_long_as_what_is_shown(self) -> None:
        mail = _mail()

        await _history(mail, _calendar())

        assert mail.search_emails.await_args.kwargs["max_results"] == FIVE

    async def test_no_mailbox_is_said_rather_than_nothing_found(self) -> None:
        history = await _history(_refused_door(), _calendar())

        assert history.mail == "disabled"

    async def test_a_mailbox_that_failed_is_never_read_as_empty(self) -> None:
        mail = MagicMock(
            search_emails=AsyncMock(side_effect=ConnectorAPIError("gmail", 503, "down"))
        )

        history = await _history(mail, _calendar([_by_ana("e1")]))

        assert history.mail == "unavailable"
        assert history.received == []
        assert [item.id for item in history.organized_by_them] == ["e1"]


def _refused_door() -> Exception:
    try:
        refuse(NOT_CONNECTED)
    except Exception as refusal:
        return refusal
    raise AssertionError("refuse never returns")


class TestTheMeetings:
    async def test_who_organised_it_decides_where_it_stands(self) -> None:
        history = await _history(_mail(), _calendar([_by_me("mine", 2), _by_ana("hers", 1)]))

        assert [item.id for item in history.organized_by_them] == ["hers"]
        assert [item.id for item in history.organized_by_you] == ["mine"]
        assert history.calendar == "used"

    async def test_an_address_is_folded_like_any_other_mailbox(self) -> None:
        event = _event("e1", organizer={"email": ANA.upper()})

        history = await _history(_mail(), _calendar([event]))

        assert [item.id for item in history.organized_by_them] == ["e1"]

    async def test_a_meeting_someone_else_organised_answers_neither_list(self) -> None:
        event = _event("e1", organizer={"email": "boss@x.org"}, attendees=[{"email": ANA}])

        history = await _history(_mail(), _calendar([event]))

        assert history.organized_by_them == []
        assert history.organized_by_you == []
        assert history.shared == []

    async def test_a_meeting_the_contact_is_not_part_of_is_left_out(self) -> None:
        history = await _history(
            _mail(), _calendar([_event("e1", organizer={"email": "me@x.org", "self": True})])
        )

        assert history.organized_by_you == []

    async def test_a_meeting_that_names_no_organiser_is_shared_never_guessed(self) -> None:
        event = _event("e1", attendees=[{"email": ANA}])

        history = await _history(_mail(), _calendar([event]))

        assert [item.id for item in history.shared] == ["e1"]
        assert history.organized_by_them == []

    async def test_an_empty_organiser_is_no_organiser(self) -> None:
        event = _event("e1", organizer={}, attendees=[{"email": ANA}])

        assert [item.id for item in (await _history(_mail(), _calendar([event]))).shared] == ["e1"]

    async def test_a_cancelled_meeting_never_happened(self) -> None:
        event = {**_by_ana("e1"), "status": "cancelled"}

        assert (await _history(_mail(), _calendar([event]))).organized_by_them == []

    async def test_only_what_already_began_is_asked(self) -> None:
        calendar = _calendar()

        await _history(_mail(), calendar)

        first = calendar.list_events_window.await_args_list[0]
        assert first.args[0] == "cal-1"
        assert datetime.fromisoformat(first.args[2]) == NOW
        assert first.kwargs["bound"] == settings.workbench_calendar_window_max_events

    async def test_the_latest_come_first_within_a_window(self) -> None:
        oldest_first = [_by_ana("older", 3), _by_ana("newer", 1)]

        history = await _history(_mail(), _calendar(oldest_first))

        assert [item.id for item in history.organized_by_them] == ["newer", "older"]

    async def test_a_provider_that_answers_in_no_order_is_put_in_order(self) -> None:
        unordered = [_by_ana("middle", 2), _by_ana("newest", 1), _by_ana("oldest", 3)]

        history = await _history(_mail(), _calendar(unordered))

        assert [item.id for item in history.organized_by_them] == ["newest", "middle", "oldest"]

    async def test_a_meeting_two_windows_hold_is_listed_once(self) -> None:
        history = await _history(_mail(), _calendar([_by_ana("long", 89)], [_by_ana("long", 89)]))

        assert [item.id for item in history.organized_by_them] == ["long"]

    async def test_a_meeting_with_no_title_leaves_its_word_to_the_page(self) -> None:
        event = {**_by_ana("e1"), "summary": ""}

        row = (await _history(_mail(), _calendar([event]))).organized_by_them[0]

        assert row.title == ""

    async def test_the_walk_goes_back_from_now_without_a_gap(self) -> None:
        calendar = _calendar()

        await _history(_mail(), calendar)

        windows = calendar.list_events_window.await_args_list
        span = timedelta(days=WORKBENCH_CONTACT_HISTORY_SPAN_DAYS)
        assert len(windows) == WORKBENCH_CONTACT_HISTORY_SPANS
        for index, window in enumerate(windows):
            end = NOW - span * index
            assert datetime.fromisoformat(window.args[2]) == end
            assert datetime.fromisoformat(window.args[1]) == end - span

    async def test_a_later_window_comes_after_the_earlier_one(self) -> None:
        history = await _history(
            _mail(), _calendar([_by_ana("recent", 1)], [_by_ana("older", 100)])
        )

        assert [item.id for item in history.organized_by_them] == ["recent", "older"]

    async def test_the_walk_stops_once_both_lists_are_full(self) -> None:
        theirs = [_by_ana(f"t{index}", index + 1) for index in range(FIVE)]
        mine = [_by_me(f"m{index}", index + 1) for index in range(FIVE)]
        calendar = _calendar(theirs + mine)

        await _history(_mail(), calendar)

        assert calendar.list_events_window.await_count == 1

    async def test_one_full_list_does_not_stop_the_other(self) -> None:
        theirs = [_by_ana(f"t{index}", index + 1) for index in range(FIVE)]
        calendar = _calendar(theirs, [_by_me("m1", 100)])

        history = await _history(_mail(), calendar)

        assert [item.id for item in history.organized_by_you] == ["m1"]

    async def test_no_list_runs_past_what_is_shown(self) -> None:
        theirs = [_by_ana(f"t{index}", index + 1) for index in range(FIVE + 3)]

        assert len((await _history(_mail(), _calendar(theirs))).organized_by_them) == FIVE

    async def test_the_window_looked_at_is_stated(self) -> None:
        history = await _history(_mail(), _calendar())

        assert history.meetings_window_days == (
            WORKBENCH_CONTACT_HISTORY_SPAN_DAYS * WORKBENCH_CONTACT_HISTORY_SPANS
        )

    async def test_a_window_the_provider_cut_is_said(self) -> None:
        history = await _history(_mail(), _calendar([], truncated=True))

        assert history.meetings_cut is True

    async def test_a_whole_read_claims_no_cut(self) -> None:
        assert (await _history(_mail(), _calendar())).meetings_cut is False

    async def test_a_meeting_names_the_day_it_is_on_for_the_person(self) -> None:
        late = NOW.replace(hour=23, minute=30) - timedelta(days=1)
        event = {
            **_by_ana("e1"),
            "start": {"dateTime": late.isoformat()},
            "end": {"dateTime": (late + timedelta(hours=1)).isoformat()},
        }

        row = (await _history(_mail(), _calendar([event]))).organized_by_them[0]

        assert row.day == "2026-11-05"
        assert row.calendar_id == "cal-1"
        assert row.title == "Meeting e1"

    async def test_an_all_day_meeting_keeps_its_own_day(self) -> None:
        event = {
            **_by_ana("e1"),
            "start": {"date": "2026-11-03"},
            "end": {"date": "2026-11-04"},
        }

        row = (await _history(_mail(), _calendar([event]))).organized_by_them[0]

        assert row.day == "2026-11-03"
        assert row.all_day is True

    async def test_no_calendar_is_said_rather_than_nothing_found(self) -> None:
        assert (await _history(_mail(), _refused_door())).calendar == "disabled"

    async def test_a_calendar_that_failed_is_never_read_as_empty(self) -> None:
        calendar = MagicMock(
            list_events_window=AsyncMock(side_effect=ConnectorAPIError("cal", 503, "down"))
        )

        history = await _history(_mail({f"from:{ANA}": [_message("r1")]}), calendar)

        assert history.calendar == "unavailable"
        assert [item.id for item in history.received] == ["r1"]


class TestWhatItNeverDoes:
    async def test_no_model_qualifies_what_it_read(self) -> None:
        with patch.object(
            classification, "qualify_selected", AsyncMock(side_effect=AssertionError)
        ) as qualify:
            await _history(_mail({f"from:{ANA}": [_message("r1")]}), _calendar([_by_ana("e1")]))

        qualify.assert_not_awaited()


class TestTheRequest:
    def test_a_contact_with_neither_address_nor_number_asks_nothing(self) -> None:
        with pytest.raises(ValidationError):
            ContactHistoryQuery(address=[], phone=[])

    def test_numbers_alone_are_enough(self) -> None:
        query = ContactHistoryQuery(phone=["06 12 34 56 78"])

        assert (query.address, query.phone) == ([], ["06 12 34 56 78"])

    def test_numbers_are_bounded(self) -> None:
        many = [
            f"06 12 34 56 {index:02d}" for index in range(WORKBENCH_CONTACT_HISTORY_MAX_PHONES + 1)
        ]

        with pytest.raises(ValidationError):
            ContactHistoryQuery(phone=many)

    @pytest.mark.parametrize("number", ["   ", "1" * (WORKBENCH_CONTACT_VALUE_MAX_CHARS + 1)])
    def test_a_number_is_a_bounded_value(self, number: str) -> None:
        with pytest.raises(ValidationError):
            ContactHistoryQuery(phone=[number])

    def test_addresses_are_bounded(self) -> None:
        many = [f"a{index}@x.org" for index in range(WORKBENCH_CONTACT_HISTORY_MAX_ADDRESSES + 1)]

        with pytest.raises(ValidationError):
            ContactHistoryQuery(address=many)

    @pytest.mark.parametrize("address", ["not an address", "a@b.org in:trash", "from:x@y.org"])
    def test_an_address_never_carries_an_operator(self, address: str) -> None:
        with pytest.raises(ValidationError):
            ContactHistoryQuery(address=[address])


_NUMBER = "06 12 34 56 78"
_CALL = HistoryCall(
    id=uuid4(),
    at=NOW - timedelta(days=2),
    status=PhoneCallStatus.COMPLETED,
    outcome=PhoneCallOutcome.OBJECTIVE_MET,
    seconds=93.5,
    purpose="Move Tuesday's appointment",
)
_TEXT = HistoryText(
    id=uuid4(), at=NOW - timedelta(hours=3), excerpt="Call me back", truncated=False
)


def _phone(history: PhoneHistory | None = None) -> Any:
    answer = history or PhoneHistory(
        telephony="used",
        calls=[_CALL],
        calls_window=500,
        calls_cut=True,
        sms="used",
        texts=[_TEXT],
        texts_window=2000,
        texts_cut=False,
    )
    return patch.object(contacts_history, "phone_history", AsyncMock(return_value=answer))


class TestByTheirNumbers:
    async def test_a_contact_with_numbers_alone_asks_no_mailbox_nor_calendar(self) -> None:
        mail, calendar = _mail(), _calendar()

        with _phone():
            history = await _history(mail, calendar, ContactHistoryQuery(phone=[_NUMBER]))

        mail.search_emails.assert_not_awaited()
        calendar.list_events_window.assert_not_awaited()
        assert (history.mail, history.calendar) == ("not_requested", "not_requested")

    async def test_a_contact_with_addresses_alone_asks_no_phone_record(self) -> None:
        history = await _history(_mail(), _calendar())

        assert (history.telephony, history.sms) == ("not_requested", "not_requested")
        assert (history.calls, history.texts) == ([], [])

    async def test_each_number_is_asked_once(self) -> None:
        with _phone() as phone:
            await _history(
                _mail(),
                _calendar(),
                ContactHistoryQuery(phone=[_NUMBER, _NUMBER, "01 40 00 00 00"]),
            )

        phone.assert_awaited_once_with(USER, [_NUMBER, "01 40 00 00 00"])

    async def test_what_the_phone_records_hold_reaches_the_page(self) -> None:
        with _phone():
            history = await _history(_mail(), _calendar(), ContactHistoryQuery(phone=[_NUMBER]))

        assert (history.telephony, history.calls, history.calls_window, history.calls_cut) == (
            "used",
            [_CALL],
            500,
            True,
        )
        assert (history.sms, history.texts, history.texts_window, history.texts_cut) == (
            "used",
            [_TEXT],
            2000,
            False,
        )

    async def test_the_number_never_reaches_the_answer(self) -> None:
        with _phone():
            history = await _history(
                _mail(), _calendar(), ContactHistoryQuery(address=[ANA], phone=[_NUMBER])
            )

        assert "12 34 56 78" not in history.model_dump_json()
        assert "12345678" not in history.model_dump_json()
