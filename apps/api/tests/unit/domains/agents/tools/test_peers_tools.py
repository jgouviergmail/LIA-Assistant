"""Peers tools tests (Lot 4) — draft gate, quotas, executor revalidation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.agents.tools import peers_tools
from src.domains.peers.models import PeerConnectionStatus

USER_ID = uuid4()
PEER_ID = uuid4()
CONNECTION_ID = uuid4()


def _connection(status=PeerConnectionStatus.ACCEPTED.value):
    user_a, user_b = sorted([USER_ID, PEER_ID])
    return SimpleNamespace(id=CONNECTION_ID, user_a_id=user_a, user_b_id=user_b, status=status)


def _patch_db(repo):
    @asynccontextmanager
    async def _ctx():
        db = MagicMock()
        db.commit = AsyncMock()
        yield db

    return (
        patch("src.domains.agents.tools.peers_tools.get_db_context", _ctx),
        patch("src.domains.agents.tools.peers_tools.PeersRepository", return_value=repo),
    )


def _patch_runtime():
    return patch(
        "src.domains.agents.tools.peers_tools.validate_runtime_config",
        return_value=SimpleNamespace(user_id=str(USER_ID)),
    )


def _repo(connections=None, today=0, pair_today=0):
    repo = AsyncMock()
    repo.list_accepted_for_user.return_value = connections or []
    repo.count_messages_today.return_value = today
    repo.count_messages_today_for_pair.return_value = pair_today
    repo.has_block_between.return_value = False
    repo.get_by_id.return_value = _connection()
    repo.db = MagicMock()
    repo.db.execute = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=[(PEER_ID, "Marie Dupont")]))
    )
    return repo


@pytest.fixture
def sender_not_blocked():
    with patch(
        "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
        new=AsyncMock(return_value=False),
    ):
        yield


@pytest.mark.unit
class TestSendPeerMessageTool:
    async def test_unknown_recipient_lists_candidates(self, sender_not_blocked):
        repo = _repo(connections=[_connection()])
        db_patch, repo_patch = _patch_db(repo)
        with db_patch, repo_patch, _patch_runtime():
            output = await peers_tools.send_peer_message_tool.coroutine(  # type: ignore[misc]
                recipient_name="Inconnu Total", message="salut", runtime=MagicMock()
            )
        assert output.success is False
        assert output.error_code == "NOT_FOUND"
        assert "Marie Dupont" in output.message

    async def test_daily_quota_blocks_the_send(self, sender_not_blocked):
        repo = _repo(connections=[_connection()], today=settings.peers_message_max_per_day)
        db_patch, repo_patch = _patch_db(repo)
        with db_patch, repo_patch, _patch_runtime():
            output = await peers_tools.send_peer_message_tool.coroutine(  # type: ignore[misc]
                recipient_name="Marie Dupont", message="salut", runtime=MagicMock()
            )
        assert output.success is False
        assert output.error_code == "RATE_LIMITED"

    async def test_happy_path_returns_a_peer_message_draft(self, sender_not_blocked):
        repo = _repo(connections=[_connection()])
        db_patch, repo_patch = _patch_db(repo)
        draft_service = MagicMock()
        draft_service.create_draft.return_value = "DRAFT_OUTPUT"
        with (
            db_patch,
            repo_patch,
            _patch_runtime(),
            patch(
                "src.domains.agents.tools.peers_tools.DraftService",
                return_value=draft_service,
            ),
        ):
            output = await peers_tools.send_peer_message_tool.coroutine(  # type: ignore[misc]
                recipient_name="marie dupont",  # folded match — case-insensitive
                message="Demande-lui comment il va",
                runtime=MagicMock(),
            )
        assert output == "DRAFT_OUTPUT"
        content = draft_service.create_draft.call_args.kwargs["content"]
        assert content["recipient_name"] == "Marie Dupont"
        assert content["message"] == "Demande-lui comment il va"
        assert content["connection_id"] == str(CONNECTION_ID)

    async def test_empty_message_rejected_before_any_io(self):
        with _patch_runtime():
            output = await peers_tools.send_peer_message_tool.coroutine(  # type: ignore[misc]
                recipient_name="Marie", message="   ", runtime=MagicMock()
            )
        assert output.success is False
        assert output.error_code == "INVALID_INPUT"


@pytest.mark.unit
class TestExecutePeerMessageDraft:
    def _content(self):
        return {
            "connection_id": str(CONNECTION_ID),
            "recipient_id": str(PEER_ID),
            "recipient_name": "Marie Dupont",
            "message": "salut",
        }

    async def test_removed_connection_refuses_at_confirmation_time(self, sender_not_blocked):
        repo = _repo()
        repo.get_by_id.return_value = _connection(PeerConnectionStatus.REMOVED.value)
        db_patch, repo_patch = _patch_db(repo)
        with db_patch, repo_patch:
            result = await peers_tools.execute_peer_message_draft(
                self._content(), USER_ID, deps=None
            )
        assert result == {"success": False, "error": "peers_not_connected"}
        repo.enqueue_message.assert_not_awaited()

    async def test_success_enqueues_and_kicks_delivery(self, sender_not_blocked):
        repo = _repo()
        repo.enqueue_message.return_value = SimpleNamespace(id=uuid4())
        db_patch, repo_patch = _patch_db(repo)
        kick = MagicMock()
        with (
            db_patch,
            repo_patch,
            patch("src.infrastructure.scheduler.peer_message_delivery.kick_delivery_soon", kick),
        ):
            result = await peers_tools.execute_peer_message_draft(
                self._content(), USER_ID, deps=None
            )
        assert result["success"] is True
        repo.enqueue_message.assert_awaited_once_with(CONNECTION_ID, USER_ID, PEER_ID, "salut")
        kick.assert_called_once()
