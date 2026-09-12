"""What an anonymous reader may learn about this instance's capabilities.

The public client configuration (``GET /config``) publishes, for EVERY
capability of the registry, whether it is effectively available — the
deployment ceiling AND the operator switch — so a page that links to an
instance (the demonstrator invitation of another LIA) can list what a visitor
will find and what they will not, live, without a hand-kept copy.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.domains.feature_switches import public_state
from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability

pytestmark = pytest.mark.unit

MODULE = "src.domains.feature_switches.public_state"


class TestEveryCapabilityIsPublished:
    async def test_the_payload_names_every_registry_member_once(self) -> None:
        with patch(f"{MODULE}.disabled_capabilities", return_value=frozenset()):
            payload = await public_state.public_capability_states()
        assert set(payload) == {capability.value for capability in CAPABILITY_SPECS}

    async def test_each_entry_carries_its_family_from_the_spec(self) -> None:
        with patch(f"{MODULE}.disabled_capabilities", return_value=frozenset()):
            payload = await public_state.public_capability_states()
        for capability, spec in CAPABILITY_SPECS.items():
            assert payload[capability.value]["family"] == spec.family


class TestEnabledMeansEffective:
    """Ceiling AND switch — a reader is told what they will actually find."""

    async def test_a_capability_the_deployment_forbids_reads_off(self) -> None:
        with (
            patch(f"{MODULE}.deployment_allows", return_value=False),
            patch(f"{MODULE}.disabled_capabilities", return_value=frozenset()),
        ):
            payload = await public_state.public_capability_states()
        assert not any(entry["enabled"] for entry in payload.values())

    async def test_a_capability_the_operator_switched_off_reads_off(self) -> None:
        switched_off = frozenset({PlatformCapability.WORKBOARD})
        with (
            patch(f"{MODULE}.deployment_allows", return_value=True),
            patch(f"{MODULE}.disabled_capabilities", return_value=switched_off),
        ):
            payload = await public_state.public_capability_states()
        assert payload[PlatformCapability.WORKBOARD.value]["enabled"] is False
        assert payload[PlatformCapability.WEB_SEARCH.value]["enabled"] is True

    async def test_a_capability_allowed_on_both_sides_reads_on(self) -> None:
        with (
            patch(f"{MODULE}.deployment_allows", return_value=True),
            patch(f"{MODULE}.disabled_capabilities", return_value=frozenset()),
        ):
            payload = await public_state.public_capability_states()
        assert all(entry["enabled"] is True for entry in payload.values())

    async def test_the_switch_store_is_read_once_for_the_whole_payload(self) -> None:
        """One pass over the store, not one read per capability per request."""
        with (
            patch(f"{MODULE}.deployment_allows", return_value=True),
            patch(f"{MODULE}.disabled_capabilities", return_value=frozenset()) as reads,
        ):
            await public_state.public_capability_states()
        assert reads.await_count == 1


class TestThePayloadIsPlainData:
    async def test_values_are_json_scalars_only(self) -> None:
        with patch(f"{MODULE}.disabled_capabilities", return_value=frozenset()):
            payload = await public_state.public_capability_states()
        for entry in payload.values():
            assert set(entry) == {"enabled", "family"}
            assert isinstance(entry["enabled"], bool)
            assert isinstance(entry["family"], str) and entry["family"]
