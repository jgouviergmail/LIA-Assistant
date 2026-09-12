"""Client-config feature flags contract (peers program, Lot 2).

The « Connexions » settings section gates on ``features.peers_enabled`` from
``/api/v1/config`` (OpenLoopsSection precedent). Pinning the key here means a
renamed/removed flag breaks a test instead of silently hiding the section on
every instance.
"""

from unittest.mock import patch

import pytest

from src.api.v1.routes import get_client_config
from src.core.config import settings


@pytest.fixture(autouse=True)
def _no_switch_store():
    """``/config`` now reads the capability switches; a unit test has no store."""
    with patch(
        "src.domains.feature_switches.public_state.disabled_capabilities",
        return_value=frozenset(),
    ):
        yield


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

    async def test_every_capability_is_published_with_its_effective_state(self):
        """The demonstrator invitation of another LIA lists what a visitor will
        find here, read live from this payload — every registry member, keyed by
        the frontend's own label vocabulary, with a boolean and a family."""
        from src.domains.feature_switches.registry import CAPABILITY_SPECS

        payload = await get_client_config()
        published = payload["capabilities"]
        assert set(published) == {capability.value for capability in CAPABILITY_SPECS}
        for entry in published.values():
            assert isinstance(entry["enabled"], bool)
            assert isinstance(entry["family"], str)
