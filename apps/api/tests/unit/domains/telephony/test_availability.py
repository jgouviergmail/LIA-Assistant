"""Unit tests for the telephony availability pre-fetch (P3.2).

The load-bearing test is the leak assertion: a calendar event carrying a title
and a location must project to a busy time range that contains NEITHER — the
minimization is by capability (the projection reads only start/end), so the
guarantee is verifiable in isolation on the pure projector.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

import src.domains.telephony.availability as availability
from src.domains.telephony.availability import (
    build_availability_summary,
    summarize_busy_periods,
)

# A timed event and an all-day event, each carrying detail fields that MUST NOT
# leak into the projected summary.
_SECRET_TITLE = "Chemo appointment"
_SECRET_LOCATION = "Oncology ward, room 12"
_EVENTS: list[dict] = [
    {
        "summary": _SECRET_TITLE,
        "location": _SECRET_LOCATION,
        "attendees": [{"email": "doctor@example.com"}],
        "start": {"dateTime": "2026-07-14T09:00:00+02:00"},
        "end": {"dateTime": "2026-07-14T10:30:00+02:00"},
    },
    {
        "summary": "Family holiday",
        "start": {"date": "2026-07-20"},
        "end": {"date": "2026-07-21"},
    },
]


@pytest.mark.unit
def test_summary_emits_busy_ranges_and_leaks_nothing() -> None:
    """Busy ranges are present; titles/locations/attendees never appear."""
    out = summarize_busy_periods(_EVENTS, "Europe/Paris", "fr")

    # Busy time ranges are present (French localized time components).
    assert "09:00" in out and "10:30" in out
    assert "→" in out
    # Leak assertion: no meeting detail whatsoever.
    assert _SECRET_TITLE not in out
    assert _SECRET_LOCATION not in out
    assert "Family holiday" not in out
    assert "doctor@example.com" not in out


@pytest.mark.unit
def test_all_day_event_renders_without_spurious_time() -> None:
    """An all-day (date-only) block renders as a date, not a shifted time."""
    out = summarize_busy_periods([_EVENTS[1]], "Europe/Paris", "en")
    # Date-only events use include_time=False → no "at HH:MM" tail.
    assert " at " not in out
    assert "July" in out


@pytest.mark.unit
def test_empty_events_returns_all_free_phrase() -> None:
    """No events → the localized 'fully available' line, per language."""
    assert summarize_busy_periods([], "Europe/Paris", "fr").startswith("Aucun créneau")
    assert summarize_busy_periods([], "Europe/Paris", "en").startswith("No busy periods")
    assert summarize_busy_periods([], "Europe/Paris", "zh-CN").startswith("该时间段内无占用")


@pytest.mark.unit
def test_event_without_start_is_skipped() -> None:
    """A malformed event with no start yields no busy line (treated as free)."""
    out = summarize_busy_periods([{"summary": "x", "end": {"date": "2026-07-21"}}], "UTC", "en")
    assert out.startswith("No busy periods")


class _FakeCalendarClient:
    """Minimal calendar client: records the list_events kwargs, returns _EVENTS."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.last_kwargs: dict = {}

    async def list_events(self, **kwargs: object) -> dict:
        self.last_kwargs = kwargs
        return {"items": _EVENTS}


def _fake_connector_service() -> SimpleNamespace:
    async def _get_connector_credentials(user_id: object, resolved_type: object) -> object:
        return {"token": "x"}

    return SimpleNamespace(db=None, get_connector_credentials=_get_connector_credentials)


@pytest.mark.unit
async def test_build_summary_requests_only_start_end_and_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper asks the provider for start/end only and projects busy blocks."""
    resolved = SimpleNamespace(is_apple=False, value="google_calendar")

    async def _resolve(*args: object, **kwargs: object) -> object:
        return resolved

    fake_client = _FakeCalendarClient()
    monkeypatch.setattr(
        "src.domains.connectors.provider_resolver.resolve_active_connector", _resolve
    )
    monkeypatch.setattr(
        "src.domains.connectors.clients.registry.ClientRegistry.get_client_class",
        staticmethod(lambda _t: (lambda *a, **k: fake_client)),
    )

    # Keep the calendar-id resolution off the DB in this unit test.
    async def _primary(*args: object, **kwargs: object) -> str:
        return "primary"

    monkeypatch.setattr(availability, "_resolve_calendar_id", _primary)

    out = await build_availability_summary(
        uuid4(),
        datetime(2026, 7, 14, tzinfo=UTC),
        datetime(2026, 7, 21, tzinfo=UTC),
        _fake_connector_service(),  # type: ignore[arg-type]
        "Europe/Paris",
        "fr",
    )

    assert fake_client.last_kwargs.get("fields") == ["start", "end"]
    assert "09:00" in out and _SECRET_TITLE not in out


@pytest.mark.unit
async def test_build_summary_unavailable_when_no_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No active calendar connector → localized 'unavailable' line, never raises."""

    async def _resolve(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "src.domains.connectors.provider_resolver.resolve_active_connector", _resolve
    )
    out = await build_availability_summary(
        uuid4(),
        datetime(2026, 7, 14, tzinfo=UTC),
        datetime(2026, 7, 21, tzinfo=UTC),
        _fake_connector_service(),  # type: ignore[arg-type]
        "Europe/Paris",
        "fr",
    )
    assert out.startswith("Disponibilités indisponibles")


@pytest.mark.unit
async def test_build_summary_swallows_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider HTTP error is swallowed → 'unavailable', the call is not blocked."""

    async def _boom(*args: object, **kwargs: object) -> object:
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("src.domains.connectors.provider_resolver.resolve_active_connector", _boom)
    out = await build_availability_summary(
        uuid4(),
        datetime(2026, 7, 14, tzinfo=UTC),
        datetime(2026, 7, 21, tzinfo=UTC),
        _fake_connector_service(),  # type: ignore[arg-type]
        "Europe/Paris",
        "en",
    )
    assert out.startswith("Availability unavailable")
