"""Resolve connected peers and enqueue explicitly requested messages directly.

The registered effect gate claims direct sends before this tool runs. The
shared admission command rechecks authority and quotas atomically. Historical
PEER_MESSAGE cards retain their confirmation path and use that same command.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, assert_never
from uuid import UUID

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from sqlalchemy import select

from src.core.config import get_settings
from src.domains.agents.constants import AGENT_PEER
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.peer.name_directory import (
    PeerNameMatch,
    PeerNameOutcome,
    resolve_connected_peer,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.name_refusals import ambiguous_name_failure
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.peers.message_command import (
    PeerMessageReceipt,
    PeerMessageRefusal,
    enqueue_peer_message,
    valid_peer_message,
)
from src.domains.peers.models import PeerConnection
from src.domains.peers.repository import PeersRepository
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


async def _resolve_recipient(
    repo: PeersRepository, user_id: UUID, recipient_name: str
) -> tuple[PeerConnection | None, PeerNameMatch, dict[UUID, str]]:
    """Resolve a recipient among the caller's ACCEPTED connections by name.

    Args:
        repo: Peers repository bound to the current session.
        user_id: The caller.
        recipient_name: Name as the user said it — full, or a first name that
            designates one connection.

    Returns:
        (connection or None, the name decision, peer_id→name directory).
    """
    connections = await repo.list_accepted_for_user(user_id)
    if not connections:
        return None, PeerNameMatch(PeerNameOutcome.UNKNOWN), {}
    peer_ids = {(c.user_b_id if c.user_a_id == user_id else c.user_a_id): c for c in connections}
    rows = (
        await repo.db.execute(select(User.id, User.full_name).where(User.id.in_(peer_ids.keys())))
    ).all()
    directory = {uid: (name or "") for uid, name in rows}
    # A partial name reads the relationship list, whose SMS senders can ask
    # the contacts provider: the reads end before that wait (ADR-304).
    await repo.db.commit()
    match = await resolve_connected_peer(
        user_id, recipient_name, [(name, uid) for uid, name in directory.items()]
    )
    if match.outcome is not PeerNameOutcome.READ or match.peer_id is None:
        return None, match, directory
    return peer_ids[match.peer_id], match, directory


def _recipient_failure(
    match: PeerNameMatch, recipient_name: str, directory: dict[UUID, str]
) -> UnifiedToolOutput:
    """The refusal for a name that designates no single connected user."""
    if match.outcome is PeerNameOutcome.AMBIGUOUS:
        return ambiguous_name_failure(recipient_name, match.candidates)
    connected = sorted(name for name in directory.values() if name)
    if match.outcome is PeerNameOutcome.NOT_A_CONNECTION:
        reason = (
            f"'{recipient_name}' designates {', '.join(match.candidates)}, who is "
            "not a connected LIA user: a relayed message only reaches a connected user."
        )
    else:
        reason = f"No connected user matches '{recipient_name}'."
    return UnifiedToolOutput.failure(
        message=f"{reason} Connected users: {', '.join(connected) if connected else 'none'}.",
        error_code=ToolErrorCode.NOT_FOUND,
        metadata={"connected_users": connected},
    )


@write_tool(name="send_peer_message", agent_name=AGENT_PEER)
async def send_peer_message_tool(
    recipient_name: Annotated[
        str,
        "Name of the CONNECTED user to relay the message to, as the person said "
        "it: the full name, or a first name when it designates one connection",
    ],
    message: Annotated[
        str,
        "The message to relay, written as ADDRESSED TO the recipient (direct "
        "address, second person) in the USER'S OWN LANGUAGE (never translate). "
        "Convert indirect speech: 'ask Paul how they are doing' -> message 'How "
        "are you doing?'. The recipient's own assistant conveys its intent in "
        "its own voice.",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Queue a message for a connected user without a confirmation card.

    Resolve the recipient among accepted connections; ambiguous names still
    ask for clarification. The recipient's assistant delivers asynchronously
    in its own voice and language. The receipt states queued, never delivered.

    Args:
        recipient_name: Full or unique first name among accepted connections.
        message: Directive addressed to the recipient in the user's language.
        runtime: Injected LangChain tool runtime.

    Returns:
        An explicit queue receipt or a typed refusal.
    """
    settings = get_settings()
    validated = validate_runtime_config(runtime, "send_peer_message_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))

    if not valid_peer_message(message):
        return UnifiedToolOutput.failure(
            message=f"The message must contain text and at most {settings.peers_message_max_chars} characters.",
            error_code=ToolErrorCode.INVALID_INPUT,
        )

    async with get_db_context() as db:
        repo = PeersRepository(db)
        connection, match, directory = await _resolve_recipient(repo, user_id, recipient_name)
        if connection is None:
            return _recipient_failure(match, recipient_name, directory)
        peer_id = connection.user_b_id if connection.user_a_id == user_id else connection.user_a_id
        connection_id = connection.id

    result = await enqueue_peer_message(user_id, connection_id, peer_id, message)
    if isinstance(result, PeerMessageRefusal):
        return _queue_failure(result)
    _kick_delivery()
    return UnifiedToolOutput.data_success(
        message="Message queued for asynchronous delivery. It has not yet been delivered.",
        structured_data=_receipt_data(result),
    )


def _queue_failure(refusal: PeerMessageRefusal) -> UnifiedToolOutput:
    """Project a domain refusal into the tool's error vocabulary."""
    match refusal:
        case PeerMessageRefusal.DISABLED:
            code = ToolErrorCode.CONFIGURATION_ERROR
        case PeerMessageRefusal.NOT_CONNECTED:
            code = ToolErrorCode.NOT_FOUND
        case PeerMessageRefusal.INVALID_MESSAGE:
            code = ToolErrorCode.INVALID_INPUT
        case PeerMessageRefusal.QUOTA_REACHED:
            code = ToolErrorCode.RATE_LIMIT_EXCEEDED
        case _:
            assert_never(refusal)
    return UnifiedToolOutput.failure(message=refusal.value, error_code=code)


def _receipt_data(receipt: PeerMessageReceipt) -> dict[str, object]:
    """Use the same honest receipt on the direct and historical draft paths."""
    return {
        "message_id": str(receipt.message_id),
        "recipient_name": receipt.recipient_name,
        "status": "pending",
    }


def _kick_delivery() -> None:
    """Wake the existing sweep only after admission has committed."""
    from src.infrastructure.scheduler.peer_message_delivery import kick_delivery_soon

    kick_delivery_soon()


@read_tool(name="list_peer_connections", agent_name=AGENT_PEER)
async def list_peer_connections_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """List the caller's accepted connections with both share directions.

    Args:
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with the connections (names, shares given/received).
    """
    validated = validate_runtime_config(runtime, "list_peer_connections_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))

    async with get_db_context() as db:
        from src.domains.peers.service import PeersService

        views = await PeersService(db).get_connections(user_id)

    return UnifiedToolOutput.data_success(
        message=f"{len(views)} accepted connection(s).",
        structured_data={
            "connections": [
                {
                    "name": view.peer_display_name,
                    "since": view.responded_at.isoformat() if view.responded_at else None,
                    "i_share": [f"{s.domain}:{s.level}" for s in view.my_shares],
                    "they_share": [f"{s.domain}:{s.level}" for s in view.their_shares],
                }
                for view in views
            ]
        },
    )


async def execute_peer_message_draft(
    draft_content: Mapping[str, object], user_id: UUID, deps: object
) -> dict[str, object]:
    """Execute a historically confirmed card through current admission rules.

    Args:
        draft_content: The content approved by the historical card.
        user_id: Confirming owner, never a value taken from the draft.
        deps: Existing executor dependency contract (unused here).

    Returns:
        A pending receipt or a typed error; malformed and stale cards never enqueue.
    """
    connection = draft_content.get("connection_id")
    recipient = draft_content.get("recipient_id")
    message = draft_content.get("message")
    if (
        not isinstance(connection, str)
        or not isinstance(recipient, str)
        or not isinstance(message, str)
    ):
        return {"success": False, "error": PeerMessageRefusal.INVALID_MESSAGE.value}
    try:
        connection_id, recipient_id = UUID(connection), UUID(recipient)
    except ValueError:
        return {"success": False, "error": PeerMessageRefusal.INVALID_MESSAGE.value}
    result = await enqueue_peer_message(user_id, connection_id, recipient_id, message)
    if isinstance(result, PeerMessageRefusal):
        return {"success": False, "error": result.value}
    _kick_delivery()
    return {"success": True, **_receipt_data(result)}
