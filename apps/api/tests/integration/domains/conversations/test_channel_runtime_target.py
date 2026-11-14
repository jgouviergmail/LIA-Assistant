"""The external channel reads current Main's generation, never a business-id Redis key."""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.conversation_execution import ConversationBusy, RunAdmission, RunEnd
from src.core.run_authority import current_run_authority
from src.core.stream_codes import HITL_DECISION_STALE_ERROR_CODE
from src.domains.agents.api import internal_admission, stream_gates
from src.domains.agents.api.channel_gateway import build_channel_gateway
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.api.service import AgentService
from src.domains.agents.utils import HITLStore
from src.domains.conversations.catalogue_service import (
    ConversationCatalogueService,
    conversation_ref,
)
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.models import Conversation
from src.infrastructure.channels.assistant_gateway import ChannelAgentRequest
from src.infrastructure.database import session as database
from src.infrastructure.streaming import run_admission

pytestmark = pytest.mark.integration


@pytest.fixture
def provider_calls(
    async_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> list[RunAdmission]:
    """Compose real SQL/Redis and replace only the paid graph body."""
    calls: list[RunAdmission] = []

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    async def allowed(owner: object) -> None:
        return None

    async def body(*args: object, **kwargs: object) -> AsyncGenerator[ChatStreamChunk]:
        authority = current_run_authority()
        assert authority is not None
        assert kwargs["target"] == authority.admission.target
        assert kwargs["run_id"] == authority.admission.run_id
        calls.append(authority.admission)
        yield ChatStreamChunk(type="token", content="A controlled channel response")
        yield ChatStreamChunk(type="done", content="")

    monkeypatch.setattr(database, "get_db_context", session)
    monkeypatch.setattr(internal_admission, "get_db_context", session)
    monkeypatch.setattr(stream_gates, "usage_limit_error_chunk", allowed)
    monkeypatch.setattr(stream_gates, "capture_location_fire_and_forget", lambda *_: None)
    monkeypatch.setattr(AgentService, "_stream_with_new_services", body)
    return calls


def _request(admission: RunAdmission, original: str | None) -> ChannelAgentRequest:
    return ChannelAgentRequest(
        user_message="A controlled answer",
        user_id=admission.target.owner_id,
        session_id="channel-test",
        user_timezone="UTC",
        user_language="en",
        user_memory_enabled=True,
        original_run_id=original,
        user_display_name=None,
        user_journals_enabled=True,
        user_psyche_enabled=True,
        hitl_decision=None,
    )


@pytest.mark.parametrize("stale", [False, True])
async def test_channel_pending_question_follows_rotated_main(
    reserved: RunAdmission,
    async_engine: AsyncEngine,
    provider_calls: list[RunAdmission],
    stale: bool,
) -> None:
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        await ConversationExecutionRepository(db).close_owned(reserved, end=RunEnd.NORMAL)
        row = await ConversationCatalogueService(db).ensure_primary_row(
            reserved.target.owner_id, "en"
        )
        target = replace(conversation_ref(row), revision=3, runtime_id=uuid4())
        await db.execute(
            update(Conversation)
            .where(Conversation.id == target.id)
            .values(
                revision=target.revision,
                runtime_id=target.runtime_id,
            )
        )
        await db.commit()
    async with run_admission.execution_for_turn(
        target.owner_id,
        target=target,
        admission=None,
        run_id="channel-question",
        language="en",
    ) as authority:
        redis = await run_admission.get_redis_cache()
        store = HITLStore(redis_client=redis, ttl_seconds=120)
        await store.save_interrupt(
            str(target.runtime_id),
            {
                "run_id": "channel-question",
                "action_requests": [{"type": "clarification"}],
            },
        )
    try:
        pending = await build_channel_gateway().pending(target.owner_id, str(target.id))
        assert pending is not None and pending["run_id"] == "channel-question"
        assert await build_channel_gateway().pending(uuid4(), str(target.id)) is None
        assert (
            await build_channel_gateway().pending(target.owner_id, str(reserved.target.id)) is None
        )
        original = "an-old-question" if stale else "channel-question"
        async with aclosing(build_channel_gateway().stream(_request(reserved, original))) as stream:
            chunks = [chunk async for chunk in stream]
        if stale:
            assert chunks[0].metadata == {"error_code": HITL_DECISION_STALE_ERROR_CODE}
            assert provider_calls == []
        else:
            assert [chunk.type for chunk in chunks] == ["token", "done"]
            assert len(provider_calls) == 1
            assert provider_calls[0].target == target
            assert provider_calls[0].run_id == "channel-question"
            assert provider_calls[0].activity_id != authority.admission.activity_id
        async with AsyncSession(async_engine) as db:
            assert (
                await ConversationExecutionRepository(db).active_for_owner(target.owner_id) is None
            )
    finally:
        await store.clear_interrupt_for_run(
            str(target.runtime_id),
            "channel-question",
            activity_id=authority.admission.activity_id,
        )


async def test_an_annex_prevents_a_channel_main_turn_before_any_provider(
    reserved: RunAdmission,
    provider_calls: list[RunAdmission],
) -> None:
    with pytest.raises(ConversationBusy):
        async with aclosing(build_channel_gateway().stream(_request(reserved, None))) as stream:
            await anext(stream)
    assert provider_calls == []
