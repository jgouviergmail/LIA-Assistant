"""Administrable platform capabilities: one declaration, two enforcement layers.

An operator must be able to turn off speech, images, documents or the browser
without a deployment — on the public demonstrator, but equally on a private
instance whose owner does not want to pay for image generation this month.

The rules that make such a switch trustworthy:

- **Two bounds, the smallest wins.** The environment flag is the DEPLOYMENT
  ceiling and the admin switch acts inside it. An operator can always turn a
  capability OFF; they can never turn on what the deployment forbids. Same
  doctrine as the spend ceiling (ADR-216), and the composition is a plain AND.
- **One declaration feeds everything.** The capability registry generates its
  own settings-store entries, so adding a capability cannot leave a key
  undeclared — the boot assert of the settings registry covers it for free.
- **A switch that governs nothing is a lie.** Every capability names the agents
  it disables; the boot checks those agents actually exist in the registry.
- **Reading never raises.** A capability check sits on the request path: any
  failure resolves to the environment value, which is the pre-existing
  behaviour, never to a surprise "on".

Note on vocabulary: ``PlatformCapability`` (here) is what an operator switches
on and off. ``DirectiveCapability`` (``agents/capability_directives.py``,
ADR-191) is what a CLIENT invokes by name. Different registries, different
lifetimes, deliberately different names.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.feature_switches.registry import (
    CAPABILITY_SPECS,
    PlatformCapability,
    assert_capability_agents_exist,
    disabled_capabilities,
    is_capability_enabled,
)
from src.domains.system_settings.models import SystemSettingKey
from src.domains.system_settings.registry import SETTING_SPECS

pytestmark = pytest.mark.unit


def _settings(**flags: bool) -> MagicMock:
    fake = MagicMock()
    for spec in CAPABILITY_SPECS.values():
        setattr(fake, spec.env_flag, flags.get(spec.env_flag, True))
    return fake


def _admin(**switches: bool) -> object:
    """Patch the admin-side read of every capability switch."""

    async def _read(key: SystemSettingKey) -> bool:
        return switches.get(key.value, True)

    return patch("src.domains.feature_switches.registry.read_setting", _read)


# ---------------------------------------------------------------------------
# Declaration integrity
# ---------------------------------------------------------------------------


def test_every_capability_is_declared_once() -> None:
    assert set(CAPABILITY_SPECS) == set(PlatformCapability)


def test_every_capability_owns_a_settings_key_that_the_store_knows() -> None:
    for capability, spec in CAPABILITY_SPECS.items():
        # Generated from this registry, so the settings-store boot assert
        # covers new capabilities without anyone remembering to add a spec.
        assert spec.setting_key in SETTING_SPECS, capability
        assert SETTING_SPECS[spec.setting_key].default is True


def test_capability_settings_default_to_enabled() -> None:
    # A switch nobody touched must not change today's behaviour: the
    # deployment flag alone decides.
    for spec in CAPABILITY_SPECS.values():
        assert SETTING_SPECS[spec.setting_key].default is True


def test_every_capability_names_a_deployment_flag() -> None:
    from src.core.config import settings

    for capability, spec in CAPABILITY_SPECS.items():
        # A capability whose flag does not exist would be permanently off
        # (getattr → False) or permanently on, depending on the default.
        assert hasattr(settings, spec.env_flag), f"{capability}: {spec.env_flag}"


def test_capabilities_declare_distinct_settings_keys() -> None:
    keys = [spec.setting_key for spec in CAPABILITY_SPECS.values()]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Composition: environment AND admin
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "admin", "expected"),
    [
        (True, True, True),
        (True, False, False),  # the operator turns it off
        (False, True, False),  # the deployment forbids it: admin cannot raise
        (False, False, False),
    ],
)
async def test_the_effective_state_is_the_logical_and(
    env: bool, admin: bool, expected: bool
) -> None:
    capability = PlatformCapability.IMAGE_GENERATION
    spec = CAPABILITY_SPECS[capability]
    with (
        patch("src.domains.feature_switches.registry.settings", _settings(**{spec.env_flag: env})),
        _admin(**{spec.setting_key.value: admin}),
    ):
        assert await is_capability_enabled(capability) is expected


async def test_a_disabled_deployment_flag_short_circuits_the_admin_read() -> None:
    capability = PlatformCapability.BROWSER
    spec = CAPABILITY_SPECS[capability]
    read = AsyncMock(return_value=True)
    with (
        patch(
            "src.domains.feature_switches.registry.settings", _settings(**{spec.env_flag: False})
        ),
        patch("src.domains.feature_switches.registry.read_setting", read),
    ):
        assert await is_capability_enabled(capability) is False
    # No point asking the store what an operator may not change anyway.
    read.assert_not_awaited()


async def test_a_failing_store_falls_back_to_the_deployment_value() -> None:
    capability = PlatformCapability.SKILLS
    spec = CAPABILITY_SPECS[capability]
    with (
        patch("src.domains.feature_switches.registry.settings", _settings(**{spec.env_flag: True})),
        patch(
            "src.domains.feature_switches.registry.read_setting",
            AsyncMock(side_effect=RuntimeError("store down")),
        ),
    ):
        # Pre-existing behaviour, never a surprise: a broken store must not
        # silently amputate the product.
        assert await is_capability_enabled(capability) is True


# ---------------------------------------------------------------------------
# Bulk read (request path)
# ---------------------------------------------------------------------------


async def test_disabled_capabilities_reports_exactly_what_is_off() -> None:
    off = {
        PlatformCapability.IMAGE_GENERATION: CAPABILITY_SPECS[PlatformCapability.IMAGE_GENERATION],
        PlatformCapability.BROWSER: CAPABILITY_SPECS[PlatformCapability.BROWSER],
    }
    with (
        patch(
            "src.domains.feature_switches.registry.settings",
            _settings(**{spec.env_flag: False for spec in off.values()}),
        ),
        _admin(),
    ):
        disabled = await disabled_capabilities()
    assert disabled == frozenset(off)


async def test_disabled_capabilities_is_empty_when_everything_is_on() -> None:
    with patch("src.domains.feature_switches.registry.settings", _settings()), _admin():
        assert await disabled_capabilities() == frozenset()


async def test_disabled_capabilities_never_raises() -> None:
    with (
        patch("src.domains.feature_switches.registry.settings", _settings()),
        patch(
            "src.domains.feature_switches.registry.read_setting",
            AsyncMock(side_effect=RuntimeError("store down")),
        ),
    ):
        # Degrading to "nothing disabled" keeps the product whole; the check
        # is a switch, not a security boundary (the routes enforce that).
        assert await disabled_capabilities() == frozenset()


# ---------------------------------------------------------------------------
# Completeness against the real agent registry (ADR-085)
# ---------------------------------------------------------------------------


def _registry_with(manifest_names: list[str]) -> MagicMock:
    """A registry whose CATALOGUE exposes exactly these agent manifests."""
    registry = MagicMock()
    # SimpleNamespace, not MagicMock: `name=` is consumed by MagicMock's own
    # constructor and never becomes an attribute.
    registry.list_agent_manifests.return_value = [
        SimpleNamespace(name=name) for name in manifest_names
    ]
    return registry


def test_the_boot_assert_rejects_a_capability_naming_an_unknown_agent() -> None:
    with patch("src.domains.feature_switches.registry.settings", _settings()):
        with pytest.raises(AssertionError, match="unknown agent"):
            assert_capability_agents_exist(_registry_with(["email_agent"]))


def test_the_boot_assert_passes_when_every_named_agent_exists() -> None:
    named = sorted({agent for spec in CAPABILITY_SPECS.values() for agent in spec.agents})
    with patch("src.domains.feature_switches.registry.settings", _settings()):
        assert_capability_agents_exist(_registry_with(named))


def test_a_capability_its_deployment_forbids_is_not_demanded_at_boot() -> None:
    # Telephony ships no manifest when its flag is off; demanding one would
    # fail the boot on a perfectly valid configuration (it is off by default).
    spec = CAPABILITY_SPECS[PlatformCapability.TELEPHONY]
    others = sorted(
        {
            agent
            for capability, other in CAPABILITY_SPECS.items()
            if capability is not PlatformCapability.TELEPHONY
            for agent in other.agents
        }
    )
    with patch(
        "src.domains.feature_switches.registry.settings", _settings(**{spec.env_flag: False})
    ):
        assert_capability_agents_exist(_registry_with(others))


def test_a_capability_without_agents_declares_where_it_IS_enforced() -> None:
    # Speech owns no catalogue entry. Recording is refused at the route layer;
    # synthesis has no route at all (it is produced inside the chat stream) and
    # is refused at the single voice-synthesis chokepoint. The spec states
    # which one, so a reader never has to guess — and the wiring test can
    # check the claim.
    stt = CAPABILITY_SPECS[PlatformCapability.STT]
    assert stt.agents == () and stt.route_enforced is True

    tts = CAPABILITY_SPECS[PlatformCapability.TTS]
    assert tts.agents == () and tts.service_enforced is True
    assert tts.route_enforced is False


def test_every_capability_is_enforced_somewhere() -> None:
    for capability, spec in CAPABILITY_SPECS.items():
        # A switch that filters no agent, guards no route and gates no service
        # would be a button that does nothing.
        assert spec.agents or spec.route_enforced or spec.service_enforced, capability
