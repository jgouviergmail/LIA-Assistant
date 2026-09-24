"""
Unit tests for SmartPlannerService._build_iot_device_context().

Tests the IoT device discovery and context injection into planner prompts,
including Hue light/room name fetching, domain filtering, and error handling.

Created: 2026-03-27
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.services.smart_planner_service import SmartPlannerService
from tests.helpers.runtime_context import installed_runtime_context, no_runtime_context

#: The config the planner receives carries thread plumbing only; the acting user
#: reaches _build_iot_device_context through the run context (ADR-231).
_CONFIG: dict = {"configurable": {}}


@pytest.fixture(autouse=True)
def _run_context():
    """Install a run context so the discovery sees an acting user."""
    with installed_runtime_context(user_id=uuid4()):
        yield


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


class _Units:
    """A detached connector service counting the sessions it holds open."""

    def __init__(self, service: MagicMock) -> None:
        self.service = service
        self.open = 0

    @asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[MagicMock]:
        self.open += 1
        try:
            yield self.service
        finally:
            self.open -= 1


_DETACHED = "src.domains.connectors.session_scope.DetachedConnectorService"
_CLIENT = "src.domains.connectors.clients.philips_hue_client.PhilipsHueClient"


class TestBuildIotDeviceContext:
    """Test IoT device discovery and context injection."""

    @pytest.mark.asyncio
    async def test_empty_when_no_domains(self) -> None:
        """Returns empty string when no domains are passed."""
        config = _CONFIG
        assert await SmartPlannerService._build_iot_device_context(None, config) == ""
        assert await SmartPlannerService._build_iot_device_context([], config) == ""

    @pytest.mark.asyncio
    async def test_empty_when_non_hue_domain(self) -> None:
        """Returns empty string when domains don't include Hue."""
        config = _CONFIG
        result = await SmartPlannerService._build_iot_device_context(["weather", "email"], config)
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_when_no_run_context(self) -> None:
        """Returns empty string outside a run — the only way to have no user.

        Identity is a mandatory field of LiaRuntimeContext (ADR-231), so
        "no acting user" is no longer a missing key in a config dict.
        """
        with no_runtime_context():
            result = await SmartPlannerService._build_iot_device_context(["hue"], _CONFIG)
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_when_no_hue_credentials(self) -> None:
        """Returns empty string when user has no Hue connector configured."""
        config = _CONFIG
        mock_service = MagicMock()
        mock_service.get_hue_credentials = AsyncMock(return_value=None)

        with (
            patch(_DETACHED, return_value=_Units(mock_service)),
            patch(_CLIENT) as client_class,
        ):
            result = await SmartPlannerService._build_iot_device_context(["hue"], config)
        assert result == ""
        client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_injects_light_and_room_names(self) -> None:
        """Injects exact light and room names into context string."""
        config = _CONFIG
        lights = [_make_light("Plafond salon"), _make_light("Bureau")]
        rooms = [_make_room("Salon"), _make_room("Chambre")]

        mock_service = MagicMock()
        mock_service.get_hue_credentials = AsyncMock(return_value=MagicMock())
        units = _Units(mock_service)
        open_while_asked: list[int] = []

        async def _lights() -> list[dict]:
            open_while_asked.append(units.open)
            return lights

        mock_client = MagicMock()
        mock_client.list_lights = AsyncMock(side_effect=_lights)
        mock_client.list_rooms = AsyncMock(return_value=rooms)
        mock_client.close = AsyncMock()

        with (
            patch(_DETACHED, return_value=units),
            patch(_CLIENT, return_value=mock_client),
        ):
            result = await SmartPlannerService._build_iot_device_context(["hue"], config)

        # ADR-304: no session held while the bridge answers; the transport closed.
        assert open_while_asked == [0]
        mock_client.close.assert_awaited_once()

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
        config = _CONFIG

        with patch(_DETACHED, side_effect=RuntimeError("DB unavailable")):
            result = await SmartPlannerService._build_iot_device_context(["hue"], config)
        assert result == ""

    @pytest.mark.asyncio
    async def test_empty_when_no_lights_or_rooms(self) -> None:
        """Returns empty string when bridge has no devices."""
        config = _CONFIG

        mock_client = MagicMock()
        mock_client.list_lights = AsyncMock(return_value=[])
        mock_client.list_rooms = AsyncMock(return_value=[])
        mock_client.close = AsyncMock()

        mock_service = MagicMock()
        mock_service.get_hue_credentials = AsyncMock(return_value=MagicMock())

        with (
            patch(_DETACHED, return_value=_Units(mock_service)),
            patch(_CLIENT, return_value=mock_client),
        ):
            result = await SmartPlannerService._build_iot_device_context(["hue"], config)
        assert result == ""
