"""Native personal connector readers; every result is typed, scope-fenced and coverage-qualified."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.domains.connectors.active_client import ActiveClient, open_active_client
from src.domains.connectors.calendar_access import CalendarAccess, open_active_calendar
from src.domains.connectors.discussion_authority import require_reader_authority
from src.domains.connectors.discussion_calendar import enrich_calendar_series
from src.domains.connectors.discussion_projections import (
    calendar_evidence,
    contact_evidence,
    email_evidence,
    provider_identifier,
    task_evidence,
)
from src.domains.connectors.preferences.owner_defaults import TASK_LIST, resolve_owner_container_id
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


class EmailDiscussionSource:
    """The person's active mailbox, read under fresh authority."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one message by reference, or the window's messages up to now.

        A model query is searched as quoted literal text, never as mailbox operators
        that could widen the window.

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
                )
                rows, more = (raw,), False
            else:
                query = f"after:{int(request.window_start.timestamp())} before:{int(min(request.window_end, request.now).timestamp())+1}"
                if request.request.query:
                    # Model text is quoted as literal text, not mailbox operators broadening the window.
                    query += (
                        ' "' + request.request.query.replace("\\", "\\\\").replace('"', '\\"') + '"'
                    )
                raw = await opened.client.search_emails(
                    query=query,
                    max_results=request.item_limit,
                    use_cache=False,
                    headers_only=False,
                    page_token=request.cursor,
                )
                page = ProviderPage.model_validate(raw)
                rows, more = page.messages, bool(page.next_page_token)
                cursor = page.next_page_token
            result = _snapshot(request, rows, account, email_evidence, more=more, cursor=cursor)
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
    """The person's preferred task list in their active tasks connector."""

    async def read(self, request: SourceReadRequest) -> SourceSnapshot:
        """Read one task by reference, or the list's tasks (due in the window when future).

        A query filters the page read; it does not search the provider.

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
        async with open_active_client(
            "tasks", request.owner_id, container=TASK_LIST, fresh=True
        ) as opened:
            if not isinstance(opened, ActiveClient):
                return closed_source(request, disabled=False, reason="provider")
            task_list = await resolve_owner_container_id(
                client=opened.client,
                name=opened.preferred_name,
                owner_id=request.owner_id,
                container=TASK_LIST,
            )
            account = await require_reader_authority(
                request.owner_id, opened.connector_type, opened.client, container=task_list
            )
            rows: tuple[object, ...]
            if request.request.reference:
                raw: object = await opened.client.get_task(
                    task_list,
                    provider_identifier(request.request.reference, SourceKey.TASKS, account),
                )
                rows = (raw,)
            else:
                raw = await opened.client.list_tasks(
                    task_list_id=task_list,
                    max_results=request.item_limit + 1,
                    show_completed=True,
                    show_hidden=False,
                    due_min=(
                        request.window_start.isoformat()
                        if request.request.operation == "future"
                        else None
                    ),
                    due_max=(
                        request.window_end.isoformat()
                        if request.request.operation == "future"
                        else None
                    ),
                )
                rows = ProviderPage.model_validate(raw).items
            result = _snapshot(request, rows, account, task_evidence)
            if request.request.query:
                result = result.model_copy(
                    update={
                        "items": tuple(
                            item
                            for item in result.items
                            if request.request.query.casefold() in item.excerpt.casefold()
                        )
                    }
                )
            await _check_unchanged(request, opened, account, container=task_list)
            return result
