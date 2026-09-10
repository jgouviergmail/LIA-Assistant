"""Every feature a person experiences is switchable, and every switch governs (B7).

The admin panel offered twelve capabilities while the product shipped a
workboard, journals, habits, proactive notifications, peer connections, a
psychological profile, external channels, open loops, long-term memory,
interest tracking, relationship debriefs, delegated sub-agents and an ephemeral
Python sandbox — thirteen features an operator could neither see nor switch off.
That is the drift ADR-085's completeness asserts exist to close, pointed at the
switch registry itself.

Three properties this pins, and each has a matching boot assert or a wiring
test beside it:

- **the partition is COMPLETE**: every capability an operator switches names a
  deployment ceiling that exists, a settings key that exists, and a decided fate
  on the capability map;
- **a switch governs something**: agents it removes, a route that refuses, or a
  service chokepoint — a switch that governs nothing is a lie an operator acts
  on;
- **a switch removes the ABILITY, never the RECORD.** Uploads are the worked
  example (ADR-279): switching them off must not close reading and deleting the
  files LIA already produced.
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.domains.feature_switches.registry import (
    CAPABILITY_SPECS,
    PlatformCapability,
)
from src.domains.system_settings.models import SystemSettingKey

pytestmark = pytest.mark.unit

#: What the product ships and an operator must be able to switch. Named here
#: rather than derived: the point is to compare the registry against a list a
#: PERSON maintains, so a feature that ships without a switch fails loudly.
EXPECTED_CAPABILITIES: frozenset[str] = frozenset(
    {
        # The original twelve.
        "stt",
        "tts",
        "image_generation",
        "document_generation",
        "attachments",
        "rag_spaces",
        "web_search",
        "browser",
        "skills",
        "mcp",
        "telephony",
        "meetings",
        # B7 — thirteen features that shipped without a switch.
        "workboard",
        "journals",
        "habits",
        "heartbeat",
        "peers",
        "psyche",
        "channels",
        "open_loops",
        "memory",
        "interests",
        "relation_debrief",
        "sub_agents",
        "python_sandbox",
    }
)


class TestThePartitionIsComplete:
    def test_every_shipped_feature_has_a_switch(self) -> None:
        declared = {capability.value for capability in PlatformCapability}
        missing = EXPECTED_CAPABILITIES - declared
        assert not missing, f"features with no admin switch: {sorted(missing)}"

    def test_no_switch_exists_for_a_feature_nobody_declared(self) -> None:
        # The other direction: a capability added here without being added to
        # the expectation above is a switch nobody decided to ship.
        declared = {capability.value for capability in PlatformCapability}
        extra = declared - EXPECTED_CAPABILITIES
        assert not extra, f"switches nobody declared: {sorted(extra)}"

    def test_every_capability_has_a_spec(self) -> None:
        assert set(CAPABILITY_SPECS) == set(PlatformCapability)


class TestEverySpecPointsAtSomethingReal:
    @pytest.mark.parametrize("capability", sorted(PlatformCapability, key=lambda c: c.value))
    def test_the_deployment_ceiling_exists(self, capability: PlatformCapability) -> None:
        # The env flag is the ceiling the switch acts inside. A misspelled
        # attribute would read as False and switch the feature off for good.
        spec = CAPABILITY_SPECS[capability]
        assert hasattr(settings, spec.env_flag), f"{capability.value}: no settings.{spec.env_flag}"

    @pytest.mark.parametrize("capability", sorted(PlatformCapability, key=lambda c: c.value))
    def test_the_settings_key_exists(self, capability: PlatformCapability) -> None:
        spec = CAPABILITY_SPECS[capability]
        assert spec.setting_key in SystemSettingKey

    @pytest.mark.parametrize("capability", sorted(PlatformCapability, key=lambda c: c.value))
    def test_the_settings_key_is_named_after_its_capability(
        self, capability: PlatformCapability
    ) -> None:
        # A key naming another capability would let an operator switch one
        # feature and turn another off.
        spec = CAPABILITY_SPECS[capability]
        assert spec.setting_key.value == f"capability_{capability.value}_enabled"


class TestASwitchThatGovernsNothingIsALie:
    @pytest.mark.parametrize("capability", sorted(PlatformCapability, key=lambda c: c.value))
    def test_every_switch_governs_agents_a_route_or_a_service(
        self, capability: PlatformCapability
    ) -> None:
        spec = CAPABILITY_SPECS[capability]
        governs = bool(spec.agents) or spec.route_enforced or spec.service_enforced
        assert governs, (
            f"{capability.value} declares no agents, no route and no service "
            "chokepoint — an operator would switch it and change nothing."
        )


class TestTheLabelsAreResolvable:
    @pytest.mark.parametrize("capability", sorted(PlatformCapability, key=lambda c: c.value))
    def test_each_label_key_follows_the_convention(self, capability: PlatformCapability) -> None:
        # The frontend resolves this key; a bespoke one would surface as a raw
        # identifier in six languages.
        spec = CAPABILITY_SPECS[capability]
        assert spec.label_key == f"capabilities.items.{capability.value}"
