"""The actual SMS graph uses its own slot and the existing model middleware."""

from unittest.mock import patch
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.display.jev_qualification import compatible_collection_item
from src.domains.agents.graphs.sms_agent_builder import build_sms_agent
from src.domains.shared.phone_domains import PHONE_DOMAINS
from tests.unit.domains.agents.graphs.test_base_agent_builder_invocation import (
    _captured_prompts,
    _CapturingChatModel,
)


@pytest.mark.asyncio
async def test_real_sms_agent_builds_and_invokes_its_own_slot_without_provider_calls():
    _captured_prompts.clear()
    with patch(
        "src.domains.agents.graphs.base_agent_builder.get_llm", return_value=_CapturingChatModel()
    ) as factory:
        agent = build_sms_agent()
    assert factory.call_args.args[0] == "sms_agent"
    result = await agent.ainvoke({"messages": [HumanMessage(content="Read my selected SMS")]})
    assert result["messages"][-1].content == "ok"
    assert _captured_prompts
    prompt = str(_captured_prompts[0][0].content)
    assert "sms_messages" in prompt and "EXTERNAL DATA" in prompt
    assert "{current_datetime}" not in prompt and "{context_instructions}" not in prompt
    _captured_prompts.clear()


def test_explicit_phone_sms_does_not_enable_collection_decision_calls():
    from src.domains.agents.telephony.live_specs import NATIVE_LOOKUPS

    assert "sms" in PHONE_DOMAINS
    sms_lookups = [spec for spec in NATIVE_LOOKUPS if spec.domain == "sms"]
    assert len(sms_lookups) == 1
    assert sms_lookups[0].name == "list_sms_tool" and sms_lookups[0].native
    item = RegistryItem(
        id="sms_" + uuid4().hex,
        type=RegistryItemType.SMS,
        payload={"body": "Personal SMS"},
        meta=RegistryItemMeta(source="phone_ingestion", domain="sms"),
    )
    assert not compatible_collection_item(item)
