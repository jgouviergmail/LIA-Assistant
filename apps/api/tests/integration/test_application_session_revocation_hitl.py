"""The normal exact-HITL dispatcher protects original-session-bound revocation."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_repository import cancel_command, get_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    ["valid", "current", "gone", "cancel", "operator_off", "other_origin", "lost_ack"],
)
async def test_session_revocation_requires_exact_confirmation_and_original_live_origin(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    intervention: str,
) -> None:
    tools = import_module("src.domains.agents.tools.application_session_tools")
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    redis = await get_redis_session()
    store = SessionStore(redis)
    current = await store.create_session(str(test_user.id))
    target = current if intervention == "current" else await store.create_session(str(test_user.id))
    alternate = await store.create_session(str(test_user.id))
    origin = bind_browser_session(test_user.id, current.session_id)
    queue: asyncio.Queue[object] = asyncio.Queue()
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    monkeypatch.setattr(tools, "get_db_context", session)
    monkeypatch.setattr("src.domains.agents.application.command_service.get_db_context", session)
    monkeypatch.setattr("src.domains.agents.application.draft_execution.get_db_context", session)
    try:
        with installed_runtime_context(
            user_id=test_user.id, application_origin=origin, language="fr", side_channel_queue=queue
        ):
            proposal = await tools.revoke_lia_device_session_tool.coroutine(
                change={"display_id": target.display_id},
                runtime=make_tool_runtime(
                    user_id=test_user.id,
                    application_origin=origin,
                    language="fr",
                    store=InMemoryStore(),
                ),
            )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        assert await redis.exists(f"session:{target.session_id}")
        item = next(iter(proposal.registry_updates.values()))
        row = await get_command(
            async_session, UUID(item.payload["content"]["command_id"]), test_user.id
        )
        assert row is not None and row.origin_binding_encrypted is not None
        assert current.session_id not in str(item.payload) and target.session_id not in str(
            item.payload
        )
        if intervention == "cancel":
            assert await cancel_command(async_session, item.id, test_user.id)
        elif intervention == "operator_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "other_origin":
            origin = bind_browser_session(test_user.id, alternate.session_id)
        elif intervention == "gone":
            await store.delete_session(target.session_id)
        elif intervention == "lost_ack":
            from redis.exceptions import RedisError

            from src.domains.auth import session_commands

            actual = session_commands.revoke_selected_sessions

            async def lose_ack(*args, **kwargs):
                await actual(*args, **kwargs)
                raise RedisError("private-cookie provider-secret")

            monkeypatch.setattr(session_commands, "revoke_selected_sessions", lose_ack)
        with (
            installed_runtime_context(
                user_id=test_user.id,
                application_origin=origin,
                language="fr",
                deps=object(),
                side_channel_queue=queue,
            ),
            patch("src.domains.agents.effects.runtime._LEDGER", ledger),
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            outcome = await draft_executor._execute_confirmed_draft(
                {
                    "draft_id": item.id,
                    "draft_type": "application_action",
                    "draft_content": item.payload["content"],
                },
                {"configurable": {"thread_id": "session-revocation-hitl"}},
                "session-revocation-hitl",
                "fr",
            )
        successful = intervention in {"valid", "current", "gone"}
        assert outcome.success is successful
        removed = successful or intervention == "lost_ack"
        assert bool(await redis.exists(f"session:{target.session_id}")) is not removed
        assert await redis.exists(f"session:{alternate.session_id}")
        if not successful and intervention != "lost_ack":
            ledger.claim.assert_not_awaited()
        if intervention == "lost_ack":
            assert outcome.error == "COMPLETION_UNKNOWN"
            assert "private-cookie" not in str(outcome.to_agent_result())
            assert "provider-secret" not in str(outcome.to_agent_result())
        assert current.session_id not in str(outcome.to_agent_result())
        assert target.session_id not in str(outcome.to_agent_result())
        hints = [queue.get_nowait() for _ in range(queue.qsize())]
        hints = [event for event in hints if event.type == "application_state_changed"]
        assert len(hints) == int(intervention in {"valid", "current"})
        if hints:
            assert hints[0].metadata["change"]["resources"] == ["device_sessions"]
            assert hints[0].metadata["change"]["changed_fields"] == ["session_to_revoke"]
    finally:
        for session in (current, target, alternate):
            await store.delete_session(session.session_id)
