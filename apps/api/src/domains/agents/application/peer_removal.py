"""Confirmed severance delegates lifecycle and work restitution to their existing owners."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
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
from src.domains.agents.application.peer_removal_schemas import (
    PeerRemovalInput,
    PeerRemovalPatch,
    PeerRemovalSelection,
)
from src.domains.agents.application.peer_removal_spec import PEER_REMOVAL_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.models import PeerConnection, PeerDomainShare
from src.domains.peers.notifications import dispatch_peer_events
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.service import PeersService
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def _removal_access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PEERS)
    await load_actor(db, actor_id)


async def _removal_selection(
    db: AsyncSession, actor_id: UUID, request: PeerRemovalInput, *, lock: bool = False
) -> PeerRemovalSelection:
    cards = await PeersService(db).get_connections(actor_id)
    card = next((row for row in cards if row.id == request.connection_id), None)
    if card is None:
        raise_not_found_or_unauthorized("peer", request.connection_id)
    assert card is not None
    pair_query = select(func.to_jsonb(PeerConnection.__table__.table_valued())).where(
        PeerConnection.id == card.id
    )
    if lock:
        pair_query = pair_query.with_for_update()
    pair = await db.scalar(pair_query)
    shares = (
        await db.scalars(
            select(func.to_jsonb(PeerDomainShare.__table__.table_valued()))
            .where(PeerDomainShare.connection_id == card.id)
            .order_by(PeerDomainShare.id)
        )
    ).all()
    return PeerRemovalSelection(
        request=request,
        peer_id=card.peer_id,
        display_name=card.peer_display_name,
        email_hint=card.peer_email_hint,
        my_shares=card.my_shares,
        their_shares=card.their_shares,
        state_digest=payload_digest({"pair": pair, "shares": list(shares)}),
    )


async def prepare_peer_removal(
    db: AsyncSession, actor_id: UUID, request: PeerRemovalInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = PeerRemovalInput.model_validate(request.model_dump())
    await _removal_access(db, actor_id)
    scope = await _removal_selection(db, actor_id, selected)
    await _removal_access(db, actor_id)
    return build_action_content(
        actor_id,
        PEER_REMOVAL_OPERATION,
        PeerRemovalPatch(peer_removal=scope),
        {"peer_removal": scope.public_scope()},
        {"peer_removal": scope.public_scope(after=True)},
        command_id=command_id,
    )


def canonical_peer_removal(draft: ApplicationActionDraftContent) -> bool:
    scope = PeerRemovalPatch.model_validate(draft.intent).peer_removal
    return draft.before == {"peer_removal": scope.public_scope()} and draft.after == {
        "peer_removal": scope.public_scope(after=True)
    }


async def _verify_removal_selection(
    db: AsyncSession, actor_id: UUID, expected: PeerRemovalSelection
) -> None:
    try:
        current = await _removal_selection(db, actor_id, expected.request, lock=True)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("peer_removal", detail={"error_code": "STALE_STATE"}) from exc
    if current != expected:
        raise ResourceConflictError("peer_removal", detail={"error_code": "STALE_STATE"})


async def _verify_removed_pair(
    service: PeersService, identity: UUID, returned_id: UUID, status: str
) -> None:
    pair = await service.repo._get_fresh(identity)
    remaining = await service.db.scalar(
        select(func.count(PeerDomainShare.id)).where(PeerDomainShare.connection_id == identity)
    )
    if (
        pair is None
        or pair.status != "removed"
        or returned_id != identity
        or status != "removed"
        or remaining != 0
    ):
        raise ValueError("Source severance postcondition differs from approved result")


async def execute_peer_removal(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "peer_connection.remove":
        raise CommandRejected("FORBIDDEN")
    if not canonical_peer_removal(draft):
        raise ValueError("Severance requires exact approved source state")
    expected = PeerRemovalPatch.model_validate(draft.intent).peer_removal

    async def check() -> None:
        await _removal_access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await lock_peer_pair(db, actor_id, expected.peer_id)
    await check()
    await _verify_removal_selection(db, actor_id, expected)
    service = PeersService(db)
    result = await service.remove_connection(actor_id, expected.request.connection_id)
    await _verify_removed_pair(service, expected.request.connection_id, result.id, result.status)
    await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    released = {
        identity: count for event in service.pending_events for identity, count in event.released
    }
    public: dict[str, JsonValue] = {
        **expected.public_scope(after=True),
        "own_tickets_released": released.get(actor_id),
        "notification_status": "attempted",
    }
    receipt.values = {"peer_removal": public}
    await notify_saved_peer_action(service.pending_events, dispatch_peer_events, public)
