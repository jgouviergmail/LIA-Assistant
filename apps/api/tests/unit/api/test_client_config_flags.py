"""Client-config feature flags contract (peers program, Lot 2).

The « Connexions » settings section gates on ``features.peers_enabled`` from
``/api/v1/config`` (OpenLoopsSection precedent). Pinning the key here means a
renamed/removed flag breaks a test instead of silently hiding the section on
every instance.
"""

import pytest

from src.api.v1.routes import get_client_config
from src.core.config import settings


@pytest.mark.unit
class TestClientConfigFlags:
    """The additive instance flags the frontend gates sections on."""

    async def test_peers_flag_present_and_mirrors_settings(self):
        payload = await get_client_config()
        assert "peers_enabled" in payload["features"]
        assert payload["features"]["peers_enabled"] is bool(settings.peers_enabled)

    async def test_workboard_flag_present_and_mirrors_settings(self):
        """ADR-274: the board page, its settings section and the chat's ticket
        actions all gate on this flag — the gate-keeper rule (ADR-061)."""
        payload = await get_client_config()
        assert "workboard_enabled" in payload["features"]
        assert payload["features"]["workboard_enabled"] is bool(settings.workboard_enabled)

    async def test_sibling_gate_flags_still_present(self):
        """The section-gating flags the settings page consumes (page.tsx memo)."""
        payload = await get_client_config()
        assert {"open_loops_enabled", "channels_enabled", "heartbeat_enabled"} <= set(
            payload["features"]
        )
