"""One search across the tools (ADR-369, lot 13).

Words are looked for at once in every ready tool that can search them, each its own request. A
tool that fails is named beside what the others found: it never empties them, and silence would
read as « nothing there » (ADR-292). A cut is said (ADR-185), and so is a mailbox searched from
its inbox alone, where the provider has no place holding every message. Tasks are left out:
neither provider searches them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from src.core.constants import WORKBENCH_CALENDAR_IDS_MAX, WORKBENCH_SEARCH_HITS_PER_TOOL
from src.core.exceptions import BaseAPIException
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import calendar_service, contacts_service, files_service, mail_reading
from src.domains.workbench.availability import read_availability
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.mail_query import SYSTEM_PLACES
from src.domains.workbench.schemas.calendar import CalendarEvent, EventSearchQuery
from src.domains.workbench.schemas.common import ToolAvailability
from src.domains.workbench.schemas.contacts import ContactsQuery
from src.domains.workbench.schemas.files import DriveItem, FilesQuery
from src.domains.workbench.schemas.mail import SYSTEM_FOLDER_PREFIX, MailListing, MailSummary
from src.domains.workbench.schemas.search import GlobalSearch, SearchHit, ToolHits

logger = structlog.get_logger(__name__)

_READY: Final = "ready"
_BOUND: Final = WORKBENCH_SEARCH_HITS_PER_TOOL
_ALL_MAIL: Final = f"{SYSTEM_FOLDER_PREFIX}all"
_INBOX: Final = f"{SYSTEM_FOLDER_PREFIX}inbox"
#: What a tool found, and whether part of it could not be read.
_Found = tuple[ToolHits, bool]


def _group(
    tool: WorkbenchTool, hits: Sequence[SearchHit], *, more: bool, inbox_only: bool = False
) -> ToolHits:
    return ToolHits(
        tool=tool.value,
        hits=list(hits[:_BOUND]),
        truncated=more or len(hits) > _BOUND,
        inbox_only=inbox_only,
    )


def _sender(message: MailSummary) -> str | None:
    if message.sender is None:
        return None
    return message.sender.name or message.sender.address


async def _mail(user_id: UUID, zone: ZoneInfo, words: str, rail: ToolAvailability) -> _Found:
    whole = "all" in SYSTEM_PLACES[ConnectorType(rail.provider)]
    folder = _ALL_MAIL if whole else _INBOX
    page = await mail_reading.list_messages(
        user_id, zone, MailListing(folder=folder, q=words), size=_BOUND
    )
    hits = [
        SearchHit(id=item.id, title=item.subject, subtitle=_sender(item), mail_folder=folder)
        for item in page.items
    ]
    found = _group(WorkbenchTool.MAIL, hits, more=bool(page.next_page_token), inbox_only=not whole)
    return found, bool(page.skipped)


def _day(event: CalendarEvent, zone: ZoneInfo) -> str:
    if event.all_day:
        return event.start[:10]
    return datetime.fromisoformat(event.start).astimezone(zone).date().isoformat()


async def _calendar(user_id: UUID, zone: ZoneInfo, words: str, _: ToolAvailability) -> _Found:
    calendars = [item.id for item in (await calendar_service.list_calendars(user_id)).calendars]
    if not calendars:
        return _group(WorkbenchTool.CALENDAR, [], more=False), False
    asked = calendars[:WORKBENCH_CALENDAR_IDS_MAX]
    found = await calendar_service.search_events(
        user_id, zone, EventSearchQuery(q=words, calendar_ids=asked)
    )
    hits = [
        SearchHit(
            id=event.id,
            title=event.summary,
            subtitle=event.location,
            calendar_id=event.calendar_id,
            day=_day(event, zone),
        )
        for event in found.events
    ]
    more = found.truncated or len(asked) < len(calendars)
    return _group(WorkbenchTool.CALENDAR, hits, more=more), bool(found.failed)


async def _contacts(user_id: UUID, _: ZoneInfo, words: str, __: ToolAvailability) -> _Found:
    page = await contacts_service.list_contacts(user_id, ContactsQuery(q=words))
    hits = [
        SearchHit(id=item.id, title=item.name, subtitle=item.email or item.phone)
        for item in page.items
    ]
    return _group(WorkbenchTool.CONTACTS, hits, more=page.truncated), False


def _file_hit(item: DriveItem) -> SearchHit:
    return SearchHit(
        id=item.target_id or item.id,
        title=item.name,
        is_folder="folder" in (item.kind, item.target_kind),
    )


async def _files(user_id: UUID, _: ZoneInfo, words: str, __: ToolAvailability) -> _Found:
    page = await files_service.list_files(user_id, FilesQuery(q=words))
    hits = [_file_hit(item) for item in page.items]
    return _group(WorkbenchTool.FILES, hits, more=bool(page.next_page_token)), False


#: The tools that can search, in the rail's order.
_SEARCHERS: Final[
    dict[WorkbenchTool, Callable[[UUID, ZoneInfo, str, ToolAvailability], Awaitable[_Found]]]
] = {
    WorkbenchTool.MAIL: _mail,
    WorkbenchTool.CALENDAR: _calendar,
    WorkbenchTool.CONTACTS: _contacts,
    WorkbenchTool.FILES: _files,
}


def _log_unforeseen(tool: WorkbenchTool, failure: Exception) -> None:
    """A refusal was told where it was raised; anything else is only known from here."""
    if not isinstance(failure, BaseAPIException):
        logger.error(
            "workbench_search_tool_failed",
            tool=tool.value,
            error_type=type(failure).__name__,
            exc_info=failure,
        )


async def search_everything(user_id: UUID, zone: ZoneInfo, words: str) -> GlobalSearch:
    """Words looked for in every ready tool that can search them.

    Args:
        user_id: The account.
        zone: The person's, which an event's day is read on.
        words: The words.

    Returns:
        What each tool found, and the tools that could not answer, or only in part.
    """
    rail = await read_availability(user_id)
    ready = {item.tool: item for item in rail.tools if item.state == _READY}
    asked = [tool for tool in _SEARCHERS if tool in ready]
    answers = await asyncio.gather(
        *(_SEARCHERS[tool](user_id, zone, words, ready[tool]) for tool in asked),
        return_exceptions=True,
    )
    results: list[ToolHits] = []
    failed: list[str] = []
    for tool, answer in zip(asked, answers, strict=True):
        if isinstance(answer, Exception):
            _log_unforeseen(tool, answer)
            failed.append(tool.value)
        elif isinstance(answer, BaseException):
            raise answer
        else:
            found, partly = answer
            results.append(found)
            if partly:
                failed.append(tool.value)
    return GlobalSearch(results=results, failed=failed)


__all__ = ["search_everything"]
