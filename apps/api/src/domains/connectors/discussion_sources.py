"""Native personal connector readers; every result is typed, scope-fenced and coverage-qualified."""

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.core.mail_reply_state import REPLY_STATE_KEY
from src.domains.connectors.active_client import ActiveClient, open_active_client
from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.connectors.discussion_authority import require_reader_authority
from src.domains.connectors.discussion_calendar import enrich_calendar_series
from src.domains.connectors.discussion_projections import (
    EmailRecord,
    calendar_evidence,
    contact_evidence,
    email_evidence,
    provider_identifier,
)
from src.domains.connectors.discussion_tasks import read_discussion_tasks
from src.domains.connectors.mail_reply_states import answered_mark
from src.domains.shared.discussion_sources import (
    DiscussionEvidence,
    SourceKey,
    SourceReadRequest,
    SourceSnapshot,
    closed_source,
    source_snapshot,
)


class ProviderPage(BaseModel):
    """One provider listing page, whatever key it files rows and the next token under."""

    model_config = ConfigDict(extra="ignore")
    items: tuple[object, ...] = Field(default=(), max_length=101)
    messages: tuple[object, ...] = Field(default=(), max_length=101)
    results: tuple[object, ...] = Field(default=(), max_length=101)
    nextPageToken: str | None = None
    next_page_token: str | None = None


class ContactHit(BaseModel):
    """One contact search hit, wrapping the person record."""

    model_config = ConfigDict(extra="ignore")
    person: object


class Projection(Protocol):
    """A provider-record projection: one raw record into one piece of evidence."""

    def __call__(
        self, raw: object, *, account: str, now: datetime, chars: int
    ) -> DiscussionEvidence: ...


def _snapshot(
    request: SourceReadRequest,
    raw: tuple[object, ...],
    account: str,
    project: Projection,
    *,
    more: bool = False,
    cursor: str | None = None,
) -> SourceSnapshot:
    rows = raw[: request.item_limit]
    items = tuple(
        project(row, account=account, now=request.now, chars=request.item_max_chars) for row in rows
    )
    truncated = more or len(raw) > request.item_limit
    return source_snapshot(
        request,
        status="truncated" if truncated else "ok" if items else "empty",
        items=items,
        complete=False,
        cursor=cursor,
        coverage_kind=(
            "occurrences" if request.request.source == SourceKey.CALENDAR else "active_facts"
        ),
    )


def _permitted(request: SourceReadRequest, source: SourceKey) -> bool:
    if request.request.source != source:
        raise ValueError("connector source mismatch")
    return source in request.allowed_sources


async def _check_unchanged(
    request: SourceReadRequest,
    opened: ActiveClient | CalendarAccess,
    account: str,
    *,
    container: str = "",
) -> None:
    if account != await require_reader_authority(
        request.owner_id, opened.connector_type, opened.client, container=container
    ):
        raise ValueError("connector account or permissions changed while reading")


class CalendarDiscussionSource:
    """The selected calendar of the active calendar connector, read under fresh authority."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one event by reference, or the window's events, then enrich recurring series.

        The connector account and its permissions are checked before and after the
        read; any change refuses the page.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when the source is not consented or no calendar connector
            is active.

        Raises:
            ValueError: The reference belongs to another account, or the account or its
                permissions changed while reading.
        """
        if not _permitted(request, SourceKey.CALENDAR):
            return closed_source(request, disabled=True, reason="consent")
        async with open_active_calendar(request.owner_id, fresh=True) as opened:
            if not isinstance(opened, CalendarAccess):
                return closed_source(request, disabled=False, reason="provider")
            account = await require_reader_authority(
                request.owner_id, opened.connector_type, opened.client, container=opened.calendar_id
            )
            if request.request.reference:
                identifier = provider_identifier(
                    request.request.reference, SourceKey.CALENDAR, account
                )
                raw: object = await opened.client.get_event(
                    identifier, calendar_id=opened.calendar_id
                )
                result = _snapshot(request, (raw,), account, calendar_evidence)
            else:
                raw = await opened.client.list_events(
                    time_min=request.window_start.isoformat(),
                    time_max=request.window_end.isoformat(),
                    max_results=request.item_limit + 1,
                    calendar_id=opened.calendar_id,
                    query=request.request.query,
                )
                page = ProviderPage.model_validate(raw)
                result = _snapshot(
                    request, page.items, account, calendar_evidence, more=bool(page.nextPageToken)
                )
            result = await enrich_calendar_series(request, opened, result)
            await _check_unchanged(request, opened, account, container=opened.calendar_id)
            return result


def _window_query(request: SourceReadRequest) -> str:
    """The window's messages up to now, in the mailbox query every client translates."""
    query = f"after:{int(request.window_start.timestamp())} before:{int(min(request.window_end, request.now).timestamp())+1}"
    if request.request.query:
        # Model text is quoted as literal text, not mailbox operators broadening the window.
        query += ' "' + request.request.query.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return query


