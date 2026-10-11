"""Real proposal/HITL/edit/replay executes one source copy and one delivery attempt."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_editing import rebuild_application_draft
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_peer_tools
from src.domains.peers.models import PeerConnectionStatus, PeerImageShare
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.peers.test_image_share_db import _connection, _image, _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("scenario", ["confirmed", "no_confirmation", "edit", "replay"])
async def test_image_share_hitl_replay(
    async_session, test_user, monkeypatch, tmp_path: Path, scenario
):
    monkeypatch.setattr(settings, "peers_enabled", True)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    owner = test_user.id
    peer = await _user(async_session, f"image-flow-{scenario}@example.com", "Alice")
    pair = await _connection(async_session, owner, peer.id, PeerConnectionStatus.ACCEPTED)
    image = await _image(async_session, tmp_path, owner)
    pair_id, image_id = pair.id, image.id
    await async_session.commit()
    deliver = AsyncMock(return_value=True)
    monkeypatch.setattr("src.domains.agents.application.peer_image.deliver_shared_image", deliver)

    @asynccontextmanager
    async def session():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "peer_image_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(application_peer_tools, "get_db_context", session)
    queue = asyncio.Queue()
    with installed_runtime_context(user_id=owner, deps=object(), side_channel_queue=queue):
        proposal = await application_peer_tools.share_lia_peer_image_tool.coroutine(
            request={
                "connection_id": str(pair_id),
                "attachment_id": str(image_id),
                "comment": "Bonjour",
            },
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        assert await async_session.scalar(select(func.count(PeerImageShare.id))) == 0
        deliver.assert_not_awaited()
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario == "no_confirmation":
            with pytest.raises(CommandRejected, match="CONFIRMATION_MISSING"):
                await execute_application_action_draft(
                    draft.model_dump(mode="json"), owner, object()
                )
            deliver.assert_not_awaited()
            return
        if scenario == "edit":
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"),
                    {
                        "intent": {
                            "connection_id": str(pair_id),
                            "attachment_id": str(image_id),
                            "comment": "Bonsoir",
                        }
                    },
                )
            )
            assert str(draft.command_id) == item.payload["content"]["command_id"]
        with patch.dict(draft_executor.EXECUTOR_REGISTRY):
            draft_executor.register_executor("application_action", execute_application_action_draft)
            invocation = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": draft.model_dump(mode="json"),
            }
            result = await draft_executor._execute_confirmed_draft(
                invocation,
                {"configurable": {"thread_id": "peer-image-flow"}},
                "peer-image-flow",
                "fr",
            )
            assert result.success, result.to_agent_result()
            if scenario == "replay":
                replay = await draft_executor._execute_confirmed_draft(
                    invocation,
                    {"configurable": {"thread_id": "peer-image-flow"}},
                    "peer-image-flow",
                    "fr",
                )
                assert replay.success and replay.result_data == result.result_data
        deliver.assert_awaited_once()
        assert deliver.call_args.args[0].comment == ("Bonsoir" if scenario == "edit" else "Bonjour")
        assert await async_session.scalar(select(func.count(PeerImageShare.id))) == 1
        changes = [
            event
            for event in (queue.get_nowait() for _ in range(queue.qsize()))
            if event.type == "application_state_changed"
        ]
        assert len(changes) == 1 and changes[0].metadata["change"]["resources"] == ["peers"]
