"""Incoming decisions require actual HITL, re-confirmation after edits and one replay receipt."""

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
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay"])
async def test_incoming_response_confirmation_and_replay(
    async_session, test_user, monkeypatch, scenario
):
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
        status="pending",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.commit()
    identity = pair.id
    notices = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.domains.agents.application.peer_response.dispatch_peer_events", notices
    )

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "peer_response_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_peer_tools, "get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_peer_tools.respond_lia_peer_request_tool.coroutine(
            request={"connection_id": str(identity), "accept": True},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        assert (
            await async_session.scalar(
                select(PeerConnection.status).where(PeerConnection.id == identity)
            )
            == "pending"
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
                    {"intent": {"connection_id": str(identity), "accept": False}},
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
                {"configurable": {"thread_id": "peer-response-flow"}},
                "peer-response-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                replay = await draft_executor._execute_confirmed_draft(
                    invocation,
                    {"configurable": {"thread_id": "peer-response-flow"}},
                    "peer-response-flow",
                    "fr",
                )
                assert replay.success and replay.result_data == result.result_data
        notices.assert_awaited_once()
        assert await async_session.scalar(
            select(PeerConnection.status).where(PeerConnection.id == identity)
        ) == ("declined" if scenario == "edit" else "accepted")
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["peers"]
