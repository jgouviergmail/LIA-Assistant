"""Conversation lifecycle cannot spend again or renew either platform allowance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import TypedDict
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.constants import INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
from src.core.conversation_execution import ExecutionKind, RunAdmission, RunEnd
from src.core.conversation_source import conversation_source_scope
from src.core.reservation_work import reservation_work_scope
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.services.semantic_pivot_service import translate_to_english
from src.domains.chat import service as tracking
from src.domains.chat.models import MessageTokenSummary, TokenUsageLog, UserStatistics
from src.domains.conversations.catalogue_schemas import ConversationCreateRequest
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.execution_repository import ConversationExecutionRepository
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.conversations.models import Conversation
from src.domains.conversations.reservation_repository import ConversationReservationRepository
from src.domains.system_settings import service as operator_settings
from src.domains.telephony.schemas import SelfCallRelay
from src.domains.usage_limits.instance_budget import InstanceBudgetService
from src.domains.usage_limits.models import InstanceDailyBudget, UserUsageLimit
from src.domains.usage_limits.service import UsageLimitService
from src.domains.voice_sessions.session import VoiceSession
from src.domains.voice_sessions.transcript import VoiceTranscript
from src.infrastructure import llm
from src.infrastructure.cache import llm_cache
from src.infrastructure.cache import redis as cache
from src.infrastructure.llm import token_capture
from src.infrastructure.scheduler import voice_relay, voice_session_closing
from tests.fixtures.chat_http import HttpHarness
from tests.fixtures.chat_http import http as http
from tests.fixtures.learning_sources import Sources
from tests.fixtures.learning_sources import sources as sources

pytestmark = pytest.mark.integration
_REAL_USAGE_CHECK = UsageLimitService.check_user_allowed
_PAID_EUR = Decimal("0.24")


class _Translation(TypedDict):
    query: str
    english: str


async def test_context_free_translation_cache_is_shared_only_inside_the_account(
    redis_client: Redis, sources: Sources, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real cached consumer has no semantic dependency on a discussion generation."""

    async def redis_connection() -> Redis:
        return redis_client

    provider = AsyncMock(
        side_effect=[AIMessage(content=text) for text in ("first", "second", "third")]
    )
    monkeypatch.setattr(llm_cache, "get_redis_cache", redis_connection)
    monkeypatch.setattr(llm, "get_llm", lambda _slot: SimpleNamespace(ainvoke=provider))

    async def translate(state: _Translation) -> dict[str, str]:
        return {"english": await translate_to_english(state["query"])}

    builder = StateGraph(_Translation, context_schema=LiaRuntimeContext)
    builder.add_node("translate", translate)
    builder.add_edge(START, "translate")
    builder.add_edge("translate", END)
    graph = builder.compile()
    target = sources.annex
    next_generation = replace(target, revision=target.revision + 1, runtime_id=uuid4())
    another_account = replace(target, owner_id=uuid4(), id=uuid4(), runtime_id=uuid4())
    query = f"Synthetic query {uuid4().hex}"
    for scope in (sources.main, target, next_generation):
        result = await graph.ainvoke(
            {"query": query, "english": ""},
            context=LiaRuntimeContext.for_conversation(target=scope),
        )
        assert result["english"] == "first"
    distinct = await graph.ainvoke(
        {"query": query, "english": ""},
        context=LiaRuntimeContext.for_conversation(target=another_account),
    )
    assert distinct["english"] == "second"
    different_query = await graph.ainvoke(
        {"query": query + " variant", "english": ""},
        context=LiaRuntimeContext.for_conversation(target=target),
    )
    assert different_query["english"] == "third"
    assert provider.await_count == 3


async def _remove_test_spend(engine: AsyncEngine, now: datetime) -> None:
    """Remove only the contribution this test wrote in the disposable ledger."""
    async with AsyncSession(engine) as db:
        await db.execute(
            update(InstanceDailyBudget)
            .where(InstanceDailyBudget.utc_day == now.date())
            .values(
                spent_cost_eur=InstanceDailyBudget.spent_cost_eur - _PAID_EUR,
                run_count=InstanceDailyBudget.run_count - 1,
            )
        )
        await db.commit()


