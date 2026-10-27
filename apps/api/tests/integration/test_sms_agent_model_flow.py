"""Actual LangChain tool node to fake model: SMS data must reach the domain reader."""

from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.graphs.sms_agent_builder import build_sms_agent
from src.domains.agents.registry import AgentRegistry
from src.domains.agents.sms.catalogue_manifests import SMS_AGENT_MANIFEST as SMS_AGENT_MANIFEST
from src.domains.sms.identity import IdentityBook
from src.domains.sms.ingestion import SmsIngestionService
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message
from tests.integration.test_sms_relations import sms_actor_session as sms_actor_session
from tests.unit.domains.agents.graphs.test_base_agent_builder_invocation import (
    _captured_prompts,
    _CapturingChatModel,
)

pytestmark = pytest.mark.integration


class SmsCallingModel(_CapturingChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        _captured_prompts.append(list(messages))
        reply = (
            AIMessage(content="ok")
            if any(isinstance(item, ToolMessage) for item in messages)
            else AIMessage(
                content="",
                tool_calls=[
                    {"id": "sms-call", "name": "list_sms_tool", "args": {"request": {"limit": 1}}}
                ],
            )
        )
        return ChatResult(generations=[ChatGeneration(message=reply)])


async def test_actual_sms_tool_node_supplies_literal_body_to_domain_model(
    sms_actor_session, monkeypatch
):
    db_session, test_user = sms_actor_session
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor, [message(sender="Alice", body="LITERAL_SMS_EVIDENCE_FOR_DOMAIN_MODEL")]
    )
    test_user.sms_preferences = {"assistant_enabled": True}
    await db_session.commit()

    @asynccontextmanager
    async def session():
        yield db_session

    async def book(_, *, cache_scope=None):
        return IdentityBook(complete=True)

    monkeypatch.setattr("src.domains.agents.tools.sms_tools.get_db_context", session)
    monkeypatch.setattr("src.domains.sms.identity_resolution.load_identity_book", book)
    context = LiaRuntimeContext(
        user_id=test_user.id,
        thread_id=str(uuid4()),
        conversation_id=str(uuid4()),
        store=InMemoryStore(),
    )
    _captured_prompts.clear()
    with (
        patch(
            "src.domains.agents.graphs.base_agent_builder.get_llm", return_value=SmsCallingModel()
        ),
        patch(
            "src.infrastructure.llm.providers.adapter.configured_api_key",
            return_value="test-only-inert-key",
        ) as configured_key,
        patch(
            "src.infrastructure.llm.middleware_config.init_chat_model",
            return_value=_CapturingChatModel(),
        ) as summarizer,
        patch(
            "src.domains.agents.registry.get_global_registry",
            return_value=AgentRegistry(store=context.store),
        ),
    ):
        agent = build_sms_agent()
    configured_key.assert_called_once_with("openai")
    summarizer.assert_called_once()
    await agent.ainvoke(
        {"messages": [HumanMessage(content="Read the last SMS")]},
        config={"configurable": {"thread_id": context.thread_id}},
        context=context,
    )
    assert len(_captured_prompts) == 2
    tool_messages = [item for item in _captured_prompts[-1] if isinstance(item, ToolMessage)]
    tool_text = "\n".join(str(item.content) for item in tool_messages)
    assert "configuration_error" not in tool_text
    assert "LITERAL_SMS_EVIDENCE_FOR_DOMAIN_MODEL" in tool_text
    _captured_prompts.clear()
