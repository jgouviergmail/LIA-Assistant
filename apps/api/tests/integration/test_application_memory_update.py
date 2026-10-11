"""Real source persistence and exact confirmation guard editing and its paid work."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import UsageLimitExceededError
from src.domains.agents.application import memory_pin as pin_operations
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.memory_update_schemas import (
    MemoryUpdateChanges,
    MemoryUpdateRequest,
)
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_memory_tools import update_lia_memory_tool
from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.memories.service import MemoryService
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "metadata",
        "no_op",
        "usage",
        "content",
        "quota",
        "corrected",
        "late_corrected",
        "disabled",
        "invalidated",
        "late_disabled",
        "late_expired",
        "commit_unknown",
    ],
)
async def test_update_confirms_then_preserves_fresh_owned_fact_and_source_write(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner, identity = test_user.id, uuid4()
    test_user.memory_enabled = False
    revision = test_user.extraction_revision
    async_session.add(
        Memory(
            id=identity,
            user_id=owner,
            content="Original fact",
            category="personal",
            emotional_weight=2,
            trigger_topic="topic",
            usage_nuance="Nuance",
            importance=0.8,
            pinned=True,
            char_count=13,
        )
    )
    await async_session.commit()
    calls: list[str] = []

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise

    async def budget(user_id: UUID, *, layer: str) -> None:
        assert user_id == owner
        if scenario == "quota":
            raise UsageLimitExceededError(limit_name="cycle_cost")

    async def provider(text: str) -> None:
        async with AsyncSession(bind=async_session.bind) as observer:
            assert (
                await observer.scalar(
                    select(User.id).where(User.id == owner).with_for_update(nowait=True)
                )
                == owner
            )
            await observer.rollback()
        calls.append(text)
        if scenario == "late_corrected" and len(calls) == 1:
            await async_session.execute(
                update(Memory).where(Memory.id == identity).values(content="Concurrent correction")
            )
            await async_session.commit()
        return None

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    with (
        installed_runtime_context(user_id=owner, language="fr", deps=object()),
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
        embedding_change = scenario in {"content", "quota", "late_corrected"}
        changes = (
            MemoryUpdateChanges(content="Revised fact")
            if embedding_change
            else MemoryUpdateChanges(importance=0.8 if scenario == "no_op" else 0.0)
        )
        output = await update_lia_memory_tool.coroutine(
            selection=MemoryUpdateRequest(memory_id=identity, changes=changes),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert output.success and output.metadata["requires_confirmation"] and not calls
        item = next(iter(output.registry_updates.values()))
        content = item.payload["content"]
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, owner, object())
        assert not calls
        if scenario == "usage":
            await MemoryRepository(async_session).increment_usage([identity])
            await async_session.commit()
        elif scenario == "corrected":
            await async_session.execute(
                update(Memory).where(Memory.id == identity).values(content="Concurrent correction")
            )
            await async_session.commit()
        elif scenario == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario == "invalidated":
            await async_session.execute(
                update(Memory)
                .where(Memory.id == identity)
                .values(invalidated_at=datetime.now().astimezone())
            )
            await async_session.commit()
        elif scenario in {"late_disabled", "late_expired", "commit_unknown"}:
            source_update, source_commit = (
                MemoryService.update_from_management,
                async_session.commit,
            )

            async def lose_ack() -> None:
                await source_commit()
                monkeypatch.setattr(async_session, "commit", source_commit)
                raise SQLAlchemyError("simulated lost acknowledgement")

            async def intervene(
                service: MemoryService, row: Memory, changes: MemoryUpdateChanges
            ) -> Memory:
                written = await source_update(service, row, changes)
                if scenario == "late_disabled":
                    monkeypatch.setattr(settings, "application_tools_enabled", False)
                elif scenario == "late_expired":
                    deadline = datetime.fromisoformat(content["expires_at"])
                    monkeypatch.setattr(
                        pin_operations, "datetime", SimpleNamespace(now=lambda zone: deadline)
                    )
                else:
                    monkeypatch.setattr(async_session, "commit", lose_ack)
                return written

            monkeypatch.setattr(MemoryService, "update_from_management", intervene)
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "memory-update"}},
            "memory-update",
            "fr",
        )
        success = scenario in {"metadata", "no_op", "usage", "content"}
        assert result.success is success
        row = await async_session.scalar(
            select(Memory).where(Memory.id == identity).execution_options(populate_existing=True)
        )
        assert row is not None and row.pinned is True and row.usage_nuance == "Nuance"
        assert row.content == (
            "Revised fact"
            if scenario == "content"
            else (
                "Concurrent correction"
                if scenario in {"corrected", "late_corrected"}
                else "Original fact"
            )
        )
        assert row.importance == (
            0.0 if scenario in {"metadata", "usage", "commit_unknown"} else 0.8
        )
        assert len(calls) == (2 if scenario in {"content", "late_corrected"} else 0)
        await async_session.refresh(test_user)
        assert test_user.memory_enabled is False
        assert test_user.extraction_revision == revision + (
            1 if (success and scenario != "no_op") or scenario == "commit_unknown" else 0
        )
        if not success:
            assert (
                result.error
                == {
                    "quota": "USAGE_LIMIT_EXCEEDED",
                    "corrected": "STALE_STATE",
                    "late_corrected": "STALE_STATE",
                    "disabled": "CAPABILITY_DISABLED",
                    "invalidated": "STALE_STATE",
                    "late_disabled": "CAPABILITY_DISABLED",
                    "late_expired": "EXPIRED",
                    "commit_unknown": "COMPLETION_UNKNOWN",
                }[scenario]
            )
        repeated = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "memory-update"}},
            "memory-update",
            "fr",
        )
        assert not repeated.success
