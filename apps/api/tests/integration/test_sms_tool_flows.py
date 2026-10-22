"""Real tool decorators, source SQL, body continuation and context withdrawal in both modes."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.memory import InMemoryStore

from src.core.constants import EXTERNAL_CONTENT_OPEN_TAG
from src.domains.agents.context.manager import ToolContextManager
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.formatters.resolved_context import generate_html_for_resolved_context
from src.domains.agents.sms import snapshots
from src.domains.agents.sms.catalogue_manifests import SMS_AGENT_MANIFEST
from src.domains.agents.tools import sms_tools
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
from src.domains.sms import identity_resolution as facade
from src.domains.sms.identity import IdentityBook
from src.domains.sms.ingestion import SmsIngestionService
from tests.integration.test_sms_ingestion import authority, message

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("sms_identity_session")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
async def test_real_sms_tool_entry_projection_context_and_withdrawal(
    db_session, test_user, monkeypatch, mode
):
    actor = await authority(db_session, test_user)
    await SmsIngestionService(db_session).ingest(
        actor, [message(sender="Alice", body="Bonjour demain. " + "texte " * 1500)]
    )
    test_user.sms_preferences = {"assistant_enabled": True}
    await db_session.commit()

    @asynccontextmanager
    async def context():
        yield db_session

    async def directory(owner, *, cache_scope=None):
        return IdentityBook()

    monkeypatch.setattr(sms_tools, "get_db_context", context)
    monkeypatch.setattr(snapshots, "get_db_context", context)
    monkeypatch.setattr(facade, "load_identity_book", directory)
    store = InMemoryStore()
    thread = str(uuid4())
    runtime = ToolRuntime(
        state={"current_turn_id": 1},
        context=LiaRuntimeContext(
            user_id=test_user.id,
            thread_id=thread,
            conversation_id=thread,
            store=store,
            execution_mode=mode,
        ),
        config={"configurable": {"thread_id": thread}},
        stream_writer=lambda _: None,
        tool_call_id="sms-flow",
        store=store,
    )
    listing = sms_tools.list_sms_tool
    assert isinstance(listing, StructuredTool) and listing.coroutine is not None
    assert listing.name in SMS_AGENT_MANIFEST.tools
    first = await listing.coroutine(request={"sender": "Alice"}, runtime=runtime)
    assert isinstance(first, UnifiedToolOutput) and first.success
    row = first.structured_data["sms_messages"][0]
    assert row["sender"] == "Alice" and row["next_body_offset"] > 0
    manager = ToolContextManager()
    saved = await manager.get_list(test_user.id, thread, "sms_messages", store)
    assert saved and saved.items[0]["id"] == row["id"] and saved.items[0]["index"] == 1
    wrapper = ReactToolWrapper(listing)
    rendered = wrapper._process_result(first)
    assert EXTERNAL_CONTENT_OPEN_TAG in rendered and rendered.count(row["body"]) == 1
    html = generate_html_for_resolved_context(
        {"source_domain": "sms_messages", "items": saved.items}, user_language="en"
    )
    assert "/dashboard/sms?message=" + row["id"] in html
    getter = sms_tools.get_sms_tool
    assert isinstance(getter, StructuredTool) and getter.coroutine is not None
    continued = await getter.coroutine(
        request={"message_id": row["id"], "body_offset": row["next_body_offset"]}, runtime=runtime
    )
    assert isinstance(continued, UnifiedToolOutput) and continued.success
    assert continued.structured_data["sms_messages"][0]["body_offset"] == row["next_body_offset"]
    unchanged = await manager.get_list(test_user.id, thread, "sms_messages", store)
    assert (
        unchanged and unchanged.items[0]["body_offset"] == 0
    ), "A detail/body continuation must preserve the ordinal list"
    focused = await manager.get_current_item(test_user.id, thread, "sms_messages", store)
    assert focused and focused["body_offset"] == row["next_body_offset"]
    test_user.sms_preferences = {"assistant_enabled": False}
    await db_session.commit()
    assert await manager.get_list(test_user.id, thread, "sms_messages", store) is None
    denied = await getter.coroutine(request={"message_id": row["id"]}, runtime=runtime)
    assert (
        isinstance(denied, UnifiedToolOutput)
        and not denied.success
        and denied.error_code == "PERMISSION_DENIED"
    )
    assert not denied.registry_updates and not denied.structured_data