@pytest.mark.parametrize("ceiling", ["account", "instance"])
async def test_creation_and_reset_cannot_bypass_either_ceiling(
    http: HttpHarness,
    async_engine: AsyncEngine,
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
    ceiling: str,
) -> None:
    """Restore real admission policy in the native HTTP harness before calling the route."""
    owner = http.admission.target.owner_id
    now = datetime.now(UTC)

    async def operator_ceiling() -> Decimal | None:
        return None

    monkeypatch.setattr(UsageLimitService, "check_user_allowed", staticmethod(_REAL_USAGE_CHECK))
    monkeypatch.setattr(operator_settings, "get_instance_daily_budget_eur", operator_ceiling)
    monkeypatch.setattr(cache, "_redis_cache", redis_client)
    monkeypatch.setattr(settings, "secondary_conversations_enabled", True)
    monkeypatch.setattr(settings, "usage_limits_enabled", ceiling == "account")
    monkeypatch.setattr(
        settings, "instance_daily_budget_eur", _PAID_EUR if ceiling == "instance" else None
    )
    async with AsyncSession(async_engine, expire_on_commit=False) as db:
        assert await ConversationExecutionRepository(db).close_owned(
            http.admission, end=RunEnd.NORMAL
        )
        if ceiling == "account":
            db.add(UserUsageLimit(user_id=owner, is_usage_blocked=True))
        else:
            await InstanceBudgetService.record_spend(db, cost_eur=_PAID_EUR, now=now)
        await db.commit()

    try:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            catalogue = ConversationCatalogueService(db)
            main = await catalogue.ensure_primary(owner)
            await db.commit()
            created = await catalogue.create_secondary(
                owner,
                ConversationCreateRequest(title="New eligible generation", request_id=uuid4()),
            )
            annex = created.conversation
            reset = await ConversationLifecycle(db).request_reset(
                owner, annex.id, operation_id=uuid4(), expected_revision=annex.revision
            )
        assert reset.new_revision == annex.revision + 1
        for identity, revision in (
            (main.id, main.revision),
            (annex.id, reset.new_revision),
            (http.admission.target.id, http.admission.target.revision),
        ):
            response = await http.client.post(
                "/agents/chat/stream",
                json={
                    **http.payload(),
                    "conversation_id": str(identity),
                    "conversation_revision": revision,
                },
            )
            assert response.status_code == 429, response.text
            assert response.headers["content-type"].startswith("application/json")
            if ceiling == "instance":
                assert INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE in response.text
                assert int(response.headers["retry-after"]) > 0
        assert http.calls == []
    finally:
        if ceiling == "instance":
            await _remove_test_spend(async_engine, now)


@pytest.mark.parametrize("action", ["current", "reset", "delete"])
async def test_first_bill_preserves_the_ledgers_and_links_only_the_current_source(
    async_engine: AsyncEngine,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    """A billable extraction can return after its source is retired, before its first flush."""
    target = sources.annex
    run_id = uuid4().hex
    now = datetime.now(UTC)

    @asynccontextmanager
    async def connection() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    monkeypatch.setattr(tracking, "get_db_context", connection)
    monkeypatch.setattr(settings, "usage_limits_enabled", True)
    visible_during_invalidation: list[bool] = []

    async def invalidate(owner_id: UUID) -> None:
        assert owner_id == target.owner_id
        async with connection() as db:
            # A separate transaction can lock the source and see the bill
            # while the Redis invalidation is in progress.
            assert (
                await db.scalar(
                    select(Conversation.id)
                    .where(Conversation.id == target.id)
                    .with_for_update(nowait=True)
                )
                == target.id
            )
            visible_during_invalidation.append(
                await db.scalar(
                    select(MessageTokenSummary.id).where(MessageTokenSummary.run_id == run_id)
                )
                is not None
            )

    monkeypatch.setattr(UsageLimitService, "invalidate_cache_static", staticmethod(invalidate))
    committed = False
    try:
        with conversation_source_scope(target):
            bill = tracking.TrackingContext(
                run_id, target.owner_id, "paid-extraction", target.id, auto_commit=False
            )
        async with bill:
            await bill.record_node_tokens(
                "memory_extraction",
                "synthetic-billed-model",
                7,
                4,
                2,
                cost_eur=float(_PAID_EUR),
                cost_usd=float(_PAID_EUR),
                usd_to_eur_rate=Decimal(1),
            )
            if action != "current":
                async with connection() as db:
                    lifecycle = ConversationLifecycle(db)
                    retire = (
                        lifecycle.request_reset if action == "reset" else lifecycle.request_delete
                    )
                    await retire(
                        target.owner_id,
                        target.id,
                        operation_id=uuid4(),
                        expected_revision=target.revision,
                    )
            await bill.commit(strict=True)
            committed = True
            await bill.commit(strict=True)
        assert visible_during_invalidation == [True]
        async with connection() as db:
            summary = await db.scalar(
                select(MessageTokenSummary).where(MessageTokenSummary.run_id == run_id)
            )
            assert summary is not None and summary.billed_cost_eur == _PAID_EUR
            assert summary.conversation_id == (target.id if action == "current" else None)
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(TokenUsageLog)
                    .where(TokenUsageLog.run_id == run_id)
                )
                == 1
            )
            stats = await db.scalar(
                select(UserStatistics).where(UserStatistics.user_id == target.owner_id)
            )
            assert stats is not None and stats.total_cost_eur == _PAID_EUR
    finally:
        if committed:
            await _remove_test_spend(async_engine, now)


