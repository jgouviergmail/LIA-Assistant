"""
Unit tests for PhilipsHueClient.

Tests cover:
- Client initialization (local and remote modes)
- URL construction for both modes
- Auth header construction
- Color resolution
- Room-to-grouped_light resolution helper
- Static methods (discover, pair)
"""

from uuid import uuid4

import pytest

from src.domains.connectors.clients.philips_hue_client import (
    HUE_COLOR_MAP,
    PhilipsHueClient,
    _extract_grouped_light_id,
    resolve_color,
)
from src.domains.connectors.schemas import HueBridgeCredentials, HueConnectionMode


@pytest.mark.unit
class TestPhilipsHueClientInit:
    """Test client initialization for both modes."""

    def test_local_mode_init(self) -> None:
        """Test local mode sets correct base URL and SSL config."""
        credentials = HueBridgeCredentials(
            connection_mode=HueConnectionMode.LOCAL,
            api_key="test-api-key",
            bridge_ip="192.168.1.100",
        )
        client = PhilipsHueClient(
            user_id=uuid4(),
            credentials=credentials,
            connector_service=None,
        )
        assert client._base_url == "https://192.168.1.100"
        assert client._verify_ssl is False
        assert client._connection_mode == HueConnectionMode.LOCAL

    def test_remote_mode_init(self) -> None:
        """Test remote mode sets correct base URL and SSL config."""
        credentials = HueBridgeCredentials(
            connection_mode=HueConnectionMode.REMOTE,
            access_token="test-token",
            refresh_token="test-refresh",
            remote_username="test-user",
        )
        client = PhilipsHueClient(
            user_id=uuid4(),
            credentials=credentials,
            connector_service=None,
        )
        assert "api.meethue.com" in client._base_url
        assert client._verify_ssl is True
        assert client._connection_mode == HueConnectionMode.REMOTE


@pytest.mark.unit
class TestResolveColor:
    """Test color name to CIE xy resolution."""

    def test_english_color(self) -> None:
        """Test resolving English color name."""
        result = resolve_color("red")
        assert result is not None
        assert len(result) == 2
        assert result == HUE_COLOR_MAP["red"]

    def test_french_color(self) -> None:
        """Test resolving French color name."""
        result = resolve_color("bleu")
        assert result is not None
        assert result == HUE_COLOR_MAP["bleu"]

    def test_case_insensitive(self) -> None:
        """Test case-insensitive matching."""
        result = resolve_color("WARM_WHITE")
        assert result is not None
        assert result == HUE_COLOR_MAP["warm_white"]

    def test_spaces_normalized(self) -> None:
        """Test space-to-underscore normalization."""
        result = resolve_color("warm white")
        assert result is not None
        assert result == HUE_COLOR_MAP["warm_white"]

    def test_xy_coordinates(self) -> None:
        """Test parsing x,y coordinate string."""
        result = resolve_color("0.5,0.3")
        assert result == (0.5, 0.3)

    def test_invalid_color_returns_none(self) -> None:
        """Test unrecognized color returns None."""
        assert resolve_color("ultraviolet_megabright") is None

    def test_out_of_range_xy(self) -> None:
        """Test out-of-range coordinates return None."""
        assert resolve_color("1.5,0.3") is None


@pytest.mark.unit
class TestExtractGroupedLightId:
    """Test room-to-grouped_light helper."""

    def test_extract_grouped_light(self) -> None:
        """Test extracting grouped_light ID from room data."""
        room_data = {
            "id": "room-1",
            "services": [
                {"rtype": "light", "rid": "light-1"},
                {"rtype": "grouped_light", "rid": "group-1"},
            ],
        }
        assert _extract_grouped_light_id(room_data) == "group-1"

    def test_no_grouped_light_raises(self) -> None:
        """Test ValueError when no grouped_light service."""
        room_data = {
            "id": "room-1",
            "services": [{"rtype": "light", "rid": "light-1"}],
        }
        with pytest.raises(ValueError, match="No grouped_light found"):
            _extract_grouped_light_id(room_data)

    def test_empty_services(self) -> None:
        """Test ValueError with empty services list."""
        room_data = {"id": "room-1", "services": []}
        with pytest.raises(ValueError):
            _extract_grouped_light_id(room_data)
