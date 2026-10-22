"""The phone offers consented SMS reads and refuses stale/cross-owner output."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.sms.live_authority import SmsLiveAuthority
from src.domains.agents.sms.proof import SmsSnapshotProof
from src.domains.agents.telephony.sms_output import guard_sms_voice_output
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.shared.phone_domains import PHONE_DOMAINS

pytestmark = pytest.mark.unit


def test_sms_is_a_phone_domain():
    assert "sms" in PHONE_DOMAINS


@pytest.mark.parametrize("state", ["current", "withdrawn", "erased", "foreign", "malformed"])
async def test_voice_output_rechecks_live_authority(monkeypatch, state):
    import src.domains.agents.telephony.sms_output as source

    owner, identifier = uuid4(), uuid4()
    proof = SmsSnapshotProof(
        owner=uuid4() if state == "foreign" else owner, revision=2, ids=[identifier]
    )
    authority = (
        None
        if state == "withdrawn"
        else SmsLiveAuthority(
            owner=owner,
            revision=2,
            ids=frozenset() if state == "erased" else frozenset({identifier}),
        )
    )
    lookup = AsyncMock(return_value=authority)
    monkeypatch.setattr(source, "load_sms_authority", lookup)
    result = UnifiedToolOutput.data_success(
        message="SMS archive read.",
        structured_data={"sms_messages": [{"body_excerpt": "PRIVATE_VOICE_SMS"}]},
        metadata={"sms_snapshot": "{}" if state == "malformed" else proof.model_dump_json()},
    )
    guarded = await guard_sms_voice_output(result, owner)
    if state == "current":
        assert guarded is result
    else:
        assert not guarded.success and "PRIVATE_VOICE_SMS" not in str(guarded)
    if state in ("foreign", "malformed"):
        lookup.assert_not_awaited()


async def test_native_sms_offer_respects_domain_and_capability(monkeypatch):
    import src.domains.agents.telephony.live_tools as source

    monkeypatch.setattr(source.settings, "sms_enabled", True)
    monkeypatch.setattr(source, "_SPECS", source.NATIVE_LOOKUPS)
    monkeypatch.setattr(source, "get_global_registry", lambda: None)
    monkeypatch.setattr(source, "tools_hidden_by_capabilities", AsyncMock(return_value=set()))
    offered = await source.available_live_tools(
        feature_enabled=True, disabled_domains=frozenset({"sms"})
    )
    assert all(spec.domain != "sms" for spec in offered)
    monkeypatch.setattr(
        source, "tools_hidden_by_capabilities", AsyncMock(return_value={"list_sms_tool"})
    )
    assert all(
        spec.domain != "sms" for spec in await source.available_live_tools(feature_enabled=True)
    )
