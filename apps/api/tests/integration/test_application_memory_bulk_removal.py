"""Global erasure freezes the whole source set without sending facts to the model."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application import memory_pin as pin_operations
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.memory_bulk_schemas import MemoryBulkDeleteRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_memory_tools import delete_all_lia_memories_tool
from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "all",
        "keep",
        "empty",
        "usage",
        "corrected",
        "added",
        "pin_changed",
        "disabled",
        "late_disabled",
        "late_expired",
        "commit_unknown",
        "miscount",
    ],
)
async def test_bulk_erasure_confirms_exact_counts_all_history_and_preserves_foreign_data(
    async_session: AsyncSession,
    test_user: User,
    test_superuser: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    test_user.memory_enabled = False
    revision = test_user.extraction_revision
    identities = [uuid4() for _ in range(0 if scenario == "empty" else 205)]
    rows = [
        Memory(
            id=identity,
            user_id=owner,
            content=f"Private fact {index}",
            category="procedural" if index == 3 else "personal",
            importance=0.7,
            pinned=index < 3,
            invalidated_at=datetime.now(UTC) if index == 4 else None,
            char_count=16,
            emotional_weight=0,
            trigger_topic="",
            usage_nuance="",
        )
        for index, identity in enumerate(identities)
    ]
    foreign_id = uuid4()
    foreign = Memory(
        id=foreign_id,
        user_id=test_superuser.id,
        content="Foreign saved fact",
        category="personal",
        char_count=18,
    )
    async_session.add_all([*rows, foreign])
    await async_session.commit()

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
    provider = AsyncMock(side_effect=AssertionError("Bulk erasure cannot spend tokens"))
    with (
        installed_runtime_context(user_id=owner, language="fr", deps=object()),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.memories.service._generate_document_embedding", provider),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        output = await delete_all_lia_memories_tool.coroutine(
            selection=MemoryBulkDeleteRequest(preserve_pinned=scenario == "keep"),
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert output.success and output.metadata["requires_confirmation"]
        item = next(iter(output.registry_updates.values()))
        content = item.payload["content"]
        expected = content["before"]["memories_to_delete"]
        assert expected["selected_count"] == (
            0 if scenario == "empty" else 202 if scenario == "keep" else 205
        )
        assert expected["invalidated_count"] == int(scenario != "empty")
        assert "Private fact" not in str(content) and "Foreign saved fact" not in str(output)
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, owner, object())
        if scenario == "usage":
            await MemoryRepository(async_session).increment_usage([identities[-1]])
            await async_session.commit()
        elif scenario in {"corrected", "pin_changed"}:
            values = (
                {"content": "Changed after approval"}
                if scenario == "corrected"
                else {"pinned": True}
            )
            await async_session.execute(
                update(Memory).where(Memory.id == identities[-1]).values(**values)
            )
            await async_session.commit()
        elif scenario == "added":
            async_session.add(
                Memory(
                    user_id=owner,
                    content="Unconfirmed new fact",
                    category="personal",
                    char_count=20,
                )
            )
            await async_session.commit()
        elif scenario == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario in {
            "late_disabled",
            "late_expired",
            "commit_unknown",
            "miscount",
        }:
            source_delete, source_commit = (
                MemoryRepository.delete_all_for_user,
                async_session.commit,
            )

            async def lose_ack() -> None:
                await source_commit()
                monkeypatch.setattr(async_session, "commit", source_commit)
                raise SQLAlchemyError("simulated lost acknowledgement")

            async def intervene(
                repository: MemoryRepository, user_id, preserve_pinned: bool = False
            ) -> int:
                removed = await source_delete(repository, user_id, preserve_pinned)
                if scenario == "late_disabled":
                    monkeypatch.setattr(settings, "application_tools_enabled", False)
                elif scenario == "late_expired":
                    deadline = datetime.fromisoformat(content["expires_at"])
                    monkeypatch.setattr(
                        pin_operations, "datetime", SimpleNamespace(now=lambda zone: deadline)
                    )
                elif scenario == "commit_unknown":
                    monkeypatch.setattr(async_session, "commit", lose_ack)
                return 0 if scenario == "miscount" else removed

            monkeypatch.setattr(MemoryRepository, "delete_all_for_user", intervene)
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "memory-delete-all"}},
            "memory-delete-all",
            "fr",
        )
        success = scenario in {"all", "keep", "empty", "usage"}
        assert result.success is success
        owned_count = await async_session.scalar(
            select(func.count()).select_from(Memory).where(Memory.user_id == owner)
        )
        assert owned_count == (
            3
            if scenario == "keep"
            else (
                0
                if success or scenario == "commit_unknown"
                else 206 if scenario == "added" else 205
            )
        )
        assert await async_session.get(Memory, foreign_id) is not None
        await async_session.refresh(test_user)
        assert test_user.memory_enabled is False
        assert test_user.extraction_revision == revision + int(
            (success and scenario != "empty") or scenario == "commit_unknown"
        )
        if not success:
            assert (
                result.error
                == {
                    "corrected": "STALE_STATE",
                    "added": "STALE_STATE",
                    "pin_changed": "STALE_STATE",
                    "disabled": "CAPABILITY_DISABLED",
                    "late_disabled": "CAPABILITY_DISABLED",
                    "late_expired": "EXPIRED",
                    "commit_unknown": "COMPLETION_UNKNOWN",
                    "miscount": "STALE_STATE",
                }[scenario]
            )
        else:
            repeated = await draft_executor._execute_confirmed_draft(
                {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
                {"configurable": {"thread_id": "memory-delete-all"}},
                "memory-delete-all",
                "fr",
            )
            assert not repeated.success
        provider.assert_not_awaited()
