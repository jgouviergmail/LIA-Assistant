"""Peers tools — relay messages to connected users from chat (Lot 4, spec A3).

Two tools plus the confirmed-draft executor:

- ``send_peer_message_tool`` — resolves the recipient among the CALLER's
  accepted connections (folded exact name — never the discovery index),
  enforces the quotas and the sender's LLM budget, then returns a
  **PEER_MESSAGE draft** (A3: the send is the email class — nothing leaves
  until the user confirms the HITL card). The draft mechanism is the
  fail-closed two-phase confirmation: it gates pipeline AND ReAct AND
  skill-subagent contexts identically (devops FN-1 doctrine).
- ``list_peer_connections_tool`` — read-only listing of the caller's
  connections with both share directions (name resolution + "who am I
  connected to").
- ``execute_peer_message_draft`` — re-validates every guard at confirmation
  time (an arbitrary delay separates draft from approval — devops doctrine),
  enqueues the message and kicks the delivery sweep.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import get_settings
from src.domains.agents.constants import AGENT_PEER
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.peers.models import PeerConnectionStatus
from src.domains.peers.repository import PeersRepository
from src.domains.shared.text_normalization import fold_name
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def _resolve_recipient(
    repo: PeersRepository, user_id: UUID, recipient_name: str
) -> tuple[Any | None, list[str], dict[UUID, str]]:
    """Resolve a recipient among the caller's ACCEPTED connections by name.

    Args:
        repo: Peers repository bound to the current session.
        user_id: The caller.
        recipient_name: Name as the user said it (folded exact match).

    Returns:
        (connection or None, candidate display names, peer_id→name directory).
    """
    from sqlalchemy import select

    from src.domains.users.models import User

    connections = await repo.list_accepted_for_user(user_id)
    if not connections:
        return None, [], {}
    peer_ids = {(c.user_b_id if c.user_a_id == user_id else c.user_a_id): c for c in connections}
    rows = (
        await repo.db.execute(select(User.id, User.full_name).where(User.id.in_(peer_ids.keys())))
    ).all()
    directory = {uid: (name or "") for uid, name in rows}
    folded = fold_name(recipient_name)
    matches = [
        (peer_ids[uid], directory[uid]) for uid in peer_ids if fold_name(directory[uid]) == folded
    ]
    if len(matches) == 1:
        return matches[0][0], [matches[0][1]], directory
    return None, sorted(name for name in directory.values() if name), directory


@write_tool(name="send_peer_message", agent_name=AGENT_PEER)
async def send_peer_message_tool(
    recipient_name: Annotated[
        str, "Full name of the CONNECTED user to relay the message to (exact name)"
    ],
    message: Annotated[
        str,
        "The message to relay, written as ADDRESSED TO the recipient (direct "
        "address, second person) in the USER'S OWN LANGUAGE (never translate). "
        "Convert indirect speech: 'ask Paul how he is doing' -> message 'How "
        "are you doing?'. The recipient's own assistant conveys its intent in "
        "its own voice.",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare a message for a connected user — sent only after confirmation.

    Nothing is sent here (A3): this returns a PEER_MESSAGE draft the user must
    confirm. Delivery then happens assistant-to-assistant: the recipient's
    assistant conveys the message in its own personality and language.

    Replies included: relays are STATELESS (no message_id/thread) — replying
    to a relayed message is simply sending a new one. Recipient matching is
    accent- and case-insensitive; the message stays in the user's language and
    is phrased in DIRECT ADDRESS: an indirect request ("ask X how he is
    doing") becomes the words meant for the recipient ("how are you doing?").

    Args:
        recipient_name: Display name among the caller's accepted connections.
        message: The directive to relay (recipient's assistant rephrases it).
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput carrying the draft, or a typed failure.
    """
    settings = get_settings()
    validated = validate_runtime_config(runtime, "send_peer_message_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated
    user_id = UUID(str(validated.user_id))

    if not message.strip():
        return UnifiedToolOutput.failure(
            message="The message is empty.", error_code="INVALID_INPUT"
        )
    if len(message) > settings.peers_message_max_chars:
        return UnifiedToolOutput.failure(
            message=(f"The message exceeds {settings.peers_message_max_chars} characters."),
            error_code="INVALID_INPUT",
        )

    async with get_db_context() as db:
        repo = PeersRepository(db)
        connection, candidates, _directory = await _resolve_recipient(repo, user_id, recipient_name)
        if connection is None:
            return UnifiedToolOutput.failure(
                message=(
                    "No connected user matches that exact name. "
                    f"Connected users: {', '.join(candidates) if candidates else 'none'}."
                ),
                error_code="NOT_FOUND",
                metadata={"connected_users": candidates},
            )
        quota_failure = await _check_send_quotas(repo, user_id, connection, settings)
        if quota_failure is not None:
            return quota_failure
        peer_id = connection.user_b_id if connection.user_a_id == user_id else connection.user_a_id
        recipient_display = candidates[0]

    logger.info(
        "peer_message_draft_created",
        user_id=str(user_id),
        connection_id=str(connection.id),
    )
    return DraftService().create_draft(
        draft_type=DraftType.PEER_MESSAGE,
        content={
            "connection_id": str(connection.id),
            "recipient_id": str(peer_id),
            "recipient_name": recipient_display,
            "message": message,
        },
        source_tool="send_peer_message_tool",
    )


async def _check_send_quotas(
    repo: PeersRepository,
    user_id: UUID,
    connection: Any,
    settings: Any,
) -> UnifiedToolOutput | None:
    """Enforce the daily quotas and the sender's LLM budget (spec §9).

    Returns:
        A typed failure output, or None when sending is allowed.
    """
    from src.domains.usage_limits.service import UsageLimitService

    if await UsageLimitService.is_user_blocked_for_llm(user_id, layer="peer_message_send"):
        return UnifiedToolOutput.failure(
            message="Your usage limit is reached — relayed messages are paused.",
            error_code="RATE_LIMITED",
        )
    now = datetime.now(UTC)
    peer_id = connection.user_b_id if connection.user_a_id == user_id else connection.user_a_id
    if await repo.count_messages_today(user_id, now=now) >= settings.peers_message_max_per_day:
        return UnifiedToolOutput.failure(
            message=(
                f"Daily relayed-message quota reached "
                f"({settings.peers_message_max_per_day}/day)."
            ),
            error_code="RATE_LIMITED",
        )
    if (
        await repo.count_messages_today_for_pair(user_id, peer_id, now=now)
        >= settings.peers_message_max_per_day_per_pair
    ):
        return UnifiedToolOutput.failure(
            message=(
                f"Daily quota toward this contact reached "
                f"({settings.peers_message_max_per_day_per_pair}/day)."
            ),
            error_code="RATE_LIMITED",
        )
    return None


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
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Execute a confirmed PEER_MESSAGE draft: enqueue + kick delivery.

    Registered in ``draft_executor_registry.ensure_executors_registered()``.
    Every guard is re-checked here on purpose (devops doctrine): an arbitrary
    delay separates the draft from the confirmation — the connection may have
    been removed, a block placed, or a quota reached in between.

    Args:
        draft_content: PEER_MESSAGE draft content.
        user_id: The sender (draft owner).
        deps: ToolDependencies (unused — own session).

    Returns:
        {"success", "recipient_name"} on enqueue; {"success": False, "error"}
        with a typed code otherwise.
    """
    from src.infrastructure.scheduler.peer_message_delivery import kick_delivery_soon

    settings = get_settings()
    connection_id = UUID(draft_content["connection_id"])
    recipient_id = UUID(draft_content["recipient_id"])
    message_text = draft_content["message"]

    async with get_db_context() as db:
        repo = PeersRepository(db)
        connection = await repo.get_by_id(connection_id)
        if (
            connection is None
            or connection.status != PeerConnectionStatus.ACCEPTED.value
            or user_id not in (connection.user_a_id, connection.user_b_id)
        ):
            return {"success": False, "error": "peers_not_connected"}
        if await repo.has_block_between(user_id, recipient_id):
            return {"success": False, "error": "peers_not_connected"}  # neutral
        quota_failure = await _check_send_quotas(repo, user_id, connection, settings)
        if quota_failure is not None:
            return {"success": False, "error": "peers_quota_reached"}
        message = await repo.enqueue_message(connection_id, user_id, recipient_id, message_text)
        await db.commit()

    kick_delivery_soon()
    logger.info(
        "peer_message_enqueued",
        message_id=str(message.id),
        user_id=str(user_id),
    )
    return {"success": True, "recipient_name": draft_content.get("recipient_name", "?")}
