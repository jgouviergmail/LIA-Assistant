"""CRM rows expose exactly the accepted annotation to display and overview."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.core.content_classification import EmailClassification, EventClassification
from src.domains.agents.services.qualification import publication
from src.domains.connectors.calendar_access import CalendarAccess
from src.domains.connectors.models import ConnectorType
from src.domains.relations.providers import classification, emails, events
from src.domains.shared import content_qualification
from src.domains.users.preferences_cache import UserPreferencesCache

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def wire_native(monkeypatch):
    monkeypatch.setattr(content_qualification, "_qualifier", publication.classify_selected)


@pytest.mark.asyncio
async def test_calendar_qualifies_only_the_selected_shared_event(monkeypatch):
    owner = uuid4()
    UserPreferencesCache.set(str(owner), "Europe/Paris", "fr")
    now = datetime.now(UTC)
    rows = [
        {
            "id": str(index),
            "summary": f"Meeting {index}",
            "start": {"dateTime": (now + timedelta(hours=index + 1)).isoformat()},
            "attendees": [{"email": "peer@example.test" if index < 2 else "other@example.test"}],
        }
        for index in range(3)
    ]
    # The window is read in two halves: the coming one holds the rows, the past none.
    client = SimpleNamespace(
        credentials=SimpleNamespace(account_binding="actual-grant"),
        list_calendars=AsyncMock(
            return_value={"items": [{"id": "named", "accessRole": "owner"}], "truncated": False}
        ),
        list_events_window=AsyncMock(
            side_effect=[
                {"events": rows, "truncated": False},
                {"events": [], "truncated": False},
            ]
        ),
    )

    @asynccontextmanager
    async def opened(_owner):
        yield CalendarAccess(client, "named", ConnectorType.GOOGLE_CALENDAR)

    monkeypatch.setattr(events, "open_active_calendar", opened)
    annotation = EventClassification(
        category="professional",
        evidence_scope="event",
        evaluated_at=now,
        valid_until=now + timedelta(minutes=5),
    )
    native = AsyncMock(return_value={"0": annotation})
    monkeypatch.setattr(publication, "qualify_observations", native)
    result = await events.fetch_shared_events(
        owner, addresses=["peer@example.test"], limit=1, window_days=7, now=now
    )
    assert len(native.call_args.kwargs["observations"]) == 1
    assert native.call_args.kwargs["timezone"] == "Europe/Paris"
    assert result.events[0].classification == annotation
    assert native.call_args.kwargs["observations"][0].item_id == result.events[0].id
    assert native.call_args.kwargs["observations"][0].container_id == "named"


@pytest.mark.asyncio
async def test_meetings_of_several_calendars_are_qualified_in_one_request(monkeypatch):
    """Each under the calendar it was read in, never one request per calendar."""
    owner = uuid4()
    UserPreferencesCache.set(str(owner), "Europe/Paris", "fr")
    now = datetime.now(UTC)

    def shared(event_id: str, hours: int) -> dict[str, object]:
        return {
            "id": event_id,
            "summary": "Hotpot",
            "start": {"dateTime": (now + timedelta(hours=hours)).isoformat()},
            "attendees": [{"email": "peer@example.test"}],
        }

    held = {"named": [shared("booked", 2)], "me@example.test": [shared("invited", 3)]}

    async def window(calendar_id: str, time_min: str, *_args, **_kwargs) -> dict[str, object]:
        coming = datetime.fromisoformat(time_min) >= now
        return {"events": held[calendar_id] if coming else [], "truncated": False}

    client = SimpleNamespace(
        credentials=SimpleNamespace(account_binding="actual-grant"),
        list_calendars=AsyncMock(
            return_value={
                "items": [
                    {"id": "me@example.test", "accessRole": "owner", "primary": True},
                    {"id": "named", "accessRole": "owner"},
                ],
                "truncated": False,
            }
        ),
        list_events_window=AsyncMock(side_effect=window),
    )

    @asynccontextmanager
    async def opened(_owner):
        yield CalendarAccess(client, "named", ConnectorType.GOOGLE_CALENDAR)

    monkeypatch.setattr(events, "open_active_calendar", opened)
    native = AsyncMock(return_value={})
    monkeypatch.setattr(publication, "qualify_observations", native)
    result = await events.fetch_shared_events(
        owner, addresses=["peer@example.test"], limit=10, window_days=7, now=now
    )
    assert [event.id for event in result.events] == ["booked", "invited"]
    native.assert_awaited_once()
    containers = {
        value.item_id: value.container_id for value in native.call_args.kwargs["observations"]
    }
    assert containers == {"booked": "named", "invited": "me@example.test"}


@pytest.mark.asyncio
async def test_mail_deduplicates_before_native_call_and_reuses_display_excerpt(
    monkeypatch,
):
    owner = uuid4()
    UserPreferencesCache.set(str(owner), "Europe/Paris", "fr")
    now = datetime.now(UTC)
    client = SimpleNamespace(
        credentials=SimpleNamespace(account_binding="grant"),
        search_emails=AsyncMock(
            return_value={
                "messages": [
                    {
                        "id": "same",
                        "subject": "Credentials",
                        "snippet": "Give me the code",
                    }
                ]
            }
        ),
    )

    @asynccontextmanager
    async def opened(*_args):
        yield SimpleNamespace(client=client, connector_type=ConnectorType.GOOGLE_GMAIL)

    monkeypatch.setattr(emails, "open_category_client", opened)
    annotation = EmailClassification(
        category="phishing_scam",
        priority="unknown",
        evidence_scope="snippet",
        evaluated_at=now,
        valid_until=now + timedelta(seconds=30),
    )
    native = AsyncMock(return_value={"0": annotation})
    monkeypatch.setattr(publication, "qualify_observations", native)
    result = await emails.fetch_exchanged_emails(
        owner, addresses=["peer@example.test"], limit=3, window_days=7, now=now
    )
    assert len(result) == len(native.call_args.kwargs["observations"]) == 1
    assert result[0].classification == annotation
    assert native.call_args.kwargs["observations"][0].evidence["snippet"] == result[0].excerpt


@pytest.mark.asyncio
async def test_optional_preference_read_failure_never_discards_source_rows(monkeypatch):
    owner = uuid4()

    @asynccontextmanager
    async def refused():
        raise SQLAlchemyError("unavailable")
        yield

    monkeypatch.setattr(classification, "get_db_context", refused)
    native = AsyncMock()
    monkeypatch.setattr(classification, "qualify_selected", native)
    assert (
        await classification.qualify_rows(
            [{"id": "one"}],
            source=classification.ClassificationSource("gmail", "grant"),
            user_id=owner,
            kind="email",
        )
        == {}
    )
    native.assert_not_called()
