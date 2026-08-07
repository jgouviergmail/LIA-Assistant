"""Administering the capability switches.

The panel must never let an operator believe a switch took effect when it did
not. So the API reports three separate facts per capability: what the operator
set, what the deployment permits, and what the runtime actually enforces.

Everything else — audit trail, cache invalidation, codecs — is the generic
settings store's job (lot 1). This service adds the deployment ceiling and
nothing more, which is why these tests focus on that composition.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.feature_switches.admin_service import CapabilitySwitchAdminService
from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability
from src.domains.feature_switches.schemas import CapabilitySwitchUpdate

pytestmark = pytest.mark.unit


def _settings(**flags: bool) -> MagicMock:
    fake = MagicMock()
    for spec in CAPABILITY_SPECS.values():
        setattr(fake, spec.env_flag, flags.get(spec.env_flag, True))
    return fake


def _stored(value: bool | None) -> object:
    """Patch the generic store read: value plus the row it came from."""
    setting = MagicMock(updated_by=uuid4(), updated_at=None) if value is not None else None
    return patch(
        "src.domains.feature_switches.admin_service.read_setting_with_metadata",
        AsyncMock(return_value=(True if value is None else value, setting)),
    )


async def test_every_capability_is_listed() -> None:
    service = CapabilitySwitchAdminService(MagicMock())
    with patch("src.domains.feature_switches.registry.settings", _settings()), _stored(True):
        rows = await service.list_switches()

    assert {row.capability for row in rows} == {c.value for c in PlatformCapability}


async def test_a_switch_off_is_reported_as_not_effective() -> None:
    service = CapabilitySwitchAdminService(MagicMock())
    with patch("src.domains.feature_switches.registry.settings", _settings()), _stored(False):
        rows = {row.capability: row for row in await service.list_switches()}

    row = rows[PlatformCapability.BROWSER.value]
    assert row.switch_enabled is False
    assert row.deployment_available is True
    assert row.effective_enabled is False


async def test_a_deployment_ceiling_is_reported_even_with_the_switch_on() -> None:
    spec = CAPABILITY_SPECS[PlatformCapability.TELEPHONY]
    service = CapabilitySwitchAdminService(MagicMock())
    with (
        patch(
            "src.domains.feature_switches.registry.settings",
            _settings(**{spec.env_flag: False}),
        ),
        _stored(True),
    ):
        rows = {row.capability: row for row in await service.list_switches()}

    row = rows[PlatformCapability.TELEPHONY.value]
    # The operator's switch is on, and it still does not apply: showing only
    # `switch_enabled` would be a lie the panel tells its own administrator.
    assert row.switch_enabled is True
    assert row.deployment_available is False
    assert row.effective_enabled is False


async def test_an_untouched_switch_is_flagged_as_default() -> None:
    service = CapabilitySwitchAdminService(MagicMock())
    with patch("src.domains.feature_switches.registry.settings", _settings()), _stored(None):
        rows = await service.list_switches()

    assert all(row.is_default for row in rows)
    # Absent means enabled: an instance nobody administered behaves as before.
    assert all(row.switch_enabled for row in rows)


async def test_each_row_says_where_the_switch_is_enforced() -> None:
    service = CapabilitySwitchAdminService(MagicMock())
    with patch("src.domains.feature_switches.registry.settings", _settings()), _stored(True):
        rows = {row.capability: row for row in await service.list_switches()}

    # Catalogue-only (no route of its own), so the panel can explain what
    # switching it off actually does.
    assert rows[PlatformCapability.WEB_SEARCH.value].enforced_in_catalogue is True
    assert rows[PlatformCapability.WEB_SEARCH.value].enforced_on_routes is False
    # Route-enforced, no catalogue entry.
    assert rows[PlatformCapability.ATTACHMENTS.value].enforced_on_routes is True
    assert rows[PlatformCapability.ATTACHMENTS.value].enforced_in_catalogue is False
    # Speech synthesis: enforced at a service chokepoint, reported as such.
    assert rows[PlatformCapability.TTS.value].enforced_on_routes is True


async def test_flipping_a_switch_writes_through_the_generic_store() -> None:
    service = CapabilitySwitchAdminService(MagicMock())
    admin_id = uuid4()
    request = MagicMock()
    with (
        patch("src.domains.feature_switches.registry.settings", _settings()),
        _stored(False),
        patch(
            "src.domains.feature_switches.admin_service.write_setting", new_callable=AsyncMock
        ) as write,
    ):
        await service.set_switch(
            PlatformCapability.IMAGE_GENERATION,
            CapabilitySwitchUpdate(enabled=False, change_reason="too expensive"),
            admin_id,
            request,
        )

    write.assert_awaited_once()
    kwargs = write.await_args.kwargs
    # Audit and invalidation come free from the store; the action name carries
    # the capability so the trail is readable.
    assert kwargs["action"] == "capability_image_generation_changed"
    assert kwargs["admin_user_id"] == admin_id
    assert kwargs["change_reason"] == "too expensive"


async def test_the_response_reflects_the_new_state_not_the_request() -> None:
    service = CapabilitySwitchAdminService(MagicMock())
    spec = CAPABILITY_SPECS[PlatformCapability.MCP]
    with (
        patch(
            "src.domains.feature_switches.registry.settings",
            _settings(**{spec.env_flag: False}),
        ),
        _stored(True),
        patch("src.domains.feature_switches.admin_service.write_setting", new_callable=AsyncMock),
    ):
        row = await service.set_switch(
            PlatformCapability.MCP,
            CapabilitySwitchUpdate(enabled=True),
            uuid4(),
            MagicMock(),
        )

    # Asked for "on", deployment says no: the answer is honest about it.
    assert row.switch_enabled is True
    assert row.effective_enabled is False
