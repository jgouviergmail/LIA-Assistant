"""Real graph checkpoints and tracing never carry the session bearer credential."""

import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.load import dumps
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.context.runtime_context_builder import build_runtime_context
from src.domains.agents.models import MessagesState
from src.infrastructure.application_sessions import bind_browser_session

pytestmark = pytest.mark.unit


async def test_live_transport_reader_is_private_and_never_checkpointed() -> None:
    actor = uuid4()
    cookie = "PRIVATE-COOKIE-NOT-FOR-THE-MODEL"
    redis = AsyncMock()
    redis.get.return_value = json.dumps(
        {
            "user_id": str(actor),
            "created_at": datetime.now(UTC).isoformat(),
            "step_up_at": datetime.now(UTC).isoformat(),
        }
    )
    origin = bind_browser_session(actor, cookie)
    assert origin is not None
    context = build_runtime_context(
        state={"messages": []}, user_id=actor, conversation_id=uuid4(), application_origin=origin
    )
    assert (
        cookie not in repr(origin) and cookie not in dumps(origin) and cookie not in dumps(context)
    )
    seen: list[LiaRuntimeContext] = []

    async def observe(
        state: MessagesState, runtime: Runtime[LiaRuntimeContext]
    ) -> dict[str, list[AIMessage]]:
        seen.append(runtime.context)
        proof = runtime.context.application_origin
        assert proof is origin
        facts = await proof.require_session(
            actor, expected_binding=origin.binding_id, recent_step_up=True
        )
        assert facts.user_id == actor
        return {"messages": [AIMessage(content="Observed current session without a credential.")]}

    graph = StateGraph(MessagesState, context_schema=LiaRuntimeContext)
    graph.add_node("observe", observe)
    graph.add_edge(START, "observe")
    graph.add_edge("observe", END)
    compiled = graph.compile(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": str(context.conversation_id)}}
    with patch(
        "src.infrastructure.application_sessions.get_redis_session", AsyncMock(return_value=redis)
    ):
        result = await compiled.ainvoke(
            {"messages": [HumanMessage(content="Read current session")]}, config, context=context
        )
    assert seen == [context]
    assert "application_origin" not in result and cookie not in repr(result)
    async for checkpoint in compiled.aget_state_history(config):
        assert cookie not in repr(checkpoint) and "application_origin" not in checkpoint.values


def test_missing_transport_and_foreign_context_cannot_create_session_authority() -> None:
    actor = uuid4()
    assert bind_browser_session(actor, None) is None
    origin = bind_browser_session(actor, "private")
    context = build_runtime_context(
        state={"messages": []}, user_id=uuid4(), conversation_id=uuid4(), application_origin=origin
    )
    assert context.application_origin is None


def test_every_authenticated_http_chat_call_forwards_the_transport_origin() -> None:
    tree = ast.parse(Path("src/domains/agents/api/router.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "stream_chat_response"
    ]
    assert len(calls) >= 2
    for call in calls:
        forwarded = next(
            (item.value for item in call.keywords if item.arg == "application_origin"), None
        )
        assert isinstance(forwarded, ast.Name) and forwarded.id == "application_origin"
    factories = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "bind_browser_recording_session"
    ]
    assert len(factories) == 1
    assert ast.unparse(factories[0].args[0]) == "current_user.id"
    assert ast.unparse(factories[0].args[1]) == "bff_session_id"
    keywords = {item.arg: ast.unparse(item.value) for item in factories[0].keywords}
    assert keywords["recording_snapshot"] == "request.recording_device"
