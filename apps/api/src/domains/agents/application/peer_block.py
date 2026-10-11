"""Exact directional blocks reuse source silent severance and never restore old grants."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import false, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    raise_invalid_input,
    raise_not_found_or_unauthorized,
)
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.peer_block_schemas import (
    PeerBlockInput,
    PeerBlockPatch,
    PeerBlockSelection,
)
from src.domains.agents.application.peer_block_spec import PEER_BLOCK_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.models import (
    PeerBlock,
    PeerConnection,
    PeerConnectionStatus,
    PeerDomainShare,
    canonical_pair,
)
from src.domains.peers.pair_fence import lock_peer_pair
from src.domains.peers.schemas import ConnectionView
from src.domains.peers.service import PeersService
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def _block_access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PEERS)
    await load_actor(db, actor_id)


async def _visible_block_target(
    service: PeersService, actor_id: UUID, peer_id: UUID
) -> tuple[str | None, str | None, ConnectionView | None]:
    if actor_id == peer_id:
        raise_invalid_input("peers_self_block")
    cards = await service.get_connections(actor_id)
    cards.extend(await service.get_pending(actor_id))
    card = next((row for row in cards if row.peer_id == peer_id), None)
    if card is not None:
        return card.peer_display_name, card.peer_email_hint, card
    blocks = await service.list_blocks(actor_id)
    own = next((row for row in blocks if row.blocked_id == peer_id), None)
    if own is None:
        raise_not_found_or_unauthorized("peer", peer_id)
    assert own is not None
    return own.blocked_display_name, None, None


async def _block_selection(
    db: AsyncSession, actor_id: UUID, request: PeerBlockInput, *, lock: bool = False
) -> PeerBlockSelection:
    name, hint, card = await _visible_block_target(PeersService(db), actor_id, request.peer_id)
    lo, hi = canonical_pair(actor_id, request.peer_id)
    pair_query = select(func.to_jsonb(PeerConnection.__table__.table_valued())).where(
        PeerConnection.user_a_id == lo, PeerConnection.user_b_id == hi
    )
    own_query = select(func.to_jsonb(PeerBlock.__table__.table_valued())).where(
        PeerBlock.blocker_id == actor_id, PeerBlock.blocked_id == request.peer_id
    )
    if lock:
        pair_query = pair_query.with_for_update()
        own_query = own_query.with_for_update()
    pair = await db.scalar(pair_query)
    own = await db.scalar(own_query)
    # The parent pair is the source share fence; both present and absent grants are stable.
    shares = (
        await db.scalars(
            select(func.to_jsonb(PeerDomainShare.__table__.table_valued()))
            .where(PeerDomainShare.connection_id == UUID(pair["id"]) if pair else false())
            .order_by(PeerDomainShare.id)
        )
    ).all()
    return PeerBlockSelection(
        request=request,
        display_name=name,
        email_hint=hint,
        before_blocked=own is not None,
        pair_status=PeerConnectionStatus(pair["status"]) if pair else None,
        my_shares=card.my_shares if card else [],
        their_shares=card.their_shares if card else [],
        state_digest=payload_digest({"pair": pair, "own_block": own, "shares": list(shares)}),
        share_digest=payload_digest(list(shares)),
    )


async def prepare_peer_block(
    db: AsyncSession, actor_id: UUID, request: PeerBlockInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = PeerBlockInput.model_validate(request.model_dump())
    await _block_access(db, actor_id)
    scope = await _block_selection(db, actor_id, selected)
    await _block_access(db, actor_id)
    return build_action_content(
        actor_id,
        PEER_BLOCK_OPERATION,
        PeerBlockPatch(peer_block=scope),
        {"peer_block": scope.public_scope()},
        {"peer_block": scope.public_scope(after=True)},
        command_id=command_id,
    )


def canonical_peer_block(draft: ApplicationActionDraftContent) -> bool:
    scope = PeerBlockPatch.model_validate(draft.intent).peer_block
    return draft.before == {"peer_block": scope.public_scope()} and draft.after == {
        "peer_block": scope.public_scope(after=True)
    }


async def _verify_block_selection(
    db: AsyncSession, actor_id: UUID, expected: PeerBlockSelection
) -> None:
    try:
        current = await _block_selection(db, actor_id, expected.request, lock=True)
    except ResourceNotFoundError as exc:
        raise ResourceConflictError("peer_block", detail={"error_code": "STALE_STATE"}) from exc
    if current != expected:
        raise ResourceConflictError("peer_block", detail={"error_code": "STALE_STATE"})


async def _verify_block_result(
    db: AsyncSession, actor_id: UUID, expected: PeerBlockSelection
) -> None:
    actual = await db.scalar(
        select(PeerBlock.id).where(
            PeerBlock.blocker_id == actor_id, PeerBlock.blocked_id == expected.request.peer_id
        )
    )
    if (actual is not None) != expected.request.blocked:
        raise ValueError("Source directional block differs from approved outcome")
    pair = await PeersService(db).repo.get_pair(actor_id, expected.request.peer_id)
    status = pair.status if pair else None
    if status != expected.public_scope(after=True)["connection_status"]:
        raise ValueError("Source block must not restore or retain a severed connection")
    if not expected.request.blocked and pair is not None:
        shares = (
            await db.scalars(
                select(func.to_jsonb(PeerDomainShare.__table__.table_valued()))
                .where(PeerDomainShare.connection_id == pair.id)
                .order_by(PeerDomainShare.id)
            )
        ).all()
        if payload_digest(list(shares)) != expected.share_digest:
            raise ValueError("Source unblock must preserve existing sharing state")
    if expected.severs_pair and pair is not None:
        remaining = await db.scalar(
            select(func.count(PeerDomainShare.id)).where(PeerDomainShare.connection_id == pair.id)
        )
        if remaining != 0:
            raise ValueError("Source block left revoked sharing in place")


async def execute_peer_block(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "peer_block.update":
        raise CommandRejected("FORBIDDEN")
    if not canonical_peer_block(draft):
        raise ValueError("Block requires exact approved source state")
    expected = PeerBlockPatch.model_validate(draft.intent).peer_block

    async def check() -> None:
        await _block_access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    await lock_peer_pair(db, actor_id, expected.request.peer_id)
    await check()
    await _verify_block_selection(db, actor_id, expected)
    service = PeersService(db)
    if not expected.no_op:
        if expected.request.blocked:
            await service.block_peer(actor_id, expected.request.peer_id)
        else:
            await service.unblock_peer(actor_id, expected.request.peer_id)
    await _verify_block_result(db, actor_id, expected)
    if service.pending_events:
        raise ValueError("Source block/unblock must remain silent")
    await check()
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    receipt.no_op = expected.no_op
    receipt.values = {"peer_block": expected.public_scope(after=True)}
