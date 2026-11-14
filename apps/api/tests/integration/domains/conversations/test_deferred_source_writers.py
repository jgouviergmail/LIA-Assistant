"""Actual delayed record writers reject retired sources while keeping reported spend."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.run_authority import run_authority_scope
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.services import open_loop_extractor
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.open_loops.models import OpenLoop
from src.domains.psyche.models import PsycheHistory
from src.domains.psyche.post_response import psyche_post_response_background
from src.domains.users.models import User
from src.infrastructure.llm.token_capture import TokenCaptureHandler
from tests.fixtures.learning_sources import Sources, source_authority
from tests.fixtures.learning_sources import sources as sources
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("change", ["none", "source_reset", "other_reset", "consent"])
async def test_open_loop_paid_result_keeps_cost_but_rechecks_source_before_writing(
    async_engine: AsyncEngine, sources: Sources, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    target = sources.annex

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    capture = TokenCaptureHandler("offline-model")

    async def model(**kwargs: object) -> open_loop_extractor.OpenLoopExtraction:
        capture.on_llm_end(
            LLMResult(
                generations=[
                    [
                        ChatGeneration(
                            message=AIMessage(
                                content="Fictional extraction",
                                usage_metadata={
                                    "input_tokens": 11,
                                    "output_tokens": 7,
                                    "total_tokens": 18,
                                },
                            )
                        )
                    ]
                ]
            ),
            run_id=uuid4(),
        )
        async with AsyncSession(async_engine) as db:
            if change == "consent":
                await db.execute(
                    update(User).where(User.id == target.owner_id).values(extraction_revision=1)
                )
                await db.commit()
            elif change in {"source_reset", "other_reset"}:
                reset = target if change == "source_reset" else sources.main
                await ConversationLifecycle(db).request_reset(
                    reset.owner_id, reset.id, operation_id=uuid4(), expected_revision=0
                )
        return open_loop_extractor.OpenLoopExtraction(
            items=[open_loop_extractor.OpenLoopItem(action="open", subject="Fictional obligation")]
        )

    paid = AsyncMock()
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr("src.domains.psyche.post_response.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.llm.get_llm", lambda _: FakeListChatModel(responses=[]))
    monkeypatch.setattr(open_loop_extractor, "TokenCaptureHandler", lambda _: capture)
    monkeypatch.setattr("src.infrastructure.llm.structured_output.get_structured_output", model)
    monkeypatch.setattr("src.infrastructure.proactive.tracking.track_proactive_tokens", paid)
    context = LiaRuntimeContext(
        user_id=target.owner_id,
        thread_id=str(target.runtime_id),
        conversation_id=str(target.id),
        extraction_revision=0,
    )
    with run_authority_scope(source_authority(target)), installed_runtime_context(context):
        with run_authority_scope(None):
            await open_loop_extractor._run_extraction(
                str(target.owner_id),
                [HumanMessage(content="A fictional obligation to remember")],
                str(target.id),
                str(uuid4()),
                zone=UTC,
            )
    paid.assert_awaited_once()
    assert paid.await_args is not None
    assert paid.await_args.kwargs["tokens_in"] == 11
    assert paid.await_args.kwargs["tokens_out"] == 7
    async with AsyncSession(async_engine) as db:
        count = await db.scalar(
            select(func.count()).select_from(OpenLoop).where(OpenLoop.user_id == target.owner_id)
        )
    assert count == int(change in {"none", "other_reset"})


@pytest.mark.parametrize("change", ["none", "source_reset", "other_reset", "consent"])
async def test_psyche_update_rechecks_its_original_source_and_account_consent(
    async_engine: AsyncEngine, sources: Sources, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    target = sources.annex

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    async with AsyncSession(async_engine) as db:
        if change == "consent":
            await db.execute(
                update(User)
                .where(User.id == target.owner_id)
                .values(psyche_enabled=False, extraction_revision=1)
            )
            await db.commit()
        elif change in {"source_reset", "other_reset"}:
            reset = target if change == "source_reset" else sources.main
            await ConversationLifecycle(db).request_reset(
                reset.owner_id, reset.id, operation_id=uuid4(), expected_revision=0
            )
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr("src.domains.psyche.post_response.get_db_context", session)
    context = LiaRuntimeContext(
        user_id=target.owner_id,
        thread_id=str(target.runtime_id),
        conversation_id=str(target.id),
        extraction_revision=0,
    )
    with run_authority_scope(source_authority(target)), installed_runtime_context(context):
        with run_authority_scope(None):
            await psyche_post_response_background(
                str(target.owner_id), None, str(uuid4()), extraction_revision=0
            )
    async with AsyncSession(async_engine) as db:
        count = await db.scalar(
            select(func.count())
            .select_from(PsycheHistory)
            .where(PsycheHistory.user_id == target.owner_id)
        )
    assert count == int(change in {"none", "other_reset"})
