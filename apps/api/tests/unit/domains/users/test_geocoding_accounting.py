"""Geocoding the person's own address is a billed Places call, filed on them.

The module used a direct recorder (``GoogleApiUsageService.record_api_call``,
deleted 2026-09-20) that wrote the usage log and the user statistics but
neither the run's summary row nor the instance's daily ledger — half a
ledger, and a second implementation of the statistics increment. It now opens
its own ``TrackingContext``, the one persistence path every family shares,
on its OWN session: Google bills a search that finds nothing, and the request
that then answers 400 rolls its session back.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.context import current_tracker
from src.core.exceptions import BaseAPIException
from src.domains.chat.service import TrackingContext
from src.domains.connectors.clients.google_api_tracker import track_google_api_call
from src.domains.users import geocoding

pytestmark = pytest.mark.unit


@pytest.fixture
def persisted(monkeypatch: pytest.MonkeyPatch) -> list[TrackingContext]:
    seen: list[TrackingContext] = []

    async def _persist(self: TrackingContext) -> None:
        seen.append(self)

    monkeypatch.setattr(TrackingContext, "_persist_to_database", _persist)
    monkeypatch.setattr(
        "src.domains.google_api.pricing_service.GoogleApiPricingService.get_cost_per_request",
        lambda *_a, **_k: (Decimal("0.032"), Decimal("0.029"), Decimal("0.91")),
    )
    monkeypatch.setattr(
        "src.domains.shared.consultation_surfaces.record_surface_consultations", MagicMock()
    )
    return seen


def _client(monkeypatch: pytest.MonkeyPatch, places: list[dict]) -> None:
    async def _search_text(*, query: str, max_results: int, use_cache: bool) -> dict:
        # What the real client does after Google answers.
        track_google_api_call("places", "/places:searchText", cached=False)
        return {"places": places}

    client = MagicMock()
    client.search_text = AsyncMock(side_effect=_search_text)
    monkeypatch.setattr(
        "src.domains.connectors.clients.google_places_client.GooglePlacesClient",
        MagicMock(return_value=client),
    )


def _location(address: str = "1 rue de la Paix, Paris") -> MagicMock:
    location = MagicMock()
    location.lat = 0.0
    location.lon = 0.0
    location.place_id = None
    location.address = address
    return location


async def test_a_resolved_address_is_filed_on_the_person(
    monkeypatch: pytest.MonkeyPatch, persisted: list
) -> None:
    _client(monkeypatch, [{"id": "ChIJ", "location": {"latitude": 48.87, "longitude": 2.33}}])
    user_id = uuid.uuid4()
    lat, lon, place_id = await geocoding.resolve_home_coordinates(
        user_id=user_id, user=MagicMock(language="fr"), location=_location()
    )
    assert (lat, lon, place_id) == (48.87, 2.33, "ChIJ")
    (tracker,) = persisted
    assert tracker.user_id == user_id
    assert tracker.run_id.startswith("profile_geocoding_")
    assert tracker.pending_families()["google_api"] == 1
    assert current_tracker.get() is None


async def test_a_search_that_finds_nothing_is_still_billed_and_still_filed(
    monkeypatch: pytest.MonkeyPatch, persisted: list
) -> None:
    _client(monkeypatch, [])
    with pytest.raises(BaseAPIException):
        await geocoding.resolve_home_coordinates(
            user_id=uuid.uuid4(), user=MagicMock(language="fr"), location=_location()
        )
    (tracker,) = persisted
    assert tracker.pending_families()["google_api"] == 1


async def test_meaningful_coordinates_call_nothing(
    monkeypatch: pytest.MonkeyPatch, persisted: list
) -> None:
    location = _location()
    location.lat, location.lon, location.place_id = 48.87, 2.33, "ChIJ"
    client = MagicMock()
    monkeypatch.setattr(
        "src.domains.connectors.clients.google_places_client.GooglePlacesClient", client
    )
    result = await geocoding.resolve_home_coordinates(
        user_id=uuid.uuid4(), user=MagicMock(language="fr"), location=location
    )
    assert result == (48.87, 2.33, "ChIJ")
    client.assert_not_called()
    assert persisted == []
