"""Native pin binds exact HITL to fresh owned memory data and truthful completion."""

import asyncio
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
from src.domains.agents.application.memory_pin_schemas import MemoryPinRequest
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_memory_tools import set_lia_memory_pin_tool
from src.domains.memories.models import Memory
from src.domains.memories.repository import MemoryRepository
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    [
        "none",
        "unpin",
        "no_op",
        "usage_only",
        "corrected",
        "invalidated",
        "writer_off",
        "actor_off",
        "commit_unknown",
        "expired",
        "late_writer_off",
        "late_expired",
    ],
)
async def test_pin_requires_exact_hitl_and_never_announces_uncommitted_state(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    test_user.memory_enabled = False
    actor_id = test_user.id
    row = Memory(
        user_id=actor_id,
        content="Owned fact",
        category="personal",
        importance=0.7,
        pinned=intervention in {"no_op", "unpin"},
        char_count=10,
    )
    async_session.add(row)
    await async_session.commit()
    identity = row.id

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
    queue: asyncio.Queue[object] = asyncio.Queue()
    with (
        installed_runtime_context(
            user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
        ),
        patch("src.domains.agents.tools.application_memory_tools.get_db_context", session),
        patch("src.domains.agents.application.command_service.get_db_context", session),
        patch("src.domains.agents.application.draft_execution.get_db_context", session),
        patch("src.domains.agents.effects.runtime._LEDGER", ledger),
        patch.dict(draft_executor.EXECUTOR_REGISTRY),
    ):
        proposal = await set_lia_memory_pin_tool.coroutine(
            selection=MemoryPinRequest(memory_id=identity, pinned=intervention != "unpin"),
            runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        content = item.payload["content"]
        with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
            await execute_application_action_draft(content, actor_id, object())
        assert row.pinned is (intervention in {"no_op", "unpin"})
        if intervention == "usage_only":
            await MemoryRepository(async_session).increment_usage([identity])
            await async_session.commit()
        elif intervention in {"corrected", "invalidated"}:
            changes: dict[str, object] = (
                {"content": "Corrected fact"}
                if intervention == "corrected"
                else {"invalidated_at": datetime.now(UTC)}
            )
            await async_session.execute(
                update(Memory)
                .where(Memory.id == identity)
                .values(changes)
                .execution_options(synchronize_session=False)
            )
            await async_session.commit()
        elif intervention == "writer_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "actor_off":
            await async_session.execute(
                update(User)
                .where(User.id == actor_id)
                .values(is_active=False)
                .execution_options(synchronize_session=False)
            )
            await async_session.commit()
        elif intervention == "expired":
            expiry = datetime.fromisoformat(content["expires_at"])
            monkeypatch.setattr(
                "src.domains.agents.application.memory_pin.datetime",
                SimpleNamespace(now=lambda zone: expiry),
            )
        elif intervention == "commit_unknown":
            source_commit = async_session.commit

            async def lose_ack() -> None:
                await source_commit()
                monkeypatch.setattr(async_session, "commit", source_commit)
                raise SQLAlchemyError("simulated lost commit acknowledgement")

            # Arm after the command claim, when its source write flushes.
            source_flush = async_session.flush

            async def arm_after_flush(*args: object, **kwargs: object) -> None:
                await source_flush()
                monkeypatch.setattr(async_session, "commit", lose_ack)
                monkeypatch.setattr(async_session, "flush", source_flush)

            monkeypatch.setattr(async_session, "flush", arm_after_flush)
        elif intervention in {"late_writer_off", "late_expired"}:
            source_pin = pin_operations.set_locked_memory_pin

            async def withdraw_after_write(db: AsyncSession, memory: Memory, pinned: bool) -> None:
                await source_pin(db, memory, pinned)
                if intervention == "late_writer_off":
                    monkeypatch.setattr(settings, "application_tools_enabled", False)
                else:
                    expiry = datetime.fromisoformat(content["expires_at"])
                    monkeypatch.setattr(
                        pin_operations, "datetime", SimpleNamespace(now=lambda zone: expiry)
                    )

            monkeypatch.setattr(pin_operations, "set_locked_memory_pin", withdraw_after_write)
        draft_executor.register_executor("application_action", execute_application_action_draft)
        result = await draft_executor._execute_confirmed_draft(
            {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
            {"configurable": {"thread_id": "memory-pin"}},
            "memory-pin",
            "fr",
        )
        assert result.success is (intervention in {"none", "no_op", "unpin", "usage_only"})
        current = await async_session.scalar(
            select(Memory).where(Memory.id == identity).execution_options(populate_existing=True)
        )
        assert current is not None and current.pinned is (
            intervention in {"none", "no_op", "commit_unknown", "usage_only"}
        )
        if intervention not in {"none", "no_op", "unpin", "usage_only"}:
            assert (
                result.error
                == {
                    "corrected": "STALE_STATE",
                    "invalidated": "STALE_STATE",
                    "writer_off": "CAPABILITY_DISABLED",
                    "expired": "EXPIRED",
                    "commit_unknown": "COMPLETION_UNKNOWN",
                    "actor_off": "FORBIDDEN",
                    "late_writer_off": "CAPABILITY_DISABLED",
                    "late_expired": "EXPIRED",
                }[intervention]
            )
        assert "configuration_digest" not in str(result.result_data)
        events = [queue.get_nowait() for _ in range(queue.qsize())]
        changes = [event for event in events if event.type == "application_state_changed"]
        assert len(changes) == (1 if intervention in {"none", "unpin", "usage_only"} else 0)
        if intervention in {"none", "unpin", "commit_unknown"}:
            repeated = await draft_executor._execute_confirmed_draft(
                {"draft_id": item.id, "draft_type": "application_action", "draft_content": content},
                {"configurable": {"thread_id": "memory-pin"}},
                "memory-pin",
                "fr",
            )
            assert repeated.success is False