@pytest.mark.parametrize("provider_failed", [False, True])
async def test_a_direct_live_first_bill_reaches_its_annex_once(
    async_engine: AsyncEngine,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
    provider_failed: bool,
) -> None:
    """Both synthesis exits preserve the one known paid attempt in the selected discussion."""
    target = sources.annex
    session_id = uuid4().hex
    run_id = f"live_session_{session_id}"
    now = datetime.now(UTC)

    @asynccontextmanager
    async def connection() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    async def provider(*, config: RunnableConfig, **_kwargs: object) -> SelfCallRelay:
        callbacks = config["callbacks"]
        assert isinstance(callbacks, list)
        capture = next(
            item for item in callbacks if isinstance(item, token_capture.TokenCaptureHandler)
        )
        attempt = uuid4()
        capture.on_chat_model_start({}, [[]], run_id=attempt)
        response = AIMessage(
            content="Synthetic reply",
            usage_metadata={"input_tokens": 7, "output_tokens": 4, "total_tokens": 11},
        )
        capture.on_llm_end(
            LLMResult(generations=[[ChatGeneration(message=response)]]), run_id=attempt
        )
        if provider_failed:
            raise ValueError("Synthetic invalid structured reply")
        return SelfCallRelay(owner_confirmed=True, relay_message="Synthetic relay", summary="Recap")

    monkeypatch.setattr(tracking, "get_db_context", connection)
    monkeypatch.setattr(voice_relay, "get_llm", lambda _slot: object())
    monkeypatch.setattr(voice_relay, "get_structured_output_with_retry", provider)
    monkeypatch.setattr(
        token_capture,
        "get_cached_cost_usd_eur",
        lambda **_kwargs: (float(_PAID_EUR), float(_PAID_EUR)),
    )
    async with connection() as db:
        admission = await ConversationExecutionRepository(db).admit(
            target,
            run_id=run_id,
            stream_id=session_id,
            worker_id=uuid4(),
            kind=ExecutionKind.LIVE,
        )
        assert isinstance(admission, RunAdmission)
        work = await ConversationReservationRepository(db).begin_closing(
            admission, worker_id=uuid4()
        )
    session = VoiceSession.browser(
        session_id=session_id,
        run_id=run_id,
        mode="direct",
        user_id=target.owner_id,
        conversation_id=target.id,
        language="en",
        timezone="UTC",
        reservation=work,
    )
    committed = False
    try:
        with reservation_work_scope(work):
            fate, _ = await voice_session_closing._synthesize_direct(
                session, VoiceTranscript.from_rows([("user", "Synthetic request")])
            )
        expected_fate = "failed" if provider_failed else "scheduled"
        assert fate == expected_fate
        async with connection() as db:
            summary = await db.scalar(
                select(MessageTokenSummary).where(MessageTokenSummary.run_id == run_id)
            )
            assert summary is not None
            committed = True
            assert summary.conversation_id == target.id
            assert summary.billed_cost_eur == _PAID_EUR
            count = await db.scalar(
                select(func.count())
                .select_from(TokenUsageLog)
                .where(TokenUsageLog.run_id == run_id)
            )
            assert count == 1
    finally:
        async with connection() as db:
            await ConversationReservationRepository(db).finish(work)
        if committed:
            await _remove_test_spend(async_engine, now)
