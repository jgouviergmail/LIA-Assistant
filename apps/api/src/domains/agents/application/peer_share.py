"""Exact owned-domain consent reuses source pair fencing and share validation."""

from datetime import UTC, datetime
from uuid import UUID

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
from src.domains.agents.application.peer_share_schemas import (
    PeerShareInput,
    PeerSharePatch,
    PeerShareSelection,
)
from src.domains.agents.application.peer_share_spec import PEER_SHARE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.models import PeerConnection, PeerDomainShare, PeerShareLevel
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.service import PeersService
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def _share_access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PEERS)
    await load_actor(db, actor_id)


async def _share_selection(
    db: AsyncSession, actor_id: UUID, request: PeerShareInput, *, lock: bool = False
) -> PeerShareSelection:
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
    share = await db.scalar(
        select(func.to_jsonb(PeerDomainShare.__table__.table_valued())).where(
            PeerDomainShare.connection_id == card.id,
            PeerDomainShare.owner_user_id == actor_id,
            PeerDomainShare.domain == request.domain.value,
        )
    )
    level = next(
        (item.level for item in card.my_shares if item.domain == request.domain.value), None
    )
    return PeerShareSelection(
        request=request,
        peer_id=card.peer_id,
        display_name=card.peer_display_name,
        email_hint=card.peer_email_hint,
        before_level=PeerShareLevel(level) if level else None,
        state_digest=payload_digest({"pair": pair, "own_share": share}),
    )


async def prepare_peer_share(
    db: AsyncSession, actor_id: UUID, request: PeerShareInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = PeerShareInput.model_validate(request.model_dump())
    await _share_access(db, actor_id)
    scope = await _share_selection(db, actor_id, selected)
    await _share_access(db, actor_id)
    return build_action_content(
        actor_id,
        PEER_SHARE_OPERATION,
        PeerSharePatch(peer_share=scope),
        {"peer_share": scope.public_scope()},
        {"peer_share": scope.public_scope(after=True)},
        command_id=command_id,
    )


def canonical_peer_share(draft: ApplicationActionDraftContent) -> bool:
    scope = PeerSharePatch.model_validate(draft.intent).peer_share
    return draft.before == {"peer_share": scope.public_scope()} and draft.after == {
        "peer_share": scope.public_scope(after=True)
    }


async def _verify_share_selection(
    db: AsyncSession, actor_id: UUID, expected: PeerShareSelection
) -> None:
    try:
        current = await _share_selection(db, actor_id, expected.request, lock=True)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("peer_share", detail={"error_code": "STALE_STATE"}) from exc
    if current != expected:
        raise ResourceConflictError("peer_share", detail={"error_code": "STALE_STATE"})


async def execute_peer_share(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "peer_share.update":
        raise CommandRejected("FORBIDDEN")
    if not canonical_peer_share(draft):
        raise ValueError("Share requires exact approved source state")
    expected = PeerSharePatch.model_validate(draft.intent).peer_share

    async def check() -> None:
        await _share_access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await lock_peer_pair(db, actor_id, expected.peer_id)
    await check()
    await _verify_share_selection(db, actor_id, expected)
    request = expected.request
    no_op = request.level == expected.before_level
    if not no_op:
        await PeersService(db).set_share(
            actor_id, request.connection_id, request.domain, request.level
        )
    actual = await db.scalar(
        select(PeerDomainShare.level).where(
            PeerDomainShare.connection_id == request.connection_id,
            PeerDomainShare.owner_user_id == actor_id,
            PeerDomainShare.domain == request.domain.value,
        )
    )
    if actual != (request.level.value if request.level else None):
        raise ValueError("Source share postcondition differs from approved level")
    await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    receipt.no_op = no_op
    receipt.values = {"peer_share": expected.public_scope(after=True)}
