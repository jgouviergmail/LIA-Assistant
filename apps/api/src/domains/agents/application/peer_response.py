"""Exact incoming response preserves source ownership, claim and post-commit notice behavior."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    AuthorizationError,
    ResourceConflictError,
    ResourceNotFoundError,
    raise_not_found_or_unauthorized,
)
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.peer_notifications import notify_saved_peer_action
from src.domains.agents.application.peer_response_schemas import (
    PeerResponseInput,
    PeerResponsePatch,
    PeerResponseSelection,
)
from src.domains.agents.application.peer_response_spec import PEER_RESPONSE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.models import PeerConnection
from src.domains.peers.notifications import dispatch_peer_events
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.service import PeersService
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def _response_access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PEERS)
    await load_actor(db, actor_id)


async def _response_selection(
    db: AsyncSession, actor_id: UUID, request: PeerResponseInput, *, lock: bool = False
) -> PeerResponseSelection:
    cards = await PeersService(db).get_pending(actor_id)
    card = next((row for row in cards if row.id == request.connection_id), None)
    if card is None:
        raise_not_found_or_unauthorized("peer", request.connection_id)
    assert card is not None
    if card.direction != "incoming":
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    query = select(func.to_jsonb(PeerConnection.__table__.table_valued())).where(
        PeerConnection.id == card.id,
        or_(PeerConnection.user_a_id == actor_id, PeerConnection.user_b_id == actor_id),
    )
    if lock:
        query = query.with_for_update()
    stored = await db.scalar(query)
    if stored is None:
        raise_not_found_or_unauthorized("peer", request.connection_id)
    return PeerResponseSelection(request=request, card=card, state_digest=payload_digest(stored))


async def prepare_peer_response(
    db: AsyncSession, actor_id: UUID, request: PeerResponseInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = PeerResponseInput.model_validate(request.model_dump())
    await _response_access(db, actor_id)
    scope = await _response_selection(db, actor_id, selected)
    await _response_access(db, actor_id)
    return build_action_content(
        actor_id,
        PEER_RESPONSE_OPERATION,
        PeerResponsePatch(peer_response=scope),
        {"peer_response": scope.public_scope()},
        {"peer_response": scope.public_scope(after=True)},
        command_id=command_id,
    )


def canonical_peer_response(draft: ApplicationActionDraftContent) -> bool:
    scope = PeerResponsePatch.model_validate(draft.intent).peer_response
    return draft.before == {"peer_response": scope.public_scope()} and draft.after == {
        "peer_response": scope.public_scope(after=True)
    }


async def _verify_response_selection(
    db: AsyncSession, actor_id: UUID, expected: PeerResponseSelection
) -> None:
    try:
        current = await _response_selection(db, actor_id, expected.request, lock=True)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("peer_response", detail={"error_code": "STALE_STATE"}) from exc
    if current != expected:
        raise ResourceConflictError("peer_response", detail={"error_code": "STALE_STATE"})


async def execute_peer_response(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "peer_connection.respond":
        raise CommandRejected("FORBIDDEN")
    if not canonical_peer_response(draft):
        raise ValueError("Response requires exact approved incoming source state")
    expected = PeerResponsePatch.model_validate(draft.intent).peer_response

    async def check() -> None:
        await _response_access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await lock_peer_pair(db, actor_id, expected.card.peer_id)
    await check()
    await _verify_response_selection(db, actor_id, expected)
    service = PeersService(db)
    result = await service.respond_request(actor_id, expected.card.id, expected.request.accept)
    pair = await service.repo._get_fresh(expected.card.id)
    desired = "accepted" if expected.request.accept else "declined"
    if pair is None or pair.status != desired or result.status != desired or result.id != pair.id:
        raise ValueError("Source response postcondition differs from approved result")
    await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    public: dict[str, JsonValue] = {
        **expected.public_scope(after=True),
        "notification_status": "attempted",
    }
    receipt.values = {"peer_response": public}
    await notify_saved_peer_action(service.pending_events, dispatch_peer_events, public)
