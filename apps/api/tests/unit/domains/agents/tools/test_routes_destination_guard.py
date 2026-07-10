"""get_route destination guard (C3b) — unit tests.

Historical failure: a person name passed as destination fell through the
Places search ("no results") and was forwarded raw to the Routes API, which
geocoded it to an arbitrary location — then cached the wrong route. The
resolver now returns an ``_UnresolvedDestination`` marker for that exact
case, which the tool converts into a recoverable failure BEFORE the Routes
API call (so nothing is cached).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import settings
from src.domains.agents.tools import routes_tools
from src.domains.agents.tools.routes_tools import (
    _resolve_destination,
    _UnresolvedDestination,
)
from src.domains.agents.tools.runtime_helpers import ResolvedLocation

ORIGIN = ResolvedLocation(lat=45.75, lon=4.85, source="browser")
PERSON = "Alexandre Gouvier"


def _httpx_client_returning(payload: dict) -> MagicMock:
    """Mock httpx.AsyncClient context manager whose post() returns `payload`."""
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=payload)
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


class TestResolveDestinationUnresolved:
    @pytest.mark.asyncio
    async def test_places_empty_returns_unresolved_marker(self, monkeypatch):
        """Places ran and found nothing → marker, never the raw passthrough."""
        monkeypatch.setattr(settings, "google_api_key", "test-key", raising=False)

        with patch("httpx.AsyncClient", _httpx_client_returning({"places": []})):
            result = await _resolve_destination(PERSON, runtime=MagicMock(), origin_location=ORIGIN)

        assert isinstance(result, _UnresolvedDestination)
        assert result.query == PERSON

    @pytest.mark.asyncio
    async def test_places_result_still_resolves_to_coordinates(self, monkeypatch):
        """A findable place keeps the historical enriched resolution."""
        monkeypatch.setattr(settings, "google_api_key", "test-key", raising=False)
        payload = {
            "places": [
                {
                    "displayName": {"text": "Parc de la Tête d'Or"},
                    "location": {"latitude": 45.77, "longitude": 4.85},
                }
            ]
        }

        with patch("httpx.AsyncClient", _httpx_client_returning(payload)):
            result = await _resolve_destination(
                "parc de la tête d'or", runtime=MagicMock(), origin_location=ORIGIN
            )

        assert isinstance(result, dict)
        assert result["latitude"] == 45.77

    @pytest.mark.asyncio
    async def test_address_like_destination_passes_through_without_api_call(self, monkeypatch):
        """Address heuristics short-circuit before any Places call."""
        monkeypatch.setattr(settings, "google_api_key", "test-key", raising=False)

        with patch("httpx.AsyncClient") as mock_client:
            result = await _resolve_destination(
                "10 rue de la Paix, Paris", runtime=MagicMock(), origin_location=ORIGIN
            )

        assert result == "10 rue de la Paix, Paris"
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_places_api_error_fails_open_to_passthrough(self, monkeypatch):
        """An API failure is not evidence the destination is bad (best-effort)."""
        monkeypatch.setattr(settings, "google_api_key", "test-key", raising=False)
        failing = MagicMock()
        failing.__aenter__ = AsyncMock(side_effect=ConnectionError("boom"))
        failing.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", MagicMock(return_value=failing)):
            result = await _resolve_destination(PERSON, runtime=MagicMock(), origin_location=ORIGIN)

        assert result == PERSON


class TestGetRouteUnresolvedDestination:
    @pytest.mark.asyncio
    async def test_marker_becomes_recoverable_failure_before_routes_api(self):
        """The tool returns destination_unresolved and never reaches compute/cache."""
        with (
            patch.object(
                routes_tools,
                "_resolve_origin",
                AsyncMock(return_value=(ORIGIN, None)),
            ),
            patch.object(
                routes_tools,
                "_resolve_destination",
                AsyncMock(return_value=_UnresolvedDestination(query=PERSON)),
            ),
        ):
            output = await routes_tools.get_route_tool.coroutine(destination=PERSON)

        assert output.success is False
        assert output.error_code == "destination_unresolved"
        # The recoverable message guides the LLM towards contacts.
        assert "contacts" in output.message
        assert PERSON in output.message
