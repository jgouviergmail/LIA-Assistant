"""Unavailable origin storage is a finite dependency failure, never a proposal."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.native_tool_preparation import prepare_native_tool
from src.domains.agents.application.recording_device_schemas import RecordingDeviceRequest
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


async def test_native_origin_dependency_failure_is_a_structured_refusal() -> None:
    @asynccontextmanager
    async def sessions() -> AsyncIterator[AsyncSession]:
        yield AsyncMock(spec=AsyncSession)

    async def prepare(
        db: AsyncSession, actor_id: UUID, request: RecordingDeviceRequest
    ) -> ApplicationActionDraftContent:
        raise RedisError("controlled unavailable origin")

    result = await prepare_native_tool(
        RecordingDeviceRequest(action="start"),
        make_tool_runtime(user_id=uuid4(), store=InMemoryStore()),
        name="control_lia_meeting_recording_tool",
        model=RecordingDeviceRequest,
        prepare=prepare,
        sessions=sessions,
    )
    assert not result.success and result.error is not None
    assert result.error_code == "DEPENDENCY_ERROR"
    assert not result.registry_updates
