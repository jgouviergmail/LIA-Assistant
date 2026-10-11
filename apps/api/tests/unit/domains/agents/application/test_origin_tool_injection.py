"""Actual LangChain calls carry only their injected transport authority, never model hints."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore

from src.domains.agents.context.runtime_context import tool_runtime_context
from src.infrastructure.application_sessions import bind_browser_session
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("family", ["session", "security"])
async def test_actual_tool_passes_its_own_origin_to_the_owned_reader(
    family: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.agents.tools import application_security_tools, application_session_tools
    from src.domains.auth.security_queries import AccountSecurityProjection, effective_auth_features
    from src.domains.auth.session_queries import DeviceSessionsProjection

    actor = uuid4()
    origin = bind_browser_session(actor, "COOKIE-SENTINEL-PRIVATE")
    runtime = make_tool_runtime(user_id=actor, application_origin=origin, store=InMemoryStore())
    context = tool_runtime_context(runtime)
    assert context is not None and context.application_origin is origin
    module = application_session_tools if family == "session" else application_security_tools
    reader_name = "read_session_settings" if family == "session" else "read_security_settings"
    projection = (
        DeviceSessionsProjection(sessions=[], total=0)
        if family == "session"
        else AccountSecurityProjection(features=effective_auth_features(), password_set=True)
    )
    reader = AsyncMock(return_value=projection)
    monkeypatch.setattr(module, reader_name, reader)

    @asynccontextmanager
    async def session() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(module, "get_db_context", session)
    tool = (
        module.get_lia_device_sessions_tool
        if family == "session"
        else module.get_lia_security_settings_tool
    )
    result = await tool.ainvoke({"runtime": runtime})
    assert result.success
    assert reader.await_args.kwargs["origin"] is origin
    assert "COOKIE-SENTINEL-PRIVATE" not in str(result.model_dump(mode="json"))
    schema = tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"query"}
