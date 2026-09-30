"""Weather provider chokepoint (lot E, 2026-08).

`resolve_weather_client` is the single place briefing/heartbeat obtain the
active weather provider's client — OWM-shaped whichever provider it is:
Google Weather (platform key) or OpenWeatherMap (personal key).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.google_weather_client import GoogleWeatherClient
from src.domains.connectors.clients.openweathermap_client import OpenWeatherMapClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.weather_provider import (
    open_platform_weather_client,
    resolve_weather_client,
)

pytestmark = pytest.mark.unit


def _resolver(resolved: ConnectorType | None) -> object:
    return patch(
        "src.domains.connectors.provider_resolver.resolve_active_connector",
        new=AsyncMock(return_value=resolved),
    )


class TestResolveWeatherClient:
    async def test_google_weather_active_yields_platform_client(self) -> None:
        service = MagicMock()
        with (
            _resolver(ConnectorType.GOOGLE_WEATHER),
            patch(
                "src.domains.connectors.weather_provider.settings",
                MagicMock(google_api_key="platform-key"),
            ),
        ):
            client = await resolve_weather_client(uuid4(), service)
        assert isinstance(client, GoogleWeatherClient)

    async def test_owm_active_yields_user_key_client(self) -> None:
        service = MagicMock()
        service.get_api_key_credentials = AsyncMock(return_value=MagicMock(api_key="owm-key"))
        with _resolver(ConnectorType.OPENWEATHERMAP):
            client = await resolve_weather_client(uuid4(), service)
        assert isinstance(client, OpenWeatherMapClient)
        assert client.api_key == "owm-key"

    async def test_no_active_provider_yields_none(self) -> None:
        with _resolver(None):
            assert await resolve_weather_client(uuid4(), MagicMock()) is None

    async def test_google_weather_without_platform_key_yields_none(self) -> None:
        with (
            _resolver(ConnectorType.GOOGLE_WEATHER),
            patch(
                "src.domains.connectors.weather_provider.settings",
                MagicMock(google_api_key=""),
            ),
        ):
            assert await resolve_weather_client(uuid4(), MagicMock()) is None

    async def test_owm_active_without_credentials_yields_none(self) -> None:
        service = MagicMock()
        service.get_api_key_credentials = AsyncMock(return_value=None)
        with _resolver(ConnectorType.OPENWEATHERMAP):
            assert await resolve_weather_client(uuid4(), service) is None


class TestOpenPlatformWeatherClient:
    """What a weather routine reads: the instance's Google Weather, never the person's choice."""

    async def test_the_instance_serving_google_weather_yields_its_client(self) -> None:
        service = MagicMock()
        service.is_connector_active = AsyncMock(return_value=True)
        user_id = uuid4()

        client = await open_platform_weather_client(user_id, service)

        assert isinstance(client, GoogleWeatherClient)
        assert client.user_id == user_id
        service.is_connector_active.assert_awaited_once_with(user_id, ConnectorType.GOOGLE_WEATHER)

    async def test_a_person_on_openweathermap_still_gets_google_weather(self) -> None:
        service = MagicMock()
        service.is_connector_active = AsyncMock(return_value=True)
        with _resolver(ConnectorType.OPENWEATHERMAP) as resolver:
            client = await open_platform_weather_client(uuid4(), service)

        assert isinstance(client, GoogleWeatherClient)
        resolver.assert_not_awaited()

    async def test_the_instance_withholding_google_weather_yields_none(self) -> None:
        # Switched off by the administrator, or no platform key (ADR-307).
        service = MagicMock()
        service.is_connector_active = AsyncMock(return_value=False)

        assert await open_platform_weather_client(uuid4(), service) is None


class TestGoogleWeatherClientContractSurface:
    async def test_close_is_a_safe_noop(self) -> None:
        """briefing/heartbeat call client.close() in finally — must exist."""
        await GoogleWeatherClient(uuid4()).close()

    async def test_reverse_geocode_returns_owm_shaped_city_entries(self) -> None:
        client = GoogleWeatherClient(uuid4())
        with patch(
            "src.domains.connectors.clients.google_weather_client.google_reverse_city",
            new=AsyncMock(return_value=("Paris", "FR")),
        ):
            entries = await client.reverse_geocode(lat=48.85, lon=2.35, limit=1)
        assert entries == [{"name": "Paris", "country": "FR"}]

    async def test_reverse_geocode_no_result_is_empty_list(self) -> None:
        client = GoogleWeatherClient(uuid4())
        with patch(
            "src.domains.connectors.clients.google_weather_client.google_reverse_city",
            new=AsyncMock(return_value=None),
        ):
            assert await client.reverse_geocode(lat=0.0, lon=0.0) == []
