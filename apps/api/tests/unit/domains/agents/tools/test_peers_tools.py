"""Peer adapters preserve disambiguation and share one admission command."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.tools import peers_tools
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.peers.message_command import PeerMessageReceipt, PeerMessageRefusal
from src.domains.peers.models import PeerConnection
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit
USER_ID, PEER_ID, CONNECTION_ID = uuid4(), uuid4(), uuid4()


def _connection() -> PeerConnection:
    first, second = sorted([USER_ID, PEER_ID])
    return PeerConnection(id=CONNECTION_ID, user_a_id=first, user_b_id=second, status="accepted")


@pytest.fixture
def repository() -> Iterator[MagicMock]:
    db = MagicMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(all=MagicMock(return_value=[(PEER_ID, "Marie Dupont")]))
    )
    repo = MagicMock()
    repo.db = db
    repo.list_accepted_for_user = AsyncMock(return_value=[_connection()])

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        yield db

    with (
        patch.object(peers_tools, "get_db_context", database),
        patch.object(peers_tools, "PeersRepository", return_value=repo),
        patch("src.domains.agents.peer.name_directory.RelationsService") as relations,
    ):
        relations.return_value.directory = AsyncMock(return_value=[])
        yield repo


async def _send(name: str, message: str = "Bonjour") -> UnifiedToolOutput:
    coroutine = peers_tools.send_peer_message_tool.coroutine
    assert coroutine is not None
    result = await coroutine(
        recipient_name=name,
        message=message,
        runtime=make_tool_runtime(user_id=USER_ID, store=InMemoryStore()),
    )
    assert isinstance(result, UnifiedToolOutput)
    return result


@pytest.mark.parametrize("name", ["marie dupont", "Marie"])
async def test_direct_send_returns_queue_receipt_without_card(
    repository: MagicMock, name: str
) -> None:
    receipt = PeerMessageReceipt(uuid4(), "Marie Dupont")
    with (
        patch.object(
            peers_tools, "enqueue_peer_message", new_callable=AsyncMock, return_value=receipt
        ) as enqueue,
        patch.object(peers_tools, "_kick_delivery") as kick,
    ):
        output = await _send(name)
    enqueue.assert_awaited_once_with(USER_ID, CONNECTION_ID, PEER_ID, "Bonjour")
    assert output.success
    assert output.structured_data == {
        "message_id": str(receipt.message_id),
        "recipient_name": receipt.recipient_name,
        "status": "pending",
    }
    assert "draft_id" not in output.model_dump()
    assert "not yet been delivered" in output.message
    kick.assert_called_once()


@pytest.mark.parametrize(
    "refusal,code",
    [
        (PeerMessageRefusal.QUOTA_REACHED, "RATE_LIMIT_EXCEEDED"),
        (PeerMessageRefusal.NOT_CONNECTED, "NOT_FOUND"),
        (PeerMessageRefusal.DISABLED, "CONFIGURATION_ERROR"),
    ],
)
async def test_current_admission_refusal_reaches_the_tool(
    repository: MagicMock, refusal: PeerMessageRefusal, code: str
) -> None:
    with (
        patch.object(
            peers_tools, "enqueue_peer_message", new_callable=AsyncMock, return_value=refusal
        ),
        patch.object(peers_tools, "_kick_delivery") as kick,
    ):
        output = await _send("Marie")
    assert not output.success and output.error_code == code
    kick.assert_not_called()


async def test_unknown_recipient_lists_candidates_without_enqueuing(repository: MagicMock) -> None:
    with patch.object(peers_tools, "enqueue_peer_message", new_callable=AsyncMock) as enqueue:
        output = await _send("Inconnu Total")
    assert not output.success and output.error_code == "NOT_FOUND"
    assert "Marie Dupont" in output.message
    enqueue.assert_not_awaited()


async def test_ambiguous_first_name_asks_without_enqueuing(repository: MagicMock) -> None:
    other_id = uuid4()
    other = PeerConnection(id=uuid4(), user_a_id=USER_ID, user_b_id=other_id, status="accepted")
    repository.list_accepted_for_user.return_value.append(other)
    repository.db.execute.return_value.all.return_value.append((other_id, "Marie Lin"))
    with patch.object(peers_tools, "enqueue_peer_message", new_callable=AsyncMock) as enqueue:
        output = await _send("Marie")
    assert not output.success and output.error_code == "DISAMBIGUATION_REQUIRED"
    assert output.metadata["candidates"] == ["Marie Dupont", "Marie Lin"]
    enqueue.assert_not_awaited()


async def test_reads_end_before_relationship_directory_provider_wait(repository: MagicMock) -> None:
    order: list[str] = []
    repository.db.commit.side_effect = lambda: order.append("commit")
    with patch("src.domains.agents.peer.name_directory.RelationsService") as relations:
        relations.return_value.directory = AsyncMock(
            side_effect=lambda: order.append("directory") or []
        )
        output = await _send("Paul")
    assert output.error_code == "NOT_FOUND"
    assert order[0:2] == ["commit", "directory"]


@pytest.mark.parametrize("message", [" ", "x" * (settings.peers_message_max_chars + 1)])
async def test_invalid_message_refused_before_any_io(message: str) -> None:
    with patch.object(peers_tools, "get_db_context") as database:
        output = await _send("Marie", message)
    assert not output.success and output.error_code == "INVALID_INPUT"
    database.assert_not_called()


def _content() -> dict[str, object]:
    return {
        "connection_id": str(CONNECTION_ID),
        "recipient_id": str(PEER_ID),
        "recipient_name": "Old name",
        "message": "Bonjour",
    }


async def test_historical_card_revalidates_through_common_command() -> None:
    with patch.object(
        peers_tools,
        "enqueue_peer_message",
        new_callable=AsyncMock,
        return_value=PeerMessageRefusal.NOT_CONNECTED,
    ) as enqueue:
        result = await peers_tools.execute_peer_message_draft(_content(), USER_ID, None)
    assert result == {"success": False, "error": "peers_not_connected"}
    enqueue.assert_awaited_once_with(USER_ID, CONNECTION_ID, PEER_ID, "Bonjour")


async def test_historical_card_receipt_uses_current_recipient_name() -> None:
    receipt = PeerMessageReceipt(uuid4(), "Current name")
    with (
        patch.object(
            peers_tools, "enqueue_peer_message", new_callable=AsyncMock, return_value=receipt
        ),
        patch.object(peers_tools, "_kick_delivery") as kick,
    ):
        result = await peers_tools.execute_peer_message_draft(_content(), USER_ID, None)
    assert result == {
        "success": True,
        "message_id": str(receipt.message_id),
        "recipient_name": "Current name",
        "status": "pending",
    }
    kick.assert_called_once()


@pytest.mark.parametrize(
    "field,value", [("recipient_id", "bad uuid"), ("connection_id", None), ("message", 7)]
)
async def test_malformed_historical_card_never_enqueues(field: str, value: object) -> None:
    with patch.object(peers_tools, "enqueue_peer_message", new_callable=AsyncMock) as enqueue:
        result = await peers_tools.execute_peer_message_draft(
            {**_content(), field: value}, USER_ID, None
        )
    assert result["success"] is False
    enqueue.assert_not_awaited()