async def _mail_page(
    client: EmailClientProtocol, request: SourceReadRequest
) -> tuple[tuple[object, ...], str | None]:
    """One page of the window's messages, each one whole, and where the next page starts.

    A proof is read again whole, by its reference, before any use (ADR-358): what a page
    hands out must be that very read, or every version differs and the run stops. A
    mailbox whose listing carries a preview (Graph) is therefore read one message at a
    time, its own mark with it. One call lists and one reads each hit, so the page lists
    no more hits than the read's allowance reads whole: the rest is the next page's.
    """
    whole = client.SEARCH_HITS_ARE_WHOLE
    raw = await client.search_emails(
        query=_window_query(request),
        max_results=(
            request.item_limit if whole else max(1, min(request.item_limit, request.call_limit - 1))
        ),
        use_cache=False,
        headers_only=False,
        page_token=request.cursor,
    )
    page = ProviderPage.model_validate(raw)
    if whole:
        return page.messages, page.next_page_token
    hits = [EmailRecord.model_validate(hit).id for hit in page.messages]
    return (
        tuple([await client.get_message(hit, use_cache=False, mailbox_mark=True) for hit in hits]),
        page.next_page_token,
    )


def _with_mailbox_mark(row: object) -> object:
    """A message with what its own mailbox marks of it, as its evidence tells it (ADR-379)."""
    if isinstance(row, Mapping) and (said := answered_mark(row)):
        return {**row, REPLY_STATE_KEY: said}
    return row


class EmailDiscussionSource:
    """The person's active mailbox, read under fresh authority."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one message by reference, or the window's messages up to now.

        A model query is searched as quoted literal text, never as mailbox operators
        that could widen the window. Each message says what its own mailbox marks of
        it — that the person answered it — read WITH the message, so a page and the
        read of one message again tell the same fact (``mail_reply_states``).

        Args:
            request: The bounded read.

        Returns:
            The page; closed when the source is not consented or no mailbox is active.

        Raises:
            ValueError: The reference belongs to another account, or the account or its
                permissions changed while reading.
        """
        if not _permitted(request, SourceKey.EMAILS):
            return closed_source(request, disabled=True, reason="consent")
        async with open_active_client("email", request.owner_id, fresh=True) as opened:
            if not isinstance(opened, ActiveClient):
                return closed_source(request, disabled=False, reason="provider")
            account = await require_reader_authority(
                request.owner_id, opened.connector_type, opened.client
            )
            rows: tuple[object, ...]
            cursor = None
            if request.request.reference:
                raw: object = await opened.client.get_message(
                    provider_identifier(request.request.reference, SourceKey.EMAILS, account),
                    use_cache=False,
                    mailbox_mark=True,
                )
                rows = (raw,)
            else:
                rows, cursor = await _mail_page(opened.client, request)
            result = _snapshot(
                request,
                tuple(map(_with_mailbox_mark, rows)),
                account,
                email_evidence,
                more=bool(cursor),
                cursor=cursor,
            )
            await _check_unchanged(request, opened, account)
            return result


class ContactDiscussionSource:
    """The person's active address book, read by search or reference only."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one contact by reference, or the contacts a search matches.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when the source is not consented or no address book is
            active.

        Raises:
            ValueError: Neither a search nor a reference was given (an address book is
                never listed whole), the reference belongs to another account, or the
                account changed while reading.
        """
        if not _permitted(request, SourceKey.CONTACTS):
            return closed_source(request, disabled=True, reason="consent")
        async with open_active_client("contacts", request.owner_id, fresh=True) as opened:
            if not isinstance(opened, ActiveClient):
                return closed_source(request, disabled=False, reason="provider")
            account = await require_reader_authority(
                request.owner_id, opened.connector_type, opened.client
            )
            rows: tuple[object, ...]
            if request.request.reference:
                raw: object = await opened.client.get_person(
                    provider_identifier(request.request.reference, SourceKey.CONTACTS, account),
                    use_cache=False,
                )
                rows = (raw,)
            elif request.request.query:
                raw = await opened.client.search_contacts(
                    query=request.request.query, max_results=request.item_limit, use_cache=False
                )
                rows = tuple(
                    ContactHit.model_validate(hit).person
                    for hit in ProviderPage.model_validate(raw).results
                )
            else:
                raise ValueError("contact context requires a bounded search or reference")
            result = _snapshot(request, rows, account, contact_evidence)
            await _check_unchanged(request, opened, account)
            return result


class TaskDiscussionSource:
    """Every task list of the person's active tasks connector, each its own container."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one task by reference, or every list's tasks (due in the window when future).

        The lists read, their fencing and their bound are ``discussion_tasks``'s.

        Args:
            request: The bounded read.

        Returns:
            The page; closed when the source is not consented or no tasks connector is
            active.

        Raises:
            ValueError: The reference belongs to another account, or the account or its
                permissions changed while reading.
        """
        if not _permitted(request, SourceKey.TASKS):
            return closed_source(request, disabled=True, reason="consent")
        async with open_active_client("tasks", request.owner_id, fresh=True) as opened:
            if not isinstance(opened, ActiveClient):
                return closed_source(request, disabled=False, reason="provider")
            return await read_discussion_tasks(request, opened)
