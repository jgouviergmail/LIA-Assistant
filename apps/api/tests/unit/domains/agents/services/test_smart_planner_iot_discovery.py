"""
Unit tests for SmartPlannerService._build_iot_device_context().

Tests the IoT device discovery and context injection into planner prompts,
including Hue light/room name fetching, domain filtering, and error handling.

Created: 2026-03-27
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.smart_planner_service import SmartPlannerService


def _make_config(user_id: str | None = None) -> dict:
    """Build a minimal RunnableConfig dict for testing."""
    return {"configurable": {"user_id": user_id or str(uuid4())}}


def _make_light(name: str, light_id: str = "") -> dict:
    """Build a minimal Hue light resource dict."""
    return {
        "id": light_id or str(uuid4()),
        "metadata": {"name": name},
        "on": {"on": True},
        "dimming": {"brightness": 100.0},
    }


def _make_room(name: str, room_id: str = "") -> dict:
    """Build a minimal Hue room resource dict."""
    return {
        "id": room_id or str(uuid4()),
        "metadata": {"name": name},
    }


def _mock_async_session_context(mock_session: MagicMock) -> MagicMock:
    """Wrap a mock to behave as an async context manager."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


class TestBuildIotDeviceContext:
    """Test IoT device discovery and context injection."""

    @pytest.mark.asyncio
    async def test_empty_when_no_domains(self) -> None:
        """Returns empty string when no domains are passed."""
        config = _make_config()
        assert await SmartPlannerService._build_iot_device_context(None, config) == ""
        assert await SmartPlannerService._build_iot_device_context([], config) == ""

    @pytest.mark.asyncio
    async def test_empty_when_non_hue_domain(self) -> None:
        """Returns empty string when domains don't include Hue."""
        config = _make_config()
        result = await SmartPlannerService._build_iot_device_context(["weather", "email"], config)
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_when_no_user_id(self) -> None:
        """Returns empty string when user_id is missing from config."""
        config: dict = {"configurable": {}}
        result = await SmartPlannerService._build_iot_device_context(["hue"], config)
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_when_no_hue_credentials(self) -> None:
        """Returns empty string when user has no Hue connector configured."""
        config = _make_config()
        mock_service = MagicMock()
        mock_service.get_hue_credentials = AsyncMock(return_value=None)
        mock_session = MagicMock()

        with (
            patch(
                "src.infrastructure.database.session.AsyncSessionLocal",
                return_value=_mock_async_session_context(mock_session),
            ),
            patch(
                "src.domains.connectors.service.ConnectorService",
                return_value=mock_service,
            ),
        ):
            result = await SmartPlannerService._build_iot_device_context(["hue"], config)
        assert result == ""

    @pytest.mark.asyncio
    async def test_injects_light_and_room_names(self) -> None:
        """Injects exact light and room names into context string."""
        config = _make_config()
        lights = [_make_light("Plafond salon"), _make_light("Bureau")]
        rooms = [_make_room("Salon"), _make_room("Chambre")]

        mock_client = MagicMock()
        mock_client.list_lights = AsyncMock(return_value=lights)
        mock_client.list_rooms = AsyncMock(return_value=rooms)

        mock_credentials = MagicMock()
        mock_service = MagicMock()
        mock_service.get_hue_credentials = AsyncMock(return_value=mock_credentials)
        mock_session = MagicMock()

        with (
            patch(
                "src.infrastructure.database.session.AsyncSessionLocal",
                return_value=_mock_async_session_context(mock_session),
            ),
            patch(
                "src.domains.connectors.service.ConnectorService",
                return_value=mock_service,
            ),
            patch(
                "src.domains.connectors.clients.philips_hue_client.PhilipsHueClient",
                return_value=mock_client,
            ),
        ):
            result = await SmartPlannerService._build_iot_device_context(["hue"], config)

        assert '"Plafond salon"' in result
        assert '"Bureau"' in result
        assert '"Salon"' in result
        assert '"Chambre"' in result
        assert "AVAILABLE HUE LIGHTS" in result
        assert "AVAILABLE HUE ROOMS" in result
        assert "EXACT name" in result

    @pytest.mark.asyncio
    async def test_graceful_failure_on_api_error(self) -> None:
        """Returns empty string on any exception (non-blocking)."""
        config = _make_config()

        with patch(
            "src.infrastructure.database.session.AsyncSessionLocal",
            side_effect=RuntimeError("DB unavailable"),
        ):
            result = await SmartPlannerService._build_iot_device_context(["hue"], config)
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_when_no_lights_or_rooms(self) -> None:
        """Returns empty string when bridge has no devices."""
        config = _make_config()

        mock_client = MagicMock()
        mock_client.list_lights = AsyncMock(return_value=[])
        mock_client.list_rooms = AsyncMock(return_value=[])

        mock_credentials = MagicMock()
        mock_service = MagicMock()
        mock_service.get_hue_credentials = AsyncMock(return_value=mock_credentials)
        mock_session = MagicMock()

        with (
            patch(
                "src.infrastructure.database.session.AsyncSessionLocal",
                return_value=_mock_async_session_context(mock_session),
            ),
            patch(
                "src.domains.connectors.service.ConnectorService",
                return_value=mock_service,
            ),
            patch(
                "src.domains.connectors.clients.philips_hue_client.PhilipsHueClient",
                return_value=mock_client,
            ),
        ):
            result = await SmartPlannerService._build_iot_device_context(["hue"], config)
        assert result == ""
