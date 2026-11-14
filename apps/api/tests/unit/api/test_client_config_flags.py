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

    @pytest.mark.parametrize(("platform_key", "expected"), [("platform-key", True), ("", False)])
    async def test_home_address_flag_is_the_places_ceiling(
        self, platform_key: str, expected: bool, monkeypatch: pytest.MonkeyPatch
    ):
        """The starter checklist offers the home address only where an address
        can be saved: saving geocodes it through Google Places, which a
        deployment without the platform key withholds (ADR-307) — the public
        demonstrator has none (measured 2026-10-22)."""
        monkeypatch.setattr(settings, "google_api_key", platform_key)
        payload = await get_client_config()
        assert payload["features"]["home_address_enabled"] is expected

    @pytest.mark.parametrize("mounted", [True, False])
    async def test_telephony_flag_mirrors_what_mounts_its_routes(
        self, mounted: bool, monkeypatch: pytest.MonkeyPatch
    ):
        """A stored telephony key is a record: the connectors screen keeps
        offering its removal under the operator's switch (ADR-280), which it
        can only tell from an unmounted router by this flag."""
        monkeypatch.setattr(settings, "telephony_enabled", mounted)
        payload = await get_client_config()
        assert payload["features"]["telephony_enabled"] is mounted

    @pytest.mark.parametrize("mounted", [True, False])
    async def test_personal_mcp_flag_mirrors_what_mounts_its_routes(
        self, mounted: bool, monkeypatch: pytest.MonkeyPatch
    ):
        """The MCP switch's ceiling is ``mcp_enabled``; the personal servers'
        router is mounted by ``mcp_user_enabled``. With the first on and the
        second off the capability map says « offered » for a router that is not
        there: the web's door needs the second flag to close the section."""
        monkeypatch.setattr(settings, "mcp_user_enabled", mounted)
        payload = await get_client_config()
        assert payload["features"]["mcp_user_enabled"] is mounted

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


@pytest.mark.unit
class TestTheComposerIsToldWhatAnUploadAccepts:
    """Enforced means published (ADR-184): the composer's picker and drop zone
    read what the upload accepts, from the instance's own allowlists — a
    browser reports no usable type for a ``.md`` or a ``.csv``, so documents
    are published by extension (ADR-295 amendment 2026-11-12)."""

    async def test_the_instance_s_formats_are_published(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "attachments_allowed_image_types", "image/png, image/jpeg")
        monkeypatch.setattr(
            settings,
            "attachments_allowed_doc_types",
            "application/pdf,text/csv,"
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        payload = await get_client_config()

        assert payload["attachments"] == {
            "image_types": ["image/jpeg", "image/png"],
            "document_extensions": [".csv", ".docx", ".pdf"],
        }

    async def test_an_operator_who_narrowed_the_allowlist_narrows_the_composer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "attachments_allowed_doc_types", "application/pdf")

        payload = await get_client_config()

        assert payload["attachments"]["document_extensions"] == [".pdf"]
