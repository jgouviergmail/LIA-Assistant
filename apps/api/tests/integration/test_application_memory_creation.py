"""Exact approval precedes paid work; source writes retain identity, authority and quota checks."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import UsageLimitExceededError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.memory_create_schemas import MemoryCreateConfiguration
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_memory_tools import create_lia_memory_tool
from src.domains.memories.models import Memory
from src.domains.users.models import User
from src.infrastructure.llm.embedding_context import get_embedding_context
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention", ["none", "procedural", "quota", "late_quota", "late_disabled", "commit_unknown"]
)
async def test_memory_creation_pays_only_after_hitl_and_rechecks_before_each_call_and_write(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor_id = test_user.id
    test_user.memory_enabled = False
    revision = test_user.extraction_revision
    await async_session.commit()
    calls: list[str] = []
    prior_context = get_embedding_context()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise

    async def budget(user_id: UUID, *, layer: str) -> None:
        assert user_id == actor_id
        if intervention == "quota" or (intervention == "late_quota" and calls):
            raise UsageLimitExceededError(limit_name="cycle_cost")

    async def provider(text: str) -> None:
        context = get_embedding_context()
        assert context is not None and context.user_id == str(actor_id)
        # NOWAIT in another transaction proves paid work does not hold the user lock.
        async with AsyncSession(bind=async_session.bind) as observer:
            observed = await observer.scalar(
                select(User.id).where(User.id == actor_id).with_for_update(nowait=True)
            )
            assert observed == actor_id
            await observer.rollback()
        calls.append(text)
        if intervention == "late_disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return None  # Source permits storage without semantic vectors on provider unavailability.

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    with (
        installed_runtime_context(user_id=actor_id, language="fr", deps=object()),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch(
            "src.domains.agents.application.memory_creation_embeddings.enforce_usage_limit", budget
        ),
        patch(
            "src.domains.agents.application.memory_creation_embeddings._generate_document_embedding",
            provider,
        ),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        output = await create_lia_memory_tool.coroutine(
            configuration=MemoryCreateConfiguration(
                content="Explicit owned fact",
                category="procedural" if intervention == "procedural" else "personal",
                importance=0.0,
                trigger_topic="topic",
            ),
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert output.success and output.metadata["requires_confirmation"] and not calls
        item = next(iter(output.registry_updates.values()))
        content = item.payload["content"]
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        assert not calls
        target = UUID(content["command_id"])
        assert await async_session.get(Memory, target) is None
        if intervention == "commit_unknown":
            source_commit, source_flush = async_session.commit, async_session.flush

            async def lose_ack() -> None:
                await source_commit()
                monkeypatch.setattr(async_session, "commit", source_commit)
                raise SQLAlchemyError("simulated lost commit acknowledgement")

            async def arm_after_write(*args: object, **kwargs: object) -> None:
                await source_flush()
                monkeypatch.setattr(async_session, "commit", lose_ack)
                monkeypatch.setattr(async_session, "flush", source_flush)

            monkeypatch.setattr(async_session, "flush", arm_after_write)
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "memory-create"}},
            "memory-create",
            "fr",
        )
        row = await async_session.scalar(
            select(Memory).where(Memory.id == target).execution_options(populate_existing=True)
        )
        success = intervention in {"none", "procedural"}
        stored = success or intervention == "commit_unknown"
        assert result.success is success and (row is not None) is stored
        assert len(calls) == (2 if stored else 0 if intervention == "quota" else 1)
        assert get_embedding_context() == prior_context
        if row is not None:
            assert (
                row.user_id == actor_id
                and row.importance == 0.0
                and row.pinned is (intervention == "procedural")
            )
            assert row.embedding is None and row.context_biometric is None
            await async_session.refresh(test_user)
            assert (
                test_user.memory_enabled is False and test_user.extraction_revision == revision + 1
            )
            if intervention == "commit_unknown":
                assert draft_refusal_code(result) == "COMPLETION_UNKNOWN"
            repeated = await draft_executor._execute_confirmed_draft(
                {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
                {"configurable": {"thread_id": "memory-create"}},
                "memory-create",
                "fr",
            )
            assert repeated.success is False and len(calls) == 2
        else:
            assert draft_refusal_code(result) == (
                "CAPABILITY_DISABLED" if intervention == "late_disabled" else "USAGE_LIMIT_EXCEEDED"
            )
