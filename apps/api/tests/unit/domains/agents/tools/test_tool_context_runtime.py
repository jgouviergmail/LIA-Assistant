"""Legacy and child tools publish only context their normal reader can find."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.tools import StructuredTool
from langgraph.store.memory import InMemoryStore

from src.core.conversation_target import ConversationKind, ConversationRef
from src.domains.agents.constants import CONTEXT_DOMAIN_EVENTS
from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    derive_sub_agent_context,
)
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.tools.calendar_context import resolve_calendar_id_from_context
from src.domains.agents.tools.calendar_tools import get_event_details_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.unit


def _context(*, child: bool) -> LiaRuntimeContext:
    target = ConversationRef(uuid4(), uuid4(), ConversationKind.SECONDARY, 2, uuid4())
    context = LiaRuntimeContext.for_conversation(target=target)
    return derive_sub_agent_context(context, thread_id="research-child") if child else context


@pytest.mark.parametrize("child", [False, True])
async def test_calendar_details_publish_only_readable_context(child: bool) -> None:
    """The real decorator and lookup agree, without orphan per-item writes."""
    context = _context(child=child)
    store = InMemoryStore()
    runtime = make_tool_runtime(context=context, store=store)
    item = RegistryItem(
        id="event_proof",
        type=RegistryItemType.EVENT,
        payload={"id": "proof", "summary": "Example", "calendar_id": "other-calendar"},
        meta=RegistryItemMeta(source="google_calendar"),
    )
    output = UnifiedToolOutput.data_success(message="One event", registry_updates={item.id: item})
    tool: object = get_event_details_tool
    assert isinstance(tool, StructuredTool) and tool.coroutine is not None
    with (
        installed_runtime_context(context),
        patch(
            "src.domains.agents.tools.calendar_tools._get_event_details_tool_instance.execute",
            AsyncMock(return_value=output),
        ),
    ):
        result = await tool.coroutine(event_id="proof", runtime=runtime)
        validated = validate_runtime_config(runtime, "calendar-proof")
        assert not isinstance(validated, UnifiedToolOutput)
        assert await resolve_calendar_id_from_context(validated, "proof") == "other-calendar"
    assert isinstance(result, UnifiedToolOutput) and result.success
    saved = await store.asearch((str(context.user_id),))
    assert {item.key for item in saved} == {"list", "current"}
    assert all(
        item.namespace[:4]
        == (str(context.user_id), str(context.runtime_id), "context", CONTEXT_DOMAIN_EVENTS)
        for item in saved
    )


async def test_an_explicit_child_cannot_open_a_second_delegation() -> None:
    """The depth guard is a typed refusal, before any new model work."""
    context = _context(child=True)
    runtime = make_tool_runtime(context=context, store=InMemoryStore())
    assert isinstance(delegate_to_sub_agent_tool, StructuredTool)
    assert delegate_to_sub_agent_tool.coroutine is not None
    result = await delegate_to_sub_agent_tool.coroutine(
        expertise="Research", instruction="Look up the fact", runtime=runtime
    )
    assert isinstance(result, UnifiedToolOutput) and not result.success
    assert result.error_code == "DEPTH_LIMIT_EXCEEDED"
