"""Saved ordinal references fail closed as a whole, without shifting item numbers."""

from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.services.memory_extraction_context import format_messages_for_extraction


@pytest.mark.asyncio
async def test_registered_read_guard_protects_both_list_and_current(monkeypatch):
    monkeypatch.setattr(ContextTypeRegistry, "_registry", dict(ContextTypeRegistry._registry))
    permitted = True
    calls = []

    async def guard(owner, items):
        calls.append((owner, [item["id"] for item in items]))
        return permitted

    ContextTypeRegistry.register(
        ContextTypeDefinition(
            domain="sms_policy_test",
            agent_name="sms_agent",
            primary_id_field="id",
            display_name_field="sender",
            reference_fields=["sender"],
            read_guard=guard,
        )
    )
    store = InMemoryStore()
    manager = ToolContextManager()
    owner = str(uuid4())
    await manager.save_list(
        owner, "session", "sms_policy_test", [{"id": "one", "sender": "Alice"}], {}, store
    )
    assert (await manager.get_list(owner, "session", "sms_policy_test", store)).items[0][
        "index"
    ] == 1
    assert (await manager.get_current_item(owner, "session", "sms_policy_test", store))[
        "id"
    ] == "one"
    permitted = False
    assert await manager.get_list(owner, "session", "sms_policy_test", store) is None
    assert await manager.get_current_item(owner, "session", "sms_policy_test", store) is None
    assert len(calls) == 4


def test_raw_sms_tool_body_is_not_implicit_memory_extraction_context():
    text = format_messages_for_extraction(
        [
            ToolMessage(content="private raw SMS", name="get_sms_tool", tool_call_id="call"),
            HumanMessage(content="Mon choix explicite"),
        ]
    )
    assert "private raw SMS" not in text and "Mon choix explicite" in text
