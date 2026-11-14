"""Business identity survives runtime rotation and synthetic child derivation."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from src.core.conversation_target import ConversationKind, ConversationRef
from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    derive_sub_agent_context,
)
from src.domains.agents.models import create_initial_state
from src.domains.agents.nodes.react_context import build_memory_profile_block
from src.domains.agents.services.response_context import fetch_user_rag_context
from src.domains.conversations.runtime_identity import checkpoint_config
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.unit


def test_rotated_runtime_never_replaces_business_identity() -> None:
    """A sub-agent inherits its real parent target, not a guessed UUID thread."""
    target = ConversationRef(uuid4(), uuid4(), ConversationKind.SECONDARY, 4, uuid4())
    parent = LiaRuntimeContext.for_conversation(target=target)
    child = derive_sub_agent_context(parent, thread_id="research-child")
    assert parent.thread_id == str(target.runtime_id)
    assert child.thread_id == "research-child"
    for context in (parent, child):
        assert context.conversation_id == str(target.id)
        assert context.runtime_id == target.runtime_id
        assert context.conversation_revision == 4
        assert context.user_id == target.owner_id


async def test_rag_embedding_cost_keeps_the_business_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shared retrieval service must never receive the runtime as its FK."""
    from src.core.config import settings

    target = ConversationRef(uuid4(), uuid4(), ConversationKind.SECONDARY, 4, uuid4())
    context = LiaRuntimeContext.for_conversation(target=target)
    retrieve = AsyncMock(return_value=None)
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    with (
        installed_runtime_context(context),
        patch("src.infrastructure.database.session.get_db_context"),
        patch("src.domains.rag_spaces.retrieval.retrieve_rag_context", retrieve),
    ):
        await fetch_user_rag_context(
            config=checkpoint_config(target), last_user_message="query", run_id="run"
        )
    retrieve.assert_awaited_once()
    assert retrieve.call_args.kwargs["user_id"] == target.owner_id
    assert retrieve.call_args.kwargs["conversation_id"] == str(target.id)
    assert retrieve.call_args.kwargs["session_id"] == str(target.runtime_id)


async def test_react_child_memory_uses_parent_provenance() -> None:
    """The child may use isolated working context without inventing a file/usage FK."""
    target = ConversationRef(uuid4(), uuid4(), ConversationKind.SECONDARY, 4, uuid4())
    context = derive_sub_agent_context(
        LiaRuntimeContext.for_conversation(target=target, memory_enabled=True),
        thread_id="research-child",
    )
    state = create_initial_state(target.owner_id, context.thread_id, "run")
    state["messages"] = [HumanMessage(content="ok")]
    profile = AsyncMock(return_value=("standing instruction", None, None))
    with (
        installed_runtime_context(context),
        patch("src.domains.agents.nodes.react_context.build_psychological_profile", profile),
    ):
        result = await build_memory_profile_block(
            state, {"configurable": {"thread_id": context.thread_id}}
        )
    assert result == "standing instruction"
    assert profile.call_args.kwargs["conversation_id"] == str(target.id)
    assert profile.call_args.kwargs["session_id"] == "research-child"
