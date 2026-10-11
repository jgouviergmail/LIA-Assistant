"""Explicit erasure needs exact confirmation and fences older automatic extraction."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application import memory_pin as pin_operations
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.memory_removal_schemas import MemoryDeleteRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_memory_tools import delete_lia_memory_tool
from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.memories.service import MemoryService
from src.domains.users.extraction_consent import ExtractionKind, snapshot_extraction_consent
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "normal",
        "procedural",
        "usage",
        "corrected",
        "invalidated",
        "disabled",
        "late_disabled",
        "late_expired",
        "commit_unknown",
    ],
)
async def test_delete_is_exact_single_use_and_cannot_be_undone_by_old_extraction(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner, identity, survivor = test_user.id, uuid4(), uuid4()
    test_user.memory_enabled = True
    revision = test_user.extraction_revision
    for identifier in [identity, survivor]:
        async_session.add(
            Memory(
                id=identifier,
                user_id=owner,
                content="Owned fact",
                category="procedural" if scenario == "procedural" else "personal",
                importance=0.8,
                pinned=True,
                emotional_weight=0,
                trigger_topic="",
                usage_nuance="",
                char_count=10,
            )
        )
    await async_session.commit()
    assert (
        await snapshot_extraction_consent(
            async_session, owner, ExtractionKind.MEMORY, expected_revision=revision
        )
        == revision
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise

    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    provider = AsyncMock(side_effect=AssertionError("Erasure cannot spend embedding tokens"))
    with (
        installed_runtime_context(user_id=owner, language="fr", deps=object()),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.memories.service._generate_document_embedding", provider),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        output = await delete_lia_memory_tool.coroutine(
            selection=MemoryDeleteRequest(memory_id=identity),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert output.success and output.metadata["requires_confirmation"]
        item = next(iter(output.registry_updates.values()))
        content = item.payload["content"]
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, owner, object())
        assert await async_session.get(Memory, identity) is not None
        if scenario == "usage":
            await MemoryRepository(async_session).increment_usage([identity])
            await async_session.commit()
        elif scenario in {"corrected", "invalidated"}:
            values = (
                {"content": "Concurrent correction"}
                if scenario == "corrected"
                else {"invalidated_at": datetime.now(UTC)}
            )
            await async_session.execute(
                update(Memory).where(Memory.id == identity).values(**values)
            )
            await async_session.commit()
        elif scenario == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario in {"late_disabled", "late_expired", "commit_unknown"}:
            source_delete, source_commit = MemoryService.delete_memory, async_session.commit

            async def lose_ack() -> None:
                await source_commit()
                monkeypatch.setattr(async_session, "commit", source_commit)
                raise SQLAlchemyError("simulated lost acknowledgement")

            async def intervene(service: MemoryService, memory: Memory) -> None:
                await source_delete(service, memory)
                if scenario == "late_disabled":
                    monkeypatch.setattr(settings, "application_tools_enabled", False)
                elif scenario == "late_expired":
                    deadline = datetime.fromisoformat(content["expires_at"])
                    monkeypatch.setattr(
                        pin_operations, "datetime", SimpleNamespace(now=lambda zone: deadline)
                    )
                else:
                    monkeypatch.setattr(async_session, "commit", lose_ack)

            monkeypatch.setattr(MemoryService, "delete_memory", intervene)
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "memory-delete"}},
            "memory-delete",
            "fr",
        )
        success = scenario in {"normal", "procedural", "usage"}
        assert result.success is success
        assert (
            await async_session.scalar(select(Memory.id).where(Memory.id == identity)) is None
        ) is (success or scenario == "commit_unknown")
        assert await async_session.get(Memory, survivor) is not None
        await async_session.refresh(test_user)
        assert test_user.memory_enabled is True and test_user.extraction_revision == revision + int(
            success or scenario == "commit_unknown"
        )
        if success:
            assert (
                await snapshot_extraction_consent(
                    async_session, owner, ExtractionKind.MEMORY, expected_revision=revision
                )
                is None
            )
            repeated = await draft_executor._execute_confirmed_draft(
                {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
                {"configurable": {"thread_id": "memory-delete"}},
                "memory-delete",
                "fr",
            )
            assert not repeated.success
        else:
            assert (
                result.error
                == {
                    "corrected": "STALE_STATE",
                    "invalidated": "STALE_STATE",
                    "disabled": "CAPABILITY_DISABLED",
                    "late_disabled": "CAPABILITY_DISABLED",
                    "late_expired": "EXPIRED",
                    "commit_unknown": "COMPLETION_UNKNOWN",
                }[scenario]
            )
        provider.assert_not_awaited()


@pytest.mark.parametrize("target", ["unknown", "foreign", "invalidated"])
async def test_selection_cannot_probe_or_delete_an_unavailable_fact(
    async_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    identity = uuid4()
    if target != "unknown":
        async_session.add(
            Memory(
                id=identity,
                user_id=test_superuser.id if target == "foreign" else test_user.id,
                content="Unavailable fact",
                category="personal",
                importance=0.7,
                pinned=False,
                invalidated_at=datetime.now(UTC) if target == "invalidated" else None,
                char_count=16,
            )
        )
        await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=test_user.id, language="fr"),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
    ):
        result = await delete_lia_memory_tool.coroutine(
            selection=MemoryDeleteRequest(memory_id=identity),
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
        assert not result.success and result.error_code == "NOT_FOUND"
        assert not result.registry_updates
