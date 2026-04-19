"""Integration tests for the weather last-known location endpoints.

Covers:
- PATCH /auth/me/weather-location-preference (opt-in toggle + wipe on opt-out)
- PUT /auth/me/last-location (push geolocation, 403 on opt-out, throttle)
- GET /auth/me/last-location (transparency view)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User


@pytest.mark.integration
class TestWeatherLocationPreference:
    """PATCH /auth/me/weather-location-preference endpoint."""

    @pytest.mark.asyncio
    async def test_opt_in_updates_flag(
        self,
        authenticated_client: tuple[AsyncClient, User],
        async_session: AsyncSession,
    ):
        client, user = authenticated_client
        resp = await client.patch(
            "/api/v1/auth/me/weather-location-preference",
            json={"enabled": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True

        await async_session.refresh(user)
        assert user.weather_use_last_known_location is True

    @pytest.mark.asyncio
    async def test_opt_out_wipes_stored_location(
        self,
        authenticated_client: tuple[AsyncClient, User],
        async_session: AsyncSession,
    ):
        client, user = authenticated_client

        # Opt-in then push a location
        await client.patch(
            "/api/v1/auth/me/weather-location-preference",
            json={"enabled": True},
        )
        await client.put(
            "/api/v1/auth/me/last-location",
            json={"lat": 48.85, "lon": 2.35, "accuracy": 25.0},
        )

        # Opt-out should wipe
        resp = await client.patch(
            "/api/v1/auth/me/weather-location-preference",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

        await async_session.refresh(user)
        assert user.weather_use_last_known_location is False
        assert user.last_known_location_encrypted is None
        assert user.last_known_location_updated_at is None


@pytest.mark.integration
class TestPutLastLocation:
    """PUT /auth/me/last-location endpoint."""

    @pytest.mark.asyncio
    async def test_forbidden_when_opt_out(
        self,
        authenticated_client: tuple[AsyncClient, User],
    ):
        client, _ = authenticated_client
        # Default is opt-out
        resp = await client.put(
            "/api/v1/auth/me/last-location",
            json={"lat": 48.85, "lon": 2.35},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_updates_when_opt_in(
        self,
        authenticated_client: tuple[AsyncClient, User],
        async_session: AsyncSession,
    ):
        client, user = authenticated_client
        await client.patch(
            "/api/v1/auth/me/weather-location-preference",
            json={"enabled": True},
        )
        resp = await client.put(
            "/api/v1/auth/me/last-location",
            json={"lat": 48.85, "lon": 2.35, "accuracy": 25.0},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] is True
        assert body["throttled"] is False

        await async_session.refresh(user)
        assert user.last_known_location_encrypted is not None
        assert user.last_known_location_updated_at is not None

    @pytest.mark.asyncio
    async def test_second_call_within_window_is_throttled(
        self,
        authenticated_client: tuple[AsyncClient, User],
    ):
        client, _ = authenticated_client
        await client.patch(
            "/api/v1/auth/me/weather-location-preference",
            json={"enabled": True},
        )
        first = await client.put(
            "/api/v1/auth/me/last-location",
            json={"lat": 48.85, "lon": 2.35},
        )
        assert first.json()["updated"] is True

        second = await client.put(
            "/api/v1/auth/me/last-location",
            json={"lat": 48.86, "lon": 2.36},
        )
        assert second.status_code == 200
        body = second.json()
        assert body["updated"] is False
        assert body["throttled"] is True

    @pytest.mark.asyncio
    async def test_rejects_out_of_range_coords(
        self,
        authenticated_client: tuple[AsyncClient, User],
    ):
        client, _ = authenticated_client
        await client.patch(
            "/api/v1/auth/me/weather-location-preference",
            json={"enabled": True},
        )
        resp = await client.put(
            "/api/v1/auth/me/last-location",
            json={"lat": 200.0, "lon": 2.35},  # lat out of [-90, 90]
        )
        assert resp.status_code == 422


@pytest.mark.integration
class TestHomeDeletionCascade:
    """Deleting the home location must also wipe the last-known location."""

    @pytest.mark.asyncio
    async def test_delete_home_wipes_last_known(
        self,
        authenticated_client: tuple[AsyncClient, User],
        async_session: AsyncSession,
    ):
        client, user = authenticated_client

        # Set up: opt-in, set home, push a last-known
        await client.patch(
            "/api/v1/auth/me/weather-location-preference",
            json={"enabled": True},
        )
        # Home must be set for the DELETE endpoint to make sense; use the
        # existing users endpoint. If Google Places is not configured in the
        # test env this write will fail — that's an env concern, not a
        # cascade-logic concern.
        await client.put(
            "/api/v1/users/me/home-location",
            json={"address": "Lyon", "lat": 45.75, "lon": 4.85, "place_id": "p1"},
        )
        await client.put(
            "/api/v1/auth/me/last-location",
            json={"lat": 48.85, "lon": 2.35},
        )

        # Sanity: last-known is stored
        view = await client.get("/api/v1/auth/me/last-location")
        assert view.json()["stored"] is True

        # Delete home
        resp = await client.delete("/api/v1/users/me/home-location")
        assert resp.status_code == 204

        # Last-known must be gone too
        await async_session.refresh(user)
        assert user.last_known_location_encrypted is None
        assert user.last_known_location_updated_at is None


@pytest.mark.integration
class TestGetLastLocation:
    """GET /auth/me/last-location endpoint."""

    @pytest.mark.asyncio
    async def test_empty_when_nothing_stored(
        self,
        authenticated_client: tuple[AsyncClient, User],
    ):
        client, _ = authenticated_client
        resp = await client.get("/api/v1/auth/me/last-location")
        assert resp.status_code == 200
        body = resp.json()
        assert body["stored"] is False
        assert body["lat"] is None
        assert body["lon"] is None

    @pytest.mark.asyncio
    async def test_returns_decrypted_view_when_stored(
        self,
        authenticated_client: tuple[AsyncClient, User],
    ):
        client, _ = authenticated_client
        await client.patch(
            "/api/v1/auth/me/weather-location-preference",
            json={"enabled": True},
        )
        await client.put(
            "/api/v1/auth/me/last-location",
            json={"lat": 48.85, "lon": 2.35, "accuracy": 25.0},
        )

        resp = await client.get("/api/v1/auth/me/last-location")
        assert resp.status_code == 200
        body = resp.json()
        assert body["stored"] is True
        assert body["lat"] == 48.85
        assert body["lon"] == 2.35
        assert body["accuracy"] == 25.0
        assert body["updated_at"] is not None
        assert body["stale"] is False
