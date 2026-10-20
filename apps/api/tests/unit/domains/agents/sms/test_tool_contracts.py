"""One SMS vocabulary across tools, plans, agent slots, trust and source policy."""

import pytest
from pydantic import ValidationError

from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.domains.agents.sms.catalogue_manifests import (
    SMS_AGENT_MANIFEST,
    SMS_TOOL_MANIFESTS,
    SMS_TOOL_MODELS,
)
from src.domains.agents.sms.schemas import SmsGetRequest, SmsListRequest, SmsSearchRequest
from src.domains.agents.tools import sms_tools
from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability
from src.domains.llm_config.constants import LLM_DEFAULTS, LLM_TYPES_REGISTRY


@pytest.mark.parametrize("manifest", SMS_TOOL_MANIFESTS, ids=lambda value: value.name)
def test_manifest_and_bound_tool_use_same_schema_and_data(manifest):
    model = SMS_TOOL_MODELS[manifest.name]
    assert manifest.parameters[0].schema == model.model_json_schema()
    actual = getattr(sms_tools, manifest.name).tool_call_schema.model_json_schema()
    assert "runtime" not in actual["properties"]
    request = actual["properties"]["request"]
    definition = actual["$defs"][request["$ref"].split("/")[-1]]
    assert definition["properties"] == model.model_json_schema()["properties"]
    assert manifest.context_key == "sms_messages"
    assert manifest.permissions.data_classification == "SENSITIVE"
    assert manifest.execution_modes == frozenset({"pipeline", "react"})
    assert manifest.name in SMS_AGENT_MANIFEST.tools


@pytest.mark.parametrize(
    "model,payload",
    [
        (SmsListRequest, {"from_ts": "2026-10-19"}),
        (SmsListRequest, {"limit": 4}),
        (SmsListRequest, {"limit": True}),
        (SmsSearchRequest, {"query": ""}),
        (SmsGetRequest, {"message_id": "not-a-uuid"}),
        (SmsGetRequest, {"message_id": "00000000-0000-0000-0000-000000000001", "body_offset": -1}),
    ],
)
def test_tools_reject_ambiguous_or_unbounded_input(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_sms_agent_has_its_own_slot_and_exhaustive_source_mappings():
    assert DOMAIN_REGISTRY["sms"].result_key == "sms_messages"
    assert "sms_agent" in LLM_DEFAULTS and "sms_agent" in LLM_TYPES_REGISTRY
    assert "sms_agent" in CAPABILITY_SPECS[PlatformCapability.SMS].agents
