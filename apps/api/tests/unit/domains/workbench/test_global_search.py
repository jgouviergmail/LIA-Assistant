"""One search across the tools (ADR-369, lot 13).

Words are looked for at once in every ready tool that can search them, each its own request. A
tool that fails is named beside what the others found: it never empties them, and silence would
read as « nothing there » (ADR-292). A cut is said, and so is a mailbox searched from its inbox
alone. Tasks are left out: neither provider searches them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from src.core.constants import WORKBENCH_CALENDAR_IDS_MAX, WORKBENCH_SEARCH_HITS_PER_TOOL
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import search
from src.domains.workbench.errors import PROVIDER_UNAVAILABLE, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.mail_query import compose_query
from src.domains.workbench.schemas.calendar import (
    CalendarEvent,
    CalendarInfo,
    CalendarList,
    EventSearch,
)
from src.domains.workbench.schemas.common import ToolAvailability
from src.domains.workbench.schemas.contacts import ContactsPage, ContactSummary
from src.domains.workbench.schemas.files import DriveItem, FilesPage
from src.domains.workbench.schemas.mail import MailAddress, MailPage, MailSummary
from src.domains.workbench.schemas.search import SearchQuery

pytestmark = pytest.mark.unit

USER = uuid4()
ZONE = ZoneInfo("Europe/Paris")
GMAIL = ConnectorType.GOOGLE_GMAIL.value
OUTLOOK = ConnectorType.MICROSOFT_OUTLOOK.value
APPLE = ConnectorType.APPLE_EMAIL.value
READY = ("mail", "calendar", "contacts", "files")


def _tool(tool: str, *, state: str = "ready", provider: str = GMAIL) -> Any:
    return ToolAvailability.model_construct(
        tool=WorkbenchTool(tool), state=state, provider=provider
    )


def _rail(*tools: Any) -> Any:
    return type("Rail", (), {"tools": [_tool(t) if isinstance(t, str) else t for t in tools]})()


def _mail(number: int = 1, *, sender: MailAddress | None = None) -> MailSummary:
    return MailSummary(
        id=f"m{number}",
        thread_id="t",
        sender=sender or MailAddress(name="Ana", address="ana@example.org"),
        subject=f"Subject {number}",
        snippet="",
        received_at=datetime(2027, 1, 4, tzinfo=UTC),
        is_read=True,
        is_starred=False,
        has_attachments=False,
        label_ids=[],
    )


def _person(number: int = 1) -> ContactSummary:
    return ContactSummary(
        id=f"people/c{number}",
        name=f"Ana {number}",
        email="ana@example.org",
        phone=None,
        organization=None,
    )


def _file(**overrides: Any) -> DriveItem:
    fields: dict[str, Any] = {
        "id": "f1",
        "name": "Plan.pdf",
        "kind": "file",
        "mime_type": "application/pdf",
        "modified_at": None,
        "size": 1,
        "web_url": None,
        "target_id": None,
        "target_kind": None,
        "formats": [],
        "downloadable": True,
    }
    return DriveItem(**{**fields, **overrides})


def _event(**overrides: Any) -> CalendarEvent:
    fields: dict[str, Any] = {
        "id": "e1",
        "calendar_id": "primary",
        "summary": "Review",
        "all_day": False,
        "start": "2027-01-04T09:00:00Z",
        "end": "2027-01-04T10:00:00Z",
        "location": "Room 2",
        "recurring": False,
        "conference_url": None,
    }
    return CalendarEvent(**{**fields, **overrides})


def _found(*events: CalendarEvent, truncated: bool = False, failed: tuple[str, ...] = ()) -> Any:
    return EventSearch(events=list(events), truncated=truncated, failed=list(failed))


def _calendars(count: int = 1) -> CalendarList:
    return CalendarList.model_construct(
        calendars=[CalendarInfo.model_construct(id=f"c{index}") for index in range(count)]
    )


def _services(**overrides: Any) -> dict[str, AsyncMock]:
    answers = {
        "list_messages": AsyncMock(
            return_value=MailPage(items=[_mail()], next_page_token=None, skipped=0)
        ),
        "list_contacts": AsyncMock(
            return_value=ContactsPage(items=[_person()], next_page_token=None, truncated=False)
        ),
        "list_files": AsyncMock(return_value=FilesPage(items=[_file()], next_page_token=None)),
        "search_events": AsyncMock(return_value=_found(_event())),
        "list_calendars": AsyncMock(return_value=_calendars()),
    }
    return {**answers, **overrides}


@contextmanager
def _patched(rail: Any, answers: dict[str, AsyncMock]) -> Iterator[None]:
    with ExitStack() as stack:
        stack.enter_context(patch.object(search, "read_availability", AsyncMock(return_value=rail)))
        for module, name in (
            (search.mail_reading, "list_messages"),
            (search.contacts_service, "list_contacts"),
            (search.files_service, "list_files"),
            (search.calendar_service, "search_events"),
            (search.calendar_service, "list_calendars"),
        ):
            stack.enter_context(patch.object(module, name, answers[name]))
        yield


async def _search(rail: Any, answers: dict[str, AsyncMock] | None = None) -> Any:
    with _patched(rail, answers or _services()):
        return await search.search_everything(USER, ZONE, "ana")


class TestEveryTool:
    async def test_each_ready_tool_answers_in_the_rail_s_order(self) -> None:
        answer = await _search(_rail("files", "contacts", "calendar", "mail"))

        assert [group.tool for group in answer.results] == list(READY)
        assert answer.failed == []

    async def test_a_tool_not_ready_is_not_asked(self) -> None:
        answers = _services()

        answer = await _search(_rail("mail", _tool("files", state="not_connected")), answers)

        assert [group.tool for group in answer.results] == ["mail"]
        answers["list_files"].assert_not_awaited()

    async def test_tasks_are_never_asked(self) -> None:
        assert (await _search(_rail("tasks"))).results == []


class TestItsMail:
    async def test_a_hit_says_who_and_where_it_opens(self) -> None:
        hit = (await _search(_rail("mail"))).results[0].hits[0]

        assert (hit.id, hit.title, hit.subtitle) == ("m1", "Subject 1", "Ana")
        assert hit.mail_folder == "system:all"

    async def test_a_sender_with_no_name_is_its_address(self) -> None:
        nameless = _mail(sender=MailAddress(name="", address="ana@example.org"))
        answers = _services(
            list_messages=AsyncMock(
                return_value=MailPage(items=[nameless], next_page_token=None, skipped=0)
            )
        )

        hit = (await _search(_rail("mail"), answers)).results[0].hits[0]

        assert hit.subtitle == "ana@example.org"

    async def test_gmail_is_searched_whole_and_no_more_is_read_than_is_shown(self) -> None:
        answers = _services()

        group = (await _search(_rail("mail"), answers)).results[0]

        call = answers["list_messages"].await_args
        assert call.args[2].folder == "system:all"
        assert call.kwargs == {"size": WORKBENCH_SEARCH_HITS_PER_TOOL}
        assert group.inbox_only is False

    @pytest.mark.parametrize("provider", [OUTLOOK, APPLE])
    async def test_a_mailbox_with_no_such_place_says_it_read_its_inbox(self, provider: str) -> None:
        answers = _services()

        group = (await _search(_rail(_tool("mail", provider=provider)), answers)).results[0]

        assert answers["list_messages"].await_args.args[2].folder == "system:inbox"
        assert group.inbox_only is True
        assert group.hits[0].mail_folder == "system:inbox"

    @pytest.mark.parametrize("provider", [GMAIL, OUTLOOK, APPLE])
    async def test_the_place_asked_is_one_the_provider_holds(self, provider: str) -> None:
        answers = _services()

        await _search(_rail(_tool("mail", provider=provider)), answers)

        listing = answers["list_messages"].await_args.args[2]
        assert compose_query(ConnectorType(provider), listing, ZONE).query.startswith("ana")

    async def test_hits_it_could_not_read_are_a_failure_in_part(self) -> None:
        answers = _services(
            list_messages=AsyncMock(
                return_value=MailPage(items=[_mail()], next_page_token=None, skipped=2)
            )
        )

        answer = await _search(_rail("mail"), answers)

        assert answer.results[0].hits[0].id == "m1"
        assert answer.failed == ["mail"]


class TestItsCalendar:
    async def test_a_hit_opens_on_its_day(self) -> None:
        hit = (await _search(_rail("calendar"))).results[0].hits[0]

        assert (hit.title, hit.subtitle) == ("Review", "Room 2")
        assert (hit.calendar_id, hit.day) == ("primary", "2027-01-04")

    async def test_a_day_is_the_person_s_not_utc_s(self) -> None:
        late = _event(start="2027-01-04T23:30:00Z", end="2027-01-05T00:00:00Z")
        answers = _services(search_events=AsyncMock(return_value=_found(late)))

        hit = (await _search(_rail("calendar"), answers)).results[0].hits[0]

        assert hit.day == "2027-01-05"

    @pytest.mark.parametrize("zone", ["Pacific/Honolulu", "Pacific/Kiritimati"])
    async def test_an_all_day_event_keeps_its_day_on_every_clock(self, zone: str) -> None:
        day = _event(all_day=True, start="2027-01-04", end="2027-01-05")
        answers = _services(search_events=AsyncMock(return_value=_found(day)))

        with _patched(_rail("calendar"), answers):
            answer = await search.search_everything(USER, ZoneInfo(zone), "ana")

        assert answer.results[0].hits[0].day == "2027-01-04"

    async def test_no_calendar_is_nothing_found_and_nothing_asked(self) -> None:
        answers = _services(list_calendars=AsyncMock(return_value=_calendars(0)))

        answer = await _search(_rail("calendar"), answers)

        assert answer.results[0].hits == []
        assert answer.failed == []
        answers["search_events"].assert_not_awaited()

    async def test_past_the_bound_the_first_calendars_are_asked_and_the_cut_said(self) -> None:
        answers = _services(
            list_calendars=AsyncMock(return_value=_calendars(WORKBENCH_CALENDAR_IDS_MAX + 1))
        )

        group = (await _search(_rail("calendar"), answers)).results[0]

        asked = answers["search_events"].await_args.args[2].calendar_ids
        assert len(asked) == WORKBENCH_CALENDAR_IDS_MAX
        assert group.truncated is True

    async def test_a_search_that_found_more_than_it_shows_is_a_cut(self) -> None:
        answers = _services(search_events=AsyncMock(return_value=_found(_event(), truncated=True)))

        assert (await _search(_rail("calendar"), answers)).results[0].truncated is True

    async def test_a_calendar_that_failed_is_a_failure_in_part(self) -> None:
        answers = _services(search_events=AsyncMock(return_value=_found(_event(), failed=("c0",))))

        answer = await _search(_rail("calendar"), answers)

        assert answer.results[0].hits[0].title == "Review"
        assert answer.failed == ["calendar"]


class TestItsContactsAndFiles:
    async def test_a_contact_says_how_to_reach_it(self) -> None:
        hit = (await _search(_rail("contacts"))).results[0].hits[0]

        assert (hit.id, hit.title, hit.subtitle) == ("people/c1", "Ana 1", "ana@example.org")

    async def test_a_file_opens_as_a_file(self) -> None:
        hit = (await _search(_rail("files"))).results[0].hits[0]

        assert (hit.id, hit.title, hit.is_folder) == ("f1", "Plan.pdf", False)

    @pytest.mark.parametrize(
        ("item", "opened", "is_folder"),
        [
            ({"id": "d1", "kind": "folder"}, "d1", True),
            (
                {"id": "s1", "kind": "shortcut", "target_id": "d2", "target_kind": "folder"},
                "d2",
                True,
            ),
            (
                {"id": "s2", "kind": "shortcut", "target_id": "f2", "target_kind": "file"},
                "f2",
                False,
            ),
        ],
    )
    async def test_a_folder_or_a_shortcut_opens_what_it_is(
        self, item: dict[str, Any], opened: str, is_folder: bool
    ) -> None:
        answers = _services(
            list_files=AsyncMock(
                return_value=FilesPage(items=[_file(**item)], next_page_token=None)
            )
        )

        hit = (await _search(_rail("files"), answers)).results[0].hits[0]

        assert (hit.id, hit.is_folder) == (opened, is_folder)


class TestACut:
    async def test_a_page_past_the_bound_is_cut_and_says_so(self) -> None:
        many = [_mail(number) for number in range(WORKBENCH_SEARCH_HITS_PER_TOOL + 1)]
        answers = _services(
            list_messages=AsyncMock(
                return_value=MailPage(items=many, next_page_token=None, skipped=0)
            )
        )

        group = (await _search(_rail("mail"), answers)).results[0]

        assert len(group.hits) == WORKBENCH_SEARCH_HITS_PER_TOOL
        assert group.truncated is True

    async def test_a_next_page_of_mail_is_a_cut(self) -> None:
        answers = _services(
            list_messages=AsyncMock(
                return_value=MailPage(items=[_mail()], next_page_token="n", skipped=0)
            )
        )

        assert (await _search(_rail("mail"), answers)).results[0].truncated is True

    async def test_a_next_page_is_a_cut_too(self) -> None:
        answers = _services(
            list_files=AsyncMock(return_value=FilesPage(items=[_file()], next_page_token="n"))
        )

        assert (await _search(_rail("files"), answers)).results[0].truncated is True

    async def test_a_search_that_says_it_may_hold_more_is_a_cut(self) -> None:
        answers = _services(
            list_contacts=AsyncMock(
                return_value=ContactsPage(items=[_person()], next_page_token=None, truncated=True)
            )
        )

        assert (await _search(_rail("contacts"), answers)).results[0].truncated is True

    async def test_nothing_found_is_said_as_empty_not_failed(self) -> None:
        answers = _services(
            list_messages=AsyncMock(
                return_value=MailPage(items=[], next_page_token=None, skipped=0)
            )
        )

        answer = await _search(_rail("mail"), answers)

        assert (answer.results[0].hits, answer.results[0].truncated) == ([], False)
        assert answer.failed == []


class TestAFailure:
    async def test_a_refusal_is_named_and_the_others_stand(self) -> None:
        def down(*_: Any) -> Any:
            refuse(PROVIDER_UNAVAILABLE)

        answers = _services(list_files=AsyncMock(side_effect=down))

        answer = await _search(_rail("mail", "files"), answers)

        assert [group.tool for group in answer.results] == ["mail"]
        assert answer.failed == ["files"]

    async def test_what_nobody_foresaw_is_named_too_and_logged_by_its_type(self) -> None:
        answers = _services(list_files=AsyncMock(side_effect=KeyError("Ana's secret")))

        with patch.object(search.logger, "error") as logged:
            answer = await _search(_rail("mail", "files"), answers)

        assert answer.failed == ["files"]
        assert [group.tool for group in answer.results] == ["mail"]
        logged.assert_called_once()
        assert logged.call_args.kwargs["tool"] == "files"
        assert logged.call_args.kwargs["error_type"] == "KeyError"

    async def test_a_refusal_needs_no_log_of_its_own(self) -> None:
        def down(*_: Any) -> Any:
            refuse(PROVIDER_UNAVAILABLE)

        answers = _services(list_files=AsyncMock(side_effect=down))

        with patch.object(search.logger, "error") as logged:
            await _search(_rail("files"), answers)

        logged.assert_not_called()

    async def test_a_cancellation_is_never_read_as_a_failure(self) -> None:
        answers = _services(list_files=AsyncMock(side_effect=asyncio.CancelledError))

        with pytest.raises(asyncio.CancelledError):
            await _search(_rail("files"), answers)


class TestItsWords:
    def test_empty_words_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            SearchQuery(q="   ")

    def test_words_past_the_bound_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            SearchQuery(q="x" * 1000)

    def test_a_control_character_never_reaches_a_tool(self) -> None:
        with pytest.raises(ValidationError):
            SearchQuery(q="ana\x00")
