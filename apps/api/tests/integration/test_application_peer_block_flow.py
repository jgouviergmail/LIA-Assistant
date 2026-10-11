"""Directional block proposals remain inert until actual HITL and replay is silent."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_peer_tools
from src.domains.peers.models import PeerConnection, canonical_pair
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay"])
async def test_block_confirmation_edit_and_replay(async_session, test_user, monkeypatch, scenario):
    monkeypatch.setattr(settings, "peers_enabled", True)
    owner = test_user.id
    peer = User(
        id=uuid4(), email=f"response-flow-{uuid4()}@example.com", full_name="Alice", is_active=True
    )
    async_session.add(peer)
    await async_session.flush()
    lo, hi = canonical_pair(owner, peer.id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=peer.id,
        status="accepted",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.commit()
    identity = pair.id
    notices = AsyncMock(return_value=None)
    monkeypatch.setattr("src.domains.peers.notifications.dispatch_peer_events", notices)

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "peer_block_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_peer_tools, "get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_peer_tools.update_lia_peer_block_tool.coroutine(
            request={"peer_id": str(peer.id), "blocked": True},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        assert (
            await async_session.scalar(
                select(PeerConnection.status).where(PeerConnection.id == identity)
            )
            == "accepted"
        )
        notices.assert_not_awaited()
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            notices.assert_not_awaited()
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {"intent": {"peer_id": str(peer.id), "blocked": False}},
                )
            )
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            invocation = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            }
            result = await draft_executor._execute_confirmed_draft(
                invocation,
                {"configurable": {"thread_id": "peer-block-flow"}},
                "peer-block-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                replay = await draft_executor._execute_confirmed_draft(
                    invocation,
                    {"configurable": {"thread_id": "peer-block-flow"}},
                    "peer-block-flow",
                    "fr",
                )
                assert replay.success and replay.result_data == result.result_data
        notices.assert_not_awaited()
        assert await async_session.scalar(
            select(PeerConnection.status).where(PeerConnection.id == identity)
        ) == ("accepted" if scenario == "edit" else "removed")
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == (0 if scenario == "edit" else 1)
        if changes:
            assert changes[0].metadata["change"]["resources"] == ["peers", "relations", "workboard"]
