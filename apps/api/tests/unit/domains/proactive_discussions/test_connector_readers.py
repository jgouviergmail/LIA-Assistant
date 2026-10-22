"""Exercise real source adapters against bounded native-client seams, without provider calls."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.connectors.discussion_sources import (
    CalendarDiscussionSource,
    ContactDiscussionSource,
    EmailDiscussionSource,
    TaskDiscussionSource,
)
from src.domains.connectors.models import ConnectorType
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey, SourceReadRequest

pytestmark = pytest.mark.unit


async def test_expanded_occurrences_load_one_parent_declaration_without_parent_private_body(
    native_clients, monkeypatch
) -> None:
    calls = []

    async def listing(**kwargs):
        return {
            "items": [
                {
                    "id": f"instance-{index}",
                    "summary": "Fictional appointment",
                    "recurringEventId": "parent-1",
                    "originalStartTime": {"dateTime": original},
                    "start": {"dateTime": start},
                    "end": {"dateTime": end},
                }
                for index, original, start, end in [
                    (1, "2026-09-20T09:00:00Z", "2026-10-19T09:00:00Z", "2026-10-19T10:00:00Z"),
                    (2, "2026-10-20T09:00:00Z", "2026-10-21T09:00:00Z", "2026-10-21T10:00:00Z"),
                ]
            ]
        }

    async def parent(identifier, **kwargs):
        calls.append(identifier)
        return {
            "id": "parent-1",
            "recurrence": ["RRULE:FREQ=MONTHLY"],
            "description": "Private parent body must stay out",
        }

    monkeypatch.setattr(native_clients, "list_events", listing)
    monkeypatch.setattr(native_clients, "get_event", parent, raising=False)
    result = await CalendarDiscussionSource().read(request(SourceKey.CALENDAR))
    assert calls == ["parent-1"]
    assert all(
        item.recurrence_rule == "RRULE:FREQ=MONTHLY" and item.supports for item in result.items
    )
    assert "Private parent body" not in result.model_dump_json()


NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


def request(source: SourceKey, *, operation="recent", query=None) -> SourceReadRequest:
    return SourceReadRequest(
        owner_id=UUID(int=1),
        run_id=UUID(int=2),
        policy_revision=0,
        request=ResearchRequest(source=source, operation=operation, query=query),
        now=NOW,
        window_start=NOW - timedelta(days=3),
        window_end=NOW + timedelta(days=7),
        allowed_sources=(source,),
        item_limit=2,
        item_max_chars=4000,
        call_limit=8,
        timeout_seconds=10,
    )


class NativeClient:
    async def list_events(self, **kwargs):
        assert (
            kwargs["max_results"] <= 3
            and kwargs["time_min"] == request(SourceKey.CALENDAR).window_start.isoformat()
        )
        return {
            "items": [
                {
                    "id": "event",
                    "summary": "Fictional recital",
                    "start": {"dateTime": "2026-10-21T10:00:00Z"},
                    "end": {"dateTime": "2026-10-21T11:00:00Z"},
                }
            ],
            "nextPageToken": "opaque-page",
        }

    async def search_emails(self, **kwargs):
        assert kwargs["use_cache"] is False and kwargs["headers_only"] is False
        return {
            "messages": [{"id": "mail", "subject": "Fictional", "body": "Actual readable content"}],
            "next_page_token": None,
        }

    async def list_tasks(self, **kwargs):
        assert kwargs["show_completed"] is True and kwargs["show_hidden"] is False
        return {
            "items": [
                {
                    "id": "task",
                    "title": "Fictional",
                    "status": "needsAction",
                    "due": "2026-10-21T00:00:00Z",
                }
            ]
        }

    async def search_contacts(self, **kwargs):
        assert kwargs["query"] == "Alice" and kwargs["use_cache"] is False
        return {
            "results": [
                {
                    "person": {
                        "resourceName": "people/alice",
                        "names": [{"displayName": "Fictional Alice"}],
                    }
                }
            ]
        }


@pytest.fixture
def native_clients(monkeypatch):
    client = NativeClient()

    @asynccontextmanager
    async def open_calendar(owner, **kwargs):
        yield CalendarAccess(
            client=client, calendar_id="primary", connector_type=ConnectorType.GOOGLE_CALENDAR
        )

    @asynccontextmanager
    async def open_client(category, owner, **kwargs):
        yield ActiveClient(
            client=client,
            connector_type={
                "email": ConnectorType.GOOGLE_GMAIL,
                "tasks": ConnectorType.GOOGLE_TASKS,
                "contacts": ConnectorType.GOOGLE_CONTACTS,
            }[category],
            preferred_name=None,
        )

    async def authority(owner, kind, opened, *, container=""):
        return f"{kind.value}:fictional-account:{container}"

    monkeypatch.setattr(
        "src.domains.connectors.discussion_sources.open_active_calendar", open_calendar
    )
    monkeypatch.setattr("src.domains.connectors.discussion_sources.open_active_client", open_client)
    monkeypatch.setattr(
        "src.domains.connectors.discussion_sources.require_reader_authority", authority
    )
    return client


async def test_calendar_retains_partial_coverage(native_clients) -> None:
    result = await CalendarDiscussionSource().read(request(SourceKey.CALENDAR))
    assert result.items[0].assertion == "planned" and not result.complete
    assert result.status == "truncated"


async def test_email_task_and_contact_reads_use_native_shapes_without_implicit_sources(
    native_clients,
) -> None:
    mail = await EmailDiscussionSource().read(request(SourceKey.EMAILS))
    tasks = await TaskDiscussionSource().read(request(SourceKey.TASKS))
    contacts = await ContactDiscussionSource().read(
        request(SourceKey.CONTACTS, operation="search", query="Alice")
    )
    assert "Actual readable content" in mail.items[0].excerpt
    assert tasks.items[0].planned_date.isoformat() == "2026-10-21"
    assert "Fictional Alice" in contacts.items[0].excerpt


async def test_mail_page_exposes_its_real_opaque_continuation(native_clients, monkeypatch):
    async def search(**kwargs):
        return {
            "messages": [{"id": "fixture", "subject": "Fictional page"}],
            "next_page_token": "native-opaque-cursor",
        }

    monkeypatch.setattr(native_clients, "search_emails", search, raising=False)
    result = await EmailDiscussionSource().read(request(SourceKey.EMAILS))
    assert result.cursor == "native-opaque-cursor" and not result.complete
