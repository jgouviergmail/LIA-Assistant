"""A meeting's place name is a billed Geocoding call, filed under the meeting's run.

The reverse geocoding ran in the processing job with no tracker ambient, so
the counter inside the geocoding helper « did nothing » — a euro on the
deployment's key, no row anywhere (2026-09-19). The enrichment now opens
the meeting run's own accounting around what it reads.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.context import current_tracker
from src.domains.chat.service import TrackingContext
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.meetings import enrichment

pytestmark = pytest.mark.unit


@pytest.fixture
def persisted(monkeypatch: pytest.MonkeyPatch) -> list[TrackingContext]:
    seen: list[TrackingContext] = []

    async def _persist(self: TrackingContext) -> None:
        seen.append(self)

    monkeypatch.setattr(TrackingContext, "_persist_to_database", _persist)
    monkeypatch.setattr(
        "src.domains.google_api.pricing_service.GoogleApiPricingService.get_cost_per_request",
        lambda *_a, **_k: (Decimal("0.005"), Decimal("0.0046"), Decimal("0.91")),
    )
    return seen


def _meeting(*, lat: float | None = 48.85, lon: float | None = 2.35) -> MagicMock:
    meeting = MagicMock()
    meeting.user_id = uuid.uuid4()
    meeting.started_at = datetime(2026, 9, 20, 9, 0, tzinfo=UTC)
    meeting.location_label = None
    meeting.location_lat = lat
    meeting.location_lon = lon
    return meeting


async def test_the_geocoding_call_lands_on_the_meeting_run(
    monkeypatch: pytest.MonkeyPatch, persisted: list
) -> None:
    async def _geocode(lat: float, lon: float, *, language: str) -> str:
        # What the real helper does after Google answers: record on the
        # ambient tracker — the one the enrichment must have published.
        assert current_tracker.get() is not None
        track_google_api_call("geocoding", "/geocode/json", cached=False)
        return "Paris"

    monkeypatch.setattr(enrichment, "match_calendar_event", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "src.domains.connectors.clients.google_geocoding_helpers.reverse_geocode", _geocode
    )
    meeting = _meeting()
    calendar, label = await enrichment.enrich_meeting(
        MagicMock(),
        meeting,
        stopped_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        language="fr",
        run_id="proactive_meeting_abc",
    )
    assert (calendar, label) == (None, "Paris")
    (tracker,) = persisted
    assert tracker.run_id == "proactive_meeting_abc"
    assert tracker.user_id == meeting.user_id
    assert tracker.pending_families()["google_api"] == 1
    assert current_tracker.get() is None


async def test_a_meeting_with_no_position_bills_nothing(
    monkeypatch: pytest.MonkeyPatch, persisted: list
) -> None:
    monkeypatch.setattr(enrichment, "match_calendar_event", AsyncMock(return_value=None))
    geocode = AsyncMock()
    monkeypatch.setattr(
        "src.domains.connectors.clients.google_geocoding_helpers.reverse_geocode", geocode
    )
    calendar, label = await enrichment.enrich_meeting(
        MagicMock(),
        _meeting(lat=None, lon=None),
        stopped_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        language="fr",
        run_id="proactive_meeting_abc",
    )
    assert (calendar, label) == (None, None)
    geocode.assert_not_awaited()
    assert persisted == []


async def test_the_calendar_location_is_the_fallback(
    monkeypatch: pytest.MonkeyPatch, persisted: list
) -> None:
    match = enrichment.CalendarMatch(
        event_id="e", provider="google", title="Point", location="Salle B"
    )
    monkeypatch.setattr(enrichment, "match_calendar_event", AsyncMock(return_value=match))
    monkeypatch.setattr(
        "src.domains.connectors.clients.google_geocoding_helpers.reverse_geocode",
        AsyncMock(return_value=None),
    )
    calendar, label = await enrichment.enrich_meeting(
        MagicMock(),
        _meeting(),
        stopped_at=datetime(2026, 9, 20, 10, 0, tzinfo=UTC),
        language="fr",
        run_id="proactive_meeting_abc",
    )
    assert calendar is match and label == "Salle B"
